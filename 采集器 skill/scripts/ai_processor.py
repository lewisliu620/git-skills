"""
AI处理模块 - 选品确认后异步执行
处理内容：图片翻译（OCR+俄语+重绘）、视频字幕（ASR+翻译+压制）、描述翻译+清洗
结果回写飞书商品主表
依赖：豆包API Key、腾讯云COS
"""
import os
import json
import time
from config import config
from feishu_api import feishu, TABLE_IDS


class AIProcessor:
    """选品确认后的AI批量处理"""

    def __init__(self):
        self.doubao_api_key = config.DOUBAO_API_KEY
        self.cos_config = config.COS_CONFIG
        self.target_lang = "ru"  # Yandex俄罗斯

    def is_ready(self):
        """检查AI处理依赖是否就绪"""
        missing = []
        if not self.doubao_api_key:
            missing.append("豆包API Key")
        if not self.cos_config.get("secret_id"):
            missing.append("腾讯云COS SecretId")
        if not self.cos_config.get("secret_key"):
            missing.append("腾讯云COS SecretKey")
        return len(missing) == 0, missing

    def process_product(self, record_id, fields):
        """
        处理单个商品的AI任务
        fields: 飞书记录的字段数据
        返回: (success, result_dict, error_msg)
        """
        ready, missing = self.is_ready()
        if not ready:
            return False, {}, f"AI处理依赖未就绪: {', '.join(missing)}"

        product_name = fields.get("中文标题", "")
        original_images = fields.get("主图链接", "")
        if isinstance(original_images, str):
            original_images = original_images.split("\n")
        video_url = fields.get("视频链接", "")
        if isinstance(video_url, list):
            video_url = video_url[0] if video_url else ""

        result = {
            "translated_images": [],
            "translated_video": "",
            "translated_description": "",
            "ai_issues": [],
        }

        # 1. 图片处理：OCR识别文字 → 翻译俄语 → 重绘图片 → 上传COS
        print(f"  [AI] 处理图片: {len(original_images)}张")
        for i, img_url in enumerate(original_images):
            if not img_url:
                continue
            try:
                translated_url = self._process_image(img_url)
                if translated_url:
                    result["translated_images"].append(translated_url)
                else:
                    result["ai_issues"].append(f"图{i+1}处理失败")
            except Exception as e:
                result["ai_issues"].append(f"图{i+1}异常: {str(e)}")

        # 2. 视频处理：下载 → ASR字幕 → 翻译 → 压制字幕 → 上传COS
        if video_url:
            print(f"  [AI] 处理视频...")
            try:
                result["translated_video"] = self._process_video(video_url)
            except Exception as e:
                result["ai_issues"].append(f"视频处理异常: {str(e)}")

        # 3. 描述处理：清洗违禁词 → 翻译俄语 → 组装描述模板
        print(f"  [AI] 处理描述...")
        try:
            result["translated_description"] = self._process_description(fields)
        except Exception as e:
            result["ai_issues"].append(f"描述处理异常: {str(e)}")

        return True, result, ""

    def _process_image(self, img_url):
        """
        单张图片AI处理：
        1. 下载图片
        2. 豆包视觉API检测水印/违禁文字
        3. OCR识别图片中文字
        4. 翻译为俄语
        5. 用PIL重绘图片（替换文字区域）
        6. 上传腾讯云COS
        返回COS URL
        """
        # TODO: 实现完整图片处理流程
        # 当前为骨架，依赖豆包API和COS
        print(f"    图片处理骨架（待实现）: {img_url[:50]}...")
        return ""

    def _process_video(self, video_url):
        """
        视频AI处理：
        1. 下载视频
        2. ffmpeg提取音频
        3. 豆包ASR识别字幕
        4. 翻译为俄语
        5. ffmpeg压制字幕
        6. 上传腾讯云COS
        返回COS URL
        """
        # TODO: 实现完整视频处理流程
        print(f"    视频处理骨架（待实现）: {video_url[:50]}...")
        return ""

    def _process_description(self, fields):
        """
        描述AI处理：
        1. 从商品属性提取原始描述
        2. 清洗违禁词/品牌名/其他平台名
        3. 翻译为俄语
        4. 组装Yandex描述模板（货运/售后/关注引导）
        返回俄语描述文本
        """
        # TODO: 实现完整描述处理
        print(f"    描述处理骨架（待实现）")
        return ""

    def update_feishu(self, record_id, success, result, error_msg=""):
        """将AI处理结果回写飞书"""
        if success:
            update_fields = {
                "AI处理状态": "已完成",
                "主图链接": "\n".join(result.get("translated_images", [])),
                "视频链接": result.get("translated_video", ""),
                "AI处理结果": f"图片{len(result.get('translated_images', []))}张处理完成" +
                              (f"; 问题: {'; '.join(result['ai_issues'])}" if result.get("ai_issues") else ""),
            }
        else:
            update_fields = {
                "AI处理状态": "失败",
                "AI处理结果": error_msg,
            }
        feishu.update_record(TABLE_IDS["product"], record_id, update_fields)


def process_pending_products(limit=5):
    """
    批量处理飞书中"选品确认"且"AI待处理"的商品
    由 poll_feishu.py 定时调用
    """
    processor = AIProcessor()

    ready, missing = processor.is_ready()
    if not ready:
        print(f"[AI] 依赖未就绪，跳过: {', '.join(missing)}")
        return 0

    print(f"[AI] 查找待处理商品...")
    try:
        records = feishu.list_records(TABLE_IDS["product"], page_size=50)
        pending = []
        for r in records:
            fields = r.get("fields", {})
            status = fields.get("处理状态", [""])[0] if isinstance(fields.get("处理状态"), list) else fields.get("处理状态", "")
            ai_status = fields.get("AI处理状态", ["待处理"])[0] if isinstance(fields.get("AI处理状态"), list) else fields.get("AI处理状态", "待处理")
            if status == "选品确认" and ai_status == "待处理":
                pending.append(r)

        print(f"[AI] 找到 {len(pending)} 条待处理商品")
        processed = 0

        for record in pending[:limit]:
            record_id = record.get("record_id", "")
            fields = record.get("fields", {})
            name = fields.get("商品名称", "未知")

            print(f"\n[AI] 处理: {name[:30]}...")
            feishu.update_record(TABLE_IDS["product"], record_id, {"AI处理状态": "处理中"})

            success, result, error = processor.process_product(record_id, fields)
            processor.update_feishu(record_id, success, result, error)

            if success:
                print(f"  完成")
                processed += 1
            else:
                print(f"  失败: {error}")

            time.sleep(1)  # 避免API限流

        print(f"\n[AI] 批量处理完成: {processed}/{len(pending)}")
        return processed

    except Exception as e:
        print(f"[AI] 批量处理异常: {e}")
        return 0


if __name__ == "__main__":
    process_pending_products()
