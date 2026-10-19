"""
core/collect_pipeline.py — 一期双通道采集编排（tabbit 传送带为主，requests 移动端兜底）

策略（用户拍板：插件/浏览器通道为主、requests 兜底、重试退避、登录态失效切通道不硬采）：
  1. 先 tabbit 传送带（已登录前台，绕 x5sec）；
     - AUTH_REQUIRED（登录墙）→ 不重试，直接抛，交上层提醒人工重登；
     - NO_BRIDGE / BRIDGE_DOWN / 临时失败 → 指数退避重试（2s/4s），仍失败切 requests；
  2. requests 移动端 Fetcher1688.fetch 兜底（沿用现有 cookie session）；
  3. 两路都失败 → 抛最后一次异常，由 daemon 标「处理失败」。

未来二期升级本地 host HTTP 桥时，仅替换 collect_via_tabbit 的取数实现，本编排与
result_to_product 映射不变。
"""
import json
import re
import time

from .channel_tabbit import collect_via_tabbit, ChannelError
from .fetcher import Product1688, _extract_json_arr


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def result_to_product(result, offer_id):
    """offer.collect 同款 result → Product1688（与 requests 通道产物结构对齐，供规则校验/落库）"""
    p = Product1688()
    p.offer_id = str(result.get("offerId") or offer_id)
    p.title = result.get("title") or ""

    # 价格：skuPrice 取最低价；真阶梯价进 price_range
    p.price = _num(result.get("priceMin")) or 0.0
    if result.get("priceRanges"):
        p.price_range = [(r.get("beginAmount") or 1, _num(r.get("price")) or 0.0)
                         for r in result["priceRanges"]]
    elif result.get("priceMax") and p.price:
        p.price_range = [(1, p.price), (1, _num(result["priceMax"]))]

    # SKU：specAttrs 作为规格名，售价取 discountPrice/price
    p.skus = [{
        "name": s.get("specAttrs") or s.get("skuId") or "默认",
        "price": _num(s.get("price")) or p.price,
        "image_url": "",
        "spec_attrs": {"spec": s.get("specAttrs") or ""},
    } for s in (result.get("skus") or [])]
    if not p.skus:
        p.skus.append({"name": "默认", "price": p.price, "image_url": "", "spec_attrs": {}})

    p.images = list(result.get("mainImages") or [])
    p.video_url = (result.get("video") or {}).get("url") or ""
    p.attributes = dict(result.get("attributes") or {})
    p.brand = p.attributes.get("品牌", "")
    p.stock = 500  # 跨境店固定库存，不用1688实时可购量

    p.vendor_code = p.attributes.get("货号", "")
    p.category_id = str(result.get("leafCategoryId") or "")
    w = _num((result.get("freight") or {}).get("unitWeightG"))
    p.weight_g = w or 0.0
    p.supplier_name = (result.get("supplier") or {}).get("companyName") or ""
    p.min_order = int(_num(result.get("minOrder")) or 1)

    # 代发：属性里明示一件代发/跨境供货视为支持；缺省按本代发业务默认支持
    attr_blob = " ".join(str(v) for v in p.attributes.values())
    p.supports_drop_shipping = ("一件代发" in attr_blob) or ("跨境出口专供" in attr_blob) or True

    # 长描述：桥 detail（直出 SSR 常为空，由 _fill_description 用 requests 补）
    p.description = _html_to_text(result.get("descriptionHtml") or "")
    p.raw_data = {"channel": "tabbit", "missing": result.get("missing") or []}
    return p


def _html_to_text(html):
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:5000]


