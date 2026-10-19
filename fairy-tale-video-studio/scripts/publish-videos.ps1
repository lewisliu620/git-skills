# Batch publish videos to WeChat Channels (Shipship/Finder) via Tabbit CLI.
# Usage: powershell -File publish-videos.ps1 [-ConfigFile .\publish-config.json] [-TaskName "batch-publish"]
# Prereq: Tabbit browser running; channels.weixin.qq.com logged in (script self-checks).
# Flow per video: open create page -> upload -> wait ready -> fill desc/title -> publish -> verify in list.

param(
    [string]$ConfigFile = (Join-Path $PSScriptRoot "publish-config.json"),
    [string]$TaskName = "batch-publish"
)

$ErrorActionPreference = "Stop"
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
if (-not (Test-Path $tabbitCli)) { throw "tabbit-cli not found: $tabbitCli" }
if (-not (Test-Path $ConfigFile)) { throw "config not found: $ConfigFile" }

$videos = Get-Content -Raw -Encoding UTF8 $ConfigFile | ConvertFrom-Json
Write-Host ("Videos to publish: {0}" -f $videos.Count)
for ($i = 0; $i -lt $videos.Count; $i++) {
    Write-Host ("  [{0}] {1}" -f ($i + 1), (Split-Path $videos[$i].path -Leaf))
}

$script:seq = 0
function Invoke-Tabbit {
    param([string]$Step, [string]$Code, [int]$TimeoutMs = 150000)
    $script:seq++
    $rid = "{0}-{1}-{2}" -f $Step, $script:seq, (Get-Date -Format "HHmmssfff")
    $tmp = [IO.Path]::GetTempFileName()
    [IO.File]::WriteAllText($tmp, $Code, [Text.UTF8Encoding]::new($false))
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = cmd.exe /d /c "`"$tabbitCli`" nodejs --task `"$TaskName`" --request-id $rid --timeout-ms $TimeoutMs < `"$tmp`"" 2>&1 | Out-String
    } finally {
        $ErrorActionPreference = $prevEap
    }
    Remove-Item $tmp -ErrorAction SilentlyContinue
    $start = $out.IndexOf('{')
    if ($start -lt 0) { throw "tabbit no JSON output: $out" }
    $obj = $out.Substring($start) | ConvertFrom-Json
    if ($obj.status -ne "succeeded") { throw "tabbit status=$($obj.status) err=$($obj.error) out=$out" }
    return $obj
}

# --- login self-check ---
$code = @'
page.removeAllListeners('dialog');
page.on('dialog', d => { d.accept().catch(() => {}); });
await page.goto("https://channels.weixin.qq.com/platform/post/create", {waitUntil: "domcontentloaded", timeout: 60000});
await page.waitForTimeout(4000);
return {url: page.url()};
'@
$check = Invoke-Tabbit "check" $code 120000
if ($check.result.value.url -match "login") {
    Write-Host ""
    Write-Host "[NOT LOGGED IN] Please scan the QR code in the Tabbit browser window with WeChat, then rerun this script."
    exit 1
}
Write-Host ""
Write-Host "[OK] Logged in to Channels assistant"

