"""
飞书轮询脚本 - 定时查找选品确认后的商品，触发AI批量处理
运行方式：
  python poll_feishu.py              # 单次执行
  python poll_feishu.py --daemon     # 守护进程，每5分钟轮询一次
  python poll_feishu.py --interval 10  # 自定义间隔（分钟）
"""
import sys
import time
import argparse
from ai_processor import process_pending_products
from feishu_api import feishu, TABLE_IDS


def run_once():
    """单次执行：查找待处理商品并执行AI处理"""
    print("=" * 50)
    print(f"轮询开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    count = process_pending_products(limit=5)
    print(f"轮询结束，处理了 {count} 条商品\n")
    return count


def run_daemon(interval_minutes=5):
    """守护进程：定时轮询"""
    print(f"启动守护模式，每 {interval_minutes} 分钟轮询一次")
    print("按 Ctrl+C 停止\n")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"轮询异常: {e}")
        print(f"等待 {interval_minutes} 分钟...\n")
        time.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(description="飞书轮询 - 选品确认后触发AI处理")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式")
    parser.add_argument("--interval", type=int, default=5, help="轮询间隔（分钟），默认5")
    args = parser.parse_args()

    if args.daemon:
        run_daemon(args.interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
