"""
主调度器 - 采集阶段
流程：采集1688 → 规则校验 → 写入商品主表（状态=待选品，AI处理状态=待处理）
AI处理（图片翻译/视频字幕/描述翻译）在选品确认后由 ai_processor 异步执行

W-02（2026-10-19）：process_from_feishu 接入 S0 硬筛闸门（s0_screen）。
  采集前先跑确定性闸门（去重 / 利润率≥80% / 采购价<100 / 禁售类目）：
    pass          → 进全量采集
    duplicate     → 推荐状态=已淘汰 + 备注原因，不采集
    reject        → 推荐状态=已淘汰 + 备注原因，不采集
    pending_price → 保持待采集 + 备注待定价原因，不采集（缺售价/成本，不淘汰不放行）
"""
import sys
import json
import argparse
from core.fetcher import Fetcher1688
from core.rule_checker import RuleChecker
from core.collect_pipeline import collect_product
from core.s0_screen import screen_candidate
from core.dedup import DedupIndex, extract_offer_id
from feishu_api import feishu, TABLE_IDS
from config import config


def _cell(v, default=""):
    """select 单元格可能是 list，取 [0]"""
    if v is None:
        return default
    if isinstance(v, list):
        return v[0] if v else default
    return v


def _cell_text(v, default=""):
    """URL/文本字段可能是 str / dict{link,text} / list，统一取文本"""
    if v is None:
        return default
    if isinstance(v, list):
        return _cell_text(v[0], default) if v else default
    if isinstance(v, dict):
        return v.get("link") or v.get("text") or default
    return str(v)


def _extract_1688_link(v):
    """候选表链接字段可能是1688或Shopee竞品链接；只取 1688 采购链接"""
    text = _cell_text(v)
    if "1688.com" in text or "detail.1688.com" in text:
        return text
    return ""


