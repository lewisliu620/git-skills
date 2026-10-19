"""
core/profit_model.py — #48 S0 硬筛：利润率≥80% 的本地确定性利润模型（纯函数，无AI、无飞书依赖）

口径（用户 2026-10-18 拍板，已用候选表 28 条历史样例回归对齐）：
  · 建议售价CNY 由豆包工作/人工按泰国市场 THB 定价后 ÷4.86 折算；本地不反推、不臆造售价。
    缺少建议售价时判 pending_price（待定价），既不放行也不淘汰。
  · 预估利润CNY = 建议售价CNY − 采购成本CNY − SLS运费CNY（选品粗筛阶段不扣平台佣金）。
  · 利润率 = 预估利润CNY / 建议售价CNY；硬门槛 ≥ 0.80（80%），不达标直接淘汰。
  · SLS 运费轻量阶段拿不到重量，按两档启发式估算：极轻小件 1.0 元，套装/多件/稍重 3.5 元；
    S2 全量采集拿到真实包裹重量后按重量档覆盖复核。

历史样例对齐（候选表 tblBsUDHOIEymeLO）：
  手机贴纸 成本1 / 售价10 → pass；竹炭包5包装 成本2.5 / 30.86 → 0.807 pass；
  挂脖风扇 8.8 / 32.72 → reject；捏捏乐 3.09 / 12.14 → reject（与历史淘汰一致）。
"""
import re

# ===== 确定性常量（阈值集中在此，便于后续在飞书规则表/配置覆盖）=====
MARGIN_THRESHOLD = 0.80          # 利润率硬门槛 80%
SLS_LIGHT_CNY = 1.0              # 极轻小件 SLS 估算
SLS_HEAVY_CNY = 3.5              # 套装/多件/稍重 SLS 估算
HEAVY_WEIGHT_G = 300.0           # 全量复核：≥300g 走重档 SLS

# 套装/多件/大包装关键词（命中即按重档 SLS）；纯单件/替换芯/单片/单卷走轻档
_HEAVY_PATTERNS = [
    r"\d+\s*件套", r"\d+\s*只装", r"\d+\s*个装", r"\d+\s*条装", r"\d+\s*卷装",
    r"\d+\s*片装", r"\d+\s*包(?:装|只|个|片|卷)", r"\d+\s*只(?!手)", r"\d+\s*条(?!件)",
    r"套装", r"件套", r"组合装", r"礼盒", r"多只", r"多件", r"盒装", r"袋装",
    r"100\s*只", r"6\s*件套", r"10\s*条", r"5\s*包装", r"8\s*个装", r"16\s*条",
]
_HEAVY_RE = re.compile("|".join(_HEAVY_PATTERNS))


def estimate_sls_cny(title="", sku_names=None, weight_g=None):
    """
    估算 SLS 运费（人民币元），两档。
    优先级：真实包裹重量（全量复核）> 标题/SKU 套装关键词 > 默认轻档。
    """
    # 全量采集已拿到重量：按重量档判定，最准
    if weight_g and weight_g > 0:
        return SLS_HEAVY_CNY if weight_g >= HEAVY_WEIGHT_G else SLS_LIGHT_CNY

    blob = title or ""
    if sku_names:
        blob += " " + " ".join(str(s) for s in sku_names)

    if _HEAVY_RE.search(blob):
        return SLS_HEAVY_CNY
    return SLS_LIGHT_CNY


def calc_margin(price_cny, cost_cny, sls_cny):
    """
    计算预估利润与利润率。
    返回 (profit_cny, margin_ratio)；price<=0 时 margin 返回 None。
    """
    price = _to_float(price_cny)
    cost = _to_float(cost_cny) or 0.0
    sls = _to_float(sls_cny) or 0.0
    if price is None or price <= 0:
        return None, None
    profit = price - cost - sls
    margin = profit / price if price > 0 else None
    return round(profit, 4), margin


def profit_score(margin_ratio):
    """
    利润率 → 利润分（0-10，确定性映射，非AI）。
    80% 门槛映射到 10 分线；低于门槛按比例给分，封顶 10。
    """
    if margin_ratio is None:
        return None
    raw = (margin_ratio / MARGIN_THRESHOLD) * 10.0
    return round(max(0.0, min(10.0, raw)), 1)


def assess(price_cny, cost_cny, sls_cny=None, title="", sku_names=None, weight_g=None):
    """
    S0 利润率硬筛主入口。
    返回 dict:
      status: "pass" | "reject" | "pending_price"
      profit_cny / margin_ratio / sls_cny / profit_score
      reason: 人读判定理由
      fields: 建议写回候选表的确定性字段（采购成本/SLS/建议售价/预估利润/利润率/利润分）
    """
    cost = _to_float(cost_cny)
    price = _to_float(price_cny)
    sls = _to_float(sls_cny)
    if sls is None:
        sls = estimate_sls_cny(title, sku_names, weight_g)

    result = {
        "status": "pending_price",
        "profit_cny": None,
        "margin_ratio": None,
        "sls_cny": round(sls, 2) if sls is not None else None,
        "profit_score": None,
        "reason": "",
        "fields": {},
    }

    # 缺少建议售价：本地不臆造，待市场定价后复算，不放行不淘汰
    if price is None or price <= 0:
        result["reason"] = "缺少建议售价CNY，待市场定价后复算利润率（本地不反推售价）"
        result["fields"] = {
            "采购成本CNY": _round2(cost),
            "SLS运费CNY": round(sls, 2),
        }
        return result

    if cost is None or cost <= 0:
        result["status"] = "reject"
        result["reason"] = "缺少有效采购成本CNY，无法测算"
        return result

    profit, margin = calc_margin(price, cost, sls)
    result["profit_cny"] = round(profit, 2)
    result["margin_ratio"] = round(margin, 4)
    result["profit_score"] = profit_score(margin)

    # 浮点容差：0.80 边界（如 14.4/18）不得因浮点误差误判为 reject
    passed = margin is not None and round(margin, 4) >= MARGIN_THRESHOLD - 1e-4
    if passed:
        result["status"] = "pass"
        result["reason"] = f"利润率{margin*100:.1f}%≥80%硬门槛，预估利润¥{profit:.2f}"
    else:
        result["status"] = "reject"
        result["reason"] = f"利润率{margin*100:.1f}%<80%硬门槛，预估利润¥{profit:.2f}，淘汰"

    result["fields"] = {
        "采购成本CNY": round(cost, 2),
        "SLS运费CNY": round(sls, 2),
        "建议售价CNY": round(price, 2),
        "预估利润CNY": round(profit, 2),
        "利润率": round(margin, 4),
        "利润分": result["profit_score"],
    }
    return result


def _to_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _round2(v):
    return round(v, 2) if v is not None else None
