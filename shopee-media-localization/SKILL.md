---
name: shopee-media-localization
description: |
  Shopee跨境商品素材本地化处理。将1688采集的中文商品图/视频，处理成泰国站可用的泰文素材：图片去水印擦中文文字+加泰文标题，视频擦中文字幕+加泰文字幕+泰语配音。
  Use when:
  (1) 商品图需要去水印、擦除中文文字、替换为泰文；
  (2) 商品视频需要擦除中文字幕、加泰文字幕、生成泰语配音；
  (3) 客优云采集商品后需要做素材合规本地化。
  Input: 1688商品图URL或本地图片路径、商品视频文件路径
  Output: 擦除中文+泰文替换后的图片、擦除中文字幕+泰文字幕+泰语配音后的视频
  Do not: 不做从零生成商品图；不做视频剪辑转场；不处理非泰国站的其他语种。
---

# Shopee 商品素材本地化

## 快速开始

1. **图片本地化**：`mediakit-cli image erase-image` 擦除中文 → Python PIL 加泰文
2. **视频本地化**：
   - `probe-video-metadata` 探测 → `video-ocr` 识别中文字幕
   - `erase-video-subtitle` 擦除中文字幕
   - `text_to_audio_plus` 生成泰语配音
   - `mux-audio-video` 泰语配音替换原音轨
   - `ffmpeg` 本地烧录泰文字幕
3. **成本**：图片约0.001积分/张，11秒视频约0.13积分

## 核心职责

- 图片：擦除1688商品图中的中文文字/水印，替换为泰语文案
- 视频：擦除视频中的中文硬字幕，压制泰文字幕，生成泰语配音
- 合规：确保上架素材无中文残留、无平台违规文字
- 批量：支持单张/批量处理主图

## 图片本地化流程

### Step 1：获取商品图

从1688商品页提取主图URL，下载到本地工作目录：

```powershell
# 用Tabbit打开1688页面提取主图
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
# 导航到商品页，提取 img[src*="alicdn"] 且宽度>300 的图片
```

### Step 2：擦除中文文字

```powershell
mediakit-cli image erase-image `
  --image-url <本地图片路径> `
  --output-format jpeg
```

- 默认擦除全屏所有文字，无需指定具体文字
- 返回擦除后的图片URL，24小时有效，需及时下载
- 单张消耗约0.001积分

### Step 3：添加泰语文案

用Python PIL在原中文位置写泰文：

```python
from PIL import Image, ImageDraw, ImageFont

img = Image.open("erased.jpg")
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("C:/Windows/Fonts/tahomabd.ttf", 52)

# 泰语文案（根据商品类别生成）
title = "สติกเกอร์ติดเล็บ"
draw.text((x, y), title, fill=(120, 80, 80), font=font)
```

**泰语字体**：Windows自带Tahoma（tahomabd.ttf粗体）支持泰语，无需额外安装。

**泰语文案生成**：根据商品类别自动生成地道泰语电商文案，不要直译。

### 图片本地化脚本

见 `scripts/localize-image.py`，输入原图路径，输出擦除+泰文版。

## 视频本地化流程（已验证）

### Step 1：探测视频元信息

```powershell
mediakit-cli video probe-video-metadata --video-url <本地视频路径>
# 返回task_id，用 shared query-task 查询
```

获取时长、分辨率、编码信息。消耗约0.0001积分。

### Step 2：识别中文字幕（OCR）

```powershell
mediakit-cli video video-ocr --video-url <视频路径> --mode Detailed
```

- Detailed模式识别画面中所有文字（字幕、水印、标题）
- 返回带时间戳的字幕列表，包含字幕文本和位置坐标
- 11秒视频消耗约0.046积分

### Step 3：擦除中文硬字幕

```powershell
mediakit-cli video erase-video-subtitle --video-url <视频路径>
```

- 智能检测并擦除画面中已有的硬字幕
- 11秒视频消耗约0.074积分
- 返回擦除后视频URL，下载到本地

### Step 4：生成泰语配音

用 `text_to_audio_plus` 工具生成泰语TTS：

```
prompt: "年轻泰国女性，电商短视频解说风格，亲切活泼，语速适中，用泰语自然地说以下内容：..."
duration: 视频时长（秒）
```

- 把OCR识别出的中文台词翻译成泰语，整段传入
- 泰语口语化，适合电商短视频
- 返回WAV音频URL，下载到本地

### Step 5：音视频合流（泰语配音替换原音轨）

```powershell
mediakit-cli editing mux-audio-video `
  --video-url <擦除字幕后的视频> `
  --audio-url <泰语配音.wav> `
  --is-audio-reserve=false `
  --is-video-audio-sync=true `
  --sync-mode video `
  --sync-method trim
```

- `--is-audio-reserve=false`：替换原音轨（中文配音→泰语配音）
- `--is-video-audio-sync=true`：音视频时长对齐
- 11秒视频消耗约0.006积分

### Step 6：ffmpeg本地烧录泰文字幕

**重要**：不要用 `mediakit-cli editing add-subtitle-to-video`，PowerShell传泰文JSON会编码失败。

先用OCR时间轴创建SRT字幕文件：

```
1
00:00:00,000 --> 00:00:02,346
สติกเกอร์ลายฝรั่งเศสใหม่ น่ารักมาก

2
00:00:02,396 --> 00:00:03,644
มีทั้งหมด 4 ลาย
...
```

