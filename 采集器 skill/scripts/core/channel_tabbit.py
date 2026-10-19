"""
core/channel_tabbit.py — 一期采集通道：经 Tabbit CLI 在已登录前台新建临时 tab 读 SSR 桥

职责（只读，不下单/不写库/不发布）：
  1. subprocess 调 tabbit-cli，先 create 建任务组，再 context.newPage() 导航到商品页；
  2. 轮询 main-world 桥节点 #ysl-ssr-data，在浏览器端直接 pick 出精简结构化 result；
  3. 关闭临时 tab，Python 规整后返回 offer.collect 同款 result；
  4. 登录墙 / 桥缺失 / tabbit 未连 / 超时 分错误码抛出，供上层重试或切 requests。

关键约束（实测固化）：
  - nodejs 前必须先 create --task，否则任务不存在时 newPage 异常；
  - tabbit 的 return value 有内联体积上限，**不能回传 66KB 桥原文**（大结果走 resource
    通道），因此在浏览器端 pick 成 KB 级精简 dict 再回传；
  - 长描述 detail 不在桥内联回传，由 collect_pipeline 用 requests 兜底补。

二期升级本地 host HTTP 桥时，仅替换"取精简 result"这一步，result schema 不变。
"""
import os
import json
import subprocess
import uuid


# 通道错误码：AUTH_REQUIRED 需人工重登（不重试）；其余可重试或切兜底
class ChannelError(Exception):
    def __init__(self, code, message, recoverable=True):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


def _tabbit_cli():
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        p = os.path.join(local_app, "Tabbit", "LocalAgent", "bin", "tabbit-cli.exe")
        if os.path.exists(p):
            return p
    return "tabbit-cli"


# 浏览器端程序：新建临时 tab → 导航 → 轮询桥 → 端内 pick 精简 result → 关闭
# （不回传桥原文/长描述，避免触碰 tabbit 内联体积上限）
_JS_PROGRAM = r"""
const OFFER_ID = %s;
const LOGIN_RE = /login\.1688\.com|passport/i;

function num(v){ if(v===null||v===undefined||v==='')return null; const n=parseFloat(String(v).replace(/[,\u00a5]/g,'')); return Number.isFinite(n)?n:null; }
function str(v){ return v===null||v===undefined?'':String(v).trim(); }
function get(d, ...ks){ let c=d; for(const k of ks){ if(!c||typeof c!=='object')return undefined; c=c[k];} return c; }

function grabAttributes(){
  const out={};
  try{
    document.querySelectorAll('th.ant-descriptions-item-label').forEach(th=>{
      const key=str(th.innerText); const td=th.nextElementSibling; if(!td)return;
      const valEl=td.querySelector('.field-value')||td;
      const val=str((valEl.innerText||'').replace(/\s+/g,' '));
      if(key&&val) out[key]=val.slice(0,200);
    });
  }catch(e){}
  return out;
}

function pickBridge(raw){
  const p=JSON.parse(raw); const data=p.data||{};
  const pt=get(data,'productTitle','fields')||{};
  const g=get(data,'gallery','fields')||{};
  const mp=get(data,'mainPrice','fields')||{};
  const ss=get(data,'shippingServices','fields')||{};
  const desc=get(data,'description','fields')||{};
  const pack=get(data,'productPackInfo','fields')||{};
  const tw=get(mp,'finalPriceModel','tradeWithoutPromotion')||{};
  const missing=[];

  const rawImgs=g.offerImgList||g.mainImage||[];
  const mainImages=[...new Set(rawImgs.map(x=>str(x)).filter(Boolean))];
  if(!mainImages.length) missing.push('mainImages');

  const video=g.video||{};
  const vid=num(video.videoId)||0;
  const hasVideo=vid>0;
  if(!hasVideo) missing.push('videoUrl');
  const videoUrl=str(video.videoUrl)||str(video.coverUrl)||null;

  const rawPrices=(mp.priceModel||{}).currentPrices||[];
  const begins=[...new Set(rawPrices.map(r=>num(r.beginAmount)).filter(x=>x!==null))];
  let priceRanges=[];
  if(begins.length>=2){
    priceRanges=rawPrices.filter(r=>num(r.price)!==null)
      .map(r=>({beginAmount:num(r.beginAmount),price:num(r.price)}));
  }
  const skus=[];
  for(const s of (tw.skuMapOriginal||[])){
    const skuId=str(s.specId)||(s.skuId!=null?String(s.skuId):null);
    let price=num(s.discountPrice); if(price===null) price=num(s.price);
    const spec=str(s.specAttrs);
    if(spec||skuId) skus.push({specAttrs:spec,skuId:skuId,price,
      canBookCount:num(s.canBookCount),saleCount:num(s.saleCount)});
  }
  if(!skus.length) missing.push('skus');

  let minOrder=num(tw.offerBeginAmount); if(minOrder===null) minOrder=num(ss.startAmount);
  let uw=num(ss.unitWeight); if(uw===null) uw=num(pack.unitWeight);
  if(uw===null||uw===0){ uw=null; missing.push('weightG'); }

  return {
    offerId: str(g.offerId)||null,
    title: str(pt.title),
    unit: str(pt.unit),
    saleNum: str(pt.saleNum),
    supplier:{companyName:str(get(pt,'shopInfo','companyName'))},
    mainImages:mainImages,
    video:{state:parseInt(num(video.state)||0,10),videoId:str(video.videoId)||null,url:videoUrl,coverUrl:str(video.coverUrl)||null},
    priceType:str(mp.originPriceType)||str(get(mp,'priceModel','priceDisplayType')),
    priceMin:num(tw.offerMinPrice), priceMax:num(tw.offerMaxPrice),
    priceDisplay:str(tw.offerPriceDisplay), priceRanges,
    skus, minOrder, location:str(ss.location),
    freight:{postFeeValue:num(ss.postFeeValue),unitWeightG:uw},
    leafCategoryId:str(desc.leafCategoryId)||null,
    attributes:grabAttributes(), missing,
    descriptionHtml:""
  };
}

const tab=await context.newPage();
let out={ok:false};
try{
  await tab.goto(`https://detail.1688.com/offer/${OFFER_ID}.html`,{waitUntil:'domcontentloaded',timeout:30000});
  await new Promise(r=>setTimeout(r,1500));
  if(LOGIN_RE.test(tab.url())){ out={ok:false,error:'AUTH_REQUIRED',url:tab.url()}; }
  else{
    let raw=null;
    for(let i=0;i<30;i++){
      raw=await tab.evaluate(()=>{const n=document.getElementById('ysl-ssr-data');return n&&n.textContent?n.textContent:null;});
      if(raw) break;
      await new Promise(r=>setTimeout(r,400));
    }
    if(!raw){ out={ok:false,error:'NO_BRIDGE',url:tab.url()}; }
    else{
      const result=pickBridge(raw);
      if(!result.title) out={ok:false,error:'OFFER_MODEL_NOT_READY',url:tab.url()};
      else out={ok:true,result};
    }
  }
}catch(e){ out={ok:false,error:'THROW',msg:String(e.message||e)}; }
finally{ await tab.close().catch(()=>{}); }
return out;
"""


