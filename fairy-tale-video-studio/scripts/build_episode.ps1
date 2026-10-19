# ============================================================
# build_episode.ps1 — 童话故事短视频（动态绘本）一键合成脚本
# 用法：
#   powershell -File build_episode.ps1 -ProjectDir "C:\...\new-chat-1" `
#     -WindowsCsv "windows.csv" -Audio "米米的新围巾_多角色配音.mp3" `
#     -SubAss "ep1_sub.ass" -OutFile "第2集成片.mp4" `
#     -TitleText "米米森林奇遇记" -TitleSub "第 2 集 · 一句谢谢" `
#     -TeaserText "第 3 集预告 · 谁打碎了花瓶"
#
# windows.csv 格式（无表头，值内不要含逗号）：
#   window,image,start,end,motion,pan
#   w01,shot01_森林冬景.jpg,0,9,zoom,center
#   w02,shot02_米米围巾特写.jpg,9,24,zoom,center
#   ...
# motion: zoom(推近) | pan(横移) | tilt(上/下摇) | hold(静止)
# pan:    center | left | right | up | down （zoom/hold 时忽略，填 center）
# ============================================================
param(
    [string]$ProjectDir = (Get-Location).Path,
    [string]$ImagesDir = "",
    [string]$WindowsCsv = "windows.csv",
    [string]$OutDir = "",
    [string]$Ffmpeg = "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\sandbox_runtime\bases\c98c5042338ed152c6f10ecd8591889f\python\ffmpeg.exe",
    [int]$Fps = 30,
    [string]$TitleText = "",
    [string]$TitleSub = "",
    [string]$TeaserText = "",
    [string]$SubAss = "",
    [string]$Audio = "",
    [int]$AdelayMs = 3000,
    [string]$TitleWin = "0,3",
    [string]$OutFile = "成片.mp4"
)

