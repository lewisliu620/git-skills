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

## 手动更新（核心约定）

**任何同步动作都只在你显式说「更新」时发生，本仓库没有任何自动同步机制（无 webhook、无定时任务）。**

### 一次完整更新（在任意终端执行）

```
1. 读多维表格「SkillHub 管理台」：
   · 勾选「上架 GitHub」的 skill → 上架（git add + commit）
   · 取消勾选的 skill → 下架（git rm，本地文件保留）
   · 每条记录的「版本」「更新说明」写进 commit message
2. git pull origin main          # 先拉取其他终端的最新改动
3. git add <上架的目录> / git rm <下架的目录>
4. git commit -m "publish <name> v1.x.x: <更新说明>"
5. git push origin main          # 推送到 GitHub
6. 回填表格：上次同步版本 / 上次同步时间
```

其他终端下次说「更新」时 `git pull` 即可获得/移除对应 skill。

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
