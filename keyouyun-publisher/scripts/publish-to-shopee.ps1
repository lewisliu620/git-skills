# ============================================================
# publish-to-shopee.ps1 - 客优云发布到Shopee一键执行脚本
# 零截图，纯Tabbit CLI DOM操作
#
# 用法：
#   .\publish-to-shopee.ps1 -OfferUrl "https://detail.1688.com/offer/xxx.html" `
#     -ThaiTitle "สติกเกอร์..." -PriceCNY 10 -CostCNY 0.6 -Stock 500 `
#     -CategoryThai "อุปกรณ์เสริมโทรศัพท์" `
#     -ImagePaths '["C:/img1.jpg","C:/img2.jpg"]' -VideoPath "C:/video.mp4" `
#     -TaskName "发布手机贴纸"
# ============================================================

param(
    [Parameter(Mandatory=$true)][string]$OfferUrl,
    [string]$OfferId = "",
    [string]$ThaiTitle = "",
    [decimal]$PriceCNY = 0,
    [decimal]$CostCNY = 0,
    [int]$Stock = 500,
    [string]$CategoryThai = "",
    [string]$DescriptionThai = "",
    [string]$ImagePaths = "[]",
    [string]$VideoPath = "",
    [string]$TaskName = "客优云发布",
    [ValidateSet("collect","edit","upload","publish","all")][string]$Step = "all"
)

$ErrorActionPreference = "Stop"
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $tabbitCli)) {
    Write-Error "tabbit-cli not found at $tabbitCli"
    exit 1
}

# 从URL提取offer ID
if (-not $OfferId) {
    if ($OfferUrl -match '/offer/(\d+)') {
        $OfferId = $Matches[1]
    } else {
        $OfferId = "unknown"
    }
}

# 默认泰文描述（如果没传）
if (-not $DescriptionThai) {
    $DescriptionThai = @"
ที่มา：จีน
สไตล์：ทันสมัย
วัสดุ：คุณภาพดี

🔹 ส่วนลดค่าจัดส่งไม่ประจำสำหรับสินค้าทุกชิ้นในร้าน
📣 กดติดตามร้านของเราเพื่อรับคูปองส่วนลดจำกัดเวลา
📣 สินค้าใหม่ ลดราคาพิเศษ ไม่พลาดการอัปเดตโปรโมชั่นล่าสุด
🔹 หากสต็อกสินค้าผิดปกติ เวลาจัดส่งจะแจ้งให้ทราบภายหลัง
💯 สินค้าทุกชิ้นในสต็อกพร้อมจัดส่งทันที
📣 ขนาดอาจมีความคลาดเคลื่อนเล็กน้อยจากการวัดด้วยมือ
📣 สินค้าอาจมีความแตกต่างจากภาพถ่าย ทั้งนี้ให้ยึดตามผลิตภัณฑ์จริง
"@
}

function Invoke-TabbitJS {
    param([string]$JsCode, [string]$RequestId)
    $tmpFile = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmpFile, $JsCode, [Text.UTF8Encoding]::new($false))
        $cmd = "`"$tabbitCli`" nodejs --task `"$TaskName`" --request-id `"$RequestId`" --timeout-ms 120000 < `"$tmpFile`""
        $result = cmd.exe /d /c $cmd 2>&1
        return $result | Out-String
    } finally {
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    }
}

# Step 1: 采集
if ($Step -eq "collect" -or $Step -eq "all") {
    Write-Host "=== Step 1: 采集商品 ===" -ForegroundColor Cyan
    $template = Get-Content "$scriptDir\collect-and-publish.js" -Raw -Encoding UTF8
    $js = $template.Replace("{{OFFER_URL}}", $OfferUrl).Replace("{{TASK_NAME}}", $TaskName)
    $result = Invoke-TabbitJS -JsCode $js -RequestId "collect-$OfferId"
    Write-Host $result
}

# Step 2: 编辑
if ($Step -eq "edit" -or $Step -eq "all") {
    Write-Host "=== Step 2: 编辑商品信息 ===" -ForegroundColor Cyan
    $template = Get-Content "$scriptDir\edit-product.js" -Raw -Encoding UTF8
    $js = $template.Replace("{{OFFER_ID}}", $OfferId)
    $js = $js.Replace("{{THAI_TITLE}}", $ThaiTitle)
    $js = $js.Replace("{{PRICE_CNY}}", $PriceCNY.ToString())
    $js = $js.Replace("{{COST_CNY}}", $CostCNY.ToString())
    $js = $js.Replace("{{STOCK}}", $Stock.ToString())
    $js = $js.Replace("{{CATEGORY_THAI}}", $CategoryThai)
    $js = $js.Replace("{{DESCRIPTION_THAI}}", $DescriptionThai)
    $result = Invoke-TabbitJS -JsCode $js -RequestId "edit-$OfferId"
    Write-Host $result
}

# Step 3: 上传素材
if ($Step -eq "upload" -or $Step -eq "all") {
    Write-Host "=== Step 3: 上传图片和视频 ===" -ForegroundColor Cyan
    $template = Get-Content "$scriptDir\upload-media.js" -Raw -Encoding UTF8
    $js = $template.Replace("{{OFFER_ID}}", $OfferId)
    $js = $js.Replace("{{IMAGE_PATHS}}", $ImagePaths)
    $js = $js.Replace("{{VIDEO_PATH}}", $VideoPath)
    $result = Invoke-TabbitJS -JsCode $js -RequestId "upload-$OfferId"
    Write-Host $result
}

# Step 4: 最终发布
if ($Step -eq "publish" -or $Step -eq "all") {
    Write-Host "=== Step 4: 最终发布 ===" -ForegroundColor Cyan
    $template = Get-Content "$scriptDir\final-publish.js" -Raw -Encoding UTF8
    $js = $template.Replace("{{OFFER_ID}}", $OfferId)
    $result = Invoke-TabbitJS -JsCode $js -RequestId "publish-$OfferId"
    Write-Host $result
}

Write-Host "`n=== 完成 ===" -ForegroundColor Green
