#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_skillhub.py — 「更新 skillhub」同步脚本

以飞书多维表格「SkillHub 管理台 · Skill 清单」为发布控制台：
  - 勾选「上架 GitHub」的 skill → 上架（git add + commit）
  - 取消勾选的 skill           → 下架（git rm --cached + 移入 .gitignore 下架区，本地文件保留）

用法（在 skillhub 仓库根目录执行）：
  python3 scripts/sync_skillhub.py --base-token <BT> --table-id <TID>                # dry-run：输出同步计划
  python3 scripts/sync_skillhub.py --base-token <BT> --table-id <TID> --apply        # 执行 git add/rm + commit
  python3 scripts/sync_skillhub.py --base-token <BT> --table-id <TID> --apply --push # 执行并推送 GitHub
  python3 scripts/sync_skillhub.py --base-token <BT> --table-id <TID> --apply --write-back
                                                                    # 执行并回填表格（上次同步版本/时间）

设计约束：本脚本没有任何自动触发机制；只有用户显式说「更新」时才运行。
"""
import argparse
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IGNORE_MARKER = "# 下架区（由 sync_skillhub.py 维护，勿手改）"

GH_OWNER = "lewisliu620"
GH_REPO = "git-skills"


def sh(cmd, check=True):
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{r.stderr.strip()[:500]}")
    return r


def fetch_base_records(base_token, table_id):
    """拉取 Skill 清单全部记录（--format json：fields 名列表 + 行数组 + record_id_list）"""
    rows_all, ids_all, fields = [], [], []
    offset = 0
    while True:
        r = subprocess.run(
            ["lark-cli", "base", "+record-list", "--base-token", base_token,
             "--table-id", table_id, "--page-size", "200", "--format", "json",
             "--offset", str(offset), "--as", "user"],
            capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"读取表格失败: {r.stdout[:300]}")
        data = d.get("data", {})
        rows = data.get("data", [])
        if not fields:
            fields = data.get("fields") or []
        ids = data.get("record_id_list") or []
        if not isinstance(rows, list) or not rows:
            break
        rows_all.extend(rows)
        ids_all.extend(ids)
        if not data.get("has_more"):
            break
        offset += len(rows)
    result = []
    for row, rid in zip(rows_all, ids_all):
        if not isinstance(row, list):
            continue
        rec = {"record_id": rid}
        for name, val in zip(fields, row):
            rec[name] = val
        result.append(rec)
    return result


def get_field_ids(base_token, table_id):  # 保留：备用
    r = subprocess.run(["lark-cli", "base", "+field-list", "--base-token", base_token,
                        "--table-id", table_id, "--as", "user"],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    fields = d.get("data", {}).get("items") or d.get("data", {}).get("fields") or []
    out = {}
    for f in fields:
        out[f.get("field_name") or f.get("name")] = f.get("field_id") or f.get("id")
    return out


def cell_text(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
    return str(v)


def plan(base_token, table_id, local_names):
    """读表格 -> 对账本地 -> 返回计划"""
    records = fetch_base_records(base_token, table_id)
    plan_items = []
    for rec in records:
        def get(name):
            return rec.get(name)

        name = cell_text(get("Skill 名称")) or rec.get("record_id", "?")
        dirname = cell_text(get("本地目录"))
        checked = get("上架 GitHub")
        on = checked is True or checked in (True, "true", "True", 1)
        version = cell_text(get("版本")) or "v1.0.0"
        if version.startswith("v"):
            version = version[1:]
        note = cell_text(get("更新说明")) or "update"
        exists = bool(dirname) and dirname in local_names
        plan_items.append({
            "record_id": rec.get("record_id"),
            "name": name,
            "dir": dirname,
            "publish": bool(on),
            "exists": exists,
            "version": version,
            "note": note,
        })
    return plan_items


def git_tracked_dirs():
    r = sh(["git", "ls-files", "-z"], check=False)
    tracked = set()
    for line in r.stdout.split("\0"):
        if line:
            top = line.split("/", 1)[0]
            if top:
                tracked.add(top)
    return tracked


def read_gitignore():
    p = os.path.join(REPO_ROOT, ".gitignore")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return f.read().splitlines()


def write_gitignore(lines):
    with open(os.path.join(REPO_ROOT, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def add_to_gitignore(dirs_to_ignore):
    lines = read_gitignore()
    if IGNORE_MARKER not in lines:
        lines.append("")
        lines.append(IGNORE_MARKER)
    for d in dirs_to_ignore:
        entry = d + "/"
        if entry not in lines:
            lines.append(entry)
    write_gitignore(lines)


def remove_from_gitignore(dirs_to_unignore):
    lines = read_gitignore()
    keep = [l for l in lines if not any(l.rstrip("/") == d for d in dirs_to_unignore)]
    # 清理空的维护区
    if IGNORE_MARKER in keep:
        idx = keep.index(IGNORE_MARKER)
        # 删除标记行及紧跟的空行
        while idx + 1 < len(keep) and keep[idx + 1] == "":
            keep.pop(idx + 1)
        if idx + 1 >= len(keep):  # 标记后无内容则整段删除
            keep.pop(idx)
            if keep and keep[-1] == "":
                keep.pop()
    write_gitignore(keep)


def rebuild_manifest(published):
    """重建 manifest.json（只含上架 skill）"""
    skills = []
    for it in published:
        d = os.path.join(REPO_ROOT, it["dir"])
        skill_md = os.path.join(d, "SKILL.md")
        files = []
        total = 0
        if os.path.isdir(d):
            for fp, _, fns in os.walk(d):
                for fn in fns:
                    p = os.path.join(fp, fn)
                    rel = os.path.relpath(p, REPO_ROOT)
                    sz = os.path.getsize(p)
                    total += sz
                    files.append({"path": rel.replace(os.sep, "/"), "size": sz})
        skills.append({
            "name": it["name"],
            "dir": it["dir"],
            "version": it["version"],
            "note": it["note"],
            "fileCount": len(files),
            "sizeBytes": total,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    manifest = {
        "schema": "skillhub.manifest.v1",
        "repo": f"{GH_OWNER}/{GH_REPO}",
        "branch": "main",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skillCount": len(skills),
        "skills": skills,
    }
    with open(os.path.join(REPO_ROOT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def write_back(base_token, table_id, published, skipped):
    """回填表格：上次同步版本 / 上次同步时间 / 本地存在"""
    updates = {}
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for it in published + skipped:
        if not it["record_id"]:
            continue
        updates[it["record_id"]] = {
            "上次同步版本": it["version"],
            "上次同步时间": now,
            "本地存在": "存在" if it["exists"] else "缺失",
        }
    # 分批（≤200）
    items = list(updates.items())
    for i in range(0, len(items), 200):
        batch = dict(items[i:i + 200])
        r = subprocess.run(["lark-cli", "base", "+record-batch-update",
                            "--base-token", base_token, "--table-id", table_id,
                            "--json", json.dumps({"update_records": batch}, ensure_ascii=False),
                            "--as", "user"], capture_output=True, text=True)
        if r.returncode != 0 or '"ok": false' in r.stdout:
            print("回填失败:", r.stdout[:300], r.stderr[:300])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-token", required=True)
    ap.add_argument("--table-id", required=True)
    ap.add_argument("--apply", action="store_true", help="执行 git add/rm + commit")
    ap.add_argument("--push", action="store_true", help="推送 GitHub")
    ap.add_argument("--write-back", action="store_true", help="回填表格状态")
    args = ap.parse_args()

    local_names = set(d for d in os.listdir(REPO_ROOT)
                      if os.path.isdir(os.path.join(REPO_ROOT, d)) and not d.startswith("."))
    items = plan(args.base_token, args.table_id, local_names)
    tracked = git_tracked_dirs()

    to_add, to_remove, skipped = [], [], []
    for it in items:
        if it["publish"]:
            if it["exists"]:
                to_add.append(it)
            else:
                it["reason"] = "表格勾选但本地目录缺失"
                skipped.append(it)
        else:
            if it["dir"] in tracked:
                to_remove.append(it)

    print("=== SkillHub 同步计划 ===")
    print(f"上架: {len(to_add)} 个 | 下架: {len(to_remove)} 个 | 跳过: {len(skipped)} 个")
    for it in to_add:
        print(f"  + {it['name']} ({it['dir']}) v{it['version']}: {it['note']}")
    for it in to_remove:
        print(f"  - {it['name']} ({it['dir']}) 取消上架，本地保留")
    for it in skipped:
        print(f"  ! {it['name']}: {it.get('reason')}")

    if not args.apply:
        print("\n[dry-run] 未执行 git 操作。确认无误后加 --apply 执行。")
        return 0
    if not to_add and not to_remove:
        print("\n无变更，无需同步。")
        return 0

    if to_remove:
        remove_from_gitignore([it["dir"] for it in to_add])  # 上架的从下架区移除
        for it in to_remove:
            subprocess.run(["git", "rm", "-r", "--cached", "--quiet", it["dir"]],
                           cwd=REPO_ROOT, capture_output=True, text=True)
        add_to_gitignore([it["dir"] for it in to_remove])
        print("已下架:", ", ".join(it["dir"] for it in to_remove))

    if to_add:
        for it in to_add:
            subprocess.run(["git", "add", it["dir"]], cwd=REPO_ROOT, capture_output=True, text=True)
        remove_from_gitignore([it["dir"] for it in to_add])
        print("已暂存:", ", ".join(it["dir"] for it in to_add))

    # manifest
    rebuild_manifest(to_add)
    subprocess.run(["git", "add", "manifest.json", ".gitignore"], cwd=REPO_ROOT, capture_output=True, text=True)

    # commit message
    parts = []
    for it in to_add:
        parts.append(f"{it['name']} v{it['version']}: {it['note']}")
    for it in to_remove:
        parts.append(f"{it['name']}: 下架")
    msg = "update skillhub: " + "；".join(parts) if parts else "update skillhub: manifest 更新"
    sh(["git", "commit", "-m", msg])
    print("已提交:", msg)

    if args.push:
        sh(["git", "push", "origin", "main"])
        print("已推送 GitHub。")

    if args.write_back:
        write_back(args.base_token, args.table_id, to_add + to_remove, skipped)
        print("已回填表格：上次同步版本 / 时间 / 本地存在。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
