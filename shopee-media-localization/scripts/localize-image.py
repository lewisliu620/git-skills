"""
Shopee商品图本地化脚本
输入：原图路径
输出：擦除中文+泰文替换后的图片

用法：
  python localize-image.py <原图路径> [输出路径] [泰文标题] [泰文副标题]

示例：
  python localize-image.py product.jpg product-th.jpg "สติกเกอร์ติดเล็บ" "ลายเจาะลายหลายแบบ"
"""
import sys
import os
import subprocess
import urllib.request
from PIL import Image, ImageDraw, ImageFont

def erase_chinese_text(image_path, output_format="jpeg"):
    """调用mediakit-cli擦除图片中的中文文字"""
    cmd = [
        "mediakit-cli", "image", "erase-image",
        "--image-url", image_path,
        "--output-format", output_format
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise Exception(f"erase-image失败: {result.stderr}")
    
    import json
    data = json.loads(result.stdout)
    erased_url = data.get("image_url")
    if not erased_url:
        raise Exception(f"擦除后无URL: {data}")
    
    # 下载擦除后的图片
    erased_path = image_path.replace(".jpg", "-erased.jpg").replace(".png", "-erased.png")
    urllib.request.urlretrieve(erased_url, erased_path)
    return erased_path

def add_thai_text(erased_path, output_path, title, subtitle=None):
    """在擦除后的图片上添加泰语文案"""
    img = Image.open(erased_path)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    # 加载泰语字体
    font_bold = ImageFont.truetype("C:/Windows/Fonts/tahomabd.ttf", 52)
    font_reg = ImageFont.truetype("C:/Windows/Fonts/tahoma.ttf", 28)
    
    color = (120, 80, 80)  # 深棕色，和1688商品图风格匹配
    
    # 主标题：右上角，右对齐
    bbox = draw.textbbox((0, 0), title, font=font_bold)
    tw = bbox[2] - bbox[0]
    x = w - tw - 40
    y = 80
    draw.text((x, y), title, fill=color, font=font_bold)
    
    # 副标题：右下角小图上方
    if subtitle:
        bbox2 = draw.textbbox((0, 0), subtitle, font=font_reg)
        tw2 = bbox2[2] - bbox2[0]
        x2 = w - tw2 - 40
        y2 = h - 120
        draw.text((x2, y2), subtitle, fill=(100, 100, 100), font=font_reg)
    
    img.save(output_path, quality=95)
    return output_path

def main():
    if len(sys.argv) < 3:
        print("用法: python localize-image.py <原图路径> <输出路径> [泰文标题] [泰文副标题]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "สวัสดี"
    subtitle = sys.argv[4] if len(sys.argv) > 4 else None
    
    print(f"[1/2] 擦除中文文字: {input_path}")
    erased_path = erase_chinese_text(input_path)
    print(f"  -> 擦除完成: {erased_path}")
    
    print(f"[2/2] 添加泰语文案")
    result = add_thai_text(erased_path, output_path, title, subtitle)
    print(f"  -> 最终输出: {result}")
    print(f"  -> 成本: 约0.001积分")

if __name__ == "__main__":
    main()