Set-Location $ProjectDir
if (-not (Test-Path $Ffmpeg)) { Write-Error "找不到 ffmpeg: $Ffmpeg"; exit 1 }
if ($ImagesDir -eq "") { $ImagesDir = $ProjectDir }
if ($OutDir -eq "") { $OutDir = Join-Path $ProjectDir "ep1_video\build" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$lines = [System.IO.File]::ReadAllLines($WindowsCsv, (New-Object System.Text.UTF8Encoding $false))
$windows = @()
foreach ($l in $lines) {
    $t = $l.Trim()
    if ($t -eq "" -or $t.StartsWith("#")) { continue }
    $p = $t -split ","
    if ($p.Count -lt 6) { continue }
    if ($p[0] -eq "window") { continue }   # 兼容带表头的 CSV
    $windows += [PSCustomObject]@{
        Window = $p[0]; Image = $p[1]; Start = [double]$p[2]; End = [double]$p[3]
        Motion = $p[4]; Pan = $p[5]
    }
}
if ($windows.Count -eq 0) { Write-Error "windows.csv 为空或格式错误"; exit 1 }
Write-Output "读取 $($windows.Count) 个窗口"

$fontfile = 'C\:/Windows/Fonts/msyh.ttc'
function Escape-DrawText([string]$s) {
    return $s.Replace(':', '\:').Replace(',', '\,').Replace("'", "\'")
}

$idx = 0
$list = @()
foreach ($w in $windows) {
    $idx++
    $img = Join-Path $ImagesDir $w.Image
    if (-not (Test-Path $img)) { Write-Error "缺图: $img"; exit 1 }
    $dur = $w.End - $w.Start
    if ($dur -le 0) { Write-Error "窗口 $($w.Window) 时长非法"; exit 1 }
    $d = [int][math]::Round($dur * $Fps)
    $D = $d - 1

    # 运镜表达式（V1.19 修复 zoompan 抖动：余弦缓动替代线性匀速，业界 best practice）
    # 抖动根因：zoompan 内部把裁剪窗口坐标/尺寸截断为整像素（ffmpeg ticket #4298），慢速移动逐帧整数跳动
    # 修复三件套：①输入升采样到 2160x3840（lanczos）②zoompan 中间画布 s=2160x3840，输出再降回 1080x1920
    #           ③z/x/y 用余弦缓动 (1-cos(PI*on/D))/2，杜绝匀速机械感与跳变；fps=30
    $Ease = "(1-cos(PI*on/$D))/2"
    $z = "1"; $x = "iw/2-(iw/zoom/2)"; $y = "ih/2-(ih/zoom/2)"
    switch ($w.Motion) {
        "zoom" {
            $z = "1+0.35*$Ease"
        }
        "slowzoom" {
            $z = "1+0.25*$Ease"
        }
        "pan" {
            $z = "1.15"
            if ($w.Pan -eq "left") { $x = "(iw-iw/zoom)*(1-$Ease)" }
            else { $x = "(iw-iw/zoom)*$Ease" }
        }
        "tilt" {
            $z = "1.3"
            if ($w.Pan -eq "down") { $y = "(ih-ih/zoom)*$Ease" }
            else { $y = "(ih-ih/zoom)*(1-$Ease)" }
        }
        default { $z = "1" }  # hold
    }

    # 升采样 → zoompan(2x 中间画布) → 降回 1080x1920 → drawtext（drawtext 在最终分辨率上叠加，字号稳定）
    $vf = "scale=2160:3840:flags=lanczos,zoompan=z='${z}':d=${d}:x='${x}':y='${y}':s=2160x3840:fps=${Fps},scale=1080:1920:flags=lanczos"

    # 片头标题（第 1 窗）与预告（最后 1 窗）——TitleWin 控制显示窗口（紧凑片头 1.5s 传 "0,1.5"，与 AdelayMs 同步）
    if ($idx -eq 1 -and $TitleText -ne "") {
        $t1 = Escape-DrawText $TitleText
        $vf += ",drawtext=fontfile='$fontfile':text='$t1':fontsize=76:fontcolor=white:borderw=6:bordercolor=0x4A90E2:x=(w-text_w)/2:y=h*0.16:enable='between(t,$TitleWin)'"
        if ($TitleSub -ne "") {
            $t2 = Escape-DrawText $TitleSub
            $vf += ",drawtext=fontfile='$fontfile':text='$t2':fontsize=42:fontcolor=0xFF6B6B:borderw=4:bordercolor=white:x=(w-text_w)/2:y=h*0.16+110:enable='between(t,$TitleWin)'"
        }
    }
    if ($idx -eq $windows.Count -and $TeaserText -ne "") {
        $t3 = Escape-DrawText $TeaserText
        $vf += ",drawtext=fontfile='$fontfile':text='$t3':fontsize=44:fontcolor=white:borderw=4:bordercolor=0x4A90E2:box=1:boxcolor=0x000000@0.35:boxborderw=26:x=(w-text_w)/2:y=h*0.72"
    }

    $out = Join-Path $OutDir "$($w.Window).mp4"
    Write-Output "生成 $($w.Window) ($dur s, $($w.Motion)/$($w.Pan))"
    # 滤镜图写入临时文件，用 -filter_script 读取，避免命令行引号转义问题
    $vfFile = Join-Path $OutDir "vf_$($w.Window).txt"
    [System.IO.File]::WriteAllText($vfFile, $vf, (New-Object System.Text.UTF8Encoding $false))
    & $Ffmpeg -y -loglevel error -loop 1 -i $img -filter_script $vfFile -t $dur -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p $out
    if ($LASTEXITCODE -ne 0) { Write-Error "窗口 $($w.Window) 生成失败"; exit 1 }
    $list += "file '$($out.Replace('\', '/'))'"
}

# 拼接
$concatTxt = Join-Path $OutDir "concat.txt"
[System.IO.File]::WriteAllLines($concatTxt, $list, (New-Object System.Text.UTF8Encoding $false))
$silent = Join-Path $OutDir "full_silent.mp4"
Write-Output "拼接窗口..."
& $Ffmpeg -y -loglevel error -f concat -safe 0 -i $concatTxt -c copy $silent
if ($LASTEXITCODE -ne 0) { Write-Error "拼接失败"; exit 1 }

# 合成成片（烧字幕 + 合音频，统一走复杂滤镜图脚本，避免引号/盘符冒号问题）
$args2 = @("-y", "-loglevel", "error", "-i", $silent)
$hasAudio = ($Audio -ne "" -and (Test-Path $Audio))
if ($hasAudio) { $args2 += @("-i", $Audio) }

$fc = "[0:v]"
if ($SubAss -ne "") {
    $assPath = $SubAss.Replace('\', '/').Replace(':', '\:')
    $fc += "ass='$assPath'"
}
$fc += "[v]"
if ($hasAudio) { $fc += ";[1:a]adelay=$AdelayMs|$AdelayMs,apad[a]" }
$fcFile = Join-Path $OutDir "fc_graph.txt"
[System.IO.File]::WriteAllText($fcFile, $fc, (New-Object System.Text.UTF8Encoding $false))
$args2 += @("-filter_complex_script", $fcFile, "-map", "[v]")
if ($hasAudio) { $args2 += @("-map", "[a]") }
$args2 += @("-c:v", "libx264", "-preset", "fast", "-crf", "20")
if ($hasAudio) { $args2 += @("-c:a", "aac", "-b:a", "192k") }
$args2 += @("-pix_fmt", "yuv420p", $OutFile)
Write-Output "合成成片: $OutFile"
& $Ffmpeg @args2
if ($LASTEXITCODE -ne 0) { Write-Error "成片合成失败"; exit 1 }

$total = ($windows | Measure-Object -Property End -Sum).Sum
Write-Output "完成：$($windows.Count) 窗，总时长 $([math]::Round($total,1))s → $OutFile"
