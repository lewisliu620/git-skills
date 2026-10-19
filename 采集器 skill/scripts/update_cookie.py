"""
1688 Cookie自动更新工具
使用playwright启动浏览器，用户登录后自动保存cookie到1688_session.json

运行方式：
  python update_cookie.py
  1. 脚本自动打开浏览器访问1688
  2. 用户在浏览器中扫码或账号密码登录
  3. 登录成功后脚本自动保存cookie并关闭浏览器
  4. 采集器下次运行时自动使用新cookie
"""
import json
import time
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("错误：未安装playwright")
    print("请运行: pip install playwright && playwright install chromium")
    sys.exit(1)

SESSION_FILE = Path(__file__).parent / "1688_session.json"
LOGIN_URL = "https://login.1688.com/"
HOME_URL = "https://www.1688.com/"


def save_cookies(context):
    """从浏览器context提取cookie并保存"""
    cookies = context.cookies()
    cookie_dict = {}
    for c in cookies:
        cookie_dict[c["name"]] = c["value"]

    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(cookie_dict, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Cookie已保存，共 {len(cookie_dict)} 个")
    print(f"   文件: {SESSION_FILE}")

    # 检查关键登录态cookie
    login_cookies = ["__cn_logon__", "cookie2", "t", "_tb_token_", "unb"]
    found = [k for k in login_cookies if k in cookie_dict]
    if "__cn_logon__" in cookie_dict and cookie_dict["__cn_logon__"] == "true":
        print("   登录态: ✅ 已登录")
    else:
        print("   登录态: ⚠️  未检测到明确登录态，请确认是否登录成功")
    print(f"   关键cookie: {', '.join(found)}")

    return len(cookie_dict)


def main():
    print("=" * 60)
    print("1688 Cookie 更新工具")
    print("=" * 60)
    print("\n即将打开浏览器，请在浏览器中完成1688登录...")
    print("登录成功后脚本会自动检测并保存cookie\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 访问1688首页
        page.goto(HOME_URL, wait_until="domcontentloaded")
        print("浏览器已打开，请在页面中登录1688账号...")
        print("（登录成功后请稍候，脚本会自动检测）\n")

        # 等待登录成功：检测 __cn_logon__=true cookie 或跳转到已登录状态
        max_wait = 300  # 最多等5分钟
        start = time.time()
        logged_in = False

        while time.time() - start < max_wait:
            cookies = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}

            # 检测登录态
            if cookie_dict.get("__cn_logon__") == "true" or cookie_dict.get("unb"):
                logged_in = True
                print("✅ 检测到登录成功！")
                break

            # 检查页面是否已登录（URL变化或页面元素）
            try:
                if "login.1688.com" not in page.url and page.url != "about:blank":
                    # 检查是否有用户昵称元素
                    if page.locator(".site-name, .user-name, [class*='nick']").count() > 0:
                        logged_in = True
                        print("✅ 检测到登录成功！")
                        break
            except:
                pass

            time.sleep(3)
            elapsed = int(time.time() - start)
            if elapsed % 15 == 0:
                print(f"   等待登录中... ({elapsed}s)")

        if not logged_in:
            print("\n⚠️  等待超时，未检测到登录态")
            print("仍会保存当前cookie，但可能未登录")

        # 等待几秒确保cookie完整
        time.sleep(3)

        # 保存cookie
        save_cookies(context)

        browser.close()

    print("\n" + "=" * 60)
    print("Cookie更新完成！可以重新运行采集器了")
    print("=" * 60)


if __name__ == "__main__":
    main()
