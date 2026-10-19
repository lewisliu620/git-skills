# upload-to-ximalaya.ps1
# 用 Tabbit CLI 驱动 Tabbit 浏览器，自动完成喜马拉雅个人账号的音频上传 + 发布。
# 前置要求：Tabbit Browser 已安装并保持登录喜马拉雅（声启智航账号已实名）。
# 用法示例：
#   & .\upload-to-ximalaya.ps1 -Mp3Path "C:\xxx\第1集.mp3" -Title "第1集 睡前童话三则" -Intro "原创儿童童话合集..." -Album "童话故事屋"
# 可选：-TaskName "童话故事上传"（标签组标题，建议保持简短且每次不同；结束任务时复用同一名字）
# 注意：本脚本执行"确认发布"（对外发布动作），运行前确认内容合规且已获授权。

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Mp3Path,   # 本地 MP3 绝对路径
    [Parameter(Mandatory = $true)][string]$Title,     # 声音标题
    [string]$Intro = "",                              # 声音简介（留空则只填标题）
    [string]$Album = "童话故事屋",                     # 目标专辑名（可为"不进专辑"/"创建新专辑"）
    [string]$TaskName = "童话故事上传"                  # Tabbit 标签组标题（任务名）
)

$ErrorActionPreference = "Stop"

# ---------- 前置检查 ----------
$tabbitCli = Join-Path $env:LOCALAPPDATA "Tabbit\LocalAgent\bin\tabbit-cli.exe"
if (-not (Test-Path -LiteralPath $tabbitCli)) { throw "找不到 tabbit-cli.exe: $tabbitCli" }
if (-not (Test-Path -LiteralPath $Mp3Path))   { throw "找不到音频文件: $Mp3Path" }
$mp3Full = (Resolve-Path -LiteralPath $Mp3Path).Path
# Playwright setInputFiles 接受正斜杠路径；JS 字符串内反斜杠会被当转义符，必须替换
$mp3Js = $mp3Full.Replace("\", "/")

Write-Host "[1/5] 前置检查通过: $tabbitCli" -ForegroundColor Green
Write-Host "    音频: $mp3Full ($([math]::Round((Get-Item -LiteralPath $mp3Full).Length / 1MB, 2)) MB)"
Write-Host "    标题: $Title | 专辑: $Album | 任务名: $TaskName"

# ---------- Tabbit CLI 调用封装 ----------
function Invoke-TabbitJs {
    param([string]$RequestId, [string]$JsCode)
    $prog = [IO.Path]::GetTempFileName()
    $out  = [IO.Path]::GetTempFileName()
    try {
        # UTF-8 无 BOM 写 JS 临时文件（PowerShell 会改写 stdin 编码，须经 cmd 重定向）
        [IO.File]::WriteAllText($prog, $JsCode, (New-Object Text.UTF8Encoding($false)))
        $inner = "`"$tabbitCli`" nodejs --task `"$TaskName`" --request-id $RequestId < `"$prog`" > `"$out`""
        cmd.exe /d /c $inner | Out-Null
        $raw = [IO.File]::ReadAllText($out)
        if ([string]::IsNullOrWhiteSpace($raw)) {
            throw "Tabbit CLI 无输出（requestId=$RequestId）。偶发问题，重跑本脚本即可；持续为空请先运行: tabbit-cli diagnose --task `"$TaskName`""
        }
        return $raw.Trim()
    } finally {
        Remove-Item $prog, $out -ErrorAction SilentlyContinue
    }
}

function Parse-TabbitResult {
    param([string]$Raw)
    # 输出形如: TABBIT_PLAYWRIGHT_INSTANCE=xxx\n{"result":...,"status":...}，截取 JSON 段
    $i = $Raw.IndexOf('{"result"')
    if ($i -lt 0) { throw "无法解析 Tabbit 输出: $($Raw.Substring(0, [Math]::Min(200, $Raw.Length)))" }
    $obj = ($Raw.Substring($i)) | ConvertFrom-Json
    if ($obj.status -ne "succeeded") {
        $err = $obj.result.error
        throw "Tabbit 执行失败 (requestId=$($obj.result.requestId)): $err"
    }
    return $obj.result.value
}

