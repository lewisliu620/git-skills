# -*- coding: utf-8 -*-
"""
#53/#56 AI选品：豆包工作(AI)完成市场判断、建议售价与主观分；本地 S0 硬筛复核，产出候选待人工审批。

分工（不单独引入模型，worker=豆包工作）：
  · AI(豆包工作)负责：看真实候选，结合泰国市场给「建议售价CNY」、需求分/竞争分/合规分；
  · 本地确定性负责：去重(OfferID)、利润率≥80%(profit_model)、采购价<100、禁售词(s0_screen)。
  · 缺建议售价 → pending_price（AI未定价，不淘汰不放行）；不臆造售价、不编造OfferID/价格。

#56 多源归一化：输入可混用三类原料，脚本统一成 s0_screen 需要的字段并打「选品来源」标签：
  ① 1688 ranking.scanLight（官方榜单/热销，最小原料）：
     {offerId,title,purchasePriceCny,supplier,salesText,mainImage,url,source:{kind:'ranking',rankingName,cateId}}
  ② Shopee demand.scan（前台竞品需求情报）：
     {productId,titleTh,priceThb,salesText,shopName,productUrl,source:{kind:'search'|'flash_sale'|'product',keyword}}
     —— 无1688采购成本，不进 S0 候选，单独落 demand-intel.json 供AI反向找货。
  ③ 手动/已对齐项（喂链接或已由AI填好建议售价/分）：字段对齐 s0_screen，来源记 manual。

选品来源标签：ranking:Most_Popular / ranking:New_Arrivals / ranking:TRENDING /
              shopee:search / shopee:flash_sale / shopee:product / thirdparty / manual。

用法：
  python ai_pick.py --candidates picked.json
  python ai_pick.py --candidates picked.json --create
  python ai_pick.py --candidates picked.json --candidates-file cand.json --master-file master.json --create
去重集合由 --candidates-file(--候选表导出) 与 --master-file(--主表导出) 预取注入。
"""
import argparse, json, os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.s0_screen import screen_candidate
from core.dedup import DedupIndex, extract_offer_id

CAND_TABLE = "tblBsUDHOIEymeLO"
BASE = "QsnYbrWpaa6lGfspgLpcihfvnpb"


