# git-skills · 个人云端 SkillHub

个人 Skill 集中管理仓库：**GitHub 私有仓库是唯一事实源**，多维表格是发布控制台（勾选哪些 skill 上架、版本与更新说明都在表格管理），各电脑终端通过 Git 同步。

## 仓库结构

```
skillhub/
├── manifest.json        # skill 清单（自动生成：名称/描述/版本/文件数/体积）
├── README.md            # 本文件
├── .gitignore
└── <skill-name>/        # 每个 skill 一个目录（SKILL.md + assets + scripts）
```

## 一次完整更新（脚本驱动，任意终端执行）

更新时（只在你显式说「更新」时执行，本仓库无任何自动同步机制）：

```
1. 在飞书多维表格「SkillHub 管理台 · Skill 清单」中：
   · 勾选「上架 GitHub」的 skill → 该 skill 将上架
   · 取消勾选            → 该 skill 将下架（本地文件保留，可随时重新勾选上架）
   · 维护每条记录的「版本」「更新说明」→ 会写进 commit message
2. git pull origin main                          # 先拉取其他终端的改动
3. python3 scripts/sync_skillhub.py \
     --base-token <BT> --table-id <TID> --apply  # 读表格 → 上架/下架 → commit
4. python3 scripts/sync_skillhub.py \
     --base-token <BT> --table-id <TID> --apply --push   # 推送 GitHub
   （可选 --write-back 一并回填表格「上次同步版本/时间/本地存在」）
```

- 不加 `--apply` 时是 dry-run，只打印计划不执行。
- 下架只做 `git rm --cached` 并把目录写进 `.gitignore` 下架区，**本地文件始终保留**；重新勾选后下一次更新自动重新上架。
- 其他终端下次说「更新」时 `git pull` 即可获得/移除对应 skill。

## 使用

在任何一台电脑上：

```
git clone https://github.com/lewisliu620/git-skills.git skillhub
# 需要让豆包实际使用某个 skill 时，把它复制/链接到本机技能目录
```

## 安全

- 仓库必须保持 **private**。
- 禁止把真实密钥写进 skill 文件；敏感值走环境变量。
- 上架前可对新增/变更文件做一次密钥扫描（GitHub PAT / AWS / OpenAI / 私钥等格式）。
