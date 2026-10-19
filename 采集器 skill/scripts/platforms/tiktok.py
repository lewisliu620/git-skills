"""
TikTok Shop 平台适配器（骨架）
需要上传图片视频文件到平台
"""
from platforms.base import PlatformAdapter


class TikTokAdapter(PlatformAdapter):
    platform_name = "TikTok Shop"
    target_language = "en"
    currency = "USD"

    def __init__(self):
        super().__init__()
        self.app_key = config.TIKTOK_APP_KEY
        self.app_secret = config.TIKTOK_APP_SECRET
        self.default_brand = config.DEFAULT_TIKTOK_BRAND

    def _normalize_brand(self, brand):
        """品牌归一化：空或无品牌时使用默认值"""
        if not brand or brand in ("无品牌", "无", "其他", "其它", config.DEFAULT_BRAND):
            return self.default_brand
        return brand

    def upload_media(self, image_urls, video_url):
        """TikTok 需要下载文件后上传"""
        # TODO: 实现图片上传 → 返回 image_id 列表
        # TODO: 实现视频上传 → 返回 video_id
        return {"images": [], "video_id": ""}

    def create_listing(self, product, description, media):
        """调用 TikTok Shop API 上架"""
        if not self.app_key:
            return None, "TikTok App Key 未配置"
        # 品牌处理：无品牌时使用默认值
        brand = self._normalize_brand(product.brand)
        # TODO: 实现 TikTok Shop 商品创建 API
        return None, "TikTok Shop 上架功能待实现"
