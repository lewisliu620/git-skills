#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号草稿箱推送脚本
完整流程：获取access_token → 上传封面永久素材 → 新建草稿
支持命令行参数和JSON配置文件两种方式。
"""

import argparse
import json
import os
import re
import sys
import requests
from pathlib import Path

# ============ 配置 ============
TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
UPLOAD_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
UPLOAD_CONTENT_IMG_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

# 配置文件默认路径（用户主目录下）
DEFAULT_CONFIG_PATH = Path.home() / ".wechat_gzh_config.json"


def load_config(config_path: str = None) -> dict:
    """从配置文件读取 appid 和 secret"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_access_token(appid: str, secret: str) -> str:
    """获取全局access_token，有效期7200秒"""
    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    }
    resp = requests.get(TOKEN_URL, params=params, timeout=10)
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"获取access_token失败: {data}")
    return data["access_token"]


def upload_cover_image(access_token: str, image_path: str) -> str:
    """
    上传封面图为永久素材，返回 thumb_media_id
    封面必须是永久素材，不能用临时素材。
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"封面图不存在: {image_path}")

    url = f"{UPLOAD_MATERIAL_URL}?access_token={access_token}&type=image"
    with open(path, "rb") as f:
        files = {"media": (path.name, f, "image/jpeg")}
        resp = requests.post(url, files=files, timeout=30)
    data = resp.json()
    if "media_id" not in data:
        raise RuntimeError(f"上传封面图失败: {data}")
    return data["media_id"]


def upload_content_image(access_token: str, image_path: str) -> str:
    """
    上传正文图片，返回可在正文中使用的URL。
    注意：正文中的图片URL必须来自此接口，外部URL会被过滤。
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"正文图片不存在: {image_path}")

    url = f"{UPLOAD_CONTENT_IMG_URL}?access_token={access_token}"
    with open(path, "rb") as f:
        files = {"media": (path.name, f, "image/jpeg")}
        resp = requests.post(url, files=files, timeout=30)
    data = resp.json()
    if "url" not in data:
        raise RuntimeError(f"上传正文图片失败: {data}")
    return data["url"]


def replace_local_images_in_content(access_token: str, content_html: str, base_dir: str = ".") -> str:
    """
    扫描正文中的 <img src="本地路径">，自动上传并替换为微信可用的URL。
    支持相对路径和绝对路径。
    """
    # 匹配 <img src="..."> 标签
    img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)

    def replace_match(match):
        src = match.group(1)
        # 已经是http/https开头的远程URL，跳过
        if src.startswith(("http://", "https://", "//")):
            return match.group(0)
        # 解析本地文件路径
        local_path = Path(base_dir) / src
        if not local_path.exists():
            print(f"[警告] 正文图片不存在，跳过: {local_path}", file=sys.stderr)
            return match.group(0)
        # 上传并替换URL
        try:
            wx_url = upload_content_image(access_token, str(local_path))
            print(f"[图片] 已上传: {local_path.name} -> {wx_url[:60]}...", file=sys.stderr)
            return match.group(0).replace(src, wx_url)
        except Exception as e:
            print(f"[警告] 图片上传失败 {local_path}: {e}", file=sys.stderr)
            return match.group(0)

    return img_pattern.sub(replace_match, content_html)


def push_draft(
    access_token: str,
    title: str,
    content: str,
    thumb_media_id: str,
    author: str = "",
    digest: str = "",
    content_source_url: str = "",
    need_open_comment: int = 0,
    only_fans_can_comment: int = 0,
) -> str:
    """
    新建图文草稿，返回 media_id
    """
    article = {
        "article_type": "news",
        "title": title,
        "author": author,
        "digest": digest,
        "content": content,
        "content_source_url": content_source_url,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": need_open_comment,
        "only_fans_can_comment": only_fans_can_comment,
    }

    payload = {"articles": [article]}
    url = f"{DRAFT_ADD_URL}?access_token={access_token}"
    # 强制 UTF-8 原始中文发送，不用 ensure_ascii=True 的 \uXXXX 转义
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    resp = requests.post(url, data=body, headers=headers, timeout=30)
    data = resp.json()
    if "media_id" not in data:
        raise RuntimeError(f"新建草稿失败: {data}")
    return data["media_id"]


