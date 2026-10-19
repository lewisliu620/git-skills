"""
统一守护进程 - 采集器与飞书表格全自动联动
同时轮询两类任务：
1. 处理状态=待采集 → 自动执行1688采集
2. 处理状态=选品确认 且 AI处理状态=待处理 → 自动执行AI批量处理

运行方式：
  python daemon.py              # 前台运行，每5分钟轮询
  python daemon.py --interval 3 # 自定义间隔（分钟）
  python daemon.py --once       # 单次执行后退出
"""
import sys
import time
import json
import argparse
import traceback
from main import Collector
from ai_processor import AIProcessor, process_pending_products
from feishu_api import feishu, TABLE_IDS


class Daemon:
    """统一守护进程：采集 + AI处理 全自动联动"""

    def __init__(self, interval_minutes=5):
        self.interval = interval_minutes * 60
        self.collector = Collector()
        self.ai_processor = AIProcessor()
        self.cookie_alert_sent = False  # 避免重复发送cookie过期告警

    def run_once(self):
        """单次轮询：先处理待采集，再处理待AI"""
        print("=" * 60)
        print(f"轮询开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Cookie预检（W-04：仅提示不跳过——采集主通道是 tabbit 已登录浏览器，
        # 不依赖 requests cookie；requests 兜底失败时才需要更新cookie）
        cookie_ok, cookie_msg = self.collector.fetcher.check_cookie_valid()
        if not cookie_ok:
            print(f"\n⚠️  requests通道1688 Cookie可能已过期: {cookie_msg}")
            print("   （tabbit 浏览器通道不受影响，继续尝试采集；仅 requests 兜底会失败）")
            print("   可运行: python update_cookie.py 更新cookie（不影响本轮）")
            self.cookie_alert_sent = False
        else:
            self.cookie_alert_sent = False

        # Phase 1: 处理待采集（主通道 tabbit，cookie 失效仍可采）
        self._process_pending_collect()

        # Phase 2: 处理待AI处理
        self._process_pending_ai()

        print(f"轮询结束\n")

    def _send_cookie_alert(self, reason):
        """发送cookie过期飞书提醒"""
        try:
            import subprocess
            msg = f"⚠️ 1688 Cookie过期提醒\n原因: {reason}\n请运行: python update_cookie.py"
            subprocess.run([
                "lark-cli", "im", "+send",
                "--receive-id", "ou_1553e162fbb3505885745120dda34f0a",
                "--receive-id-type", "open_id",
                "--msg-type", "text",
                "--content", json.dumps({"text": msg}, ensure_ascii=False)
            ], capture_output=True, timeout=15)
            print("   已发送飞书提醒")
        except Exception as e:
            print(f"   飞书提醒发送失败: {e}")

    def _process_pending_collect(self):
        """扫描处理状态=待采集的记录，自动执行采集"""
        print("\n[Phase 1] 扫描待采集商品...")
        try:
            records = feishu.list_records(TABLE_IDS["product"], page_size=50)
            pending = []
            for r in records:
                fields = r.get("fields", {})
                status = self._get_select_value(fields.get("处理状态"))
                if status == "待采集":
                    pending.append(r)

            print(f"  找到 {len(pending)} 条待采集记录")

            for record in pending:
                record_id = record.get("record_id", "")
                fields = record.get("fields", {})
                url = fields.get("采购链接", "") or fields.get("1688链接", "")
                if isinstance(url, dict):
                    url = url.get("link", "") or url.get("text", "")
                if isinstance(url, list):
                    url = url[0] if url else ""

                if not url:
                    print(f"  记录 {record_id} 无1688链接，标记失败")
                    feishu.update_record(TABLE_IDS["product"], record_id, {
                        "处理状态": "处理失败",
                        "AI处理结果": "无1688链接，无法采集"
                    })
                    continue

                print(f"\n  采集: {url[:60]}...")
                # 标记为采集中
                feishu.update_record(TABLE_IDS["product"], record_id, {"处理状态": "素材处理中"})

                try:
                    product = self.collector.process_single(url, write_to_feishu=False)
                    if product:
                        # 采集成功，更新记录
                        update_fields = {
                            "中文标题": product.title,
                            "1688 OfferID": product.offer_id,
                            "采购价CNY": product.price,
                            "SKU数量": len(product.skus),
                            # 主表链接字段均为 text：传纯字符串
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
                        # W-03：新增字段（供应商/最小起订量/SKU规格明细，与 main.py 对齐）
                        if product.supplier_name:
                            update_fields["供应商"] = product.supplier_name
                        if product.min_order:
                            update_fields["最小起订量"] = product.min_order
                        if product.skus:
                            try:
                                update_fields["SKU规格明细"] = json.dumps(
                                    [{"规格": s.get("name", ""), "价格": s.get("price")} for s in product.skus],
                                    ensure_ascii=False)
                            except Exception:
                                pass
                        feishu.update_record(TABLE_IDS["product"], record_id, update_fields)
                        print(f"  采集完成: {product.title[:30]}")
                    else:
                        feishu.update_record(TABLE_IDS["product"], record_id, {
                            "处理状态": "规则淘汰",
                            "AI处理结果": "采集失败或未通过规则校验"
                        })
                        print(f"  采集失败或规则淘汰")
                except Exception as e:
                    feishu.update_record(TABLE_IDS["product"], record_id, {
                        "处理状态": "处理失败",
                        "AI处理结果": f"采集异常: {str(e)}"
                    })
                    print(f"  采集异常: {e}")
                    traceback.print_exc()

                time.sleep(2)  # 避免1688限流

        except Exception as e:
            print(f"  扫描待采集异常: {e}")
            traceback.print_exc()

    def _process_pending_ai(self):
        """扫描处理状态=选品确认 且 AI处理状态=待处理的记录"""
        print("\n[Phase 2] 扫描待AI处理商品...")
        try:
            ready, missing = self.ai_processor.is_ready()
            if not ready:
                print(f"  AI依赖未就绪，跳过: {', '.join(missing)}")
                return

            records = feishu.list_records(TABLE_IDS["product"], page_size=50)
            pending = []
            for r in records:
                fields = r.get("fields", {})
                status = self._get_select_value(fields.get("处理状态"))
                ai_status = self._get_select_value(fields.get("AI处理状态"), "待处理")
                if status == "选品确认" and ai_status == "待处理":
                    pending.append(r)

            print(f"  找到 {len(pending)} 条待AI处理记录")

            for record in pending[:5]:
                record_id = record.get("record_id", "")
                fields = record.get("fields", {})
                name = fields.get("中文标题", "未知")

                print(f"\n  AI处理: {name[:30]}...")
                feishu.update_record(TABLE_IDS["product"], record_id, {"AI处理状态": "处理中"})

                try:
                    success, result, error = self.ai_processor.process_product(record_id, fields)
                    self.ai_processor.update_feishu(record_id, success, result, error)
                    if success:
                        # AI处理完成后流转状态
                        feishu.update_record(TABLE_IDS["product"], record_id, {
                            "处理状态": "待翻译Listing"
                        })
                        print(f"  AI处理完成")
                    else:
                        print(f"  AI处理失败: {error}")
                except Exception as e:
                    feishu.update_record(TABLE_IDS["product"], record_id, {
                        "AI处理状态": "失败",
                        "AI处理结果": f"AI处理异常: {str(e)}"
                    })
                    print(f"  AI处理异常: {e}")
                    traceback.print_exc()

                time.sleep(1)

        except Exception as e:
            print(f"  扫描待AI处理异常: {e}")
            traceback.print_exc()

    @staticmethod
    def _get_select_value(field, default=""):
        """统一处理select字段的值（可能是列表、字符串、None）"""
        if field is None:
            return default
        if isinstance(field, list):
            return field[0] if field else default
        if isinstance(field, str):
            return field
        return default

    def run_forever(self):
        """守护进程模式：循环执行"""
        print(f"守护进程启动，每 {self.interval//60} 分钟轮询一次")
        print("按 Ctrl+C 停止\n")
        while True:
            try:
                self.run_once()
            except Exception as e:
                print(f"轮询异常: {e}")
                traceback.print_exc()
            print(f"等待 {self.interval//60} 分钟...\n")
            time.sleep(self.interval)


def main():
    parser = argparse.ArgumentParser(description="采集器+AI处理统一守护进程")
    parser.add_argument("--interval", type=int, default=5, help="轮询间隔（分钟），默认5")
    parser.add_argument("--once", action="store_true", help="单次执行后退出")
    args = parser.parse_args()

    daemon = Daemon(interval_minutes=args.interval)

    if args.once:
        daemon.run_once()
    else:
        try:
            daemon.run_forever()
        except KeyboardInterrupt:
            print("\n守护进程已停止")


if __name__ == "__main__":
    main()
