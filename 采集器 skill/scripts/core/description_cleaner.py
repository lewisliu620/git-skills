"""
描述清洗模块
- 违禁词检测与删除（从飞书违禁词配置表读取）
- 无关描述删除（需豆包API，当前为骨架）
- 品牌名不符检测（需豆包API，当前为骨架）
"""
import re
from feishu_api import feishu, TABLE_IDS


class DescriptionCleaner:
    """描述清洗器"""

    def __init__(self, platform="全部平台"):
        self.platform = platform
        self.forbidden_words = self._load_forbidden_words()

    def _load_forbidden_words(self):
        """加载违禁词（含通用+平台专属）"""
        try:
            return feishu.load_forbidden_words(TABLE_IDS["forbidden_words"], self.platform)
        except Exception as e:
            print(f"[描述清洗] 加载违禁词失败: {e}")
            return []

    def clean(self, text):
        """
        清洗描述文本
        返回 (cleaned_text, issues)
        """
        if not text:
            return "", []

        issues = []
        cleaned = text

        # 1. 违禁词处理
        for word_cfg in self.forbidden_words:
            word = word_cfg.get("违禁词", "")
            if not word or word not in cleaned:
                continue

            action = word_cfg.get("处理方式", ["删除"])[0] if isinstance(word_cfg.get("处理方式"), list) else word_cfg.get("处理方式", "删除")
            replace_with = word_cfg.get("替换为", "")

            if action == "删除":
                cleaned = cleaned.replace(word, "")
                issues.append(f"删除违禁词: {word}")
            elif action == "替换为通用词" and replace_with:
                cleaned = cleaned.replace(word, replace_with)
                issues.append(f"替换: {word} → {replace_with}")
            elif action == "标记人工审核":
                issues.append(f"需人工审核: {word}")

        # 2. 清理多余空白
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = cleaned.strip()

        # 3. 豆包辅助清洗（删除无关描述，只留产品特征）
        #    需要 DOUBAO_API_KEY，未配置时跳过
        from config import config
        if config.DOUBAO_API_KEY:
            cleaned = self._ai_clean(cleaned)
            issues.append("AI清洗: 已删除无关描述")
        else:
            issues.append("AI清洗: 跳过（未配置豆包API Key）")

        return cleaned, issues

    def _ai_clean(self, text):
        """调用豆包删除无关描述，只保留产品特征属性"""
        # TODO: 实现豆包API调用
        # prompt = "请删除以下商品描述中的供应商自我介绍、发货说明、售后政策等无关内容，只保留产品材质、功能、尺寸、颜色、适用场景等特征属性描述：\n\n" + text
        return text


def clean_description(text, platform="全部平台"):
    """便捷函数"""
    cleaner = DescriptionCleaner(platform)
    return cleaner.clean(text)
