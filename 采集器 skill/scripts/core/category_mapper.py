# -*- coding: utf-8 -*-
"""
core/category_mapper.py — #52 中文标题/1688类目 → Shopee 叶子类目ID 语义映射（本地纯函数，无网络、无飞书请求）

目的：上架前提前把商品对到 Shopee 叶子类目ID，解除建草稿"类目ID空缺"输入缺口，争取一次选中。

口径（2026-10-18 拍板，安全优先）：
  · 显式规则词典命中（关键词全含、且未命中排除词）→ decision="auto"，可直接回填叶子ID；
  · 规则未命中 → 只给 top3 候选 + 得分，decision="candidates"，**不自动写ID**，交人工选；
  · 命中 S0 禁售/带电/食品/化妆品等前置词 → decision="blocked_forbidden"，不给类目（应由 S0 淘汰）；
  · 模糊、无规则、得分不足 → decision="none"，不臆造ID。

字典源：Shopee 叶子扁平表 data/categories-flat.json（2209 叶子，字段 id/zh/en/path）。
本模块只做本地匹配，不读飞书、不回写；回写由调用方经 lark-cli --as user 完成，且只写 auto 项。
"""
import json
import os

# ===== S0 禁售前置词（与 s0_screen.FORBIDDEN_CATEGORY_KEYWORDS 对齐；带电/电池单独扩）=====
FORBIDDEN_HINT = [
    "零食", "化妆品", "口红", "护肤品", "面膜",
    "带电", "电池", "充电", "无线充", "USB充电", "电动", "插电",
    "医疗器械", "药品", "保健品", "体温计",
]
# 这些词出现在「材质描述」（食品级硅胶/食品级塑料）不是食品类目，禁售检测前先剥离
_FOOD_GRADE_WORDS = ["食品级", "可食用级", "食用级"]

# ===== 家庭类目兜底（规则未命中时，按粗锚点给候选，仍需人工确认，不自动写）=====
# family: 命中关键词 → 字典 path 片段，从该片段叶子里出候选
FAMILY_FALLBACK = [
    {
        "keywords": ["厨房", "餐饮", "餐具", "烹饪", "料理", "做饭", "压蒜", "蒜泥",
                     "搅蒜", "捣蒜", "蒜蓉", "冰格", "制冰", "冰块", "挖球", "水果拼盘",
                     "玉米刨", "脱粒", "削皮", "切菜"],
        "path_segment": "餐饮用品",
        "prefer": [101244, 101248, 101242],
        "label": "厨房/餐饮小工具（无专叶，建议落餐饮用品，人工确认）",
    },
]

# ===== 显式规则词典（顺序匹配，先具体后宽泛）=====
# keywords: 文本须命中其中任一；must_not: 命中即排除该规则（避免车载/充电误落到手机支架）
# id 必须是 categories-flat.json 里真实存在的叶子ID；label 用于人读说明。
RULES = [
    # —— 运动户外 / 瑜伽普拉提 ——
    {
        "keywords": ["瑜伽垫", "健身垫", "瑜伽"],
        "must_not": ["车载", "汽车"],
        "id": 101886, "label": "运动户外>瑜伽与普拉提>瑜珈垫",
    },
    {
        "keywords": ["阻力带", "弹力带", "拉力带"],
        "must_not": [],
        "id": 101888, "label": "运动户外>瑜伽与普拉提>阻力带",
    },
    {
        "keywords": ["跳绳"],
        "must_not": [],
        "id": 101891, "label": "运动户外>健身器材>跳绳",
    },
    # —— 手机配件（先区分车载/充电，避免误配）——
    {
        "keywords": ["手机挂绳", "挂脖", "背夹挂绳", "手机链", "斜挎挂绳"],
        "must_not": ["车载", "充电", "无线"],
        "id": 100280, "label": "手机平板与配件>配件>手机吊饰 & 钥匙圈",
    },
    {
        "keywords": ["手机支架", "懒人支架", "桌面手机架"],
        "must_not": ["车载", "汽车", "充电", "无线充", "磁吸充电"],
        "id": 100279, "label": "手机平板与配件>配件>手机支架",
    },
    {
        "keywords": ["手机壳", "保护壳"],
        "must_not": ["车载", "充电"],
        "id": 100490, "label": "手机平板与配件>配件>保护壳>手机保护配件",
    },
    {
        "keywords": ["钢化膜", "屏幕保护膜", "手机膜"],
        "must_not": [],
        "id": 100289, "label": "手机平板与配件>配件>屏幕保护膜",
    },
    # —— 美甲 ——
    {
        "keywords": ["指甲贴纸", "美甲贴纸", "指甲贴"],
        "must_not": [],
        "id": 102033, "label": "美妆保健>手足保养与美甲>指甲保养>指甲贴纸",
    },
    {
        "keywords": ["美甲贴片", "甲片"],
        "must_not": ["贴纸"],
        "id": 102032, "label": "美妆保健>手足保养与美甲>指甲保养>美甲贴片",
    },
    {
        "keywords": ["美甲工具", "卸甲", "美甲锉"],
        "must_not": ["贴纸", "贴片"],
        "id": 102031, "label": "美妆保健>手足保养与美甲>指甲保养>美甲工具",
    },
    # —— 纹身贴 / 装饰贴纸 ——
    {
        "keywords": ["纹身贴", "临时纹身"],
        "must_not": [],
        "id": 100164, "label": "时尚配饰>穿搭配饰>纹身贴",
    },
    {
        "keywords": ["装饰贴纸", "手机贴纸", "标签贴纸"],
        "must_not": ["指甲", "美甲", "车"],
        "id": 101379, "label": "文具>笔记本与纸质用品>标签与贴纸",
    },
    # —— 家居日用 ——
    {
        "keywords": ["垃圾袋", "塑料袋", "手提袋"],
        "must_not": [],
        "id": 101208, "label": "家居生活>居家日用品>塑料袋与垃圾袋",
    },
    {
        "keywords": ["书签"],
        "must_not": [],
        "id": 101371, "label": "文具>笔记本与纸质用品>书签",
    },
]

