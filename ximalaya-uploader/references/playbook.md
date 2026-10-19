# 喜马拉雅自动上架 Playbook（字段定位与扩展）

## 目录

- [页面与字段定位](#页面与字段定位)
- [已踩坑记录（务必遵守）](#已踩坑记录务必遵守)
- [批量上传](#批量上传)
- [定时上架（cron 组合）](#定时上架cron-组合)
- [多平台分发](#多平台分发)
- [审核与状态](#审核与状态)

## 页面与字段定位

| 对象 | 定位方式 | 说明 |
| --- | --- | --- |
| 上传页 | `https://studio.ximalaya.com/upload` | 创作中心内页 |
| 上传 iframe | `page.frames()` 中 url 含 `reform-upload` | 所有字段操作都在此 frame 内 |
| 文件输入 | `input[type='file']`（accept 含 MP3/WAV/FLAC 等） | `setInputFiles()` 注入，路径正斜杠 |
| 标题 | `input[placeholder='请输入声音标题']` | `fill()` 可用 |
| 简介（富文本存储） | `#soundRichIntro` | **readonly + 隐藏，禁止 fill** |
| 简介（可见输入框） | `textarea` 中 `offsetParent !== null` 者 | 原生 setter + input/change 事件 |
| 专辑按钮 | `button` 中 `textContent.trim() === 专辑名` | DOM 级 click（getByRole 会失败） |
| 知识产权承诺 | `input[type='checkbox']` | 发布前必须勾选 |
| 发布按钮 | `button` 中 `textContent.trim() === '确认发布'` | DOM 级 click，点击后页面切到作品列表 |
| 作品状态 | 顶层页面 body 文本 | "转码中" → "审核" → "原创" |
| 继续添加 | `button` 文本"继续添加" | 批量上传入口 |

## 已踩坑记录（务必遵守）

1. **#soundRichIntro 不可 fill**：第一次尝试 `fill("#soundRichIntro")` 超时挂起 30s——该 textarea 是 readonly 且隐藏（富文本底层存储）。正确做法：找可见 textarea，用 `Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set` 设值并派发 input/change。
2. **getByRole 匹配失败**：`getByRole("button", {name: "童话故事屋"})` 超时。该站按钮 accessible name 不稳定，统一改为 `evaluate` 内 DOM 文本匹配 + `click()`。
3. **filechooser 事件监听超时**：该站上传不用原生文件选择事件。正确做法：直接对 frame 内 `input[type=file]` `setInputFiles()`。
4. **JS 字符串路径反斜杠被吞**：`"\U"` 在 JS 中是非法转义，反斜杠会丢失。Windows 路径必须 `.Replace("\", "/")` 再嵌入 JS。
5. **CLI 输出偶发为空**：cmd 重定向 stdout 到 PowerShell 变量可能空返回。脚本内改为落盘读取；持续为空先 `tabbit-cli diagnose --task <名>` 确认 `idle:true`。
6. **request-id 复用**：复用 ID 会返回原始 receipt 而不执行。每次新 ID。
7. **任务名 = 标签组标题**：`--task` 名会显示为浏览器标签组标题，简短中文名即可；同一任务的所有调用（含 finish）必须用同一个名字。
8. **发布后页面不跳转**：点击"确认发布"后页面留在上传页几秒，随后切到作品列表。轮询顶层 body 文本找"转码中"，勿只轮询 iframe。
9. **专辑默认选中**：已有专辑（如"童话故事屋"）按钮出现即表示可选；DOM 点击后无需二次确认弹层。
10. **中文路径 setInputFiles 超时**（第 4 集实测 2026-10-05）：直接注入中文路径 MP3（如 `《小宇的勇敢夜灯》多角色配音.mp3`）挂起 30s 超时（locator 已解析到 input 但动作卡住）。正确做法：先 `Copy-Item` 为纯 ASCII 文件名（如 `ep4.mp3`）再注入，秒级成功。
11. **AI 合成 radio**（第 4 集实测）：radio 组无 name，"是/否"用 value `true/false`，默认勾"否"；发布 AI 内容必须 `check` value=true 的 radio（force），否则平台会按非 AI 内容走审核。
12. **知识产权承诺默认已勾**（第 4 集实测）：checkbox 初始即 checked，勿重复操作；先读状态再决定是否补勾。
13. **发布成功标志**（第 4 集实测）：点"确认发布"后 iframe URL 变为 `/reform-upload/page/sound/manage/<albumId>?source=uploadSuccess`，专辑列表新集出现且状态"转码中"即提交成功。标题有 40 字上限（输入框右侧显示 `11/40` 计数）。
14. **可见性默认公开**（第 4 集实测）：radio 组"公开所有人可见(value=2)"默认选中，无需改动。

## 批量上传

### 方式 A：循环调用脚本
```
$files = Get-ChildItem "C:\stories\episodes" -Filter *.mp3
foreach ($f in $files) {
  & "…\upload-to-ximalaya.ps1" -Mp3Path $f.FullName -Title $f.BaseName -Intro "…" -Album "童话故事屋" -TaskName "批量上传 $($f.BaseName)"
}
```
注意：每条是一个独立 Tabbit 任务；建议逐条确认"转码中"后再发下一条，避免并发占用。

### 方式 B：页面内"继续添加"
上传成功后可点"继续添加"追加下一个文件，最后统一发布——适合同专辑多集一次发布（脚本当前未封装，需扩展时按字段表加 JS 段）。

## 定时上架（cron 组合）

配合定时任务（doubao-cron-scheduler）可实现"每日/每周自动上架一集"：
- 生成音频（fairy-tale-studio）→ 产出 MP3 到固定目录；
- cron 触发时调用 upload-to-ximalaya.ps1（任务内写明"本次请求由 XX 定时任务触发"）；
- 注意：Tabbit 浏览器必须保持运行与登录态；定时任务运行在用户环境，需本机在线。

## 多平台分发

### 播客 RSS（推荐，审核通过后）
- 苹果播客：只接受 RSS Feed 提交，不走上传 → `https://podcasters.apple.com/zh-cn/support/897-submit-a-show`
- 网易云/小宇宙：同样走 RSS 同步
- 一源多分发：喜马拉雅专辑 RSS 作为主源，同步到苹果/网易云/小宇宙

### 蜻蜓 FM
- 开放平台有"主播-上传节目"API（POST /popenapi/v7/program），但需合作方审核资质 → `https://open.qingting.fm/documents/241`
- 个人账号暂无免审核通道时，走网页手动/半自动上传

### 荔枝
- 主播门槛最低，提供免费 Podcast RSS 方案 → `https://nj.lizhi.fm/pub/notice?id=4`
- 单条试水可直接网页上传

## 审核与状态

- 上传成功 → "转码中"（几分钟~数小时）→ "待审核" → 通过后 "原创"（正式对外可见）
- 审核批次：工作日每天上/下午各一次；非工作日 10:00 / 22:00 左右
- 审核要点：原创声明真实、标题简介合规、不导流第三方、儿童内容符合未成年人保护要求
- 账号：刘易斯Lewis（原昵称"声启智航"，2026-10-05 更名；ID 112250912，创作 633 天，信用分 100），已实名；RSS `itunes:author` 跟随昵称自动更新
- 已验证实测：2026-10-04 22:28 提交《第1集 睡前童话三则》→ 已发布；2026-10-05 18:19 提交《第4集 小宇的勇敢夜灯》→ 转码中；第 2/3 集均已发布