def read_text_file(file_path: str) -> str:
    """读取文本文件（支持UTF-8）"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="微信公众号草稿箱推送工具")
    parser.add_argument("--appid", help="公众号AppID（不填则读配置文件）")
    parser.add_argument("--secret", help="公众号AppSecret（不填则读配置文件）")
    parser.add_argument("--config", help="配置文件路径（默认 ~/.wechat_gzh_config.json）")
    parser.add_argument("--title", required=True, help="文章标题（不超过32字）")
    parser.add_argument("--author", default="刘易斯Lewis", help="作者名（默认：刘易斯Lewis）")
    parser.add_argument("--digest", default="", help="摘要（不超过120字，留空自动取正文前54字）")
    parser.add_argument("--content", help="正文HTML字符串（与--content-file二选一）")
    parser.add_argument("--content-file", help="正文HTML文件路径（与--content二选一）")
    parser.add_argument("--cover", required=True, help="封面图本地路径（jpg/png）")
    parser.add_argument("--content-source-url", default="", help="阅读原文跳转链接")
    parser.add_argument("--base-dir", default=".", help="正文图片相对路径的基准目录（默认当前目录）")
    parser.add_argument("--open-comment", type=int, default=0, choices=[0, 1], help="是否打开评论 0/1")
    parser.add_argument("--fans-only", type=int, default=0, choices=[0, 1], help="是否仅粉丝可评论 0/1")
    args = parser.parse_args()

    # 1. 读取配置
    config = load_config(args.config)
    appid = args.appid or config.get("appid")
    secret = args.secret or config.get("secret")
    if not appid or not secret:
        print("错误：缺少appid或secret，请通过命令行参数或配置文件提供", file=sys.stderr)
        print(f"配置文件默认位置: {DEFAULT_CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    # 2. 读取正文
    if args.content_file:
        content = read_text_file(args.content_file)
    elif args.content:
        content = args.content
    else:
        print("错误：必须通过 --content 或 --content-file 提供正文", file=sys.stderr)
        sys.exit(1)

    # 3. 流程开始
    print("=" * 50, file=sys.stderr)
    print(f"开始推送草稿: {args.title}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    # Step 1: 获取access_token
    print("[1/4] 获取access_token...", file=sys.stderr)
    access_token = get_access_token(appid, secret)
    print("      ✓ 获取成功", file=sys.stderr)

    # Step 2: 上传封面图
    print(f"[2/4] 上传封面图: {args.cover}...", file=sys.stderr)
    thumb_media_id = upload_cover_image(access_token, args.cover)
    print(f"      ✓ media_id: {thumb_media_id}", file=sys.stderr)

    # Step 3: 替换正文中的本地图片
    print("[3/4] 处理正文图片...", file=sys.stderr)
    content = replace_local_images_in_content(access_token, content, args.base_dir)
    print("      ✓ 正文处理完成", file=sys.stderr)

    # Step 4: 新建草稿
    print("[4/4] 创建草稿...", file=sys.stderr)
    media_id = push_draft(
        access_token=access_token,
        title=args.title,
        content=content,
        thumb_media_id=thumb_media_id,
        author=args.author,
        digest=args.digest,
        content_source_url=args.content_source_url,
        need_open_comment=args.open_comment,
        only_fans_can_comment=args.fans_only,
    )
    print(f"      ✓ 草稿创建成功!", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    # 输出结果（JSON，方便上层调用）
    result = {
        "success": True,
        "media_id": media_id,
        "title": args.title,
        "message": "草稿已推送到公众号草稿箱。请登录后台完成：1）勾选「原创声明」；2）选择合集「豆包工作」；3）预览排版后群发",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
