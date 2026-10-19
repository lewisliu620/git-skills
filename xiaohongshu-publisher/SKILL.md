---
name: xiaohongshu-publisher
description: |
  通过 Tabbit 浏览器在小红书创作服务平台（已登录账号）发布图文/视频笔记。
  Use when:
  (1) 用户要把公众号文章/图文内容发布到小红书；
  (2) 用户说"发小红书""发布到小红书""小红书发一下"；
  (3) 需要在小红书创作服务平台上传图片、填标题正文话题并点击发布；
  (4) 发布后需要核对笔记状态（审核中/已发布）。
  Input: 标题、正文、图片（本地路径）、话题标签、发布授权。
  Output: 发布成功的确认 + 笔记管理页状态（审核中/已发布）。
  Do not: 不替用户决定发布内容；内容未经用户确认不发布；不处理需要登录的未授权账号；不做批量发布。
---

# 小红书笔记发布器

通过 Tabbit 浏览器在小红书创作服务平台发布图文笔记（已登录态）。

## 快速开始

① 建 Tabbit 任务 → ② 定位/打开发布页（图文模式）→ ③ 上传图片 + 填标题正文话题 → ④ 截图验证内容 → ⑤ 点击「发布」→ ⑥ 核对发布结果（URL `published=true` + 笔记管理页状态）→ ⑦ finish 任务。

## 核心职责

1. 用 Tabbit 驱动已登录的小红书创作服务平台，完成图文/视频笔记发布
2. 上传配图、填写标题、正文、话题标签
3. 处理「发布按钮是自定义组件」的定位坑
4. 发布后核对状态并汇报

## 工作流程

### Step 0：前置确认

- 用户必须已明确授权发布（"可以直接发布这个小红书文章么" = 授权）。
- 内容（标题/正文/图片/话题）必须已定稿，或从飞书文档/本地文件取用。
- 图片需为本地文件路径（如 `C:\...\img_compare_table.png`）。

### Step 1：建 Tabbit 任务

```powershell
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
& $tabbitCli create --task "发布小红书笔记"
```

- 任务名可复用（如 `发布小红书笔记`），每次发布用同一个任务名，结束后 `finish`。
- 已有登录态的小红书创作服务平台标签页可直接复用（笔记管理页 URL: `https://creator.xiaohongshu.com/new/note-manager`）。

### Step 2：进入发布页

- 从侧边栏「发布笔记」进入；**默认是视频模式**（URL 含 `target=video`）。
- 图文笔记需要切换到「上传图文」：URL 变为 `https://creator.xiaohongshu.com/publish/publish?from=menu&target=image`。
- **坑：顶部「上传图文」tab 用 `getByText("上传图文").click()` 常被覆盖层拦截（subtree intercepts pointer events）**。
  - 解决：先截图/observe 确认 tab 的实际位置，用 `page.mouse.click(x, y)` 按像素坐标点击；或侧边栏找可见入口。

### Step 3：上传图片 + 填内容

```js
// 图片上传：等 file input 出现后 setInputFiles（本地绝对路径）
await page.setInputFiles('input[type=file]', 'C:/.../img1.png');
// 或对第二个文件框逐个设置
```

- 标题：`textbox "填写标题会有更多赞哦"` → `fill` 或键盘输入（**≤20 字**）。
- 正文：tiptap 编辑器（contenteditable）→ 点击聚焦后用 `page.keyboard.type(text, {delay: 10})` 逐字输入；话题标签（`#话题`）直接打在正文末行。
- 图片数量上限 18 张；显示 `2/18` 即已上传。

### Step 4：验证（发布前必须截图）

- 全页截图确认：标题、正文完整、话题下拉、右侧手机端预览。
- **内容未验证通过前禁止点发布。**

### Step 5：点击「发布」按钮（核心坑）

**发布按钮是自定义元素 `<xhs-publish-btn>`，不是原生 `<button>`：**

- 特征：无 shadow DOM、无子节点（`innerHTML` 为空）、属性 `submit-text="发布"`、`submit-disabled="false"`；固定底栏（元素 rect 约 x446 y892 w680 h90，视口 1671×982）。
- **定位失败路径（不要重试）**：
  - `getByRole("button", {name: "发布"})` / `getByText("发布")` / DOM 文本匹配（`textContent.trim()==="发布"`）→ 全部匹配不到或点到侧边栏「发布笔记」。
- **可行路径（二选一）**：
  1. **坐标点击（推荐，最稳）**：先滚动到 `document.body.scrollHeight`，然后按**像素坐标**点击发布文字中心。OCR 快照里按钮约在千分比 (487,937)~(547,964)，换算像素：`像素 = 千分比/1000 × 视口宽高`，视口 1671×982 时发布按钮中心 ≈ `(864, 933)`。
  2. 直接 `page.locator("xhs-publish-btn").first().click()`——元素中心可能落在按钮中部，成功率不稳定，点击后用状态确认。
- 点击后等待 5–8 秒，再检查：
  - `document.querySelector("xhs-publish-btn").getAttribute("submit-loading")` 是否变 true 后恢复 false；
  - **URL 是否变为 `published=true`**（发布成功的关键信号，`https://creator.xiaohongshu.com/publish/publish?source=&published=true`）。

### Step 6：核对发布结果

- 跳转/观察笔记管理页 `https://creator.xiaohongshu.com/new/note-manager`：
  - 顶部「全部 N」计数 +1；
  - 列表出现新笔记，标题匹配，状态「审核中」或「已发布」。
- 向用户汇报：标题、状态、时间；提醒审核通过后可去 App 看数据。

### Step 7：收尾

```powershell
& $tabbitCli finish --task "发布小红书笔记"
```

- `finish` 后标签页保留（`keep: true`），用户可自行刷新查看。

## PowerShell 传多行 JS 的标准姿势

```powershell
$program = [IO.Path]::GetTempFileName()
$code = @'
// JS here
'@
try {
  [IO.File]::WriteAllText($program, $code, [Text.UTF8Encoding]::new($false))
  cmd.exe /d /c "`"$tabbitCli`" nodejs --task `"发布小红书笔记`" --request-id unique-id < `"$program`""
} finally { Remove-Item $program -ErrorAction SilentlyContinue }
```

- 不要用 here-string 管道，PowerShell 会改写程序。
- request-id 每次唯一；超 15s 转后台后用 TaskOutput 取结果。

## 红线

1. **发布是不可逆对外动作**：必须先获得用户明确授权；内容未定稿/未验证不发布。
2. 发布前必须截图验证（标题、正文、图片、话题完整）。
3. 不批量发布、不发布用户未确认的内容。
4. 公众号等平台只走到预览，不替用户点发表（沿用 content-pipeline 红线）。
5. 失败时保留标签页与现场，向用户说明状态，不反复盲试。