# 兜底打分阈值：top1 bigram 重合度（0-1）达到才允许作为候选展示；低于则 none
FALLBACK_SCORE_FLOOR = 0.18


def _bigrams(text):
    """中文文本拆 2-gram，忽略空白与符号。"""
    t = "".join(ch for ch in str(text) if not ch.isspace() and not _is_punct(ch))
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else set()


def _is_punct(ch):
    return not ('\u4e00' <= ch <= '\u9fff' or ch.isalnum())


DEFAULT_FLAT = r"D:\AI\电商\shopee-listing-assistant-v2.0.9\data\categories-flat.json"


def load_flat_items(path=None):
    """载入 Shopee 扁平叶子字典；path 缺省用 DEFAULT_FLAT。读不到返回空列表（调用方注入）。"""
    path = path or DEFAULT_FLAT
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items") if isinstance(data, dict) else data


def _rule_match(text, rules=None):
    """返回首个命中规则 dict，未命中 None。"""
    for rule in (rules or RULES):
        if any(kw in text for kw in rule["keywords"]):
            if any(neg in text for neg in rule.get("must_not", [])):
                continue
            return rule
    return None


def _fallback_score(text_bigrams, leaf_text):
    """叶子名+路径 与文本的 bigram Jaccard 重合度。"""
    lb = _bigrams(leaf_text)
    if not text_bigrams or not lb:
        return 0.0
    inter = len(text_bigrams & lb)
    union = len(text_bigrams | lb)
    return inter / union if union else 0.0


def map_category(title_cn="", category_hint="", items=None, rules=None):
    """
    单条商品映射。
    入参：title_cn 中文标题；category_hint 粗类目列（如"厨房小工具"）；items 叶子列表。
    返回 dict:
      decision: auto | candidates | none | blocked_forbidden
      category_id / path / leaf / score（auto 时有）
      candidates: [{id,path,leaf,score}]（candidates 时）
      reasons: [人读理由]
    """
    raw_text = f"{title_cn or ''} {category_hint or ''}".strip()
    # 剥离材质型「食品级」等，避免把食品级硅胶误判成食品类目
    text = raw_text
    for fg in _FOOD_GRADE_WORDS:
        text = text.replace(fg, "")
    reasons = []

    # 0. 禁售前置：命中即不给类目，交 S0 淘汰
    for w in FORBIDDEN_HINT:
        if w in text:
            return {
                "decision": "blocked_forbidden",
                "category_id": None, "path": None, "leaf": None, "score": None,
                "candidates": [],
                "reasons": [f"命中禁售/敏感前置词「{w}」，不进类目映射（应由S0淘汰）"],
            }

    # 1. 显式规则命中 → auto
    rule = _rule_match(text, rules)
    if rule and items:
        hit = next((x for x in items if str(x.get("id")) == str(rule["id"])), None)
        if hit:
            reasons.append(f"规则命中「{rule['keywords'][0]}」→ {rule['label']}")
            return {
                "decision": "auto",
                "category_id": rule["id"],
                "path": hit.get("path"), "leaf": hit.get("zh"),
                "score": 1.0,
                "candidates": [],
                "reasons": reasons,
            }

    # 1.5 家庭类目兜底：粗锚点命中（如厨房小工具无专叶）→ 给该分支 top3 候选，不自动写
    if items:
        for fam in FAMILY_FALLBACK:
            if any(kw in text for kw in fam["keywords"]):
                pool = [it for it in items if fam["path_segment"] in (it.get("path") or "")]
                # 优先序：显式 prefer 按声明顺序在前，其余按路径；只给 top3，避免刷屏
                pref = fam.get("prefer", [])
                ordered = sorted(
                    pool,
                    key=lambda it: (
                        0 if it.get("id") in pref else 1,
                        pref.index(it.get("id")) if it.get("id") in pref else 999,
                        str(it.get("path")),
                    ),
                )
                cand = [
                    {"id": it.get("id"), "path": it.get("path"),
                     "leaf": it.get("zh"), "score": None}
                    for it in ordered[:3]
                ]
                if cand:
                    reasons.append(f"{fam['label']}：候选见下，需人工确认叶子")
                    return {
                        "decision": "candidates",
                        "category_id": None, "path": None, "leaf": None, "score": None,
                        "candidates": cand,
                        "reasons": reasons,
                    }

    # 2. 兜底 bigram 打分 → 只出候选，不自动写
    if items:
        tg = _bigrams(text)
        scored = []
        for it in items:
            leaf_text = f"{it.get('zh','')} {it.get('path','')}"
            s = _fallback_score(tg, leaf_text)
            if s >= FALLBACK_SCORE_FLOOR:
                scored.append({"id": it.get("id"), "path": it.get("path"),
                               "leaf": it.get("zh"), "score": round(s, 3)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:3]
        if top:
            reasons.append("规则未覆盖，按文本相似度给出候选，需人工确认叶子类目")
            return {
                "decision": "candidates",
                "category_id": None, "path": None, "leaf": None, "score": None,
                "candidates": top,
                "reasons": reasons,
            }

    reasons.append("无可信类目匹配，需人工指定")
    return {
        "decision": "none",
        "category_id": None, "path": None, "leaf": None, "score": None,
        "candidates": [],
        "reasons": reasons,
    }
