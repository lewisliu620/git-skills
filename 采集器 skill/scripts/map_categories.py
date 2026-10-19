# -*- coding: utf-8 -*-
"""
#52 CLI：中文标题/1688类目 → Shopee叶子类目ID 语义映射（默认 dry-run，不写飞书）。

用法：
  # 1) 先用 lark-cli --as user 导出主表 record-list JSON（data.data + data.fields）：
  #    lark-cli base +record-list --base-token QsnYbrWpaa6lGfspgLpcihfvnpb \
  #      --table-id tblccRoRGPoD8Ulw --as user --format json --limit 200 > master.json
  python map_categories.py --input master.json            # dry-run，只打印建议
  python map_categories.py --input master.json --write    # 仅回写 decision=auto 且未填类目ID 的行

安全口径：
  · 只有 decision=auto（显式规则命中）才允许 --write 回写 Shopee类目ID；
  · candidates/none/blocked_forbidden 一律不写，交人工；
  · 已填 Shopee类目ID 的行跳过，不覆盖。
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.category_mapper import map_category, load_flat_items

BASE_TOKEN = "QsnYbrWpaa6lGfspgLpcihfvnpb"
MASTER_TABLE = "tblccRoRGPoD8Ulw"
FIELD_TITLE = "中文标题"
FIELD_CAT_HINT = "类目"
FIELD_SHOPEE_CAT = "Shopee类目ID"


def _cell_text(v):
    if v is None:
        return ""
    if isinstance(v, list):
        out = []
        for x in v:
            if isinstance(x, dict):
                out.append(x.get("text") or x.get("link") or "")
            else:
                out.append(str(x))
        return " ".join(t for t in out if t)
    if isinstance(v, dict):
        return v.get("text") or v.get("link") or ""
    return str(v)


def load_records(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().lstrip("﻿")
    j = json.loads(raw)
    data = j.get("data", j)
    fields = data["fields"]
    rows = data["data"]
    rec_ids = data.get("record_id_list") or []
    out = []
    for i, row in enumerate(rows):
        rec = {fields[ix]: row[ix] for ix in range(len(fields))}
        out.append({
            "record_id": rec_ids[i] if i < len(rec_ids) else None,
            "fields": rec,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="lark record-list 导出的 JSON")
    ap.add_argument("--write", action="store_true", help="仅回写 auto 项（默认 dry-run）")
    args = ap.parse_args()

    items = load_flat_items()
    if not items:
        print("[警告] 未载入类目字典，仅规则词典生效")
    records = load_records(args.input)

    buckets = {"auto": [], "candidates": [], "blocked_forbidden": [], "none": []}
    for rec in records:
        f = rec["fields"]
        title = _cell_text(f.get(FIELD_TITLE))
        hint = _cell_text(f.get(FIELD_CAT_HINT))
        existing = _cell_text(f.get(FIELD_SHOPEE_CAT))
        if existing.strip():
            continue
        r = map_category(title, hint, items=items)
        buckets[r["decision"]].append({"rec": rec["record_id"], "title": title, "hint": hint, "r": r})

    for dec, label in [("auto", "✅ 可自动回填"), ("candidates", "🟡 需人工选（只给候选）"),
                       ("blocked_forbidden", "⛔ 禁售/敏感，不给类目"), ("none", "⚪ 无匹配，人工指定")]:
        group = buckets[dec]
        print(f"\n===== {label}：{len(group)} 条 =====")
        for g in group:
            print(f"- [{g['rec']}] {g['title'][:34]}")
            for reason in g["r"]["reasons"]:
                print(f"    · {reason}")
            if g["r"]["category_id"]:
                print(f"    → {g['r']['category_id']}  {g['r']['path']}")
            for c in g["r"]["candidates"]:
                print(f"    候选 {c['id']} ({c['score']}) {c['path']}")

    if args.write:
        auto = buckets["auto"]
        if not auto:
            print("\n[--write] 无 auto 项，不回写。")
            return
        payload = {"update_records": {}}
        for g in auto:
            payload["update_records"][g["rec"]] = {FIELD_SHOPEE_CAT: g["r"]["category_id"]}
        out = os.path.join(os.path.dirname(os.path.abspath(args.input)), "category-write.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n[--write] 已生成回写体 {out}（{len(auto)} 条），请用 lark-cli +record-batch-update 提交并 record-get 回读。")
    else:
        print("\n[dry-run] 未写飞书。确认 auto 清单后加 --write 生成回写体。")


if __name__ == "__main__":
    main()