class Collector:
    """采集器主调度（采集+规则+入库，不做AI处理）"""

    def __init__(self):
        self.fetcher = Fetcher1688()
        self.rule_checker = RuleChecker()

    def process_single(self, url_or_id, write_to_feishu=True):
        """
        处理单个商品：采集 → 规则校验 → 写入飞书（待选品）
        AI处理不在此阶段执行
        """
        print(f"\n{'='*60}")
        print(f"开始处理: {url_or_id}")
        print(f"{'='*60}")

        # Step 1: 双通道采集（tabbit 传送带为主，requests 移动端兜底，带重试退避）
        print("\n[Step 1] 采集1688商品信息（tabbit 主通道 / requests 兜底）...")
        try:
            product = collect_product(url_or_id, self.fetcher)
        except Exception as e:
            code = getattr(e, "code", "")
            if code == "AUTH_REQUIRED":
                print(f"采集失败: 1688登录态失效，请重新登录（{e}）")
            else:
                print(f"采集失败: {e}")
            return None

        print(f"  标题: {product.title[:40]}")
        print(f"  价格: ¥{product.price}")
        print(f"  SKU数: {len(product.skus)}")
        print(f"  图片数: {len(product.images)} / 详情图: {len(product.detail_images)}")
        print(f"  视频: {'有' if product.video_url else '无'}")
        print(f"  品牌: {product.brand or '无'}")
        print(f"  货号: {product.vendor_code or '无'}")
        print(f"  1688类目: {product.category_id or '无'}")
        print(f"  重量: {product.weight_g}g")
        print(f"  尺寸: {product.dimensions_mm}mm")
        print(f"  描述: {len(product.description)}字" if product.description else "  描述: 无")
        print(f"  一件代发: {'支持' if product.supports_drop_shipping else '不支持'}")

        # Step 2: 选品规则校验（纯规则，无AI）
        print("\n[Step 2] 选品规则校验...")
        passed, reasons = self.rule_checker.check(product)
        if not passed:
            print(f"  规则校验未通过:")
            for r in reasons:
                print(f"    - {r}")
            return None
        if reasons:
            print(f"  软性提醒:")
            for r in reasons:
                print(f"    - {r}")
        else:
            print("  全部通过")

        # Step 3: 写入飞书商品主表（状态=待选品，AI处理状态=待处理）
        if write_to_feishu:
            print("\n[Step 3] 写入飞书商品主表...")
            fields = {
                "中文标题": product.title,
                # 主表链接字段均为 text 类型：传纯字符串，不传 {link,text} dict
                "1688 OfferID": product.offer_id,
                "采购链接": f"https://detail.1688.com/offer/{product.offer_id}.html",
                "采购价CNY": product.price,
                "SKU数量": len(product.skus),
                "主图链接": product.images[0] if product.images else "",
                "附图链接": "\n".join(product.images[1:5]) if len(product.images) > 1 else "",
                "详情图链接": "\n".join(product.detail_images[:10]) if product.detail_images else "",
                "视频链接": product.video_url or "",
                "包裹重量g": product.weight_g,
                "商品描述中文": product.description,
                "品牌": product.brand or config.DEFAULT_BRAND,
                "商品属性JSON": json.dumps(product.attributes, ensure_ascii=False) if product.attributes else "",
                "库存": product.stock,
                "货号": product.vendor_code,
                "1688类目": product.category_id,
                "处理状态": "待选品",
                "AI处理状态": "待处理",
                "上架校验状态": "待校验",
            }
            # W-03：新增字段（已 +field-create 到主表）——供应商 / 最小起订量 / SKU规格明细
            if product.supplier_name:
                fields["供应商"] = product.supplier_name
            if product.min_order:
                fields["最小起订量"] = product.min_order
            if product.skus:
                try:
                    fields["SKU规格明细"] = json.dumps(
                        [{"规格": s.get("name", ""), "价格": s.get("price")} for s in product.skus],
                        ensure_ascii=False)
                except Exception:
                    pass
            try:
                result = feishu.create_record(TABLE_IDS["product"], fields)
                if result.get("code") == 0:
                    record_id = result.get("data", {}).get("record", {}).get("record_id", "")
                    print(f"  写入成功，记录ID: {record_id}")
                    print(f"  状态: 待选品 / AI处理状态: 待处理")
                else:
                    print(f"  写入失败: {result}")
            except Exception as e:
                print(f"  写入异常: {e}")

        print(f"\n{'='*60}")
        print("采集完成（AI处理将在选品确认后执行）")
        print(f"{'='*60}\n")
        return product

    def process_from_feishu(self, limit=10):
        """从飞书选品候选表读取待处理商品，S0 闸门后批量采集（W-02）"""
        print(f"从飞书选品候选表读取待处理商品（最多{limit}条）...")
        try:
            records = feishu.list_records(TABLE_IDS["candidate"], page_size=limit)
            pending = [r for r in records if _cell(r.get("fields", {}).get("处理状态")) == "待采集"]
            print(f"找到 {len(pending)} 条待采集记录")

            # —— S0 闸门：预取去重索引（候选表 OfferID/链接 + 主表采购链接）——
            print("\n[S0闸门] 预取候选表/主表去重索引...")
            try:
                cand_all = feishu.list_records(TABLE_IDS["candidate"], page_size=200)
            except Exception as e:
                print(f"  [S0] 候选表全量读取失败，去重索引降级为空: {e}")
                cand_all = []
            try:
                master_all = feishu.list_records(TABLE_IDS["product"], page_size=200)
            except Exception as e:
                print(f"  [S0] 主表全量读取失败，去重索引降级为空: {e}")
                master_all = []
            cand_idx = DedupIndex.from_records(cand_all, ("1688 OfferID", "参考竞品链接", "采购链接"))
            master_idx = DedupIndex.from_records(master_all, ("采购链接", "1688 OfferID"))
            print(f"  [S0] 候选表去重集 {cand_idx.size()} 个 OfferID / 主表去重集 {master_idx.size()} 个")

            for record in pending:
                fields = record.get("fields", {})
                record_id = record.get("record_id", "")

                # 构造 s0_candidate（缺字段按 None，不臆造）
                offer_id = _cell_text(fields.get("1688 OfferID"))
                cand = {
                    "offer_id": offer_id or None,
                    "采购链接": _extract_1688_link(fields.get("参考竞品链接") or fields.get("采购链接")) or None,
                    "商品名称": _cell_text(fields.get("商品名称")),
                    "采购成本CNY": fields.get("采购成本CNY"),
                    "建议售价CNY": fields.get("建议售价CNY"),
                    "SLS运费CNY": fields.get("SLS运费CNY"),
                    "类目": _cell_text(fields.get("类目")),
                }
                r = screen_candidate(cand, candidate_index=cand_idx, master_index=master_idx)
                decision = r["decision"]
                print(f"\n  [S0] {decision.upper()} | {cand['商品名称'][:30]} | {r['reason'][:80]}")

                # —— 闸门分流：非 pass 一律不采集 ——
                if decision == "duplicate":
                    note = f"S0去重: OfferID {r['offer_id']} 已存在于{('候选表' if '候选表' in r['reason'] else '主表')}，跳过采集"
                    feishu.update_record(TABLE_IDS["candidate"], record_id, {
                        "推荐状态": "已淘汰",
                        "人工备注": note,
                    })
                    print(f"  [S0] 标已淘汰（重复），不采集")
                    continue
                if decision == "reject":
                    note = f"S0硬筛淘汰: {r['reason']}"
                    feishu.update_record(TABLE_IDS["candidate"], record_id, {
                        "推荐状态": "已淘汰",
                        "处理状态": "规则淘汰",
                        "人工备注": note,
                    })
                    print(f"  [S0] 标规则淘汰，不采集")
                    continue
                if decision == "pending_price":
                    note = f"S0待定价: {r['reason']}（补建议售价/采购成本后重新采集）"
                    feishu.update_record(TABLE_IDS["candidate"], record_id, {
                        "人工备注": note,
                    })
                    print(f"  [S0] 缺定价信息，不采集（保持待采集）")
                    continue

                # —— pass：进全量采集 ——
                url = cand.get("采购链接") or offer_id
                if not url:
                    print(f"记录 {record_id} 无1688链接，跳过")
                    continue
                if offer_id and ("offer/" + str(offer_id)) not in str(url):
                    url = f"https://detail.1688.com/offer/{offer_id}.html"

                feishu.update_record(TABLE_IDS["candidate"], record_id, {"处理状态": "采集中"})
                result = self.process_single(url, write_to_feishu=True)
                if result:
                    feishu.update_record(TABLE_IDS["candidate"], record_id, {"处理状态": "已采集"})
                else:
                    feishu.update_record(TABLE_IDS["candidate"], record_id, {"处理状态": "规则淘汰"})

        except Exception as e:
            print(f"从飞书读取失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="1688通用跨境采集器 - 采集阶段")
    parser.add_argument("url", nargs="?", help="1688商品链接或ID")
    parser.add_argument("--from-feishu", action="store_true", help="从飞书选品表批量采集")
    parser.add_argument("--limit", type=int, default=10, help="批量处理数量")
    parser.add_argument("--no-write", action="store_true", help="不写入飞书，仅采集打印")
    args = parser.parse_args()

    collector = Collector()

    if args.from_feishu:
        collector.process_from_feishu(args.limit)
    elif args.url:
        collector.process_single(args.url, write_to_feishu=not args.no_write)
    else:
        parser.print_help()
        print("\n示例:")
        print("  python main.py https://detail.1688.com/offer/123456789.html")
        print("  python main.py 123456789 --no-write")
        print("  python main.py --from-feishu --limit 5")
        print("\nAI处理请运行: python poll_feishu.py")


if __name__ == "__main__":
    main()