def _fill_missing_via_requests(fetcher, product, offer_id):
    """
    W-04：tabbit 直出页缺字段时，用 requests 移动端页面兜底补全。
    补的字段：长描述 / 重量(weight_g) / 视频(video_url) / 品牌(brand) /
              货号(vendor_code) / 供应商(supplier_name) / 起批量(min_order)。
    只补缺失项；失败静默（不影响 tabbit 已采到的主体数据）。
    """
    # 无缺失直接返回
    missing = []
    if not product.description:
        missing.append("description")
    if not product.weight_g:
        missing.append("weight_g")
    if not product.video_url:
        missing.append("video_url")
    if not product.brand or not product.vendor_code:
        missing.append("brand/vendor_code")
    if not product.supplier_name:
        missing.append("supplier_name")
    if product.min_order <= 1:
        missing.append("min_order")
    if not missing:
        return

    try:
        url = f"https://m.1688.com/offer/{offer_id}.html"
        resp = fetcher.session.get(url, timeout=15, allow_redirects=True)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return
        if "login.1688.com" in resp.url or "passport" in resp.url:
            return
        html = resp.text
        if "punish" in html or "x5sec" in html or len(html) < 5000:
            return

        # 1. 长描述（原逻辑）
        if "description" in missing:
            fetcher._fetch_description(html, product)

        # 2. 视频 videoUrl
        if "video_url" in missing:
            m = re.search(r'"videoUrl"\s*:\s*"([^"]+)"', html)
            if m:
                product.video_url = m.group(1)

        # 3. 重量（skuWeight 取最大，kg→g）
        if "weight_g" in missing:
            sku_weight = re.search(r'"skuWeight"\s*:\s*\{([^}]+)\}', html)
            if sku_weight:
                weights = re.findall(r':\s*([\d.]+)', sku_weight.group(1))
                if weights:
                    max_kg = max(float(w) for w in weights)
                    if max_kg > 0:
                        product.weight_g = max_kg * 1000

        # 4. 品牌/货号（propsList 属性表）
        if "brand/vendor_code" in missing and not (product.brand and product.vendor_code):
            props = _extract_json_arr(html, "propsList")
            if props:
                try:
                    for p in json.loads(props):
                        name, value = p.get("name", ""), p.get("value", "")
                        if name and value:
                            product.attributes[name] = value
                            if name == "品牌" and not product.brand:
                                product.brand = value
                            if name == "货号" and not product.vendor_code:
                                product.vendor_code = value
                except json.JSONDecodeError:
                    pass

        # 5. 供应商
        if "supplier_name" in missing:
            m = re.search(r'"(?:companyName|shopName|sellerNick)"\s*:\s*"([^"]+)"', html)
            if m:
                product.supplier_name = m.group(1)

        # 6. 起批量
        if "min_order" in missing:
            m = re.search(r'"(?:minOrderQuantity|beginAmount)"\s*:\s*"?(\d+)"?', html)
            if m and int(m.group(1)) > 1:
                product.min_order = int(m.group(1))

        print(f"[采集通道] requests 兜底补全: {len(missing)} 项缺失已尝试补齐")
    except Exception:
        pass


def collect_product(url_or_id, fetcher, max_attempts=3, backoff=(2, 4)):
    """
    双通道采集：tabbit 主（退避重试）→ requests 兜底。
    返回 Product1688；两路都失败抛异常。
    """
    offer_id = fetcher.extract_offer_id(url_or_id)
    last_error = None

    # —— 通道1：tabbit 传送带 ——
    for attempt in range(1, max_attempts + 1):
        try:
            result = collect_via_tabbit(offer_id)
            # 串味校验（2026-10-18 实测固化）：桥回传 offerId 非空时必须等于请求
            # offerId，否则是浏览器残留/前台另一商品的 SSR data，拒绝静默落库。
            bridge_offer = str(result.get("offerId") or "").strip()
            if bridge_offer and bridge_offer != str(offer_id).strip():
                raise ChannelError(
                    "MISMATCHED_OFFER",
                    f"桥回传 offerId={bridge_offer} 与请求 {offer_id} 不符（疑似页面残留串味）",
                    recoverable=True,
                )
            product = result_to_product(result, offer_id)
            _fill_missing_via_requests(fetcher, product, offer_id)
            print(f"[采集通道] tabbit 成功（第{attempt}次）: {product.title[:30]}")
            return product
        except ChannelError as e:
            last_error = e
            if e.code == "AUTH_REQUIRED":
                # 登录墙不重试，直接上交（上层发重登提醒）
                raise
            wait = backoff[min(attempt - 1, len(backoff) - 1)]
            print(f"[采集通道] tabbit 第{attempt}次失败({e.code})，{wait}s 后重试")
            time.sleep(wait)
        except Exception as e:
            last_error = e
            print(f"[采集通道] tabbit 异常: {e}")
            time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])

    # —— 通道2：requests 移动端兜底 ——
    print(f"[采集通道] tabbit 不可用，切 requests 兜底。上次错误: {last_error}")
    return fetcher.fetch(url_or_id)
