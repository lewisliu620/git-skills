<#
.SYNOPSIS
    千恒货代快递单号回填脚本（单条/批量）。
.DESCRIPTION
    从飞书1688采购订单跟踪表读取待回填记录，通过 Tabbit CLI 在千恒货代系统
    (qianheng.huoxiaoyi.com) 录入国内快递单号并提交首公里预报，成功后回写飞书。

    千恒系统需已登录（cookie 保存在 Tabbit 浏览器 profile 中）。

.PARAMETER ShopeeOrderId
    单条模式：指定 Shopee 订单号（如 2610109QQ0S3WC）。
.PARAMETER Carrier
    单条模式：承运商名称（申通/圆通/中通/韵达/极兔/顺丰等，与千恒下拉选项一致）。
.PARAMETER TrackingNo
    单条模式：国内快递运单号。
.PARAMETER Batch
    批量模式：自动从飞书表读取"采购状态=已发货"但物流单号仍为占位符的记录。
.PARAMETER DryRun
    只打印将要执行的操作，不实际提交。

.EXAMPLE
    # 单条模式
    .\qianheng-tracking-backfill.ps1 -ShopeeOrderId 2610109QQ0S3WC -Carrier 申通 -TrackingNo 773445887926488

.EXAMPLE
    # 批量模式（处理所有待回填记录）
    .\qianheng-tracking-backfill.ps1 -Batch

.EXAMPLE
    # 预览批量内容
    .\qianheng-tracking-backfill.ps1 -Batch -DryRun
#>

param(
    [string]$ShopeeOrderId,
    [string]$Carrier,
    [string]$TrackingNo,
    [switch]$Batch,
    [switch]$DryRun
)

