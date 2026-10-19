---
name: shortvideo-qa-review
description: |
  短视频成片交付前的自动质检（QA 评审官）。任何 doc-to-shortvideo / ffmpeg 合成的 mp4 在交给用户前必须过本 skill。
  触发：(1) 成片刚合成完、准备交付/上传前；(2) 用户说"检查一下片子""质检""看看有没有问题"。
  内容：抽帧对照脚本查画面 + 自动查黑屏/音量/时长/faststart，输出逐项 pass/fail 检查单。
  纯本地 ffmpeg + 人眼（LLM 视觉）检查，不花生成额度。
  Do not: 不重剪、不重渲染；发现问题只报告并给出修法选项。
---

# shortvideo-qa-review（短视频 QA 评审官）

## 触发时机

成片合成完成后、present_files 交付之前，**必跑一遍**。不跳步。

## 检查清单（7 项，逐项 pass/fail）

### 1. 技术规格
`ffmpeg -i out.mp4 2>&1 | Select-String "Duration|Stream"`
- 时长与配音脚本一致（误差 <0.5s）；分辨率 1080x1920（或约定画幅）；30fps；有音轨 aac。

### 2. faststart（封面黑屏预防）
```python
import struct
data = open("out.mp4","rb").read(4000)
# 解析前几个 atom：必须出现 ftyp -> moov
```
- pass = moov 在前 4KB。fail = 走 shortvideo-mp4-finalize 修复。

### 3. 黑屏检测
```powershell
ffmpeg -i out.mp4 -vf "blackdetect=d=0.5:pic_th=0.1" -an -f null - 2>&1 | Select-String blackdetect
```
- 无任何 `black_start` 输出 = pass。注意参数名是 `pic_th`（像素亮度阈值），不是 p_th。

### 4. 音量健康度
```powershell
ffmpeg -i out.mp4 -af volumedetect -f null - 2>&1 | Select-String "mean_volume|max_volume"
```
- mean ≈ -18~-26dB，max ≈ -1~-3dB = pass。max > -0.5dB（削波）或 mean < -30dB（太轻）= fail。

### 5. 抽帧对照脚本（视觉检查，核心项）
按分镜段中点抽 5 帧（每段至少 1 帧）：
```powershell
ffmpeg -y -ss <t> -i out.mp4 -frames:v 1 -update 1 qa_frames\f_<t>s.png
```
逐帧 Read 图片，对照脚本查：
- 帧图文字是否溢出裁切边缘？
- 字幕条是否压到正文关键信息？
- 该段画面内容是否和脚本讲解一致（没张冠李戴）？
- 颜色是否符合品牌色卡（没有乱色）？

### 6. 运镜平滑度（防抖回归）
抽同一推镜段的 t1 和 t2 两帧，对比是否平滑缩放、无整像素跳变痕迹（放大局部看边缘文字是否锯齿跳动）。

### 7. 首尾帧
- t=0 帧：必须是钩子页（不能黑）—— 决定平台封面。
- 最后一帧：是否有收尾金句/CTA，而不是突然断掉。

## 输出格式

给用户一张检查单：

```
✅ 1 技术规格：39.3s / 1080x1920 / 30fps
✅ 2 faststart：moov 前置
✅ 3 黑屏：无
✅ 4 音量：mean -23dB / max -2dB
✅ 5 抽帧对照：5 帧无溢出/无错配
✅ 6 运镜：平滑
✅ 7 首尾帧：钩子页+金句收尾
```
任何一项 fail：写明问题、影响、修法（改哪一段命令/哪一张帧图），不让带病成片交付。

## 红线

1. 7 项全 pass 才能 present_files 交付。
2. 不替用户判断"内容好不好"，只查"对不对"——好不好是停点 1/2 的事。
3. 抽帧图片必须真的 Read 看过，不能列个"已检查"就交差。
