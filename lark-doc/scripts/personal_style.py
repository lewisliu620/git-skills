#!/usr/bin/env python3
"""捕获 writing-references 输出，仅依赖 Python 3 标准库。

从用户可写任务目录运行：python3 "/绝对路径/lark-doc/scripts/personal_style.py" --limit 12000
LIMIT 按 Python 字符数计；>= LIMIT 时保存至当前工作目录下的相对目录。
LIMIT 是原始输出的落盘触发阈值，不保证摘要总长度小于此值。
原始文件保存所捕获的 stdout/stderr 合并流的原始字节，不重排 JSON。
multi_modal 如果只是外部工具的包装，不会出现在子进程输出中；两种格式均支持。
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

LIMIT = 70000  # 暂定值，按实际沙箱限制修改，或传 --limit。
CONTENT_LIMIT = 1000
CLI_ARGS = ["docs", "+script", "--command", "writing-references"]
DOCUMENT_STRUCT = {
    "content": "string", "content_format": "string",
    "content_truncated": "boolean", "document_id": "string",
    "title": "string", "url": "string",
}
CLI_RESULT_STRUCT = {
    "ok": "boolean", "identity": "string",
    "data": {
        "edited_documents": [DOCUMENT_STRUCT],
        "recent_documents": [DOCUMENT_STRUCT],
        "template_configured": "boolean",
        "template_documents": [DOCUMENT_STRUCT],
    },
    "meta": {"count": "number"},
}


class CliNotFoundError(RuntimeError):
    """lark-cli 不在 PATH 中。"""


def execute_cli():
    cli_path = shutil.which("lark-cli")
    if cli_path is None:
        raise CliNotFoundError("未找到 lark-cli，请确认已安装并加入 PATH。")
    # 直接调用可执行程序，无需额外启动 Bash/PowerShell。
    # 在 Python 内捕获，避免原始大输出先进入外部工具的显示/截断环节。
    return subprocess.run(
        [cli_path, *CLI_ARGS],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def decode_json(text):
    text = text.lstrip("\ufeff \t\r\n")
    value, end = json.JSONDecoder().raw_decode(text)
    suffix = text[end:].strip()
    if suffix and not re.fullmatch(r"Exit code -?\d+", suffix):
        raise ValueError("JSON 后存在无法识别的内容")
    if not isinstance(value, dict):
        raise ValueError("返回结果不是 JSON 对象")
    return value


def parse_result(cli_raw_result):
    result = decode_json(cli_raw_result)
    if result.get("type") != "multi_modal":
        return result, False
    candidates = []
    for part in result.get("multi_modal", []):
        try:
            content = part["ContentType"]["Text"]["content"]
            candidate = decode_json(content)
            if "ok" in candidate or "data" in candidate:
                candidates.append(candidate)
        except (KeyError, TypeError, ValueError):
            continue
    if len(candidates) != 1:
        raise ValueError("multi_modal 中未找到唯一的 CLI JSON 结果")
    return candidates[0], True


def summarize(result):
    if result.get("ok") is False:
        raise ValueError("CLI 返回 ok=false，请查看原始文件中的 error")
    data = result.get("data")
    if not isinstance(data, dict):
        raise ValueError("缺少 data 对象")
    cli_show_result = {}
    if "template_configured" in data:
        cli_show_result["template_configured"] = data["template_configured"]
    document_keys = ("template_documents", "edited_documents", "recent_documents")
    if not any(key in data for key in document_keys):
        raise ValueError("data 中缺少文档列表")
    for key in document_keys:
        if key not in data:
            continue
        documents = data[key]
        if not isinstance(documents, list):
            raise ValueError(f"data.{key} 不是列表")
        cli_show_result[key] = []
        for doc in documents:
            if not isinstance(doc, dict) or not all(
                isinstance(doc[field], str)
                for field in ("content", "title", "document_id", "url", "content_format")
                if field in doc
            ) or ("content_truncated" in doc and not isinstance(doc["content_truncated"], bool)):
                raise ValueError(f"data.{key} 中存在类型异常的文档")
            summary = {
                field: doc[field]
                for field in ("title", "document_id", "url", "content_format", "content_truncated")
                if field in doc
            }
            if "content" in doc:
                content = doc["content"]
                summary["show_content_truncated"] = len(content) > CONTENT_LIMIT * 2 + 12
                if summary["show_content_truncated"]:
                    summary["show_content"] = content[:CONTENT_LIMIT] + "...[omit]..." + content[-CONTENT_LIMIT:]
                else:
                    summary["show_content"] = content
            cli_show_result[key].append(summary)
    return cli_show_result


def render_output(raw_bytes, limit, output_dir):
    cli_raw_result = raw_bytes.decode("utf-8", errors="replace")
    if len(cli_raw_result) < limit:
        return raw_bytes  # 不添加换行，不改动原始字节。

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now().strftime("%Y%m%d_%H%M%S_%f_")
    # 随机后缀防止并发覆盖；不自动删除，以便后续按需读取。
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=output_dir, prefix=prefix, suffix=".txt", delete=False
    ) as file:
        file.write(raw_bytes)
        save_path = Path(os.path.relpath(file.name, Path.cwd())).as_posix()

    header = f"返回的内容过大，原始文件保存至 {save_path}，"
    try:
        result, wrapped = parse_result(cli_raw_result)
        cli_show_result = summarize(result)
    except (ValueError, TypeError, AttributeError) as exc:
        # 原始内容已经保存。不要把错误结果误报为空文档列表。
        return (header + f"无法生成简略内容：{exc}。\n"
                "请按需读取原始文件。\n").encode("utf-8")

    text = header + "以下是简略的内容:\n"
    text += json.dumps(cli_show_result, ensure_ascii=False, indent=2)
    text += ("。\nshow_content_truncated 表示本脚本是否省略正文，"
             "content_truncated 保留接口原值；无 content_truncated 不代表全文完整。"
             "缺少 show_content 表示接口未返回正文。\n"
             "你可以按需获取必要的原始内容。以下为字段结构示意，"
             "各文档列表和字段是否存在及其值以原始结果为准：")
    text += json.dumps(CLI_RESULT_STRUCT, ensure_ascii=False, indent=2)
    if wrapped:
        text += ("\n注意：原始文件实际保留 multi_modal 外层包装；上述结构位于"
                 " multi_modal[i].ContentType.Text.content 的 JSON 字符串中，"
                 "末尾可能带有 Exit code N。")
    return (text + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=LIMIT, help="长度阈值（字符数）")
    parser.add_argument("--output-dir", type=Path, default=Path("writing_references_tmp"),
                        help="相对于运行时当前工作目录的保存目录")
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit 必须大于 0")
    if args.output_dir.is_absolute():
        parser.error("--output-dir 必须为相对路径")
    try:
        completed = execute_cli()
        output = render_output(completed.stdout, args.limit, args.output_dir)
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return completed.returncode  # 保留 CLI 的退出码。
    except CliNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    except (OSError, RuntimeError) as exc:
        print(f"执行或保存失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
