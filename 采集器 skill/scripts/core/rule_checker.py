"""
通用选品规则校验
从飞书「选品规则配置表」读取规则，对采集到的商品进行前置过滤
"""
from feishu_api import feishu, TABLE_IDS


class RuleChecker:
    """选品规则校验器"""

    def __init__(self):
        self.rules = self._load_rules()

    def _load_rules(self):
        """从飞书加载选品规则"""
        try:
            records = feishu.load_config_table(TABLE_IDS["selection_rules"])
            return [r for r in records if r.get("是否启用", False)]
        except Exception as e:
            print(f"[规则校验] 加载规则失败: {e}")
            return []

    def reload(self):
        """重新加载规则"""
        self.rules = self._load_rules()

    def check(self, product):
        """
        校验商品是否符合选品规则
        返回 (passed: bool, fail_reasons: list)
        硬性规则不通过 → 淘汰；软性规则不通过 → 标记提醒但不淘汰

        W-02（2026-10-19）：视频/一件代发/重量/起批属 S2 复核项，即使配置为
        「硬性规则」也只提醒不淘汰（S0 口径：S2 复核项不淘汰，待全量采集后复核）。
        """
        fail_reasons = []
        hard_fail = False

        # S2 复核项关键词：这些在采集阶段拿不全（视频直出页常缺 url、重量常缺），
        # 不因缺项直接淘汰商品，只进提醒
        S2_SOFT_KEYWORDS = ("视频", "一件代发", "代发", "重量", "千克", "kg", "起批", "起订")

        for rule in self.rules:
            rule_name = rule.get("规则名称", "")
            rule_type = rule.get("规则类型", [""])[0] if isinstance(rule.get("规则类型"), list) else rule.get("规则类型", "")
            condition = rule.get("条件", [""])[0] if isinstance(rule.get("条件"), list) else rule.get("条件", "")
            threshold = rule.get("阈值", "")
            is_hard = rule_type == "硬性规则"
            # S2 项降级为软提醒
            if is_hard and any(k in rule_name for k in S2_SOFT_KEYWORDS):
                is_hard = False

            passed, reason = self._check_single_rule(product, rule_name, condition, threshold)
            if not passed:
                fail_reasons.append(f"[{rule_type}] {rule_name}: {reason}")
                if is_hard:
                    hard_fail = True

        return (not hard_fail), fail_reasons

    def _check_single_rule(self, product, rule_name, condition, threshold):
        """校验单条规则"""
        rule_name_lower = rule_name.lower()

        # 必须有商品视频
        if "视频" in rule_name:
            has_video = bool(product.video_url)
            if condition == "必须有" and not has_video:
                return False, "商品无视频"
            return True, ""

        # 必须支持一件代发
        if "一件代发" in rule_name or "代发" in rule_name:
            if condition == "必须支持" and not product.supports_drop_shipping:
                return False, "供应商不支持一件代发"
            return True, ""

        # 价格区间
        if "价格" in rule_name:
            try:
                price = product.price
                th = float(threshold)
                if condition == "大于" and price <= th:
                    return False, f"价格{price}≤{th}"
                if condition == "小于" and price >= th:
                    return False, f"价格{price}≥{th}"
            except (ValueError, TypeError):
                pass
            return True, ""

        # 重量限制
        if "重量" in rule_name:
            try:
                weight_g = product.weight_g
                th = float(threshold)
                # 阈值单位可能是kg或g
                if "kg" in rule_name.lower() or "千克" in rule_name:
                    th_g = th * 1000
                else:
                    th_g = th
                if condition == "小于" and weight_g >= th_g:
                    return False, f"重量{weight_g}g≥{th_g}g"
            except (ValueError, TypeError):
                pass
            return True, ""

        # 起批量
        if "起批" in rule_name or "起订" in rule_name:
            try:
                min_order = product.min_order
                th = int(threshold)
                if condition == "小于等于" and min_order > th:
                    return False, f"起批量{min_order}>{th}"
                if condition == "等于" and min_order != th:
                    return False, f"起批量{min_order}≠{th}"
            except (ValueError, TypeError):
                pass
            return True, ""

        # 类目排除
        if "类目" in rule_name or "分类" in rule_name:
            if threshold and threshold in product.category:
                return False, f"类目'{product.category}'包含排除词'{threshold}'"
            return True, ""

        # 默认通过
        return True, ""


def check_product(product):
    """便捷函数"""
    checker = RuleChecker()
    return checker.check(product)