$results = @()
for ($i = 0; $i -lt $videos.Count; $i++) {
    $v = $videos[$i]
    $path = $v.path
    $desc = $v.desc
    $shortTitle = $v.shortTitle
    $name = Split-Path $path -Leaf
    Write-Host ""
    Write-Host ("===== [{0}/{1}] {2} =====" -f ($i + 1), $videos.Count, $name)

    if (-not (Test-Path $path)) {
        Write-Host "  [SKIP] file not found: $path"
        $results += [pscustomobject]@{name=$name; status="file-not-found"}
        continue
    }

    $pathJson = $path | ConvertTo-Json
    $descJson = $desc | ConvertTo-Json
    $titleJson = $shortTitle | ConvertTo-Json

    # 1) open create page and upload (file input OR click zone + filechooser)
    $uploadKwJson = "上传" | ConvertTo-Json
    $code = @"
page.removeAllListeners('dialog');
page.on('dialog', d => { d.accept().catch(() => {}); });
await page.goto('https://channels.weixin.qq.com/platform/post/create', {waitUntil: 'domcontentloaded', timeout: 60000});
await page.waitForTimeout(3000);
// dismiss possible guide layer
const guide = page.getByRole('button', {name: '我知道了', exact: true}).first();
if (await guide.count()) { await guide.click().catch(() => {}); await page.waitForTimeout(1500); }
const uploadKw = $uploadKwJson;
let input = page.locator('input[type=file]').first();
let fileCount = await input.count();
for (let w = 0; w < 12 && fileCount === 0; w++) {
  await page.waitForTimeout(5000);
  fileCount = await input.count();
}
if (fileCount > 0) {
  await input.setInputFiles($pathJson, {timeout: 90000});
} else {
  // fallback: click the upload zone (button/div) and catch the file chooser
  let zone = page.locator('button').filter({hasText: uploadKw}).first();
  let zc = await zone.count();
  if (zc === 0) {
    zone = page.locator('[class*="upload"], [class*="Upload"]').first();
    zc = await zone.count();
  }
  if (zc === 0) {
    zone = page.locator('div').filter({hasText: uploadKw}).first();
    zc = await zone.count();
  }
  if (zc === 0) {
    const body = (await page.evaluate(() => document.body ? (document.body.innerText || '') : '')).slice(0, 300);
    return {uploaded: false, reason: 'no-upload-zone', body};
  }
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser', {timeout: 20000}),
    zone.click({timeout: 15000})
  ]);
  await chooser.setFiles($pathJson);
}
await page.waitForTimeout(3000);
return {uploaded: true, url: page.url()};
"@
    $up = Invoke-Tabbit "upload" $code 180000
    if (-not $up.result.value.uploaded) {
        Write-Host ("  [FAIL] no file input: {0}" -f $up.result.value.reason)
        Write-Host ("  body: {0}" -f $up.result.value.body)
        $results += [pscustomobject]@{name=$name; status="no-file-input"}
        continue
    }
    Write-Host "  uploaded, waiting for processing..."

    # 2) poll until editor is ready (VISIBLE desc box or short-title input appears; skip hidden commodity-link textarea)
    $ready = $false
    for ($t = 1; $t -le 24; $t++) {
        Start-Sleep -Seconds 10
        $code = @'
const edCount = await page.locator('[contenteditable]').count();
const visTa = await page.locator('textarea:visible').count();
const visInput = await page.locator('input:visible').count();
return {hasEditable: edCount > 0, hasVisibleTa: visTa > 0, hasVisibleInput: visInput > 0, url: page.url()};
'@
        $st = Invoke-Tabbit "status" $code 90000
        $s = $st.result.value
        if ($s.hasEditable -or $s.hasVisibleTa -or $s.hasVisibleInput) {
            $ready = $true
            Write-Host ("  editor ready after ~{0}s" -f ($t * 10))
            break
        }
        if ($t % 6 -eq 0) { Write-Host ("  still processing... {0}s" -f ($t * 10)) }
    }
    if (-not $ready) {
        Write-Host "  [FAIL] upload timeout (~4 min), editor not shown"
        $results += [pscustomobject]@{name=$name; status="upload-timeout"}
        continue
    }

    # 3) fill description + short title (only VISIBLE boxes; hidden commodity-link textarea must be skipped)
    $code = @"