然后用ffmpeg烧录：

```powershell
# ffmpeg subtitles滤镜路径转义：\ → /，: → \:
$srtEscaped = $srtPath -replace '\\', '/' -replace ':', '\:'

ffmpeg -y -i $inputVideo `
  -vf "subtitles='$srtEscaped':force_style='FontName=Tahoma,FontSize=18,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=80'" `
  -c:a copy -c:v libx264 -crf 23 `
  $outputVideo
```

- Tahoma字体支持泰语渲染，无需额外安装字体
- `MarginV=80`：竖屏视频字幕位置偏下，避开底部互动区
- `Alignment=2`：底部居中
- 白色字体（&HFFFFFF）+ 黑色描边（&H000000）保证可读性
- 本地处理，不消耗积分

## 踩坑记录

| 坑 | 解决方案 |
|---|---|
| mediakit-cli参数是`--video-url`不是`--input` | 所有视频/音频参数统一用`--video-url`/`--audio-url` |
| 所有video域工具是异步任务 | 返回task_id后用`shared query-task --task-id <id>`查询结果 |
| PowerShell传泰文JSON给`--subtitles`参数编码失败 | 改用ffmpeg本地烧录字幕，不用mediakit字幕压制 |
| mux-audio-video的boolean参数 | 必须写`--flag=false`，不能空格写`--flag false` |
| Windows路径在ffmpeg subtitles滤镜中 | 反斜杠转正斜杠，冒号转义为`\:` |
| erase-image返回URL 24小时过期 | 处理完立即下载到本地 |
| Tahoma字体路径 | 粗体`tahomabd.ttf`，常规`tahoma.ttf` |
| IOPaint pip安装失败（Python 3.13） | imghdr模块在Python 3.13被移除，不要用IOPaint，用mediakit-cli erase-image |
| ffmpeg subtitles滤镜需要libass | 本机ffmpeg 9.0.2已含libass/libfreetype/libharfbuzz，无需额外安装 |
| 烧录字幕后必须截帧验证 | 用`ffmpeg -ss 3 -i input.mp4 -frames:v 1 check.jpg`截帧，Read打开确认泰文渲染清晰 |
| 客优云只接受MP4格式视频 | 最终输出必须是MP4，不要输出MOV/AVI |
| 视频时长10-60秒、<30MB、≤1280x1280 | 不满足客优云上传要求，用ffmpeg压缩 |

## 成本参考（11秒竖版视频）

| 步骤 | 工具 | 消耗积分 |
|---|---|---|
| 探测视频元信息 | probe-video-metadata | 0.0001 |
| OCR识别中文字幕 | video-ocr | 0.046 |
| 擦除中文硬字幕 | erase-video-subtitle | 0.074 |
| 提取原音轨（可选） | extract-audio | 0.002 |
| 泰语TTS配音 | text_to_audio_plus | ~少量 |
| 音视频合流 | mux-audio-video | 0.006 |
| ffmpeg烧录字幕 | 本地 | 0 |
| **总计** | | **~0.13积分** |

## 产物目录规范（强制）

所有商品素材必须放到当前项目目录下，不要散落到 `C:\Users\Administrator\DoubaoWork\tools\`：

```
<项目目录>/
├── products/
│   └── <商品slug>/              # 如 nail-sticker
│       ├── metadata.json        # 商品元信息（来源URL、成本、售价、状态）
│       ├── 01-source/          # 1688原始素材（主图、视频）
│       ├── 02-processed/       # 中间产物（擦字幕后、SRT、配音WAV）
│       └── 03-final/             # 最终上架素材（本地化后的图/视频）
│           ├── images/
│           └── videos/
├── scripts/                     # 自动化脚本
└── docs/                        # 方案文档
```

**商品slug规则**：小写英文+连字符，如 `nail-sticker`、`phone-case-mini`。

**新建商品第一步**：按上述结构创建目录，并写 `metadata.json` 记录来源URL、成本CNY、售价THB、利润率。

## 端到端流水线衔接

本skill处于流水线中间环节，上游和下游：

```
[AI选品] → [keyouyun-publisher采集] → [shopee-media-localization本地化] → [客优云发布上架] → [shopee-order-fulfillment发货]
   飞书选品表      Tabbit操作客优云采集        本skill                       客优云发布            订单监控+1688代发
```

- **上游输入**：客优云采集后，从1688商品页提取主图URL和视频URL，下载到 `01-source/`
- **本skill处理**：图片擦中文+加泰文；视频擦字幕+泰语配音+烧录泰文字幕
- **下游输出**：`03-final/` 里的图和视频就是客优云/Shopee上架用的素材
- **完成标记**：处理完后更新 `metadata.json` 的 `localization_status`，供keyouyun-publisher判断何时可以发布

## 红线

- **货不对版**：擦除文字后不能改变商品本身外观，只处理文字/水印区域
- **泰语文案质量**：必须是地道泰语电商用语，不要机翻直译
- **字体**：只用系统自带Tahoma，不装额外字体
- **成本控制**：批量处理前先试跑1个视频验证效果
- **产物归位**：所有文件必须在 `<项目目录>/products/<商品slug>/` 下，禁止散落到tools临时目录
- **字幕位置**：竖屏视频字幕用lower_third或MarginV=80，避开Shopee底部互动按钮
