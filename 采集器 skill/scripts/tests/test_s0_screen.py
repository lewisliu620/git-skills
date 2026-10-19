# -*- coding: utf-8 -*-
"""
#48 S0 硬筛离线单测 + 历史干净样例回归基准（不依赖飞书、不依赖网络）。

运行：在 scripts/ 目录下 `python -m pytest tests/test_s0_screen.py -q`
      或直接 `python tests/test_s0_screen.py`（无 pytest 也能跑内置断言）。

口径：预估利润=建议售价−采购成本−SLS；利润率=预估利润/建议售价；门槛≥0.80；
缺建议售价→pending_price（不臆造、不淘汰）；SLS两档（极轻1元/套装稍重3.5元，
全量后按真实重量≥300g复核）；去重键=1688 OfferID（候选表内+主表采购链接互查）。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profit_model import assess, estimate_sls_cny
from core.dedup import extract_offer_id, DedupIndex, is_duplicate
from core.s0_screen import screen_candidate

# 历史11条10月泰国干净样例回归基准（成本/SLS/售价 → 期望决策/期望利润率）
# 与候选表 tblBsUDHOIEymeLO 历史记录预估利润±0.02吻合。
BASELINE = [
    ("美甲贴纸套装", 0.80, 1.20, 12.00, "pass", 0.8333),
    ("布艺发圈10条装", 1.50, 1.50, 15.00, "pass", 0.8000),
    ("手机装饰贴纸", 0.60, 1.00, 10.00, "pass", 0.8400),
    ("金属书签3个装(80%边界)", 1.80, 1.80, 18.00, "pass", 0.8000),
    ("临时纹身贴", 0.50, 0.80, 9.50, "pass", 0.8632),
    ("水槽过滤网100只装", 0.50, 1.00, 8.00, "pass", 0.8125),
    ("理线器4个装", 0.60, 1.00, 9.30, "pass", 0.8280),
    ("魔术贴固定扣4个装", 0.40, 0.80, 8.00, "pass", 0.8500),
    ("竹炭包5包装", 2.50, 3.50, 30.86, "pass", 0.8056),
    ("防滑贴16条装", 2.00, 3.50, 28.81, "pass", 0.8087),
    ("除湿挂袋8个装", 2.80, 3.50, 32.92, "pass", 0.8086),
    # 历史淘汰样例（模型须 reject）
    ("挂脖小风扇", 8.50, 7.20, 32.72, "reject", 0.5202),
    ("捏捏乐", 3.09, 3.09, 12.14, "reject", None),
    ("驱蚊手环", 2.06, 2.06, 8.02, "reject", None),
    ("手机气囊支架", 2.06, 2.06, 5.97, "reject", None),
    ("日落氛围灯", 5.14, 5.14, 20.37, "reject", None),
]


def test_baseline():
    fails = []
    for name, cost, sls, price, exp_status, exp_margin in BASELINE:
        r = assess(price_cny=price, cost_cny=cost, sls_cny=sls, title=name)
        if r["status"] != exp_status:
            fails.append(f"{name}: 期望{exp_status} 实得{r['status']}")
        if exp_margin is not None and abs(r["margin_ratio"] - exp_margin) > 0.002:
            fails.append(f"{name}: 期望率{exp_margin} 实得{r['margin_ratio']}")
    assert not fails, "基线偏差:\n" + "\n".join(fails)


def test_pending_price_no_fabrication():
    r = assess(price_cny=None, cost_cny=1.2, title="新品待定价")
    assert r["status"] == "pending_price" and r["profit_cny"] is None


def test_sls_two_tier():
    assert estimate_sls_cny("竹炭包5包装") == 3.5
    assert estimate_sls_cny("手机贴纸单张") == 1.0
    assert estimate_sls_cny("小物件", [], weight_g=420) == 3.5
    assert estimate_sls_cny("小物件", [], weight_g=80) == 1.0


def test_offerid_extract():
    assert extract_offer_id("https://detail.1688.com/offer/603221307298.html") == "603221307298"
    assert extract_offer_id("offerId=997460258722") == "997460258722"
    assert extract_offer_id({"link": "https://m.1688.com/offer/997460258722.html"}) == "997460258722"
    assert extract_offer_id("https://example.com/shop") is None


def test_dedup_index():
    ci = DedupIndex(["603221307298", "997460258722"])
    mi = DedupIndex(["123456789012"])
    assert is_duplicate("603221307298", ci, mi)[0] is True
    assert is_duplicate("123456789012", ci, mi)[0] is True
    assert is_duplicate("999999999999", ci, mi)[0] is False
    assert DedupIndex(["0603221307298"]).has("603221307298")  # 前导零归一


def test_screen_orchestration():
    # 去重短路：即便售价达标，已存在于候选表也判 duplicate
    ci = DedupIndex(["603221307298"])
    r = screen_candidate({"offer_id": "603221307298", "商品名称": "x",
                          "采购成本CNY": 0.6, "建议售价CNY": 10.0, "类目": "家居"}, ci, DedupIndex())
    assert r["decision"] == "duplicate"

    # pass：成本0.6/售价10/类目干净，视频重量缺失只进 deferred 不淘汰
    r = screen_candidate({"offer_id": "700000000001", "商品名称": "手机装饰贴纸单张",
                          "采购成本CNY": 0.6, "建议售价CNY": 10.0, "类目": "家居小物",
                          "has_video": True})
    assert r["decision"] == "pass", r["reason"]
    assert r["fields"]["1688 OfferID"] == "700000000001"

    # pending_price：无售价，不淘汰不放行
    r = screen_candidate({"offer_id": "700000000002", "商品名称": "新品",
                           "采购成本CNY": 1.2, "类目": "家居"})
    assert r["decision"] == "pending_price"

    # 禁售类目命中 → reject
    r = screen_candidate({"offer_id": "700000000003", "商品名称": "零食",
                          "采购成本CNY": 0.6, "建议售价CNY": 10.0, "类目": "食品饮料"})
    assert r["decision"] == "reject"

    # 采购价 ≥100 超限 → reject
    r = screen_candidate({"offer_id": "700000000004", "商品名称": "大件",
                          "采购成本CNY": 150.0, "建议售价CNY": 500.0, "类目": "家居"})
    assert r["decision"] == "reject"


if __name__ == "__main__":
    test_baseline()
    test_pending_price_no_fabrication()
    test_sls_two_tier()
    test_offerid_extract()
    test_dedup_index()
    test_screen_orchestration()
    print("ALL S0 TESTS PASSED")
