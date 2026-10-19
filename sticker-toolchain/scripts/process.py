# -*- coding: utf-8 -*-
"""S3-S5 表情包后处理（已在一套 16 枚静态表情上验证通过）：
去底 -> 2px 白描边 -> 叠字 -> 7 类规格导出 -> 程序校验 -> 预览拼图 -> zip 打包。

用法：
1. 编辑下方 CONFIG（原始生成图目录、含义表、专辑名、字体、去底阈值）。
2. python process.py
3. 校验报告必须 0 错误；产物输出到 PKG。
"""
import os, glob, zipfile
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import numpy as np

# ---------------- CONFIG（每次新建表情包改这里） ----------------
RAW_DIR  = "01_raw"                      # 原始生成图目录：01.png、02.png…
ALBUM    = "工牌橘猫·职场日常"            # 专辑名（zip 根目录 + 预览标题）
FONT     = r"C:\Windows\Fonts\msyhbd.ttc"  # 叠字字体（微软雅黑粗体等）
T0, T1   = 10.0, 22.0                    # 背景距离透明斜坡 (RGB 欧氏距离)，先用 probe.py 采样定
COVER_KEY  = "01"                        # 封面取哪一枚
BANNER_KEYS = ["10", "02"]               # 横幅装饰贴纸
GUIDE_KEY   = "09"                       # 赞赏引导图贴纸
THANKS_KEY  = "13"                       # 赞赏致谢图贴纸
CAPTIONS = {  # key -> 含义词（含义无重复，16 或 24 枚）
    "01": "好的收到", "02": "摸鱼中", "03": "别催了", "04": "在做了",
    "05": "已读不回", "06": "下班倒计时", "07": "开会走神", "08": "精神离职",
    "09": "咖啡续命", "10": "不想上班", "11": "摸鱼被抓", "12": "电脑卡了",
    "13": "先吃饭吧", "14": "需求又改", "15": "预算不够", "16": "心已下班",
}
# ----------------------------------------------------------------

BASE = os.path.join(os.getcwd(), "sticker_build")
RAW = os.path.join(BASE, RAW_DIR if os.path.isabs(RAW_DIR) else os.path.join(BASE, RAW_DIR))
PROC = os.path.join(BASE, "02_processed")
PKG = os.path.join(BASE, "03_package")

def open_bg(path):
    """角点采样背景色（中位数）"""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im)
    h, w, _ = a.shape
    corners = []
    for (y0, x0) in [(0, 0), (0, w - 10), (h - 10, 0), (h - 10, w - 10)]:
        patch = a[y0:y0 + 10, x0:x0 + 10].reshape(-1, 3)
        corners.append(np.median(patch, axis=0))
    return im, np.median(np.array(corners), axis=0)