const desc = $descJson;
const title = $titleJson;
let descBox = null;
const tns = await page.locator('textarea').count();
for (let i = 0; i < tns; i++) {
  const t = page.locator('textarea').nth(i);
  if (await t.isVisible().catch(() => false)) { descBox = t; break; }
}
if (!descBox) {
  const ens = await page.locator('[contenteditable]').count();
  for (let i = 0; i < ens; i++) {
    const e = page.locator('[contenteditable]').nth(i);
    if (await e.isVisible().catch(() => false)) { descBox = e; break; }
  }
}
if (!descBox) return {filled: false, reason: 'no-desc-box'};
await descBox.click();
await descBox.fill('');
await descBox.fill(desc);
const inputs = page.locator('input');
const n = await inputs.count();
let target = null;
for (let i = 0; i < n; i++) {
  const inp = inputs.nth(i);
  if (await inp.isVisible().catch(() => false)) { target = inp; break; }
}
let titleFilled = false;
if (target) {
  await target.click();
  await target.fill('');
  await target.fill(title);
  titleFilled = true;
}
await page.waitForTimeout(1000);
return {filled: true, titleFilled, titleLen: title.length};
"@
    $fill = Invoke-Tabbit "fill" $code 120000
    Write-Host ("  desc len: {0}, title filled: {1}" -f $fill.result.value.descLen, $fill.result.value.titleFilled)
    if (-not $fill.result.value.filled) {
        Write-Host ("  [FAIL] no desc box: {0}" -f $fill.result.value.reason)
        $results += [pscustomobject]@{name=$name; status="no-desc-box"}
        continue
    }

    # 4) click publish (handle confirm dialog) -- button text injected at runtime
    $pubTextJson = ($v.publishBtn | ConvertTo-Json)
    $code = @"
const pubText = $pubTextJson;
const btn = page.locator('button').filter({hasText: pubText}).first();
const bc = await btn.count();
if (bc === 0) return {published: false, reason: 'no-publish-btn'};
const stop = new AbortController();
const handled = page.waitForEvent('dialog', {timeout: 8000, signal: stop.signal})
  .then(async d => { try { await d.accept(); return 'accepted'; } catch { return 'dismissed'; } })
  .catch(() => 'none');
await btn.click();
const dialogResult = await handled;
stop.abort();
await page.waitForTimeout(6000);
return {published: true, dialogResult, url: page.url()};
"@
    $pub = Invoke-Tabbit "publish" $code 120000
    if (-not $pub.result.value.published) {
        Write-Host ("  [FAIL] no publish button: {0}" -f $pub.result.value.reason)
        $results += [pscustomobject]@{name=$name; status="no-publish-btn"}
        continue
    }
    Write-Host ("  publish clicked (dialog: {0}), verifying..." -f $pub.result.value.dialogResult)

    # 5) verify in post list
    Start-Sleep -Seconds 8
    $titleMatchJson = $shortTitle | ConvertTo-Json
    $code = @"
page.removeAllListeners('dialog');
page.on('dialog', d => { d.accept().catch(() => {}); });
await page.goto('https://channels.weixin.qq.com/platform/post/list', {waitUntil: 'domcontentloaded', timeout: 60000});
await page.waitForTimeout(4000);
const title = $titleMatchJson;
const text = (await page.evaluate(() => document.body ? (document.body.innerText || '') : '')).replace(/\s+/g, ' ');
return {rows: text.slice(0, 600), found: text.includes(title)};
"@
    $verify = Invoke-Tabbit "verify" $code 120000
    $pageText = $verify.result.value.rows
    $found = $verify.result.value.found
    if ($found) {
        Write-Host "  [OK] found in post list: $shortTitle"
        $results += [pscustomobject]@{name=$name; status="published-verified"}
    } else {
        Write-Host "  [CHECK] not matched in list text. First 600 chars: $pageText"
        $results += [pscustomobject]@{name=$name; status="published-pending-confirm"}
    }
}

Write-Host ""
Write-Host "===== BATCH DONE ====="
foreach ($r in $results) { Write-Host ("  - {0} : {1}" -f $r.name, $r.status) }
Write-Host ""
Write-Host "Note: channels review takes a few minutes; visible in list = success."
