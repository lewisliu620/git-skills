# Skill 标准模板

> 所有新建的Skill都按这个模板写，不许改结构。

## 完整模板

```markdown
---
name: skill-name
description: |
  一句话定位。
  Use when:
  (1) 场景1；
  (2) 场景2；
  (3) 场景3。
  Input: 输入是什么。
  Output: 输出是什么。
  Do not: 禁止做什么。
---

# Skill 标题

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

- SKILL.md必须<500行
- 超过500行就把详细规则拆到references/里
- 每个reference文件顶部加目录

---

## 渐进式披露原则

三级加载系统：
1. **Metadata（name + description）** - 永远在上下文里（~100词）
2. **SKILL.md body** - 触发后加载（<5k词）
3. **Bundled resources** - 按需加载（无限）

---

## 禁止事项

不许加以下文件：
- README.md
- INSTALLATION_GUIDE.md
- QUICK_REFERENCE.md
- CHANGELOG.md
- 其他多余的说明文档