function Read-SimpleTail {
    param([string]$Raw)
    $i = $Raw.IndexOf('{"result"')
    if ($i -lt 0) { return "" }
    $obj = ($Raw.Substring($i)) | ConvertFrom-Json
    if ($obj.status -ne "succeeded") { return "" }
    return ($obj.result.value | ConvertTo-Json -Compress -Depth 4)
}

# ---------- Step 1: 建任务并确认登录态 ----------
Write-Host "[2/5] 连接 Tabbit 浏览器并确认登录态..."
$js1 = @'
let url = page.url();
if (!url.includes("studio.ximalaya.com")) {
  await page.goto("https://studio.ximalaya.com/upload", {waitUntil: "domcontentloaded"});
  url = page.url();
}
if (url.includes("passport") || url.includes("login")) return {login: false, url};
await page.waitForTimeout(1500);
const hasFrame = page.frames().some(f => f.url().includes("reform-upload"));
return {login: true, url, hasFrame};
'@
$r1 = Parse-TabbitResult (Invoke-TabbitJs "step1-login-check" $js1)
if (-not $r1.login) { throw "喜马拉雅未登录，请先在 Tabbit 浏览器登录后重试（当前 URL: $($r1.url)）" }
Write-Host "    登录态正常, 已定位上传页 (iframe=$($r1.hasFrame))" -ForegroundColor Green

# ---------- Step 2: 注入音频文件并等待上传成功 ----------
Write-Host "[3/5] 注入音频文件 $mp3Js ..."
$js2 = @'
const f = page.frames().find(fr => fr.url().includes("reform-upload"));
if (!f) throw new Error("找不到上传 iframe");
await f.locator("input[type='file']").first().setInputFiles("__MP3__");
let ok = false, tail = "";
for (let i = 0; i < 20; i++) {
  await page.waitForTimeout(2000);
  const t = await f.evaluate(() => document.body ? (document.body.innerText || "") : "");
  if (t.includes("上传成功")) { ok = true; tail = t.slice(-120); break; }
  tail = t.slice(-120);
}
return {ok, tail};
'@
$js2 = $js2.Replace("__MP3__", $mp3Js)
$r2 = Parse-TabbitResult (Invoke-TabbitJs "step2-inject-file" $js2)
if (-not $r2.ok) { throw "音频未显示'上传成功'（可能是文件格式/大小问题，或页面结构变化）。页面尾部: $($r2.tail)" }
Write-Host "    上传成功 ✓" -ForegroundColor Green

# ---------- Step 3: 填标题 / 简介 / 选专辑 ----------
Write-Host "[4/5] 填写标题、简介、选择专辑..."
$js3 = @'
const f = page.frames().find(fr => fr.url().includes("reform-upload"));
if (!f) throw new Error("找不到上传 iframe");
await f.locator("input[placeholder='请输入声音标题']").fill("__TITLE__");
await f.evaluate((intro) => {
  // 注意: #soundRichIntro 是只读隐藏富文本存储，不可直接 fill；必须找可见 textarea 用原生 setter
  const ta = Array.from(document.querySelectorAll("textarea")).find(e => e.offsetParent !== null);
  if (!ta) return false;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
  setter.call(ta, intro);
  ta.dispatchEvent(new Event("input", {bubbles: true}));
  ta.dispatchEvent(new Event("change", {bubbles: true}));
  return true;
}, "__INTRO__");
await f.evaluate((album) => {
  const btns = Array.from(document.querySelectorAll("button"));
  const b = btns.find(x => (x.textContent || "").trim() === album);
  if (b) { b.click(); return true; }
  return false;
}, "__ALBUM__");
await page.waitForTimeout(1200);
const st = await f.evaluate(() => {
  const t = document.querySelector("input[placeholder='请输入声音标题']");
  const ta = Array.from(document.querySelectorAll("textarea")).find(e => e.offsetParent !== null);
  return {title: t ? t.value : null, intro: ta ? ta.value.slice(0, 40) : null};
});
return st;
'@
$js3 = $js3.Replace("__TITLE__", $Title).Replace("__INTRO__", $Intro).Replace("__ALBUM__", $Album)
$r3 = Parse-TabbitResult (Invoke-TabbitJs "step3-fill-form" $js3)
Write-Host "    标题已填: $($r3.title)" -ForegroundColor Green
Write-Host "    简介已填: $($r3.intro)..." -ForegroundColor Green
Write-Host "    专辑选择: $Album"

