"""
core/bridge_parser.py — 1688 SSR 桥 JSON → offer.collect 同款 result（纯函数，无副作用）

背景：MV3 隔离世界读不到 main world 的 window.context，插件用 #ysl-ssr-data DOM 桥
把 {data, detail} 序列化出来。

【一期现状】tabbit 通道受 return 内联体积上限限制（不能回传 66KB 桥原文），已在浏览器端
完成 pick（见 channel_tabbit.py 的 pickBridge），Python 不再调用本文件。本纯函数保留给二期
本地 host HTTP 桥直传桥原文时复用，保证采集口径与插件 offer.collect v1.7.2 一致。

复刻 content/offer-collector.js 的 pick 规则，含三个已修 bug：
  ① 视频只要 videoId>0 即视为有（不硬判 state===1），直取 videoUrl/coverUrl；
  ② skuPrice 时 currentPrices 两端 beginAmount 相同只是 min/max 区间，不填 priceRanges；
  ③ SKU 售价取 discountPrice/price（priceAmount 是起订单位非售价），skuId 优先 specId 防大数字精度丢失。
"""
import json


def _num(v):
    if v is None or v == "":
        return None
    try:
        s = str(v).replace(",", "").replace("¥", "").strip()
        n = float(s)
        return n if n == n else None  # NaN 检查
    except (ValueError, TypeError):
        return None


def _str(v):
    return "" if v is None else str(v).strip()


def _get(d, *keys, default=None):
    """安全取嵌套字段：_get(data, 'productTitle', 'fields', 'title')"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def parse_bridge_payload(raw_text, dom_attributes=None):
    """
    入参：#ysl-ssr-data 的 textContent（{data, detail} 的 JSON 字符串），
          dom_attributes（可选，DOM 属性表 dict，tabbit 通道顺带抓回）。
    返回 offer.collect 同款 result dict；模型未就绪抛 ValueError。
    """
    payload = json.loads(raw_text)
    data = payload.get("data") or None
    if not data:
        raise ValueError("OFFER_MODEL_NOT_READY: 桥里无 data")

    pt = _get(data, "productTitle", "fields") or {}
    g = _get(data, "gallery", "fields") or {}
    mp = _get(data, "mainPrice", "fields") or {}
    ss = _get(data, "shippingServices", "fields") or {}
    desc = _get(data, "description", "fields") or {}
    pack = _get(data, "productPackInfo", "fields") or {}

    title = _str(pt.get("title"))
    if not title:
        raise ValueError("OFFER_MODEL_NOT_READY: productTitle.fields.title 为空")

    missing = []

    # 主图/附图：offerImgList 全量去重，mainImage 兜底
    raw_imgs = g.get("offerImgList") or g.get("mainImage") or []
    main_images = list(dict.fromkeys([_str(x) for x in raw_imgs if _str(x)]))
    if not main_images:
        missing.append("mainImages")

    # 视频：videoId>0 即有；videoUrl/coverUrl 直取页面字段
    video = g.get("video") or {}
    video_id_num = _num(video.get("videoId")) or 0
    has_video = video_id_num > 0
    if not has_video:
        missing.append("videoUrl")
    video_url = _str(video.get("videoUrl")) or _str(video.get("coverUrl")) or None

    # SKU 定价模型
    tw = _get(mp, "finalPriceModel", "tradeWithoutPromotion") or {}

    # 价格：区分数量阶梯价 vs SKU定价区间
    raw_prices = (mp.get("priceModel") or {}).get("currentPrices") or []
    distinct_begins = list({_num(r.get("beginAmount")) for r in raw_prices} - {None})
    price_ranges = []
    if len(distinct_begins) >= 2:
        price_ranges = [
            {"beginAmount": _num(r.get("beginAmount")), "price": _num(r.get("price"))}
            for r in raw_prices
            if _num(r.get("price")) is not None
        ]
    price_type = _str(mp.get("originPriceType")) or _str((mp.get("priceModel") or {}).get("priceDisplayType"))
    price_min = _num(tw.get("offerMinPrice"))
    price_max = _num(tw.get("offerMaxPrice"))
    price_display = _str(tw.get("offerPriceDisplay"))

    # SKU：售价取 discountPrice/price；skuId 优先 specId
    skus = []
    for s in (tw.get("skuMapOriginal") or []):
        sku_id = _str(s.get("specId")) or (str(s.get("skuId")) if s.get("skuId") is not None else None)
        price = _num(s.get("discountPrice"))
        if price is None:
            price = _num(s.get("price"))
        item = {
            "specAttrs": _str(s.get("specAttrs")),
            "skuId": sku_id,
            "price": price,
            "canBookCount": _num(s.get("canBookCount")),
            "saleCount": _num(s.get("saleCount")),
        }
        if item["specAttrs"] or item["skuId"]:
            skus.append(item)
    if not skus:
        missing.append("skus")

    # 最小起订量
    min_order = _num(tw.get("offerBeginAmount"))
    if min_order is None:
        min_order = _num(ss.get("startAmount"))

    # 重量：页面常给 0 占位，0 不视为真实重量 → missing，不猜
    unit_weight_g = _num(ss.get("unitWeight"))
    if unit_weight_g is None:
        unit_weight_g = _num(pack.get("unitWeight"))
    if unit_weight_g is None or unit_weight_g == 0:
        unit_weight_g = None
        missing.append("weightG")

    attributes = dict(dom_attributes or {})

    return {
        "offerId": _str(g.get("offerId")) or None,
        "title": title,
        "unit": _str(pt.get("unit")),
        "saleNum": _str(pt.get("saleNum")),
        "supplier": {"companyName": _str(_get(pt, "shopInfo", "companyName"))},
        "mainImages": main_images,
        "video": {
            "state": int(_num(video.get("state")) or 0),
            "videoId": _str(video.get("videoId")) or None,
            "url": video_url,
            "coverUrl": _str(video.get("coverUrl")) or None,
        },
        "priceType": price_type,
        "priceMin": price_min,
        "priceMax": price_max,
        "priceDisplay": price_display,
        "priceRanges": price_ranges,
        "skus": skus,
        "minOrder": min_order,
        "location": _str(ss.get("location")),
        "freight": {"postFeeValue": _num(ss.get("postFeeValue")), "unitWeightG": unit_weight_g},
        "leafCategoryId": _str(desc.get("leafCategoryId")) or None,
        "descriptionHtml": payload.get("detail") or "",
        "attributes": attributes,
        "missing": missing,
    }
