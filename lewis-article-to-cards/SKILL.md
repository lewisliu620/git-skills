---
name: lewis-article-to-cards
description: |
  刘易斯Lewis 图文卡片生产官。把飞书文章/课程/Skill文档转成小红书3:4组图卡片。
  触发：(1) 用户说"把这篇文章转成小红书图""文章转卡片""做多图组"；
  (2) 视频选题拍板后，同步要一组图文卡片发小红书/公众号；
  (3) 用户给了飞书文档链接要求"做成图片版"。
  输入：飞书文章链接或文本。输出：1080×1440 PNG组图（5-9张），落本地项目目录。
  视觉系统：Swiss International（AI工具/方法论默认）或 Editorial Magazine（故事/认知课）。
  成本：0积分（HTML渲染→Playwright截图，不调生图模型）。
  Do not: 不做Live Photo/实况照片；不做微信21:9封面对（需要时单独说）；不做PPT；不在卡片上放微信号/价格/二维码；不放日系治愈插画。
---

# Lewis Article to Cards（文章转多图卡片）

把飞书文章/课程/Skill文档转成小红书3:4组图。基于 guizang-social-card-skill 改造，裁剪为Lewis自己的图文生产线。

## 核心原则

1. **HTML渲染→截图，不调生图模型**。文字准确、版式可控、0积分。
2. **一套风格贯穿全组**，不混搭。
3. **每页一个观点**，不把整篇文章塞一张图。
4. **封面钩子决定停留**，其余页负责收藏。

## 工作流

### 1. 读取文章

用 `lark-doc` 读取飞书文档内容。如果用户直接给了文本则跳过。

### 2. 拆页规划

按 `references/content-planning.md` 的压缩梯：
- 一句话核心主张
- 读者划完能带走什么
- 拆成4-8个要点
- 每页只放一个要点

页数参考：
- 600-1000字 → 5-7张
- 1000-1800字 → 7-9张
- 更长 → 压到8-10张，其余放正文

页面角色要变化，不要每页都是"标题+卡片"：
- P1封面钩子
- P2痛点/问题
- P3核心方法/观点
- P4-P6清单/步骤/对比
- P7边界/注意事项
- P8 CTA（"更多内容关注@洞见AI漫步"或"需要Skill私信我"）

### 3. 选视觉系统

**默认 Swiss International**（AI工具、方法论、效率、产品介绍）：
- 配置：`<html data-accent="ikb">`（IKB蓝，AI/科技默认）
- 其他accent：`lemon-green`（新兴技术/健康）、`safety-orange`（风险/警告）
- 字体：Inter + Noto Sans SC + IBM Plex Mono
- 风格：网格对齐、细线分隔、一个高饱和强调色

**Editorial Magazine**（认知课、故事、个人观察、旅行生活）：
- 配置：`<html data-theme="indigo-porcelain">`（科技/研究）或 `ink-classic`（商业评论）
- 字体：衬线标题 + 无衬线正文
- 风格：留白、叙事、纸墨质感

**选色规则**（按内容类型，不固定教育色卡）：
- 工具实操/产品介绍 → Swiss IKB蓝
- 认知课/方法论 → Editorial Indigo Porcelain
- 风险/避坑/警告 → Swiss Safety Orange
- 新兴技术/未来感 → Swiss Lemon Green

### 4. 复制种子模板

```bash
# Swiss风
cp assets/template-swiss-card.html <任务目录>/index.html
# 或 Editorial风
cp assets/template-editorial-card.html <任务目录>/index.html
```

在 `<html>` 标签设置主题：
- Swiss: `<html data-accent="ikb">`
- Editorial: `<html data-theme="indigo-porcelain">`

在 `<!-- POSTERS_HERE -->` 处填入每页的 `<section class="poster xhs">` 块。

### 5. 渲染截图

用Playwright逐页截图：

```bash
python3 render_cards.py <任务目录>/index.html <输出目录>
```

脚本在本skill目录下 `render_cards.py`。它会：
1. 打开HTML
2. 找到所有 `.poster.xhs` 节点
3. 逐个截图为PNG（1080×1440）
4. 输出到 `output/card_01.png` ~ `card_08.png`

### 6. 交付

- 图片落本地项目目录
- 给用户看缩略图
- 说明：共N张，1080×1440，0积分
- 不在卡片上放微信号/价格/二维码
- 卡片底部统一放 `© 洞见AI漫步` 或 `刘易斯Lewis`

## 红线

1. 不调生图模型（0积分原则），需要截图时用真实产品截图
2. 不在卡片上放微信号、价格、二维码
3. 不放日系治愈插画
4. 全组视觉风格统一，不混搭Editorial和Swiss
5. 3:4卡片必须吃满画布（内容≥75%高度），不上下留白
6. 标题必须 >6字且有钩子
7. CTA口径："需要Skill？私信我" 或 "更多AI工作流关注@洞见AI漫步"