def _ensure_task(cli, task_name):
    """幂等建任务组：nodejs 前必须先 create，否则任务不存在时 newPage 异常。"""
    try:
        subprocess.run([cli, "create", "--task", task_name],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    except Exception:
        pass


def _run_tabbit(cli, offer_id, task_name="collector", timeout_ms=60000):
    program = _JS_PROGRAM % json.dumps(str(offer_id))
    request_id = f"collect-{uuid.uuid4().hex[:8]}"

    _ensure_task(cli, task_name)
    cmd = [cli, "nodejs", "--task", task_name,
           "--request-id", request_id, "--timeout-ms", str(timeout_ms)]
    try:
        proc = subprocess.run(cmd, input=program, capture_output=True,
                              text=True, encoding="utf-8", timeout=90)
    except FileNotFoundError:
        raise ChannelError("BRIDGE_DOWN", "未找到 tabbit-cli（实例未安装/未开）", recoverable=True)
    except subprocess.TimeoutExpired:
        raise ChannelError("CHANNEL_TIMEOUT", "tabbit 执行超时 90s", recoverable=True)

    stdout = (proc.stdout or "").strip()
    parsed = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if parsed is None:
        raise ChannelError("BRIDGE_DOWN",
                           f"tabbit 无返回（实例未开/未连）。stdout={stdout[:200]}",
                           recoverable=True)

    if parsed.get("status") != "succeeded":
        err = (parsed.get("result") or {}).get("error") or "UNKNOWN"
        raise ChannelError("CHANNEL_FAILED", f"tabbit 执行失败: {err}", recoverable=True)

    value = (parsed.get("result") or {}).get("value")
    if not isinstance(value, dict) or not value.get("ok"):
        code = (value or {}).get("error") or "UNKNOWN"
        if code == "AUTH_REQUIRED":
            raise ChannelError("AUTH_REQUIRED", "1688 登录态失效，请重新登录", recoverable=False)
        if code in ("NO_BRIDGE", "OFFER_MODEL_NOT_READY"):
            raise ChannelError("NO_BRIDGE", "SSR 桥未就绪/模型未注水或页面改版", recoverable=True)
        raise ChannelError("CHANNEL_FAILED", f"{code}: {(value or {}).get('msg','')}", recoverable=True)

    return value["result"]


def collect_via_tabbit(offer_id):
    """经 tabbit 传送带采集，返回 offer.collect 同款 result dict。失败抛 ChannelError。"""
    cli = _tabbit_cli()
    return _run_tabbit(cli, offer_id)
