"""
图片处理模块（三级流水线）
第1级：快速预检（本地，尺寸/白底判断）
第2级：AI检测（豆包视觉，水印/店铺名/中文文字检测）— 需API Key
第3级：处理（Pillow，涂白覆盖/翻译覆盖）

当前为骨架实现，API Key 配置后启用 AI 检测
"""
import os
import json
import hashlib
from PIL import Image
import requests
from config import config


class ImageProcessor:
    """图片处理器"""

    MIN_SIZE = 450  # 最小尺寸 px

    def __init__(self):
        self.cache = self._load_cache()

    def _load_cache(self):
        """加载图片处理缓存"""
        if os.path.exists(config.IMAGE_CACHE_FILE):
            try:
                with open(config.IMAGE_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self):
        with open(config.IMAGE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _cache_key(self, url):
        return hashlib.md5(url.encode()).hexdigest()

    def process(self, image_url, target_lang="ru"):
        """
        处理单张图片
        返回 (processed_url_or_path, issues)
        processed_url: 处理后的图片URL（COS直链）或本地路径
        """
        cache_key = self._cache_key(image_url)

        # 缓存命中
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if os.path.exists(cached.get("local_path", "")) or cached.get("cos_url"):
                return cached.get("cos_url") or cached.get("local_path"), cached.get("issues", [])

        issues = []

        # 下载图片
        local_path = self._download(image_url)
        if not local_path:
            return "", ["下载失败"]

        # 第1级：快速预检
        passed, pre_issues = self._pre_check(local_path)
        issues.extend(pre_issues)
        if not passed:
            return "", issues

        # 第2级：AI检测（需豆包API）
        if config.DOUBAO_API_KEY:
            ai_issues = self._ai_check(local_path)
            issues.extend(ai_issues)
        else:
            issues.append("AI检测: 跳过（未配置豆包API Key）")

        # 第3级：处理（涂白/翻译覆盖）
        # TODO: 实现基于AI检测结果的Pillow处理

        # 上传COS（需配置）
        cos_url = ""
        if config.COS_SECRET_ID and config.COS_BUCKET:
            cos_url = self._upload_to_cos(local_path)
            issues.append(f"已上传COS: {cos_url}")
        else:
            issues.append("COS上传: 跳过（未配置腾讯云COS）")

        # 保存缓存
        self.cache[cache_key] = {
            "local_path": local_path,
            "cos_url": cos_url,
            "issues": issues,
        }
        self._save_cache()

        return cos_url or local_path, issues

    def _download(self, url):
        """下载图片到本地temp目录"""
        try:
            filename = hashlib.md5(url.encode()).hexdigest() + ".jpg"
            local_path = os.path.join(config.TEMP_DIR, filename)
            if os.path.exists(local_path):
                return local_path
            resp = requests.get(url, timeout=15, headers={"Referer": "https://www.1688.com/"})
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                return local_path
        except Exception as e:
            print(f"[图片处理] 下载失败: {e}")
        return ""

    def _pre_check(self, local_path):
        """第1级：快速预检"""
        issues = []
        try:
            img = Image.open(local_path)
            w, h = img.size

            # 尺寸检查
            if min(w, h) < self.MIN_SIZE:
                issues.append(f"尺寸过小: {w}x{h} < {self.MIN_SIZE}px")
                return False, issues

            # 白底图判断（采样边缘像素）
            is_white_bg = self._is_white_background(img)
            if is_white_bg:
                issues.append("白底图，跳过AI检测")
                # 白底图通常没有水印和文字，可直接通过
                return True, issues

        except Exception as e:
            issues.append(f"图片打开失败: {e}")
            return False, issues

        return True, issues

    def _is_white_background(self, img, threshold=240):
        """判断是否白底图（采样四角和边缘像素）"""
        img = img.convert("RGB")
        w, h = img.size
        sample_points = [
            (0, 0), (w-1, 0), (0, h-1), (w-1, h-1),
            (w//2, 0), (w//2, h-1), (0, h//2), (w-1, h//2)
        ]
        white_count = 0
        for x, y in sample_points:
            r, g, b = img.getpixel((x, y))
            if r > threshold and g > threshold and b > threshold:
                white_count += 1
        return white_count >= 6  # 8个采样点中至少6个为白色

    def _ai_check(self, local_path):
        """第2级：AI检测（豆包视觉）"""
        # TODO: 调用豆包视觉API检测水印、店铺名、中文文字
        # 返回 issues 列表
        return ["AI检测: 待实现"]

    def _upload_to_cos(self, local_path):
        """上传到腾讯云COS"""
        # TODO: 实现COS上传
        return ""


def process_image(image_url, target_lang="ru"):
    """便捷函数"""
    processor = ImageProcessor()
    return processor.process(image_url, target_lang)