# ===================== 配置区 =====================
# lark-cli 自动发现：不写死 env hash（hash 会随环境刷新失效）。
# 优先级：环境变量 LARK_CLI > 已知稳定 envs > 扫描 sandbox_envs_dir 下最新的 lark-cli.exe。
function Resolve-LarkCli {
    if ($env:LARK_CLI -and (Test-Path $env:LARK_CLI)) { return $env:LARK_CLI }
    $candidates = @(
        "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs\5bf0f05d-e8ab-452d-b3ba-90183896de01\override_dlcs\lark-cli.exe",
        "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs\d5878cd6-edb0-4938-b12b-517ca47e9651\override_dlcs\lark-cli.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $root = "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs"
    if (Test-Path $root) {
        $hit = Get-ChildItem $root -Recurse -Filter lark-cli.exe -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return "lark-cli"
}
$LarkCli = Resolve-LarkCli

$BaseToken = "QsnYbrWpaa6lGfspgLpcihfvnpb"
$TrackingTableId = "tbl9S5Xruh3ytOib"

$TabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
$TaskName = "千恒单号回填"
$QianhengOrderUrl = "https://qianheng.huoxiaoyi.com/order?platform=shopee&tab=wait_submit"

# 承运商名称映射（飞书简称 → 千恒下拉选项完整文本）
$CarrierMap = @{
    "申通" = "申通快递"
    "圆通" = "圆通速递"
    "中通" = "中通快递"
    "韵达" = "韵达快递"
    "极兔" = "极兔速递"
    "顺丰" = "顺丰速运"
    "京东" = "京东物流"
    "百世" = "百世快递"
    "EMS" = "EMS物流"
}
# 运单号前缀兜底（1688详情页只有前缀、无中文承运商时用）：STO/YTO/ZTO/YD/JT/SF/JD/BD/EMS
$CarrierPrefixMap = @{
    "STO" = "申通"; "YTO" = "圆通"; "ZTO" = "中通"; "YD" = "韵达"; "JT" = "极兔"
    "SF" = "顺丰"; "JD" = "京东"; "BD" = "百世"; "EMS" = "EMS"
}

# 登录失效/授权过期识别（千恒页面内文，不依赖跳转URL）
$KhAuthExpiredPattern = "登录失效|授权已经过期|授权过期|请重新登录|账号登录失效"

# ===================== 工具函数 =====================

function Write-Log {
    param([string]$Msg, [string]$Color = "White")
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor $Color
}

function Invoke-TabbitJs {
    param(
        [string]$TaskName,
        [string]$TabId,
        [string]$RequestId,
        [string]$JsCode,
        [int]$TimeoutSec = 90
    )
    $tmpJs = [System.IO.Path]::GetTempFileName() + ".js"
    [System.IO.File]::WriteAllText($tmpJs, $JsCode, [Text.UTF8Encoding]::new($false))
    try {
        $args = @("nodejs", "--task", "`"$TaskName`"")
        if ($TabId) { $args += @("--tab", $TabId) }
        $args += @("--request-id", $RequestId, "--timeout-ms", ($TimeoutSec * 1000))
        $cmdLine = "`"$TabbitCli`" $($args -join ' ') < `"$tmpJs`""
        $output = cmd.exe /d /c $cmdLine 2>&1 | Out-String
        return $output
    } finally {
        Remove-Item $tmpJs -ErrorAction SilentlyContinue
    }
}

function Parse-Tracking {
    <# 解析飞书"物流单号"text（格式"承运商简称 运单号"，如"申通 773445887926488"）。
       返回 @{ carrierShort; carrierFull; trackingNo }；解析不到返回 $null。
       先按中文简称匹配，再按运单号前缀兜底。 #>
    param([string]$Raw)
    if ([string]::IsNullOrWhiteSpace($Raw)) { return $null }
    $s = $Raw.Trim()
    # 1) 中文承运商简称优先：简称 + 空白 + 单号（单号可带 YTO/STO 等字母前缀）
    foreach ($short in $CarrierMap.Keys) {
        $m = [regex]::Match($s, "$short\s+([A-Za-z]{0,3}\d{6,}[A-Za-z0-9]*)")
        if ($m.Success) {
            return @{ carrierShort = $short; carrierFull = $CarrierMap[$short]; trackingNo = $m.Groups[1].Value }
        }
    }
    # 2) 前缀兜底（无中文，只有 STO/YTO/...）
    foreach ($p in $CarrierPrefixMap.Keys) {
        $m = [regex]::Match($s, "\b$p\s*([A-Za-z]{0,3}\d{6,}[A-Za-z0-9]*)", [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($m.Success) {
            $short = $CarrierPrefixMap[$p]
            return @{ carrierShort = $short; carrierFull = $CarrierMap[$short]; trackingNo = $m.Groups[1].Value }
        }
    }
    return $null
}

function Get-PendingRecords {
    <# 从飞书表读取全部行，按 data.fields 列名映射（不硬编码列序），
       筛出"采购状态=已发货 + 可解析真实承运商/单号 + 有关联Shopee号"的待录单；
       其余行带 skipReason 返回，供 DryRun 说明为何跳过。 #>
    $tmpOut = [System.IO.Path]::GetTempFileName() + ".json"
    & $LarkCli base +record-list --base-token $BaseToken --table-id $TrackingTableId --as user --limit 200 --format json 2>&1 | Out-File $tmpOut -Encoding utf8
    $raw = Get-Content $tmpOut -Encoding utf8 -Raw | ConvertFrom-Json
    Remove-Item $tmpOut -ErrorAction SilentlyContinue

    # 列名 → 列位置映射（lark-cli 返回 data.fields 给出列序）
    $col = @{}
    for ($c = 0; $c -lt $raw.data.fields.Count; $c++) { $col[[string]$raw.data.fields[$c]] = $c }

    function Cell($row, $name, $colMap) {
        $idx = $colMap[$name]
        if ($null -eq $idx) { return "" }
        $v = $row[$idx]
        if ($null -eq $v) { return "" }
        if ($v -is [array]) { return ($v | ForEach-Object { if ($_ -is [psobject] -and $_.text) { $_.text } else { "$_" } }) -join "," }
        if ($v -is [psobject] -and $v.text) { return "$($v.text)" }
        return "$v"
    }

    $records = @()
    for ($i = 0; $i -lt $raw.data.record_id_list.Count; $i++) {
        $row = $raw.data.data[$i]
        $status = (Cell $row "采购状态" $col).Trim()
        $trackingRaw = (Cell $row "物流单号" $col).Trim()
        $shopeeId = (Cell $row "关联Shopee订单号" $col).Trim()
        $parsed = Parse-Tracking $trackingRaw
        $rec = [ordered]@{
            record_id    = $raw.data.record_id_list[$i]
            order_1688   = (Cell $row "1688订单号" $col)
            tracking_raw = $trackingRaw
            status       = $status
            supplier     = (Cell $row "供应商" $col)
            product      = (Cell $row "商品名" $col)
            shopee_id    = $shopeeId
            parsed       = $parsed
        }
        # 待录单判定：已发货 + 解析出承运商/单号 + 关联了Shopee订单
        $needs = ($status -eq "已发货" -and $null -ne $parsed -and $shopeeId -ne "")
        $rec["needs_backfill"] = $needs
        if (-not $needs) {
            if ($status -eq "已取消") { $rec["skipReason"] = "已取消，不录单" }
            elseif ($status -eq "待发货") { $rec["skipReason"] = "待发货/未付款，无真实单号" }
            elseif ($null -eq $parsed) { $rec["skipReason"] = "物流单号缺失或无法解析" }
            elseif ($shopeeId -eq "") { $rec["skipReason"] = "缺关联Shopee订单号" }
            else { $rec["skipReason"] = "非待录单状态" }
        }
        $records += [PSCustomObject]$rec
    }
    return $records
}

function Submit-ToQianheng {
    param(
        [string]$ShopeeOrderId,
        [string]$CarrierName,   # 千恒下拉中的完整名称，如"申通快递"
        [string]$TrackingNo
    )

    Write-Log "  打开千恒订单页..." "Cyan"
    # 先创建/恢复 task（幂等）
    cmd.exe /d /c "`"$TabbitCli`" create --task `"$TaskName`"" 2>&1 | Out-Null

    # 步骤1：导航到待提交打包页；先做登录态检测，再按 Shopee 订单号定位行、点"代打包"
    # 【关键修复 2026-10-19】Tabbit nodejs 程序顶层无 document/window，
    #   DOM 读取/操作必须包进 page.evaluate()，否则报 "document is not defined" 导致误判"未找到订单"。
    $js1 = @"
const tab = await context.newPage();
let out = { found: false, authExpired: false, msg: "" };
try {
  await tab.goto("$QianhengOrderUrl", { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 5000));

  // 登录失效前置检测：页面内文命中"登录失效/授权过期/重新登录"即中止，不填不点
  const authProbe = await tab.evaluate(() => {
    const text = document.body ? document.body.innerText || '' : '';
    const AUTH_RE = /$KhAuthExpiredPattern/;
    return { authExpired: AUTH_RE.test(text) };
  });
  if (authProbe.authExpired) {
    out = { found: false, authExpired: true, msg: "千恒登录态失效/授权过期，需人工重新登录" };
  } else {
    // 找到包含 ShopeeOrderId 的可见行（待提交打包列表），点行内"代打包"按钮
    const found = await tab.evaluate((orderText) => {
      const candidates = [...document.querySelectorAll("tr, .order-item, [class*='order'], li, div")];
      let targetRow = null;
      for (const row of candidates) {
        if (row.offsetParent !== null && row.textContent.includes(orderText)) { targetRow = row; break; }
      }
      if (!targetRow) return { found: false, modalOpen: false };
      const btn = targetRow.querySelector(".J_editPacking, a[class*='packing'], button");
      if (btn) btn.click();
      return { found: true, modalOpen: true };
    }, "$ShopeeOrderId");
    await new Promise(r => setTimeout(r, 2500));
    const modalOpen = await tab.evaluate(() =>
      [...document.querySelectorAll(".ivu-modal")].some(m => m.offsetParent !== null));
    out = { found: found.found, authExpired: false, modalOpen, msg: "" };
  }
} catch (e) {
  out = { found: false, authExpired: false, msg: String(e.message || e) };
} finally {
  await tab.close().catch(() => {});
}
return out;
"@
    $r1 = Invoke-TabbitJs -TaskName $TaskName -RequestId "find-$ShopeeOrderId-$(Get-Random)" -JsCode $js1
    Write-Log "  打开代打包弹窗: $r1" "Gray"

    # 登录失效：立即中止，不继续填单
    if ($r1 -match '"authExpired":true') {
        return @{ success = $false; authExpired = $true; msg = "千恒登录态失效/授权过期，请人工重新登录 qianheng.huoxiaoyi.com 后重试" }
    }
    # 队列里找不到该订单 = 已录/已签收/不在待提交打包，按"已录跳过"处理，不算失败、不重试、不重复提交
    if ($r1 -notmatch '"found":true') {
        return @{ success = $true; skippedAlready = $true; submitted = $false; authExpired = $false;
                  msg = "待提交打包队列未找到 $ShopeeOrderId（已录/已签收/不在队列），跳过，不重复提交" }
    }

    # 步骤2：在 modal 内填写快递单号（所有可见 input 都填）
    $js2 = @"
const tab = await context.newPage();
let out = { filled: false, msg: "" };
try {
  await tab.goto("$QianhengOrderUrl", { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 5000));
  const res = await tab.evaluate((trackingNo) => {
    const modal = [...document.querySelectorAll(".ivu-modal")].find(m => m.offsetParent !== null && m.textContent.includes("代打包"));
    if (!modal) return { filled: false, msg: "modal not found" };
    const inputs = [...modal.querySelectorAll("input")].filter(inp =>
        inp.offsetParent !== null &&
        (inp.placeholder || "").includes("快递单号"));
    for (const inp of inputs) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(inp, trackingNo);
      inp.dispatchEvent(new Event("input", { bubbles: true }));
      inp.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return { filled: true, count: inputs.length };
  }, "$TrackingNo");
  out = res;
} catch (e) {
  out = { filled: false, msg: String(e.message || e) };
} finally {
  await tab.close().catch(() => {});
}
return out;
"@
    $r2 = Invoke-TabbitJs -TaskName $TaskName -RequestId "fill-$ShopeeOrderId-$(Get-Random)" -JsCode $js2
    Write-Log "  填写单号: $r2" "Gray"

    # 步骤3：为每个物流公司 Select 选择承运商（坐标点击法）
    $carrierFull = "$CarrierName"

    # 获取物流公司 input 的位置信息（page.evaluate 内取坐标）
    $js3 = @"
const tab = await context.newPage();
let out = { ok: false };
try {
  await tab.goto("$QianhengOrderUrl", { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 5000));
  const res = await tab.evaluate(() => {
    const modal = [...document.querySelectorAll(".ivu-modal")].find(m => m.offsetParent !== null && m.textContent.includes("代打包"));
    if (!modal) return { ok: false, positions: [] };
    const selects = [...modal.querySelectorAll("input")].filter(inp =>
        inp.offsetParent !== null &&
        (inp.placeholder || "").includes("物流公司"));
    const positions = selects.map(inp => {
      const rect = inp.getBoundingClientRect();
      return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
    });
    return { ok: true, positions };
  });
  out = res;
} catch (e) {
  out = { ok: false, positions: [], msg: String(e.message || e) };
} finally {
  await tab.close().catch(() => {});
}
return out;
"@
    $r3 = Invoke-TabbitJs -TaskName $TaskName -RequestId "pos-$ShopeeOrderId-$(Get-Random)" -JsCode $js3
    Write-Log "  物流公司 input 位置: $r3" "Gray"

    # 解析 positions（Tabbit result 结构：status.succeeded 时 value 直接可用）
    $positions = @()
    try {
        if ($r3 -match '"ok":true') {
            $m3 = [regex]::Match($r3, '\{"result":\{.*?\}\},"status"')
            if ($m3.Success) {
                $parsed = $m3.Value.Substring(0, $m3.Value.Length - 9) | ConvertFrom-Json
                $val = $parsed.result.value
                if ($val.positions) { $positions = @($val.positions) }
            }
        }
    } catch { Write-Log "  positions 解析失败: $($_.Exception.Message)" "Yellow" }

    # 对每个 position：新开页面导航→点开下拉→点承运商选项（坐标点击必须在页面上下文中执行）
    foreach ($pos in $positions) {
        $px = [int]$pos.x
        $py = [int]$pos.y
        $jsClick = @"
const tab = await context.newPage();
let out = { selected: false };
try {
  await tab.goto("$QianhengOrderUrl", { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 5000));
  await tab.mouse.click($px, $py);
  await new Promise(r => setTimeout(r, 1200));
  const selected = await tab.evaluate((carrierFull) => {
    const options = [...document.querySelectorAll(".ivu-select-dropdown li, .ivu-select-item, li")].filter(li =>
        li.offsetParent !== null && li.textContent.trim() === carrierFull);
    if (options.length > 0) {
      const rect = options[0].getBoundingClientRect();
      return { found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
    }
    return { found: false };
  }, "$carrierFull");
  if (selected.found) {
    await tab.mouse.click(selected.x, selected.y);
    await new Promise(r => setTimeout(r, 800));
    out = { selected: true };
  }
} catch (e) {
  out = { selected: false, msg: String(e.message || e) };
} finally {
  await tab.close().catch(() => {});
}
return out;
"@
        $rc = Invoke-TabbitJs -TaskName $TaskName -RequestId "sel-$ShopeeOrderId-$(Get-Random)" -JsCode $jsClick
        Write-Log "  选承运商: $rc" "Gray"
    }

    # 步骤4：提交；成功判据 = 弹窗关闭 + 首公里预报行出现"【首公里预报】承运商 单号"
    $js4 = @"
const tab = await context.newPage();
let out = { submitted: false, forecastFound: false, authExpired: false };
try {
  await tab.goto("$QianhengOrderUrl", { waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 5000));
  const clickSubmit = await tab.evaluate(() => {
    const btn = document.querySelector(".J_orderEditorDialogSubmit");
    if (btn) { btn.click(); return true; }
    return false;
  });
  await new Promise(r => setTimeout(r, 6000));
  const res = await tab.evaluate((carrierFull, trackingNo) => {
    const modalOpen = [...document.querySelectorAll(".ivu-modal")].some(m => m.offsetParent !== null && m.textContent.includes("代打包"));
    const afterText = document.body ? document.body.innerText || "" : "";
    const forecastFound = afterText.includes("首公里预报")
      && afterText.includes(carrierFull)
      && afterText.includes(trackingNo);
    const authExpired = /$KhAuthExpiredPattern/.test(afterText);
    return { modalOpen, forecastFound, authExpired };
  }, "$carrierFull", "$TrackingNo");
  out = { submitted: clickSubmit && !res.modalOpen, forecastFound: res.forecastFound, authExpired: res.authExpired };
} catch (e) {
  out = { submitted: false, forecastFound: false, authExpired: false, msg: String(e.message || e) };
} finally {
  await tab.close().catch(() => {});
}
return out;
"@
    $r4 = Invoke-TabbitJs -TaskName $TaskName -RequestId "submit-$ShopeeOrderId-$(Get-Random)" -JsCode $js4
    Write-Log "  提交结果: $r4" "Green"

    $submitted = ($r4 -match '"submitted":true')
    $forecast = ($r4 -match '"forecastFound":true')
    if ($r4 -match '"authExpired":true') {
        return @{ success = $false; authExpired = $true; msg = "千恒登录态失效，请重新登录后重试" }
    }
    # 弹窗关闭但首公里预报未回读到，视为未完全成功（可能多SKU/校验失败），返回待人工核对
    return @{ success = ($submitted -and $forecast); submitted = $submitted; forecastFound = $forecast;
              msg = $(if ($submitted -and $forecast) { "已提交且首公里预报回读成功" } elseif ($submitted) { "弹窗已关闭但未回读到首公里预报，请人工核对" } else { "提交未成功（弹窗未关闭/校验失败）" }) }
}

function Update-FeishuRecord {
    <# 仅当飞书物流单号缺失时补写"承运商简称 运单号"（1688 S8 通常已填，此处幂等兜底）。 #>
    param([string]$RecordId, [string]$CarrierShort, [string]$TrackingNo)
    $trackingText = "$CarrierShort $TrackingNo"
    $json = "{`"update_records`":{`"$RecordId`":{`"物流单号`":`"$trackingText`"}}}"
    $tmpJson = [System.IO.Path]::GetTempFileName() + ".json"
    [System.IO.File]::WriteAllText($tmpJson, $json, [Text.UTF8Encoding]::new($false))
    try {
        & $LarkCli base +record-batch-update --base-token $BaseToken --table-id $TrackingTableId --json "@$tmpJson" --as user 2>&1 | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        Remove-Item $tmpJson -ErrorAction SilentlyContinue
    }
}

# ===================== 主流程 =====================

Write-Log "===== 千恒货代快递单号回填（#50 千恒录单固化）=====" "Cyan"
Write-Log "lark-cli: $LarkCli" "Gray"

# 单条模式
if ($ShopeeOrderId -and $Carrier -and $TrackingNo) {
    $carrierFull = if ($CarrierMap[$Carrier]) { $CarrierMap[$Carrier] } else { $Carrier }
    Write-Log "单条模式: Shopee=$ShopeeOrderId, 承运商=$carrierFull, 单号=$TrackingNo" "White"
    if ($DryRun) {
        Write-Log "[DryRun] 将导航千恒待提交打包→定位 $ShopeeOrderId→填单号 $TrackingNo→选 $carrierFull→提交并回读首公里预报（不实际提交）" "Yellow"
        exit 0
    }
    # 去重闸门在 Submit 内部：只对待提交队列里明确存在的订单提交，找不到即跳过（已录/已签收）
    $result = Submit-ToQianheng -ShopeeOrderId $ShopeeOrderId -CarrierName $carrierFull -TrackingNo $TrackingNo
    if ($result.skippedAlready) {
        Write-Log "⏭️ 已录跳过: $ShopeeOrderId / $carrierFull / $TrackingNo（待提交队列无此单，不重复提交）" "Yellow"
        exit 0
    }
    if ($result.authExpired) {
        Write-Log "⛔ $($result.msg)" "Red"
        exit 2
    }
    if ($result.success) {
        Write-Log "✅ 千恒提交成功：$ShopeeOrderId / $carrierFull / $TrackingNo（首公里预报已回读）" "Green"
    } else {
        Write-Log "❌ 千恒未完全成功: $($result.msg)" "Red"
        exit 1
    }
    exit 0
}

# 批量模式
if ($Batch) {
    Write-Log "批量模式：从飞书读取采购跟踪表..." "White"
    $all = Get-PendingRecords
    $pending = @($all | Where-Object { $_.needs_backfill })
    $skipped = @($all | Where-Object { -not $_.needs_backfill })

    Write-Log "`n=== 待录单（已发货+真实单号+关联Shopee）：$($pending.Count) 条 ===" "Yellow"
    foreach ($p in $pending) {
        Write-Log ("  · {0} | {1} | {2} | {3} {4}" -f $p.shopee_id, $p.product, $p.supplier, $p.parsed.carrierFull, $p.parsed.trackingNo) "White"
    }
    Write-Log "`n=== 跳过：$($skipped.Count) 条 ===" "Gray"
    foreach ($s in $skipped) {
        $sid = if ($s.shopee_id) { $s.shopee_id } else { "-" }
        Write-Log ("  · {0} | {1} | {2}" -f $sid, $s.product, $s.skipReason) "Gray"
    }

    if ($pending.Count -eq 0) {
        Write-Log "没有待录单记录" "Green"
        exit 0
    }
    if ($DryRun) {
        Write-Log "`n[DryRun] 以上待录单将逐条提交，不实际提交" "Yellow"
        exit 0
    }

    $ok = 0; $fail = 0; $skip = 0; $authStop = $false
    foreach ($rec in $pending) {
        Write-Log "`n处理: $($rec.shopee_id) - $($rec.product) [$($rec.parsed.carrierFull) $($rec.parsed.trackingNo)]" "Cyan"
        $result = Submit-ToQianheng -ShopeeOrderId $rec.shopee_id -CarrierName $rec.parsed.carrierFull -TrackingNo $rec.parsed.trackingNo
        if ($result.skippedAlready) {
            Write-Log "⏭️ 已录跳过: $($rec.shopee_id) — $($result.msg)" "Yellow"; $skip++; continue
        }
        if ($result.authExpired) {
            Write-Log "⛔ 千恒登录态失效，停止批量：$($result.msg)" "Red"
            $authStop = $true; break
        }
        if ($result.success) {
            Write-Log "✅ 成功: $($rec.shopee_id)" "Green"; $ok++
        } else {
            Write-Log "❌ 失败: $($rec.shopee_id) — $($result.msg)" "Red"; $fail++
        }
    }
    Write-Log "`n===== 批量结束：成功 $ok / 跳过已录 $skip / 失败 $fail$(if ($authStop) { " / 登录失效中断" }) =====" "Cyan"
    if ($authStop) { exit 2 }
    exit $(if ($fail -gt 0) { 1 } else { 0 })
}

# 无参数时显示帮助
Write-Host "`n用法:" -ForegroundColor Cyan
Write-Host "  单条: .\qianheng-tracking-backfill.ps1 -ShopeeOrderId <订单号> -Carrier <申通/圆通/...> -TrackingNo <运单号>"
Write-Host "  批量: .\qianheng-tracking-backfill.ps1 -Batch [-DryRun]"
Write-Host "`n示例:"
Write-Host '  .\qianheng-tracking-backfill.ps1 -ShopeeOrderId 2610109QQ0S3WC -Carrier 申通 -TrackingNo 773445887926488'
Write-Host '  .\qianheng-tracking-backfill.ps1 -Batch -DryRun'