# ---------- Step 4: 勾选承诺 + 确认发布 + 轮询结果 ----------
Write-Host "[5/5] 勾选知识产权承诺并确认发布（对外发布动作）..."
$js4 = @'
const f = page.frames().find(fr => fr.url().includes("reform-upload"));
const cb = await f.evaluate(() => {
  const c = document.querySelector("input[type='checkbox']");
  if (!c) return "no-checkbox";
  if (!c.checked) { c.click(); return "checked-now"; }
  return "already-checked";
});
await page.waitForTimeout(600);
const btn = await f.evaluate(() => {
  const b = Array.from(document.querySelectorAll("button")).find(x => (x.textContent || "").trim() === "确认发布");
  return b ? {disabled: !!b.disabled} : null;
});
if (!btn || btn.disabled) return {cb, published: false, reason: "发布按钮不可点（可能协议未勾选或表单未完成）"};
await f.evaluate(() => {
  const b = Array.from(document.querySelectorAll("button")).find(x => (x.textContent || "").trim() === "确认发布");
  b.click();
});
let published = false, tail = "";
for (let i = 0; i < 12; i++) {
  await page.waitForTimeout(3000);
  const t = await page.evaluate(() => document.body ? (document.body.innerText || "") : "").catch(e => "");
  if (t.includes("转码中") || t.includes("审核")) { published = true; tail = t.slice(-200); break; }
  tail = t.slice(-200);
}
return {cb, btn, published, tail};
'@
$r4 = Parse-TabbitResult (Invoke-TabbitJs "step4-publish" $js4)
$btnState = if ($r4.btn -and -not $r4.btn.disabled) { "可用" } elseif ($r4.btn) { "禁用" } else { "未找到" }
$btnNote = if ($r4.reason) { "（$($r4.reason)）" } else { "" }
Write-Host "    协议状态: $($r4.cb) | 发布按钮: $btnState $btnNote" -ForegroundColor Green

if ($r4.published) {
    Write-Host "    ✅ 发布已提交，作品进入'转码中/审核'状态" -ForegroundColor Green
} else {
    Write-Host "    ⚠️ 未观察到'转码中/审核'状态，可能仍在处理中或页面结构变化。请到创作中心确认。" -ForegroundColor Yellow
}
Write-Host "    页面尾部: $($r4.tail)" -ForegroundColor DarkGray

# ---------- Step 5: 结束任务（保留标签页） ----------
try {
    $finish = (& $tabbitCli finish --task $TaskName 2>&1) -join "`n"
    Write-Host "    任务已结束（标签页保留）: $($finish.Substring(0, [Math]::Min(80, $finish.Length)))" -ForegroundColor DarkGray
} catch {
    Write-Host "    finish 提示: $_（可忽略，标签组会保留）" -ForegroundColor DarkGray
}

# ---------- 汇总 ----------
$summary = [ordered]@{
    taskName = $TaskName
    title = $Title
    album = $Album
    file = $mp3Full
    uploaded = $r2.ok
    filled = [bool]$r3.title
    published = $r4.published
    observedStatus = if ($r4.published) { "转码中/审核" } else { "待确认" }
}
Write-Host ""
Write-Host "===== 上传结果 =====" -ForegroundColor Cyan
$summary.GetEnumerator() | ForEach-Object { Write-Host ("{0}: {1}" -f $_.Key, $_.Value) }
$summary | ConvertTo-Json -Compress