def remove_bg(im, bg):
    """按与背景色距离生成 alpha 斜坡，返回 RGBA"""
    a = np.asarray(im).astype(float)
    d = np.linalg.norm(a - bg, axis=2)
    alpha = np.clip((d - T0) / (T1 - T0), 0.0, 1.0)
    rgba = np.dstack([a, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba)

def white_outline(im, px=2):
    """alpha 膨胀 px 像素，生成白色描边"""
    alpha = im.getchannel("A")
    dilated = alpha.filter(ImageFilter.MaxFilter(px * 2 + 1))
    canvas = Image.new("RGBA", im.size, (255, 255, 255, 0))
    canvas.putalpha(dilated)
    canvas.paste(im, (0, 0), im)
    return canvas

def add_text(im, text, font_size=36, stroke=5, y_center=212):
    """白字黑描边，底部居中 (anchor=mm)"""
    draw = ImageDraw.Draw(im)
    fnt = ImageFont.truetype(FONT, font_size)
    draw.text((im.width / 2, y_center), text, font=fnt, fill=(255, 255, 255),
              stroke_width=stroke, stroke_fill=(0, 0, 0), anchor="mm")
    return im

def gradient(size, top, bottom, horizontal=False):
    w, h = size
    top = np.array(top, float); bottom = np.array(bottom, float)
    if horizontal:
        t = np.linspace(0, 1, w)[None, :, None]
        arr = (top + (bottom - top) * t)
    else:
        t = np.linspace(0, 1, h)[:, None, None]
        arr = (top + (bottom - top) * t)
    arr = np.broadcast_to(arr, (h, w, 3)).copy()
    return Image.fromarray(arr.astype(np.uint8)).convert("RGBA")

os.makedirs(PROC, exist_ok=True)
MAIN_DIR = os.path.join(PKG, "主图")
THUMB_DIR = os.path.join(PKG, "缩略图")
for d in (MAIN_DIR, THUMB_DIR, os.path.join(PKG, "封面"), os.path.join(PKG, "图标"),
          os.path.join(PKG, "横幅"), os.path.join(PKG, "赞赏引导"), os.path.join(PKG, "赞赏致谢")):
    os.makedirs(d, exist_ok=True)

transparent = {}
mains = {}
raw_paths = {k: os.path.join(RAW, k + ".png") for k in CAPTIONS}
missing = [k for k, fp in raw_paths.items() if not os.path.exists(fp)]
if missing:
    raise SystemExit(f"缺少原始图: {missing}；请确认 RAW_DIR={RAW} 下命名 {k}.png")
bg_info = {}
for k, fp in raw_paths.items():
    im, bg = open_bg(fp)
    bg_info[k] = bg
    rgba = remove_bg(im, bg).resize((240, 240), Image.LANCZOS)
    rgba = white_outline(rgba, 2)
    transparent[k] = rgba
    main = add_text(rgba.copy(), CAPTIONS[k])
    mains[k] = main
    main.save(os.path.join(MAIN_DIR, f"{k}_{CAPTIONS[k]}.png"))
    thumb = main.resize((120, 120), Image.LANCZOS)
    thumb.save(os.path.join(THUMB_DIR, f"{k}_{CAPTIONS[k]}.png"))

cover = transparent[COVER_KEY].copy()
cover.save(os.path.join(PKG, "封面", "封面.png"))
icon = cover.resize((50, 50), Image.LANCZOS)
icon.save(os.path.join(PKG, "图标", "图标.png"))

# 横幅 750x400：不透明、无字、非白底
banner = gradient((750, 400), (255, 216, 168), (255, 244, 228), horizontal=True)
bdr = ImageDraw.Draw(banner)
for (cx, cy, r, al) in [(90, 70, 55, 70), (680, 90, 40, 60), (620, 330, 65, 55), (120, 330, 40, 65), (400, 40, 25, 45)]:
    overlay = Image.new("RGBA", banner.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, al))
    banner = Image.alpha_composite(banner, overlay)
s1 = transparent[BANNER_KEYS[0]].resize((250, 250), Image.LANCZOS)
s2 = transparent[BANNER_KEYS[1]].resize((210, 210), Image.LANCZOS)
banner.alpha_composite(s1, (430, 90))
banner.alpha_composite(s2, (95, 170))
banner.convert("RGB").save(os.path.join(PKG, "横幅", "横幅.png"))

# 赞赏引导 750x560
guide = gradient((750, 560), (255, 224, 186), (255, 246, 234), horizontal=True)
gd = ImageDraw.Draw(guide)
s3 = transparent[GUIDE_KEY].resize((300, 300), Image.LANCZOS)
guide.alpha_composite(s3, (90, 140))
f_big = ImageFont.truetype(FONT, 56); f_sub = ImageFont.truetype(FONT, 34)
gd.text((430, 235), "喜欢就鼓励一下吧", font=f_big, fill=(122, 74, 31), anchor="mm", stroke_width=4, stroke_fill=(255, 255, 255))
gd.text((430, 330), "你的支持是我继续更新的动力", font=f_sub, fill=(150, 100, 55), anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255))
guide.convert("RGB").save(os.path.join(PKG, "赞赏引导", "赞赏引导图.png"))

# 赞赏致谢 750x750
thanks = gradient((750, 750), (255, 224, 186), (255, 248, 238), horizontal=True)
td = ImageDraw.Draw(thanks)
s4 = transparent[THANKS_KEY].resize((330, 330), Image.LANCZOS)
thanks.alpha_composite(s4, (210, 110))
td.text((375, 520), "谢谢你的喜欢", font=ImageFont.truetype(FONT, 62), fill=(122, 74, 31), anchor="mm", stroke_width=4, stroke_fill=(255, 255, 255))
td.text((375, 610), "会继续加油的喵~", font=ImageFont.truetype(FONT, 36), fill=(150, 100, 55), anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255))
thanks.convert("RGB").save(os.path.join(PKG, "赞赏致谢", "赞赏致谢图.png"))

