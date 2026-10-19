"""
core/s0_screen.py — #48 S0 选品硬筛编排（本地确定性，纯函数，无AI、无飞书请求）

职责：对一条候选商品做 S0 确定性闸门，输出统一判定。
  S0 硬卡（选品阶段本地可判，不达标直接 reject / duplicate）：
    1. 去重：OfferID 命中候选表或主表采购链接 → duplicate，不重复进候选；
    2. 利润率 ≥80%（profit_model.assess）：缺建议售价 → pending_price（待定价，不淘汰不放行）；
    3. 采购价上限 <100 元（对齐规则表 recvwc0dmQbyU8）；
    4. 禁售类目黑名单：食品/化妆品/带电/医疗器械（对齐规则表 recvwc0dmQSJ9b）。
  S2 复核项（选品轻量阶段拿不到，S0 只打标不淘汰，审批通过全量采集后复核）：
    视频必传、包裹重量≤2kg、一件代发、竞争度（语义分由豆包工作承担）。

输入 candidate dict（缺字段按 None 处理，不臆造）：
  offer_id / 采购链接, 商品名称, 采购成本CNY, 建议售价CNY, SLS运费CNY(可选),
  sku_names[], weight_g, has_video, supports_drop_shipping, 类目
"""
from .profit_model import assess as _assess, MARGIN_THRESHOLD
from .dedup import extract_offer_id, DedupIndex, is_duplicate

# 选品阶段本地硬规则常量（与飞书规则表对齐；飞书规则表后续可覆盖）
MAX_PURCHASE_CNY = 100.0
FORBIDDEN_CATEGORY_KEYWORDS = ["食品", "化妆品", "带电", "电池", "医疗器械", "药品", "保健品"]


def screen_candidate(candidate, candidate_index: DedupIndex = None, master_index: DedupIndex = None):
    """
    对单条候选跑 S0 硬筛。
    返回 dict:
      decision: "pass" | "reject" | "pending_price" | "duplicate"
      offer_id, checks[], margin{}, deferred[]（S2复核项）, fields{}（建议写回候选表）, reason
    """
    c = candidate or {}
    offer_id = extract_offer_id(c.get("offer_id") or c.get("采购链接") or c.get("1688 OfferID"))
    checks = []
    deferred = []
    fields = {}

    # —— 1. 去重（最先判，重复直接短路）——
    dup, where = is_duplicate(offer_id, candidate_index, master_index) if offer_id else (False, None)
    if dup:
        return {
            "decision": "duplicate",
            "offer_id": offer_id,
            "checks": [{"rule": "去重", "passed": False, "reason": f"OfferID 已存在于{('候选表' if where=='candidate' else '主表')}，跳过"}],
            "margin": None,
            "deferred": [],
            "fields": {},
            "reason": f"重复（{where}），不重复进候选",
        }

    # —— 2. 利润率硬门槛（缺售价 → pending_price）——
    margin = _assess(
        price_cny=c.get("建议售价CNY"),
        cost_cny=c.get("采购成本CNY"),
        sls_cny=c.get("SLS运费CNY"),
        title=c.get("商品名称", ""),
        sku_names=c.get("sku_names"),
        weight_g=c.get("weight_g"),
    )
    checks.append({
        "rule": f"利润率≥{int(MARGIN_THRESHOLD*100)}%",
        "passed": margin["status"] == "pass",
        "reason": margin["reason"],
    })
    fields.update(margin.get("fields", {}))

    # —— 3. 采购价上限 <100 ——
    cost = c.get("采购成本CNY")
    try:
        cost_f = float(cost) if cost not in (None, "") else None
    except (TypeError, ValueError):
        cost_f = None
    if cost_f is None:
        checks.append({"rule": "采购价<100元", "passed": None, "reason": "缺采购成本，待补"})
        deferred.append("采购成本待补后复核采购价上限")
    else:
        price_ok = cost_f < MAX_PURCHASE_CNY
        checks.append({"rule": "采购价<100元", "passed": price_ok,
                       "reason": f"采购成本¥{cost_f:.2f}" + ("" if price_ok else f"≥{MAX_PURCHASE_CNY:.0f}元超限")})

    # —— 4. 禁售类目黑名单 ——
    category = str(c.get("类目") or "")
    hit = [k for k in FORBIDDEN_CATEGORY_KEYWORDS if k in category]
    if category:
        checks.append({"rule": "排除禁售类目", "passed": len(hit) == 0,
                       "reason": "命中禁售词: " + "、".join(hit) if hit else f"类目「{category}」未命中黑名单"})
    else:
        checks.append({"rule": "排除禁售类目", "passed": None, "reason": "缺类目，待S2复核"})
        deferred.append("类目待S2全量采集后复核禁售词")

    # —— S2 复核项（只打标，不淘汰）——
    if not c.get("has_video"):
        deferred.append("视频必传：S2全量采集确认视频，缺失则上架前补")
    if c.get("weight_g") in (None, 0):
        deferred.append("包裹重量≤2kg：S2按真实重量复核")
    if c.get("supports_drop_shipping") is False:
        deferred.append("一件代发：确认供应商支持代发")

    # —— 汇总决策 ——
    hard_failed = [x for x in checks if x["passed"] is False]
    if margin["status"] == "pending_price":
        decision = "pending_price"
    elif hard_failed:
        decision = "reject"
    else:
        decision = "pass"

    fields["1688 OfferID"] = offer_id or ""
    return {
        "decision": decision,
        "offer_id": offer_id,
        "checks": checks,
        "margin": margin,
        "deferred": deferred,
        "fields": fields,
        "reason": margin["reason"] if decision == "pending_price" else
                  ("；".join(x["reason"] for x in hard_failed) if hard_failed else "S0确定性硬筛通过"),
    }
