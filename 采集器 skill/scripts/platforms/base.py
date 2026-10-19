"""
平台适配器基类
所有平台适配器（Yandex/TikTok/Shopee）继承此类
核心逻辑通用，平台差异通过配置表 + 子类实现
"""
from feishu_api import feishu, TABLE_IDS


class PlatformAdapter:
    """平台适配器基类"""

    platform_name = ""        # 子类必须设置，如 "Yandex Market"
    target_language = "ru"    # 目标语言，如 ru/en/th
    currency = "RUB"          # 目标货币

    def __init__(self):
        self.rules = self._load_rules()
        self.forbidden_words = self._load_forbidden_words()
        self.description_template = self._load_template()
        self.field_mapping = self._load_field_mapping()

    def _load_rules(self):
        """加载平台上架规则（含通用规则）"""
        try:
            return feishu.load_platform_rules(TABLE_IDS["platform_rules"], self.platform_name)
        except Exception as e:
            print(f"[{self.platform_name}] 加载规则失败: {e}")
            return []

    def _load_forbidden_words(self):
        """加载平台违禁词（含通用违禁词）"""
        try:
            return feishu.load_forbidden_words(TABLE_IDS["forbidden_words"], self.platform_name)
        except Exception as e:
            print(f"[{self.platform_name}] 加载违禁词失败: {e}")
            return []

    def _load_template(self):
        """加载平台描述模板"""
        try:
            return feishu.load_description_template(TABLE_IDS["description_templates"], self.platform_name)
        except Exception as e:
            print(f"[{self.platform_name}] 加载描述模板失败: {e}")
            return ""

    def _load_field_mapping(self):
        """加载字段映射"""
        try:
            return feishu.load_field_mapping(TABLE_IDS["field_mapping"])
        except Exception as e:
            print(f"[{self.platform_name}] 加载字段映射失败: {e}")
            return {}

    def validate(self, product):
        """
        上架前校验，读规则表执行
        返回 (passed, errors)
        """
        errors = []

        for rule in self.rules:
            rule_name = rule.get("规则名称", "")
            check_field = rule.get("检查字段", [""])[0] if isinstance(rule.get("检查字段"), list) else rule.get("检查字段", "")
            condition = rule.get("条件", [""])[0] if isinstance(rule.get("条件"), list) else rule.get("条件", "")
            threshold = rule.get("阈值", "")
            on_fail = rule.get("不通过处理", ["校验失败"])[0] if isinstance(rule.get("不通过处理"), list) else rule.get("不通过处理", "校验失败")

            passed, auto_fixed = self._check_rule(product, check_field, condition, threshold)
            if not passed:
                if on_fail == "自动修正" and auto_fixed:
                    errors.append(f"{rule_name}: 已自动修正")
                elif on_fail == "弃用该素材":
                    errors.append(f"{rule_name}: 素材不符合，已弃用")
                else:
                    errors.append(f"{rule_name}: 不符合要求（{condition} {threshold}）")

        return (len([e for e in errors if "已自动修正" not in e and "已弃用" not in e]) == 0), errors

    def _check_rule(self, product, field, condition, threshold):
        """校验单条规则，返回 (passed, auto_fixed_value)"""
        try:
            if field == "规格名称" and condition == "小于":
                max_len = int(threshold)
                for sku in product.skus:
                    if len(sku.get("name", "")) > max_len:
                        sku["name"] = sku["name"][:max_len]
                        return False, True  # 自动修正
                return True, None

            if field == "规格数量" and condition == "小于":
                if len(product.skus) > int(threshold):
                    return False, None
                return True, None

            if field == "规格价格" and condition == "小于":
                prices = [s.get("price", 0) for s in product.skus if s.get("price", 0) > 0]
                if prices and max(prices) / min(prices) > float(threshold):
                    return False, None
                return True, None

            if field == "规格图片" and condition == "不为空":
                for sku in product.skus:
                    if not sku.get("image_url"):
                        return False, None
                return True, None

            if field == "重量" and condition == "取最大值":
                # 取最重规格的重量
                weights = [s.get("weight_g", 0) for s in product.skus]
                if weights:
                    product.weight_g = max(weights)
                return True, True

            if field == "尺寸" and condition == "取最小值":
                # 取最小规格的尺寸
                # TODO: 实现取最小尺寸逻辑
                return True, True

        except (ValueError, TypeError, ZeroDivisionError):
            pass

        return True, None

    def format_description(self, product_desc):
        """组装最终描述：产品特征 + 平台模板"""
        if self.description_template:
            return f"{product_desc}\n\n{self.description_template}"
        return product_desc

    def translate(self, text):
        """翻译为平台目标语言（需豆包API）"""
        from config import config
        if not config.DOUBAO_API_KEY:
            return text  # 未配置API时返回原文
        # TODO: 调用豆包翻译API
        return text

    def upload_media(self, image_urls, video_url):
        """
        上传素材到平台
        Yandex: 直接传URL（COS直链）
        TikTok/Shopee: 需要下载后上传文件
        子类必须实现
        """
        raise NotImplementedError

    def create_listing(self, product, description, media):
        """
        调用平台API上架商品
        子类必须实现
        """
        raise NotImplementedError

    def map_field(self, generic_field):
        """通用字段 → 平台API字段"""
        mapping = self.field_mapping.get(generic_field, {})
        return mapping.get(self.platform_name, generic_field)