# 预览拼图 4x4（枚数非 16 时按行列自适应）
n = len(CAPTIONS)
cols = 4
rows = (n + cols - 1) // cols
cell_w, cell_h = 240, 270
grid = Image.new("RGB", (cell_w * cols + 10 * (cols + 1), cell_h * rows + 10 * (rows + 1) + 60), (255, 255, 255))
gd = ImageDraw.Draw(grid)
gd.text((10 + (grid.width - 10) / 2, 18), f"{ALBUM}（{n} 枚）", font=ImageFont.truetype(FONT, 34), fill=(60, 60, 60), anchor="mm")
for i, k in enumerate(sorted(CAPTIONS)):
    r, c = divmod(i, cols)
    x = 10 + c * (cell_w + 10); y = 60 + r * (cell_h + 10)
    grid.paste(mains[k].convert("RGB"), (x, y), mains[k].getchannel("A"))
    gd.text((x + cell_w / 2, y + cell_h - 16), CAPTIONS[k], font=ImageFont.truetype(FONT, 22), fill=(80, 80, 80), anchor="mm")
grid.save(os.path.join(PKG, "预览拼图.png"))

# 校验
report = [f"{ALBUM} 规格校验报告", "=" * 40, ""]
errors = []
def check(im_path, expect_size, expect_rgba, max_kb, need_transparent=False, label=""):
    im = Image.open(im_path)
    ok = True; msgs = []
    if im.size != expect_size: ok = False; msgs.append(f"尺寸 {im.size}!={expect_size}")
    if im.mode != ("RGBA" if expect_rgba else "RGB"): ok = False; msgs.append(f"模式 {im.mode}")
    kb = os.path.getsize(im_path) / 1024
    if kb > max_kb: ok = False; msgs.append(f"体积 {kb:.0f}KB>{max_kb}KB")
    if need_transparent and im.getchannel("A").getextrema()[0] == 255:
        ok = False; msgs.append("无透明像素")
    line = f"[{'OK' if ok else 'FAIL'}] {label or os.path.basename(im_path)} ({im.size[0]}x{im.size[1]}, {kb:.0f}KB)"
    report.append(line + ((" -> " + "; ".join(msgs)) if msgs else ""))
    if not ok: errors.append(line)
    return ok

for k in sorted(CAPTIONS):
    check(os.path.join(MAIN_DIR, f"{k}_{CAPTIONS[k]}.png"), (240, 240), True, 500, True, f"主图 {k}")
    check(os.path.join(THUMB_DIR, f"{k}_{CAPTIONS[k]}.png"), (120, 120), True, 500, True, f"缩略图 {k}")
check(os.path.join(PKG, "封面", "封面.png"), (240, 240), True, 500, True, "封面")
check(os.path.join(PKG, "图标", "图标.png"), (50, 50), True, 500, True, "图标")
check(os.path.join(PKG, "横幅", "横幅.png"), (750, 400), False, 500, False, "横幅")
check(os.path.join(PKG, "赞赏引导", "赞赏引导图.png"), (750, 560), False, 500, False, "赞赏引导")
check(os.path.join(PKG, "赞赏致谢", "赞赏致谢图.png"), (750, 750), False, 500, False, "赞赏致谢")
report.append("")
report.append(f"结论: {'全部通过' if not errors else f'{len(errors)} 项未通过'}")
open(os.path.join(PKG, "校验报告.txt"), "w", encoding="utf-8").write("\n".join(report))

# 含义表
cap_lines = [f"表情含义表（{n} 枚，无重复）", "=" * 30, ""]
for k in sorted(CAPTIONS):
    cap_lines.append(f"{k}  {CAPTIONS[k]}")
open(os.path.join(PKG, "表情含义表.txt"), "w", encoding="utf-8").write("\n".join(cap_lines))

# zip 打包
zip_path = os.path.join(PKG, f"{ALBUM}_投稿包.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for sub in ["主图", "缩略图", "封面", "图标", "横幅", "赞赏引导", "赞赏致谢"]:
        for fn in sorted(os.listdir(os.path.join(PKG, sub))):
            zf.write(os.path.join(PKG, sub, fn), f"{ALBUM}/{sub}/{fn}")
    zf.write(os.path.join(PKG, "表情含义表.txt"), f"{ALBUM}/表情含义表.txt")
    zf.write(os.path.join(PKG, "校验报告.txt"), f"{ALBUM}/校验报告.txt")

print("DONE zip:", zip_path, os.path.getsize(zip_path) // 1024, "KB")
print("ERRORS:", len(errors))
for e in errors: print(e)
print("BG samples:", {k: v.round(0).tolist() for k, v in list(bg_info.items())[:3]})
