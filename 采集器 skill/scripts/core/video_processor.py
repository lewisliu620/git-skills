"""
视频处理模块（两级检查 + 字幕烧录）
第1级：元数据检查（ffprobe，时长/分辨率/格式）
第2级：抽帧AI检查（内容相关性/违规文字）— 需豆包API
字幕：ASR提取 → 翻译 → ffmpeg烧录

当前为骨架实现
"""
import os
import json
import hashlib
import subprocess
import requests
from config import config


class VideoProcessor:
    """视频处理器"""

    def __init__(self):
        self.ffmpeg_available = self._check_ffmpeg()

    def _check_ffmpeg(self):
        """检查ffmpeg是否可用"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
            return True
        except:
            print("[视频处理] ffmpeg 未安装，视频处理功能受限")
            return False

    def process(self, video_url, target_lang="ru"):
        """
        处理单个视频
        返回 (processed_url_or_path, issues)
        """
        issues = []

        # 下载视频
        local_path = self._download(video_url)
        if not local_path:
            return "", ["视频下载失败"]

        # 第1级：元数据检查
        if not self.ffmpeg_available:
            issues.append("ffmpeg不可用，跳过视频处理")
            return local_path, issues

        passed, meta_issues = self._meta_check(local_path)
        issues.extend(meta_issues)
        if not passed:
            return "", issues

        # 第2级：抽帧AI检查（需豆包API）
        if config.DOUBAO_API_KEY:
            ai_issues = self._ai_check(local_path)
            issues.extend(ai_issues)
        else:
            issues.append("AI检测: 跳过（未配置豆包API Key）")

        # 字幕烧录（需豆包API + ffmpeg）
        if config.DOUBAO_API_KEY and self.ffmpeg_available:
            subtitled_path = self._add_subtitles(local_path, target_lang)
            if subtitled_path:
                local_path = subtitled_path
                issues.append(f"已烧录{target_lang}字幕")
        else:
            issues.append("字幕烧录: 跳过（需豆包API+ffmpeg）")

        # 上传COS
        cos_url = ""
        if config.COS_SECRET_ID and config.COS_BUCKET:
            cos_url = self._upload_to_cos(local_path)
            issues.append(f"已上传COS: {cos_url}")

        return cos_url or local_path, issues

    def _download(self, url):
        """下载视频"""
        try:
            filename = hashlib.md5(url.encode()).hexdigest() + ".mp4"
            local_path = os.path.join(config.TEMP_DIR, filename)
            if os.path.exists(local_path):
                return local_path
            resp = requests.get(url, timeout=30, stream=True, headers={"Referer": "https://www.1688.com/"})
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
                return local_path
        except Exception as e:
            print(f"[视频处理] 下载失败: {e}")
        return ""

    def _meta_check(self, local_path):
        """第1级：元数据检查"""
        issues = []
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", local_path],
                capture_output=True, text=True, timeout=10
            )
            meta = json.loads(result.stdout)
            duration = float(meta.get("format", {}).get("duration", 0))

            # 时长检查（通用上限60秒，各平台规则从配置表读）
            if duration > 60:
                issues.append(f"视频过长: {duration:.1f}秒 > 60秒")
                return False, issues

            # 分辨率检查
            for stream in meta.get("streams", []):
                if stream.get("codec_type") == "video":
                    width = stream.get("width", 0)
                    height = stream.get("height", 0)
                    if min(width, height) < 480:
                        issues.append(f"分辨率过低: {width}x{height}")
                        return False, issues

        except Exception as e:
            issues.append(f"元数据检查失败: {e}")
            return False, issues

        return True, issues

    def _ai_check(self, local_path):
        """第2级：抽帧AI检查"""
        # TODO: 抽3-5帧 → 豆包视觉检测内容相关性和违规文字
        return ["AI检测: 待实现"]

    def _add_subtitles(self, local_path, target_lang):
        """提取音频→ASR→翻译→烧录字幕"""
        # TODO: 实现完整字幕流水线
        return None

    def _upload_to_cos(self, local_path):
        """上传COS"""
        # TODO: 实现COS上传
        return ""


def process_video(video_url, target_lang="ru"):
    """便捷函数"""
    processor = VideoProcessor()
    return processor.process(video_url, target_lang)
