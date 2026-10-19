---
name: skill-creator
description: |
  通用Skill创建器。用来新建或升级符合harness规范的Skill，统一格式标准。
  Use when:
  (1) 用户要新建一个Skill；
  (2) 用户要升级/重构现有Skill；
  (3) 用户说"建个skill""新建个agent""写个技能""升级一下skill格式"。
  Input: 新Skill的角色、职责、使用场景。
  Output: 符合harness规范的Skill（SKILL.md + 按需references/scripts/assets）。
  Do not: 不随便加多余文件；不把所有内容堆SKILL.md里；不混用不同格式。
---

# 通用 Skill 创建器

新建或升级符合harness规范的Skill。

## 快速开始

定角色 → 按模板写 → 过检查清单 → 交付。

## 核心原则

1. **简洁优先**：AI已经很聪明了，只加它不知道的信息
2. **渐进式披露**：SKILL.md核心，详细内容拆references
3. **统一格式**：所有Skill按同一个模板写，不许各写各的

## 创建步骤

### Step 1：定角色和职责
先想清楚：
- Skill叫什么名字
- 核心职责是什么（3-5条）
- 什么时候触发（Use when）
- 输入输出是什么
- 红线有哪些

### Step 2：按模板写SKILL.md
严格按 `references/skill-template.md` 的模板写，不要自己发挥结构。

### Step 3：过检查清单
逐项检查：
- [ ] frontmatter有name + description
- [ ] description有Use when / Input / Output / Do not
- [ ] 开头有"快速开始"
- [ ] 结构统一：快速开始→核心职责→工作流程→红线
- [ ] 用祈使句
- [ ] SKILL.md <500行（超过就拆references）

### Step 4：按需加references/scripts/assets
- 详细规则、模板、示例 → references/xxx.md
- 重复执行的代码 → scripts/xxx.py
- 输出要用的模板/图片 → assets/xxx
- 每个reference文件顶部加目录

## Skill结构标准

```
skill-name/
├── SKILL.md                    # 核心：触发条件 + 快速开始 + 工作流程 + 红线
├── references/                 # 详细文档（按需）
│   └── xxx.md
├── scripts/                    # 可执行脚本（按需）
│   └── xxx.py
└── assets/                     # 输出资源（按需）
    └── xxx
```

## 红线

- 所有Skill格式必须统一，不许各写各的
- frontmatter必须只有name和description，不加其他字段
- SKILL.md必须<500行，超过就拆references
- 不许加README/CHANGELOG/INSTALL等多余文件
- 创建位置默认在 `workspace/.user_skills/` 下
