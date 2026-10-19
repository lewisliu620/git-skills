---
name: ximalaya-uploader
description: |
  喜马拉雅音频自动上架工具：用 Tabbit CLI 驱动 Tabbit 浏览器，把本地音频自动上传到喜马拉雅并提交发布（个人实名账号，无需开放平台 API）。
  Use when:
  (1) 用户要求把生成的故事/音频上传或发布到喜马拉雅（如"上传试水音频""把第X集传上去"）；
  (2) 需要批量/重复把音频上架到个人主播账号；
  (3) 用户要求"用 tabbit cli 上传"喜马拉雅音频。
  Input: 本地 MP3 路径、标题、简介（可选）、专辑名（默认"童话故事屋"）。
  Output: 发布结果（作品进入"转码中/审核"状态）。
  Do not: 不上传非原创/侵权/违规内容；不伪造《知识产权承诺》或原创声明；不用逆向接口绕过平台；不修改账号安全设置。
---

# 喜马拉雅音频自动上架（Ximalaya Uploader）

用 Tabbit CLI 指挥 Tabbit 浏览器，自动完成喜马拉雅个人账号的音频上传与发布。个人账号没有开放上传 API，Tabbit CLI 的机制就是"CLI 下发 Playwright 代码 → 浏览器执行网页操作"，所以本工具天然表现为浏览器自动操作。

## 快速开始

前置检查 → 运行 `scripts/upload-to-ximalaya.ps1` → 确认发布结果。

```
& "…\.user_skills\ximalaya-uploader\scripts\upload-to-ximalaya.ps1" `
    -Mp3Path "C:\path\第1集.mp3" -Title "第1集 睡前童话三则" `
    -Intro "原创儿童童话合集，AI多角色配音…" -Album "童话故事屋"
```

## 前置要求（不满足先处理，不跳过）

1. Tabbit Browser 已安装并正在运行（本机路径见下）。
2. Tabbit 浏览器内喜马拉雅**已登录且实名**（账号"声启智航"，实名已完成）。
3. 音频文件：MP3/WAV/FLAC 等，单文件 ≤200MB；建议单条 ≥5 分钟（部分审核场景要求）。
4. Tabbit CLI 路径：`%LOCALAPPDATA%\Tabbit\LocalAgent\bin\tabbit-cli.exe`（脚本自动探测，缺失会报错）。

## 工作流程

### Step 1 调用脚本
运行 `scripts/upload-to-ximalaya.ps1`，传入：`-Mp3Path`（必填）、`-Title`（必填）、`-Intro`（选填）、`-Album`（选填，默认"童话故事屋"）、`-TaskName`（选填，标签组标题）。

### Step 2 脚本内部自动执行（无需人工干预）
1. **建任务 + 确认登录态**：连接 Tabbit，若未登录或登录页则中止并提示。
2. **预处理音频路径**：MP3 路径含中文/空格时，先复制为纯 ASCII 路径（如 `ep4.mp3`）再注入，否则 `setInputFiles` 可能 30s 超时。
3. **注入文件**：定位上传页 iframe（`reform-upload`）内 `input[type=file]`，用 `setInputFiles` 注入本地文件，轮询到"上传成功"。
4. **填表单**：标题（≤40 字）→ 勾选"是否AI合成=是"（radio value=true）→ 简介（可见 textarea，原生 setter）→ 专辑（通常自动带出，无需操作）→ 《知识产权承诺》（默认已勾，未勾则补勾）。
5. **发布**：点击"确认发布"（DOM 级文本匹配）→ iframe 跳转 `sound/manage` 页，轮询列表新集"转码中"。
6. **收尾**：`finish` 结束任务，标签页保留。

### Step 3 验证与汇报
- 脚本返回结构化结果（uploaded / filled / published / observedStatus）。
- 向用户汇报：标题、专辑、当前状态（转码中 → 审核 → 原创即正式发布）。
- 审核批次：工作日每天上/下午各一次；非工作日 10:00 / 22:00。审核通过状态变"原创"。

### 后续多平台分发（审核通过后）
- 播客 RSS：专辑 RSS → 苹果播客/网易云/小宇宙（走 RSS 同步，不走上传）。
- 蜻蜓 FM / 荔枝：另走平台旁路上传（见 references/playbook.md）。

## 关键实现细节（必须遵守，否则失败）

- **iframe 定位**：上传表单在 `https://www.ximalaya.com/reform-upload/page/webCenter/upload` iframe 内，所有字段操作都作用于该 frame。
- **简介输入**：`#soundRichIntro` 是只读隐藏富文本存储，**禁止直接 fill**；必须用"可见 textarea + 原生 value setter + input/change 事件"。
- **按钮点击**：部分按钮 `getByRole` 匹配失败，统一用 `evaluate` 做 DOM 级 `textContent` 匹配点击。
- **文件注入**：不要监听 filechooser 事件（该站不触发）；直接对 frame 内 `input[type=file]` 执行 `setInputFiles`，路径用正斜杠（JS 字符串反斜杠会被吞）。**中文路径会触发 setInputFiles 30s 超时**，先复制为纯 ASCII 路径再注入。
- **AI 合成 radio**：radio 组无 name 属性，"是"=value `true`、"否"=value `false`，默认勾"否"；AI 合成内容必须勾 `input[type=radio][value=true]`（force），否则审核按非 AI 原创处理。
- **专辑自动带出**：专辑选择区显示"选择专辑 → 专辑名"即已选中（专辑搜索框不可见，勿尝试 fill），无需额外操作。
- **承诺默认勾选**：《知识产权承诺》checkbox 默认 checked，未勾时再补勾。
- **Windows 调用**：JS 代码写 UTF-8 无 BOM 临时文件，经 `cmd /d /c` 重定向 stdin；CLI 输出偶发为空时重跑或先 `diagnose` 确认任务空闲。
- **request-id**：每次调用用新 ID（复用会返回旧 receipt 不执行）。

## 红线

1. 只上传原创/已获授权内容；不勾选虚假承诺，不盗用他人作品。
2. 儿童内容须过 fairy-tale-studio 的安全红线（无恐怖/暴力/迷信/烟酒/危险模仿等），符合未成年人保护相关法规。
3. "确认发布"是对外可见的发布动作，仅在用户明确要求上传/试水时执行；不批量滥发、不导流第三方、不刷数据。
4. 不用逆向接口绕过平台审核与风控；遇到权限/登录问题如实上报，不绕过登录态。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| CLI 无输出 | 重跑脚本；或先 `tabbit-cli diagnose --task <任务名>` 确认任务空闲 |
| 未登录报错 | 在 Tabbit 浏览器手动登录喜马拉雅后重跑 |
| 找不到上传 iframe | 手动打开 studio.ximalaya.com/upload 确认页面可达后再跑 |
| 发布按钮不可点 | 协议未勾选或表单未完成，脚本会重试勾选；仍失败则人工查看页面 |
| 未观察到"转码中" | 可能已进入审核或页面结构变化，到创作中心人工确认 |

详细字段定位与批量/定时扩展见 `references/playbook.md`。
