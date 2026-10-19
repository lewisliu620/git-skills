---
name: yrcq-skill-creator
description: |
  「一人成军」专用Skill创建器。用来新建或升级yrcq-*系列Agent Skill，统一格式规范。
  Use when:
  (1) 星主要新建一个yrcq-* Agent（如yrcq-xxx）；
  (2) 星主要把某个yrcq-* Skill升级成统一格式；
  (3) 星主说"建个新Agent""新建个skill""升级一下skill格式"。
  Input: 新Agent的角色、职责、红线。
  Output: 符合统一规范的yrcq-* Skill（SKILL.md + 按需references）。
  Do not: 不随便加多余文件；不把所有内容堆SKILL.md里；不混用不同格式。
---

# 一人成军 · Skill创建器

新建或升级yrcq-*系列Skill，统一格式规范。

## 快速开始

定角色 → 按模板填 → 过检查清单 → 交付。

## 创建步骤

### Step 1：定角色和职责
先想清楚：
- 这个Agent叫什么名字（yrcq-xxx）
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
- [ ] SKILL.md <200行（超过就拆references）

### Step 4：按需加references
如果SKILL.md超过200行，把详细规则拆到references里：
- 详细规则、模板、示例 → references/xxx.md
- 每个reference文件顶部加目录
- SKILL.md里引用references，说明什么时候读

## 标杆参考

现有的8个yrcq-* Skill都是按这个标准写的：
- yrcq-pmo / yrcq-topic-scout / yrcq-writer
- yrcq-course-pm / yrcq-health-monitor
- yrcq-material / yrcq-support / yrcq-content-visual

## 红线

- 所有yrcq-* Skill格式必须统一，不许各写各的
- frontmatter必须只有name和description，不加其他字段
- SKILL.md必须<200行，超过就拆references
- 不许加README/CHANGELOG/INSTALL等多余文件
- 所有yrcq-* Skill都要符合harness规范
