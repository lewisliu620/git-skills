---
name: shortvideo-mp4-finalize
description: |
  ffmpeg 合成竖版短视频后的最终封装质检与修复。当用户反馈"视频上传抖音/视频号/网页后封面全黑、缩略图黑、首帧黑屏、预览加载不出画面"，或在课程/文章转短视频流水线最后一步合成完成时使用。
  典型触发：(1) 用户说"上传后封面是黑的""缩略图怎么是黑的""网页打开只听到声音看不到画面"；(2) doc-to-shortvideo / 本地 ffmpeg 合成完 mp4 交付前的最后一道质检。
  核心修复手段是 -movflags +faststart 无损 remux，不重新编码、不动画面。
  Do not: 不重写脚本、不重绘帧图、不重新生成配音；只做封装层检查与修复。
---

# shortvideo-mp4-finalize（短视频 mp4 最终封装质检）

## 结论先行

ffmpeg 默认输出的 mp4，`moov` 元数据原子在文件**末尾**。抖音/视频号/网页播放器/云盘预览在没有完整下载文件前读不到 moov，就抽不出首帧海报 → 封面/缩略图全黑，甚至首点开只听到声音。

**修复只需一条命令，stream-copy 不重编码，秒级完成：**

```bash
ffmpeg -y -i input.mp4 -c copy -movflags +faststart output.mp4
```

## 什么时候触发

1. 用户上传平台后反馈：封面黑 / 缩略图黑 / 网页预览黑屏但有声音。
2. 任何 ffmpeg 本地合成的 mp4 交付前，默认跑一遍本 skill 质检。

## 诊断流程（按顺序）

### 1. 先看首帧本身是不是黑的（排除法）

```powershell
ffmpeg -y -i in.mp4 -vf "select=eq(n\,0)" -frames:v 1 -update 1 f0.png
ffmpeg -y -ss 0.1 -i in.mp4 -frames:v 1 -update 1 f01.png
```

- 抽出来的帧**正常有画面** → 问题在封装层（moov 位置），走第 2 步。
- 抽出来的帧**真的是黑的** → 那是视频内容问题（比如开头帧是黑场/转场），不是本 skill 范围，回去查源帧图。

### 2. 查 moov 原子位置（Python，不用 ffprobe）

```python
import struct
data = open("in.mp4", "rb").read(4000)
p = 0
while p < len(data) - 8:
    sz = struct.unpack(">I", data[p:p+4])[0]
    typ = data[p+4:p+8].decode("latin1")
    print(p, typ, sz)
    if sz < 8: break
    p += sz
```

- 输出是 `ftyp → free → mdat ...`（moov 不在前 4KB）→ **确诊：缺 faststart**。
- 输出是 `ftyp → moov ...` → moov 已前置，黑屏另有原因（查像素格式是否 yuv420p、首帧是否 IDR keyframe）。

### 3. 修复（无损 remux）

```powershell
ffmpeg -y -i in.mp4 -c copy -movflags +faststart out.mp4
Move-Item -Force out.mp4 in.mp4   # 覆盖回原文件
```

### 4. 复验

再跑一次第 2 步，确认前 4KB 里出现 `moov`。再抽一次 f0.png 确认画面正常。

## 根治：合成脚本里永久加这一项

所有本地 ffmpeg 合成流水线的**最后一步混流命令**必须带：

```bash
-movflags +faststart
```

不要等上传后黑屏才补救。放在最终 mux（音视频合并）那一步，不要放在中间段，中间段无所谓但加上也无害。

## 本 skill 踩过的坑速查

| 现象 | 根因 | 修法 |
|---|---|---|
| 上传平台封面全黑、有声音 | moov 在文件末尾，抽帧失败 | `-c copy -movflags +faststart` remux |
| 网页/云盘打开要转圈半天才能播 | 同上（moov 后置不能边下边播） | 同上 |
| 画面发绿/偏色 | 像素格式不是 yuv420p | 编码时加 `-pix_fmt yuv420p` |
| 有的播放器拖到开头黑屏 | 首帧不是 IDR keyframe | 编码时 `-g 30 -keyint_min 30` 或首帧强制 keyframe |
| Windows 抽单帧 png 报错 "image sequence pattern" | ffmpeg 7.x 单帧输出需显式声明 | 加 `-update 1` |

## 开头真人小窗（固定素材复用，用户拍板的样式）

用户录过一段固定出镜素材（竖屏正脸近景），每条片子在**开头钩子段**叠一个小窗露脸，后面全程纯逻辑图。规则（Lewis 已拍板，不许改）：

- **只在开头 ~5.8 秒出现**，之后全程不挂小窗（用户明确否掉了"全程画中画"）。
- 位置：右下角，约 240×295，白边框；裁脸坐标 `crop=440:540:140:320`、`scale=240:295`。
- 合成时在最终 mux 加 overlay + enable：

```bash
ffmpeg -y -i base.mp4 -stream_loop -1 -i host.mp4 -filter_complex \
"[1:v]crop=440:540:140:320,scale=240:295[host];\
[0:v][host]overlay=x=820:y=1600:shortest=1:enable='lte(t,5.8)',\
drawbox=x=820:y=1600:w=240:h=295:color=white:t=3:enable='lte(t,5.8)'[v]" \
-map "[v]" -map 0:a -c:v libx264 -pix_fmt yuv420p -c:a copy -movflags +faststart out.mp4
```

- 注意：素材里嘴型和配音对不上（固定素材复用，非数字人），所以小窗必须小、只在开头短暂出现，别让观众盯。
- host 素材路径按当条工作目录的 assets/host.mp4，素材本身存在则复用，不要让用户重录。

## 红线

1. 修复用 `-c copy`，**绝不重编码**——用户没要求改画质，重编码既慢又掉质量。
2. 只动封装，不动脚本、帧图、配音。
3. 修复完必须复验 moov 位置 + 首帧画面，不能跑完命令就宣称修好。
