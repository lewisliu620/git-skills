# -*- coding: utf-8 -*-
"""
#52 类目语义映射离线单测（不依赖飞书、不依赖网络；字典缺失时用最小桩集）。
运行：在 scripts/ 目录 `python tests/test_category_mapper.py`
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.category_mapper import map_category, load_flat_items

# 真实字典优先；读不到用桩集保证规则断言可跑
ITEMS = load_flat_items() or [
    {"id": 101886, "zh": "瑜珈垫", "path": "运动户外>瑜伽与普拉提>瑜珈垫"},
    {"id": 100279, "zh": "手机支架", "path": "手机平板与配件>配件>手机支架"},
    {"id": 100280, "zh": "手机吊饰 & 钥匙圈", "path": "手机平板与配件>配件>手机吊饰 & 钥匙圈"},
    {"id": 102033, "zh": "指甲贴纸", "path": "美妆保健>手足保养与美甲>指甲保养>指甲贴纸"},
    {"id": 100164, "zh": "纹身贴", "path": "时尚配饰>穿搭配饰>纹身贴"},
    {"id": 101208, "zh": "塑料袋与垃圾袋", "path": "家居生活>居家日用品>塑料袋与垃圾袋"},
]

CASES = [
    # (标题, 粗类目, 期望decision, 期望id)
    ("6mm加厚防滑瑜伽垫 家用健身垫 初学者专用", "运动户外", "auto", 101886),
    ("长款手机壳斜挎挂绳ins风背夹挂脖挂肩手机链", "手机配件>手机挂绳", "auto", 100280),
    ("垃圾袋家用加厚手提式实惠装大号厨房办公室专用黑色抽绳式塑料袋", "", "auto", 101208),
    ("สติกเกอร์ติดเล็บ 法式美甲贴纸", "美甲贴纸", "auto", 102033),
    ("临时纹身贴 防水持久", "", "auto", 100164),
    # 车载无线充电支架 → 命中充电禁售前置，不给类目
    ("新款折叠磁吸车载手机支架无线充电器磁吸快充", "手机配件", "blocked_forbidden", None),
    # 食品级硅胶冰格：「食品级」是材质，不得误判食品禁售；无专叶 → candidates
    # （该条不校验具体 decision，只要求不是 blocked_forbidden，下方单独断言）
]

EXTRA = [
    # (标题, 粗类目, 禁止出现的decision)
    ("37格蜂窝冰格食品级硅胶带盖制冰盒", "厨房小工具", "blocked_forbidden"),
]


def run():
    fails = []
    for title, hint, exp_dec, exp_id in CASES:
        r = map_category(title, hint, items=ITEMS)
        ok = r["decision"] == exp_dec and (exp_id is None or r["category_id"] == exp_id)
        if not ok:
            fails.append((title, exp_dec, exp_id, r["decision"], r["category_id"]))
    # 模糊厨房小工具：不应误给 auto（规则未覆盖）
    r = map_category("压蒜泥神器家用搅蒜器大号压蒜器", "厨房小工具", items=ITEMS)
    if r["decision"] == "auto":
        fails.append(("压蒜器", "非auto", None, r["decision"], r["category_id"]))

    # 食品级硅胶不得被「食品」误判为禁售
    for title, hint, forbidden_dec in EXTRA:
        r = map_category(title, hint, items=ITEMS)
        if r["decision"] == forbidden_dec:
            fails.append((title, f"非{forbidden_dec}", None, r["decision"], None))

    if fails:
        print("FAILED", len(fails))
        for f in fails:
            print("  ", f)
        sys.exit(1)
    print(f"ALL CATEGORY-MAPPER TESTS PASSED ({len(CASES)} cases + 1 fuzzy guard)")


if __name__ == "__main__":
    run()
