---
name: sticker-toolchain
description: 表情包/贴纸（微信表情开放平台投稿）全链路制作工具链：从核心 IP 出图、串行延展整套静态表情、本地脚本去底/白描边/叠字/七类规格导出/程序校验/zip 打包、归档方案文档第 8 章，到浏览器协助投稿微信表情开放平台（扫码登录 + 用户最终提交）。使用场景：用户要做表情包、贴纸、微信表情、emoji sticker、表情专辑投稿变现、动态 GIF 表情（视频转 GIF）、或询问表情包工具链/制作流程/规格合规。
---

# Sticker Toolchain（表情包制作全链路）

## 总览

按 S0–S7 完成一整套微信表情包：出图交给豆包生图（image_gen/image_edit），规格交给本地脚本（Pillow 去底/描边/叠字/导出/校验/打包），投稿走浏览器协助（用户扫码登录、用户最终点提交）。

```
S0 核心 IP → S1-S2 串行延展 N 枚 → S3 背景色采样 → S4 后处理+校验+打包 → S5 交付 → S6 归档文档 → S7 发布微信平台
```

## 流程决策

1. 确认表情类型与用途：**静态表情**（主通道）走下方全流程；**动态 GIF 版**在 S4 前先按 `doubao-creative-video` 澄清动态范围（全部/关键 N 枚/先试做），视频生成后 ffmpeg 本地转 GIF；用户叫停则保持静态。
2. 澄清门禁（`interaction.ask`，一次问完 1–4 项）：表情类型、用途（投稿变现/自用）、首发角色/主题、枚数（16 或 24）。
3. 交付深度：用户要"方案/调研"时先产方案文档（lark-doc）；要"搭建/制作"时直接执行。

## S0 核心 IP（两种模式）

**模式 A：从零设计**（无现成角色 IP）
- 读取 `doubao-creative-design` 及 `references/prompts.md` 的 S0 模板，生成 1 张核心角色像。
- **角色锚点**要写进 prompt：体型/五官/服装/道具/风格/配色，后续所有延展只变姿势表情道具，身份锚点不变。
- 结果必须单独 `present_files` 交付后，才能进入 S1。

**模式 B：复用现有角色 IP（推荐，零角色设计成本）**
- 用户已有系列角色资产（如《米米森林奇遇记》资产包：角色卡 + 锚点图）时，**禁止从零重画**：
  1. 读资产包角色卡（画面描述**逐字复用**，不自行改写）；
  2. 定位对应锚点图（如 `ep1_images\core_anchor_米米跳跳.jpg`），FileBatchUpload 上传取稳定 URL；
  3. 该 URL 即核心 IP，直接进入 S1 延展（`image_edit` 参考图 = 该 URL），无需再生成 S0 图。
- 身份锚点不变：体型/五官/服装/道具/画风逐字复用角色卡；延展只变姿势/表情/道具。
- 表情清单模板（16 枚/辑）与规格红线见资产包 V1.2 第 11.6 节；首发建议主角 1 套试水，再按角色补齐。

## S1–S2 串行延展（image_edit，禁止 image_gen 重画）

- **必须串行**：每次基于核心 IP 用 `image_edit`（参考图=core-ip），一张成功交付后再出下一张；并行会互相覆盖。
- 每张 prompt 写清保留项（角色身份/构图）与修改项（姿势/表情/道具），中文待渲染文字不用模型渲染（见坑 1）。
- 文案表：一次定稿 N 条含义无重复，写入 `process.py` 的 `CAPTIONS`。

## S3 背景色采样（scripts/probe.py）

- 生成图通常带浅色背景（实测浅灰蓝 ≈(237,236,241)）；先运行 probe.py 采样角点背景色与到纯白距离，再定 T0/T1。

## S4 后处理（scripts/process.py）

1. 编辑脚本头部 CONFIG：`RAW_DIR`（原始生成图目录，命名 `01.png`…）、`CAPTIONS`（key→含义）、`ALBUM_NAME`、字体路径。
2. 运行 `python process.py`。内置已验证算法：角点采样背景色 → 按距离做透明斜坡去底 → 2px 白描边（alpha 膨胀 MaxFilter）→ 白字黑描边叠字 → 导出 7 类规格 → 程序校验 → 4×4 预览拼图 → zip 打包。
3. 规格与校验口径见 `references/specs.md`；`校验报告.txt` 必须 0 错误。

## S5 交付

- `present_files` 交付：投稿包 zip、预览拼图、校验报告（逐个单独交付）。

## S6 归档方案文档（lark-doc）

- 按 lark-doc 流程 fetch 最新 revision → 在方案文档第 8 章《搭建记录》追加/更新：角色圣经、文案、规格校验结论、产物与脚本；发布完成后更新「待办」并新增「发布记录」小节（提交结果、投稿口径、艺术家资料、机制备忘）。
- 写后重新 fetch 验证 revision 并交付文档链接。

## S7 发布微信表情开放平台（browser-use-automation）

完整 SOP 见 `references/publish.md`。要点：先核实发布工具（**业界无 tabbit 表情发布 CLI**；平台无官方 API，仅网页后台），用浏览器协助：用户扫码登录 → 填专辑表单（静态/卡通/角色/风格/主题/地区/赞赏）→ 上传 16 主图+7 类素材 → 填含义词 → 艺术家资料（头像 640×640）→ **最终「提交」由用户亲自点击**（interaction.request_action 交接）→ 核对"表情提交成功"页面。

## 已验证的坑（详见 references/prompts.md）

1. prompt 写中文会糊字 → 文案由 process.py 叠字。
2. `background:transparent` 无效 → 必须脚本去底（floodfill/透明斜坡）。
3. 必须串行出图，并行互相覆盖。
4. Windows PowerShell 5 下 `--content "<内联XML>"` 必坏 → 一律写文件后 `--content "@./相对路径"`。

## 资源

- `scripts/probe.py` — 背景色采样诊断。
- `scripts/process.py` — 后处理全管线（去底/描边/叠字/7 类规格/校验/zip/预览），可复用。
- `references/specs.md` — 微信平台七类素材规格与审核红线。
- `references/prompts.md` — S0/S1 提示词模板与已验证教训。
- `references/publish.md` — 微信平台浏览器发布 SOP 与机制备忘。
