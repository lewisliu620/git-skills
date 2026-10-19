# yrcq-* Skill 标准模板

> 所有yrcq-* Skill都按这个模板写，不许改结构。

## 完整模板

```markdown
---
name: yrcq-xxx
description: |
  「一人成军」xxx官，一句话定位。
  Use when:
  (1) 星主说"xxx""xxx"；
  (2) 星主说"xxx""xxx"；
  (3) 触发场景3。
  Input: 输入是什么。
  Output: 输出是什么。
  Do not: 禁止做什么。
---

# 一人成军 · xxx官

一句话定位。

## 快速开始

第一步 → 第二步 → 第三步 → 输出。

## 核心职责

1. 职责1
2. 职责2
3. 职责3

## 工作流程/详细规则

（这里写具体怎么做，分步骤/分情况/分类型）

## 语气

（可选）像什么风格。

## 红线

1. 红线1
2. 红线2
3. 红线3
```

---

## 各字段说明

### frontmatter description 格式

必须按这个顺序写：
1. 一句话定位
2. Use when：3-5个触发场景
3. Input：输入是什么
4. Output：输出是什么
5. Do not：禁止做什么

### SKILL.md 结构顺序

1. 标题
2. 一句话定位
3. 快速开始
4. 核心职责
5. 工作流程/详细规则
6. 语气（可选）
7. 红线

### 行数限制

- SKILL.md必须<200行
- 超过200行就把详细规则拆到references/里
- 每个reference文件顶部加目录

---

## 已有的8个标杆

| Skill | 角色 | 行数 |
|-------|------|------|
| yrcq-pmo | 总协调官 | ~100行 |
| yrcq-topic-scout | 选题情报官 | ~70行 |
| yrcq-writer | 内容生产官 | ~80行 |
| yrcq-course-pm | 大课项目经理 | ~90行 |
| yrcq-health-monitor | 健康度监控官 | ~60行 |
| yrcq-material | 物料生成官 | ~75行 |
| yrcq-support | 客服小助手 | ~55行 |
| yrcq-content-visual | 配图配色官 | ~80行 |
