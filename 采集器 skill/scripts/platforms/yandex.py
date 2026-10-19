"""
Yandex Market 平台适配器
通过官方 API 上架，图片视频通过 URL 传入（需先转存 COS）
"""
import requests
from config import config
from platforms.base import PlatformAdapter


class YandexAdapter(PlatformAdapter):
    platform_name = "Yandex Market"
    target_language = "ru"
    currency = "RUB"
    BASE_URL = "https://api.partner.market.yandex.ru"

    def __init__(self):
        super().__init__()
        self.api_key = config.YANDEX_API_KEY
        self.business_id = config.YANDEX_BUSINESS_ID
        self.campaign_id = config.YANDEX_CAMPAIGN_ID

    def _headers(self):
        return {
            "Authorization": f"OAuth {self.api_key}",
            "Content-Type": "application/json"
        }

    def upload_media(self, image_urls, video_url):
        """Yandex 直接传 URL，不需要上传文件"""
        return {
            "images": image_urls,
            "video": video_url
        }

    def create_listing(self, product, description, media):
        """
        调用 Yandex API 上架商品
        POST /v2/businesses/{businessId}/offer-mappings/update
        """
        if not self.api_key or not self.business_id:
            return None, "Yandex API Key 或 Business ID 未配置"

        # 组装 SKU
        offers = []
        for sku in product.skus:
            offer = {
                "offer": {
                    "offerId": f"{product.offer_id}_{sku.get('name', '')}",
                    "name": self.translate(product.title)[:200],
                    "description": description,
                    "category": product.category,
                    "pictures": media["images"][:10],
                    "weightDimensions": {
                        "weight": product.weight_g / 1000,  # g → kg
                        "length": product.dimensions_mm[0] / 10,  # mm → cm
                        "width": product.dimensions_mm[1] / 10,
                        "height": product.dimensions_mm[2] / 10,
                    },
                    "vendor": "No Brand",
                },
                "mapping": {
                    "marketCategoryId": 0,  # TODO: 类目映射
                }
            }
            if media.get("video"):
                offer["offer"]["video"] = media["video"]
            offers.append(offer)

        payload = {"offerMappings": offers}
        url = f"{self.BASE_URL}/v2/businesses/{self.business_id}/offer-mappings/update"

        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            data = resp.json()
            if resp.status_code == 200:
                return data, None
            return None, f"API错误: {data}"
        except Exception as e:
            return None, str(e)

    def update_price(self, offer_id, price):
        """更新价格"""
        url = f"{self.BASE_URL}/businesses/{self.business_id}/offer-prices/updates"
        payload = {"offers": [{"offerId": offer_id, "price": {"value": price, "currencyId": "RUR"}}]}
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=15)
        return resp.json()
