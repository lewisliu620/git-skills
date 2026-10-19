# ffmpeg 命令模板库（动态绘本合成）

> 全部命令在 Windows PowerShell 下验证通过。`$ff` = ffmpeg 路径（Doubao sandbox runtime，ffprobe 不存在）。字体用微软雅黑 `C\:/Windows/Fonts/msyh.ttc`（冒号转义 `C\:`）。

## 目录

- 环境与变量
- 单窗生成（zoompan 运镜表达式库）
- 片头/预告 drawtext
- 窗口拼接（concat）
- 字幕烧录（ASS）
- 音频处理（loudnorm / adelay / 拼接）
- 成片合成（一键命令）

---

## 环境与变量

```powershell
$ff = "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\sandbox_runtime\bases\c98c5042338ed152c6f10ecd8591889f\python\ffmpeg.exe"
$dir = "C:\Users\Administrator\DoubaoWork\chats\2026-10-05\new-chat-1"
Set-Location $dir
```

## 单窗生成（zoompan 运镜表达式库，V1.19 无抖动版）

> **V1.19 修复 zoompan 抖动（业界 best practice，ffmpeg ticket #4298）**：zoompan 内部把裁剪窗口坐标/尺寸截断为整像素，慢速移动会逐帧整数跳动（画面微抖/顿挫）。修复三件套：
> ① **输入升采样**：`scale=2160:3840:flags=lanczos`（源图先放大到 2x，让舍入误差小于一个输出像素，同时防 zoompan 默认重采样到 1280x720 导致的模糊）；
> ② **zoompan 中间画布**：`s=2160x3840`（2x），最后 `scale=1080:1920:flags=lanczos` 降回（抖动被压缩到亚像素）；
> ③ **余弦缓动**：`Ease=(1-cos(PI*on/D))/2`（on=输出帧号，D=帧数-1），z/x/y 全部用缓动曲线，禁止线性匀速（匀速产生机械感且高速段抖动最明显）。
> 统一 `fps=30`（手机播放更顺，替代 25）；drawtext 一律叠加在最终 `scale` 之后（字号按 1080x1920 稳定）。

统一前置：`-loop 1 -i 图.jpg` + `-vf "scale=2160:3840:flags=lanczos,zoompan=...:s=2160x3840:fps=30,scale=1080:1920:flags=lanczos"`，`d` = 帧数 = 时长秒 × 30，`Ease=(1-cos(PI*on/D))/2`。

| 运镜 | zoompan 表达式（z/x/y） | 适用 |
|---|---|---|
| 推近 | `z='1+0.35*(1-cos(PI*on/D))/2'`、`x='iw/2-(iw/zoom/2)'`、`y='ih/2-(ih/zoom/2)'` | 特写引入 |
| 慢推 | `z='1+0.25*(1-cos(PI*on/D))/2'` 同上 | 长段旁白 |
| 横移→右 | `z='1.15'`、`x='(iw-iw/zoom)*((1-cos(PI*on/D))/2)'`、`y='ih/2-(ih/zoom/2)'` | 场景扫视 |
| 横移→左 | `z='1.15'`、`x='(iw-iw/zoom)*(1-(1-cos(PI*on/D))/2)'` | 反向扫视 |
| 上摇 | `z='1.3'`、`x='iw/2-(iw/zoom/2)'`、`y='(ih-ih/zoom)*(1-(1-cos(PI*on/D))/2)'` | 仰视 |
| 下摇 | `z='1.3'`、`y='(ih-ih/zoom)*((1-cos(PI*on/D))/2)'` | 俯视 |
| 静止 | `z='1'`、`x='iw/2-(iw/zoom/2)'`、`y='ih/2-(ih/zoom/2)'` | 预告卡 |

示例（4s 推近窗，d=120）：

```powershell
& $ff -y -loglevel error -loop 1 -i "ep3_images\shot04_全家挖山.png" -vf "scale=2160:3840:flags=lanczos,zoompan=z='1+0.35*(1-cos(PI*on/119))/2':d=120:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=2160x3840:fps=30,scale=1080:1920:flags=lanczos" -t 4 -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p "ep3_video\w05.mp4"
```

## 片头/预告 drawtext（叠加在 zoompan 后，用 `,` 连接）

片头标题（0-3s 显示两行）：

```powershell
,drawtext=fontfile='C\:/Windows/Fonts/msyh.ttc':text='米米森林奇遇记':fontsize=76:fontcolor=white:borderw=6:bordercolor=0x4A90E2:x=(w-text_w)/2:y=h*0.16:enable='between(t,0,3)',drawtext=fontfile='C\:/Windows/Fonts/msyh.ttc':text='第 1 集 · 米米的新围巾':fontsize=42:fontcolor=0xFF6B6B:borderw=4:bordercolor=white:x=(w-text_w)/2:y=h*0.16+110:enable='between(t,0,3)'
```

预告卡（全片尾窗 3s）：

```powershell
,drawtext=fontfile='C\:/Windows/Fonts/msyh.ttc':text='第 2 集预告 · 米米学会一句神奇的话':fontsize=44:fontcolor=white:borderw=4:bordercolor=0x4A90E2:box=1:boxcolor=0x000000@0.35:boxborderw=26:x=(w-text_w)/2:y=h*0.72
```

## 窗口拼接（concat）

**list 文件必须用绝对路径 + 正斜杠**（相对路径会被拼上 list 目录前缀）：

```powershell
$list = @(); for ($i = 1; $i -le 16; $i++) { $n = "{0:D2}" -f $i; $list += "file 'C:/Users/Administrator/DoubaoWork/chats/2026-10-05/new-chat-1/ep1_video/w$n.mp4'" }
[System.IO.File]::WriteAllLines("$dir\ep1_video\concat.txt", $list, (New-Object System.Text.UTF8Encoding $false))
& $ff -y -loglevel error -f concat -safe 0 -i "ep1_video\concat.txt" -c copy "ep1_video\full_silent.mp4"
```

## 字幕烧录（ASS）

ASS 模板见第 1 集 `ep1_sub_v5.ass`：`PlayResX 1080 / PlayResY 1920`，Style 微软雅黑 52、白字描边、底部 MarginV 230。烧录（**`-vf` 必须放在输出文件前**）：

```powershell
-vf "ass='ep1_sub_v5.ass'"
```

## 音频处理

响度归一化（每段拼接前，消除忽大忽小）：

```powershell
& $ff -y -i "seg$i.wav" -af "loudnorm=I=-16:TP=-1.5:LRA=11" -ar 44100 -ac 2 "seg${i}_norm.wav"
```

成片音轨延迟 3s 进（片头）：

```powershell
-filter_complex "[1:a]adelay=3000|3000,apad[a]" -map 0:v -map "[a]"
```

## 成片合成（一键）

```powershell
& $ff -y -loglevel error -i "ep1_video\full_silent.mp4" -i "米米的新围巾_多角色配音.mp3" -filter_complex "[1:a]adelay=3000|3000,apad[a]" -map 0:v -map "[a]" -vf "ass='ep1_sub_v5.ass'" -t 141.71 -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 192k "米米的新围巾_第1集成片_v5.mp4"
```

> `-t` 总时长 = 片头 3s + 配音时长 + 预告 3s（第 1 集：3 + 135.71 + 3 = 141.71s）。