def _load_records(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        j = json.loads(f.read().lstrip("﻿"))
    data = j.get("data", j)
    fields = data["fields"]
    rows = data["data"]
    out = []
    for row in rows:
        out.append({"fields": {fields[i]: row[i] for i in range(len(fields))}})
    return out


def build_index(path, link_fields):
    recs = _load_records(path)
    return DedupIndex.from_records(recs, link_fields=link_fields)


def _num(v):
    try:
        if v in (None, ""):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# 候选表「目标站点」单选合法选项（与 tblBsUDHOIEymeLO field-list 对齐，只写已有选项）
SITE_OPTIONS = {"泰国Shopee", "俄罗斯Yandex"}

def normalize_site(raw):
    """把原料里的站点说法归一到候选表单选合法值；识别不出默认泰国Shopee。"""
    s = str(raw or "").strip()
    if s in SITE_OPTIONS:
        return s
    if "俄" in s or "yandex" in s.lower():
        return "俄罗斯Yandex"
    if "泰" in s or "th" in s.lower() or not s:
        return "泰国Shopee"
    return "泰国Shopee"


def source_tag(raw, source=None):
    """归一化选品来源标签；显式 source 字段优先，否则按原料形状推断 manual。"""
    if source and isinstance(source, dict):
        kind = source.get("kind") or ""
        rn = source.get("rankingName") or ""
        if kind == "ranking" and rn:
            return f"ranking:{rn}"
        if kind in ("search", "flash_sale", "product"):
            return f"shopee:{kind}"
    explicit = raw.get("选品来源") or raw.get("sourceTag")
    if explicit:
        return str(explicit)
    # 形状推断：带 productId/productUrl 且无 offerId → shopee 需求情报；有 offerId → manual
    if raw.get("productId") or raw.get("productUrl"):
        return "shopee:intel"
    if raw.get("thirdParty") or raw.get("thirdparty"):
        return "thirdparty"
    return "manual"


def normalize_item(raw):
    """
    把多源原料归一到 s0_screen 字段。
    返回 (norm, source_tag, is_intel)。
    is_intel=True：Shopee 前台需求情报，无采购成本，不进 S0 候选。
    """
    raw = raw or {}
    src = raw.get("source") if isinstance(raw.get("source"), dict) else None
    tag = source_tag(raw, src)

    # ② Shopee demand.scan：需求情报，不进候选
    if raw.get("productId") or (src and src.get("kind") in ("search", "flash_sale", "product")):
        intel = {
            "productId": str(raw.get("productId") or ""),
            "titleTh": raw.get("titleTh") or raw.get("商品名称") or "",
            "priceThb": _num(raw.get("priceThb")),
            "salesText": raw.get("salesText") or "",
            "shopName": raw.get("shopName") or "",
            "productUrl": raw.get("productUrl") or "",
            "keyword": (src or {}).get("keyword") or raw.get("keyword") or "",
            "选品来源": tag,
        }
        return intel, tag, True

    # ① 1688 ranking.scanLight 最小原料 → 对齐 s0_screen
    offer_id = raw.get("offerId") or raw.get("offer_id") or raw.get("1688 OfferID")
    url = raw.get("url") or raw.get("采购链接") or raw.get("参考竞品链接") or ""
    if isinstance(url, dict):
        url = url.get("link") or url.get("text") or ""
    # 补全 detail 链接（榜单/列表常给相对或 m 链接）
    if offer_id and "/offer/" not in str(url):
        url = f"https://detail.1688.com/offer/{offer_id}.html"

    norm = {
        "offer_id": str(offer_id) if offer_id else extract_offer_id(url),
        "采购链接": url,
        "商品名称": raw.get("商品名称") or raw.get("title") or "",
        "采购成本CNY": _num(raw.get("采购成本CNY", raw.get("purchasePriceCny"))),
        "建议售价CNY": _num(raw.get("建议售价CNY")),
        "SLS运费CNY": _num(raw.get("SLS运费CNY")),
        "sku_names": raw.get("sku_names") or [],
        "weight_g": _num(raw.get("weight_g")),
        "has_video": raw.get("has_video"),
        "supports_drop_shipping": raw.get("supports_drop_shipping"),
        "类目": raw.get("类目") or raw.get("category") or "",
        "目标站点": raw.get("目标站点") or "泰国",
        "AI备注": raw.get("AI备注") or raw.get("note") or "",
        "选品来源": tag,
    }
    # 榜单最小原料带的供应商/成交文案并入备注，供人工参考，不进硬筛
    sup = raw.get("supplier")
    if isinstance(sup, dict):
        sup = sup.get("companyName", "")
    memo_bits = [x for x in [sup, raw.get("salesText")] if x]
    if memo_bits:
        norm["AI备注"] = (norm["AI备注"] + " | " if norm["AI备注"] else "") + "；".join(memo_bits)
    # 透传 AI 已给的主观分（本地不反算五维）
    for k in ("需求分", "竞争分", "合规分", "综合分", "可代发分"):
        if k in raw and raw[k] is not None:
            norm[k] = raw[k]
    return norm, tag, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--candidates-file", help="候选表 record-list 导出(去重)")
    ap.add_argument("--master-file", help="主表 record-list 导出(去重)")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--intel-out", help="Shopee需求情报输出JSON路径(默认与candidates同目录 demand-intel.json)")
    args = ap.parse_args()

    cand_idx = build_index(args.candidates_file, ("1688 OfferID", "参考竞品链接", "采购链接"))
    master_idx = build_index(args.master_file, ("采购链接", "1688 OfferID"))

    with open(args.candidates, "r", encoding="utf-8") as f:
        pool = json.loads(f.read().lstrip("﻿"))
    if isinstance(pool, dict):
        pool = pool.get("items", [])

    results = []          # (norm, source_tag, s0结果)
    intel_list = []       # Shopee 需求情报
    create_records = []

    for raw in pool:
        norm, tag, is_intel = normalize_item(raw)
        if is_intel:
            intel_list.append(norm)
            continue
        r = screen_candidate(norm, candidate_index=cand_idx, master_index=master_idx)
        results.append((norm, tag, r))
        if r["decision"] == "pass":
            f = r["fields"]
            rec = {
                "商品名称": norm.get("商品名称", ""),
                "1688 OfferID": r["offer_id"] or "",
                "采购成本CNY": f.get("采购成本CNY"),
                "建议售价CNY": f.get("建议售价CNY"),
                "SLS运费CNY": f.get("SLS运费CNY"),
                "预估利润CNY": f.get("预估利润CNY"),
                "利润率": f.get("利润率"),
                "利润分": f.get("利润分"),
                "类目": norm.get("类目", ""),
                "目标站点": normalize_site(norm.get("目标站点")),
                "选品来源": tag,
                # AI 过 S0 待人工复核，尚未全量采集 → 处理状态=待采集，推荐状态=待复核（均为表内已有选项）
                "处理状态": "待采集",
                "推荐状态": "待复核",
                "选品日期": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "人工备注": norm.get("AI备注", ""),
            }
            # 透传 AI 主观分（有则写，无则留空由人工/AI补）
            for k in ("需求分", "竞争分", "合规分", "综合分", "可代发分"):
                if norm.get(k) is not None:
                    rec[k] = norm[k]
            create_records.append(rec)

    for norm, tag, r in results:
        print(f"\n[{r['decision'].upper()}] ({tag}) {norm.get('商品名称','')[:36]}  offer={r['offer_id']}")
        for chk in r["checks"]:
            mark = {"True": "✓", "False": "✗", "None": "·"}.get(str(chk["passed"]), "·")
            print(f"   {mark} {chk['rule']}: {chk['reason']}")
        for d in r["deferred"]:
            print(f"   ~ S2复核: {d}")

    n_pass = sum(1 for _, _, r in results if r["decision"] == "pass")
    print(f"\n=== 货盘候选：{len(results)} | pass {n_pass} | "
          f"reject {sum(1 for _,_,r in results if r['decision']=='reject')} | "
          f"pending_price {sum(1 for _,_,r in results if r['decision']=='pending_price')} | "
          f"duplicate {sum(1 for _,_,r in results if r['decision']=='duplicate')} ===")
    print(f"=== Shopee需求情报（不进候选，供反向找货）：{len(intel_list)} 条 ===")
    for it in intel_list:
        print(f"   · [{it['选品来源']}] {it['titleTh'][:40]} ฿{it['priceThb']} {it['salesText']}")

    if intel_list:
        intel_out = args.intel_out or os.path.join(
            os.path.dirname(os.path.abspath(args.candidates)), "demand-intel.json")
        with open(intel_out, "w", encoding="utf-8") as f:
            json.dump({"items": intel_list}, f, ensure_ascii=False, indent=2)
        print(f"\n[intel] 需求情报已写 {intel_out}")

    if args.create and create_records:
        # lark-cli +record-batch-create 外层为 create_records，元素直接是字段 map（不套 fields）
        body = {"create_records": create_records}
        out = os.path.join(os.path.dirname(os.path.abspath(args.candidates)), "candidate-create.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        print(f"\n[--create] 已生成 {out}（{len(create_records)} 条，待 lark-cli +record-batch-create 提交并回读）")


if __name__ == "__main__":
    main()
