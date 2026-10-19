"""
1688 商品信息采集模块
方案 B1：用 requests 请求 1688 移动端页面（m.1688.com），解析页面内嵌 JSON 数据
移动端页面无 x5sec 风控，可直接采集
维护 cookie 登录态（1688_session.json）
"""
import re
import json
import os
import requests
from config import config


class Product1688:
    """1688 商品数据结构"""
    def __init__(self):
        self.offer_id = ""
        self.title = ""
        self.description = ""          # 商品描述（清洗后）
        self.brand = ""                # 品牌
        self.price = 0.0
        self.price_range = []
        self.skus = []
        self.images = []
        self.detail_images = []
        self.video_url = ""
        self.attributes = {}           # 商品属性（品牌、材质、产地等）
        self.stock = 500               # 库存（默认500）
        self.vendor_code = ""          # 货号
        self.category_id = ""          # 1688类目ID
        self.category_path = ""        # 1688类目路径
        self.weight_g = 0.0
        self.dimensions_mm = (0, 0, 0)
        self.category = ""
        self.supplier_name = ""
        self.supplier_id = ""
        self.min_order = 1
        self.supports_drop_shipping = False
        self.raw_data = {}

    def to_dict(self):
        return {
            "offer_id": self.offer_id,
            "title": self.title,
            "description": self.description,
            "brand": self.brand,
            "price": self.price,
            "skus": self.skus,
            "images": self.images,
            "detail_images": self.detail_images,
            "video_url": self.video_url,
            "attributes": self.attributes,
            "stock": self.stock,
            "vendor_code": self.vendor_code,
            "category_id": self.category_id,
            "weight_g": self.weight_g,
            "dimensions_mm": self.dimensions_mm,
            "category": self.category,
            "supplier_name": self.supplier_name,
            "min_order": self.min_order,
            "supports_drop_shipping": self.supports_drop_shipping,
        }


def _extract_json_obj(text, key):
    """从文本中提取 key 对应的 JSON 对象 {...}"""
    idx = text.find(f'"{key}"')
    if idx < 0:
        return None
    start = text.find('{', idx)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def _extract_json_arr(text, key):
    """从文本中提取 key 对应的 JSON 数组 [...]"""
    idx = text.find(f'"{key}"')
    if idx < 0:
        return None
    start = text.find('[', idx)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


class Fetcher1688:
    """1688 采集器（移动端页面）"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://m.1688.com/",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._load_cookies()

    def _load_cookies(self):
        if os.path.exists(config.SESSION_FILE):
            try:
                with open(config.SESSION_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                for name, value in cookies.items():
                    self.session.cookies.set(name, value, domain=".1688.com")
                print(f"[1688] 已加载登录态，{len(cookies)} 个 cookie")
            except Exception as e:
                print(f"[1688] 加载登录态失败: {e}")
        else:
            print("[1688] 未找到登录态文件，以未登录状态采集")

    def save_cookies(self):
        cookies = {}
        for cookie in self.session.cookies:
            if "1688.com" in cookie.domain:
                cookies[cookie.name] = cookie.value
        with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    def extract_offer_id(self, url_or_id):
        m = re.search(r'/offer/(\d+)\.html', url_or_id)
        if m:
            return m.group(1)
        m = re.search(r'offer[=/](\d+)', url_or_id)
        if m:
            return m.group(1)
        if url_or_id.isdigit():
            return url_or_id
        raise ValueError(f"无法提取商品ID: {url_or_id}")

    def fetch(self, url_or_id):
        offer_id = self.extract_offer_id(url_or_id)
        print(f"[1688] 开始采集商品 {offer_id}")

        detail_url = f"https://m.1688.com/offer/{offer_id}.html"
        resp = self.session.get(detail_url, timeout=15, allow_redirects=True)
        resp.encoding = "utf-8"

        # Cookie过期/被拦截检测
        if resp.status_code != 200:
            raise Exception(f"采集失败，HTTP {resp.status_code}")

        if "punish" in resp.text or "x5sec" in resp.text:
            raise Exception("被1688反爬拦截（x5sec验证），cookie可能已过期。请运行: python update_cookie.py")

        if "login.1688.com" in resp.url or "passport" in resp.url:
            raise Exception("被重定向到登录页，cookie已过期。请运行: python update_cookie.py")

        if len(resp.text) < 5000:
            raise Exception(f"响应内容过小（{len(resp.text)}字节），可能被拦截或cookie过期。请运行: python update_cookie.py")

        product = self._parse_mobile_page(resp.text, offer_id)
        product.offer_id = offer_id

        # 数据完整性检测：标题为空说明可能cookie过期或页面结构变化
        if not product.title:
            raise Exception("采集到的商品标题为空，可能cookie过期或页面结构变化。请运行: python update_cookie.py")

        # 采集商品描述（从detailUrl，可选，失败不影响主流程）
        self._fetch_description(resp.text, product)

        self.save_cookies()

        print(f"[1688] 采集完成: {product.title[:30]}...")
        return product

    def _fetch_description(self, html, product):
        """从detailUrl采集商品描述并做基础清洗"""
        try:
            detail_match = re.search(r'"detailUrl"\s*:\s*"([^"]+)"', html)
            if not detail_match:
                return
            detail_url = detail_match.group(1)
            if not detail_url.startswith("http"):
                return

            resp = self.session.get(detail_url, timeout=10)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                return

            # detailUrl返回格式: var offer_details={"content":"<div>..."}
            content_match = re.search(r'offer_details\s*=\s*(\{.*\})', resp.text, re.DOTALL)
            if not content_match:
                return

            try:
                detail_data = json.loads(content_match.group(1))
                content_html = detail_data.get("content", "")
            except (json.JSONDecodeError, ValueError):
                # 可能是不完整的JSON，尝试提取content字段
                content_html_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', content_match.group(1))
                if content_html_match:
                    content_html = content_html_match.group(1).encode().decode('unicode_escape')
                else:
                    return

            # 从content中提取详情图
            detail_imgs = re.findall(r'<img[^>]+src="([^"]+)"', content_html)
            if detail_imgs:
                # 过滤掉gif（通常是公司实力图）和过小的图片
                product.detail_images = [img for img in detail_imgs if not img.endswith('.gif')][:config.MAX_DETAIL_IMAGES + 10]  # 多取一些备用

            # 提取描述文本（去除HTML标签）
            text = re.sub(r'<[^>]+>', ' ', content_html)
            text = re.sub(r'&[a-zA-Z]+;', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            # 基础清洗
            text = self._clean_description(text)

            if len(text) > 20:
                product.description = text[:config.MAX_DESCRIPTION_LENGTH]
        except Exception as e:
            pass

    @staticmethod
    def _clean_description(text):
        """描述基础清洗：去除违禁词、营销话术、无关信息"""
        # 违禁词列表（从配置读取，后续可改为从飞书违禁词配置表动态读取）
        forbidden = config.DEFAULT_FORBIDDEN_WORDS
        for word in forbidden:
            text = text.replace(word, "")

        # 去除常见营销话术
        marketing = ["点击购买", "立即抢购", "限时优惠", "秒杀", "包邮", "特价", "清仓",
                     "厂家直销", "量大从优", "支持定制", "来样加工", "OEM", "ODM"]
        for word in marketing:
            text = text.replace(word, "")

        # 去除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def check_cookie_valid(self):
        """快速检测cookie是否有效（访问1688首页，不采集商品）"""
        try:
            resp = self.session.get("https://m.1688.com/", timeout=10, allow_redirects=True)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            if "login.1688.com" in resp.url or "passport" in resp.url:
                return False, "被重定向到登录页"
            if "punish" in resp.text or "x5sec" in resp.text:
                return False, "被反爬拦截"
            return True, "正常"
        except Exception as e:
            return False, str(e)

    def _parse_mobile_page(self, html, offer_id):
        product = Product1688()

        # 1. 基本信息 offerInfoModel
        offer_json = _extract_json_obj(html, "offerInfoModel")
        if offer_json:
            try:
                offer = json.loads(offer_json)
                product.title = offer.get("title", "")
                price_str = str(offer.get("price", "0"))
                if "-" in price_str:
                    parts = price_str.split("-")
                    product.price = float(parts[0])
                    product.price_range = [(1, float(parts[0])), (1, float(parts[1]))]
                else:
                    product.price = float(price_str) if price_str else 0
            except (json.JSONDecodeError, ValueError):
                pass

        # 2. 主图 offerImages
        images_json = _extract_json_arr(html, "offerImages")
        if images_json:
            try:
                images = json.loads(images_json)
                product.images = [img.get("imgUrl", "") for img in images if img.get("imgUrl")]
            except json.JSONDecodeError:
                pass

        # 3. 视频 videoUrl
        video_match = re.search(r'"videoUrl"\s*:\s*"([^"]+)"', html)
        if video_match:
            product.video_url = video_match.group(1)

        # 4. SKU规格维度 skuProps
        sku_props = []
        sku_props_json = _extract_json_arr(html, "skuProps")
        if sku_props_json:
            try:
                sku_props = json.loads(sku_props_json)
            except json.JSONDecodeError:
                pass

        # 5. SKU详情 specAttrs
        sku_details = {}
        spec_json = _extract_json_obj(html, "specAttrs")
        if spec_json:
            try:
                sku_details = json.loads(spec_json)
            except json.JSONDecodeError:
                pass

        # 6. 组装SKU列表
        if sku_props and len(sku_props) == 1:
            prop = sku_props[0]
            prop_name = prop.get("prop", "")
            for value in prop.get("value", []):
                sku_name = value.get("name", "")
                sku_image = value.get("imageUrl", "")
                sku_price = product.price
                for key, detail in sku_details.items():
                    if isinstance(detail, dict):
                        if key == sku_name or sku_name in str(detail.get("specAttrs", "")):
                            try:
                                sku_price = float(detail.get("price", product.price))
                            except (ValueError, TypeError):
                                pass
                            break
                product.skus.append({
                    "name": sku_name,
                    "price": sku_price,
                    "image_url": sku_image,
                    "spec_attrs": {prop_name: sku_name},
                })
        elif sku_props:
            for prop in sku_props:
                prop_name = prop.get("prop", "")
                for value in prop.get("value", []):
                    product.skus.append({
                        "name": value.get("name", ""),
                        "price": product.price,
                        "image_url": value.get("imageUrl", ""),
                        "spec_attrs": {prop_name: value.get("name", "")},
                    })

        if not product.skus:
            product.skus.append({
                "name": "默认",
                "price": product.price,
                "image_url": product.images[0] if product.images else "",
                "spec_attrs": {},
            })

        # 7. 详情图：过滤主图和SKU图后剩下的alicdn图片
        all_images = re.findall(r'https://cbu01\.alicdn\.com/[^"\']+\.jpg', html)
        unique_images = list(dict.fromkeys(all_images))
        used_urls = set(product.images)
        for sku in product.skus:
            if sku.get("image_url"):
                used_urls.add(sku["image_url"])
        product.detail_images = [img for img in unique_images if img not in used_urls]

        # 8. 从SKU名称提取尺寸
        self._extract_dimensions_from_skus(product)

        # 9. 供应商
        supplier_match = re.search(r'"(?:companyName|shopName|sellerNick)"\s*:\s*"([^"]+)"', html)
        if supplier_match:
            product.supplier_name = supplier_match.group(1)
        member_match = re.search(r'"(?:memberId|sellerId|shopId)"\s*:\s*"?(\d+)"?', html)
        if member_match:
            product.supplier_id = member_match.group(1)

        # 10. 一件代发
        if "一件代发" in html or "代发" in html:
            product.supports_drop_shipping = True

        # 11. 起批量
        min_order_match = re.search(r'"(?:minOrderQuantity|beginAmount)"\s*:\s*"?(\d+)"?', html)
        if min_order_match:
            product.min_order = int(min_order_match.group(1))

        # 12. 商品属性 propsList（品牌、货号、材质、产地等）
        props_json = _extract_json_arr(html, "propsList")
        if props_json:
            try:
                props = json.loads(props_json)
                for p in props:
                    name = p.get("name", "")
                    value = p.get("value", "")
                    if name and value:
                        product.attributes[name] = value
                # 提取品牌
                if "品牌" in product.attributes:
                    product.brand = product.attributes["品牌"]
                # 提取货号
                if "货号" in product.attributes:
                    product.vendor_code = product.attributes["货号"]
            except json.JSONDecodeError:
                pass

        # 13. 1688类目ID
        cat_match = re.search(r'"postCategoryId"\s*:\s*"(\d+)"', html)
        if cat_match:
            product.category_id = cat_match.group(1)

        # 14. 库存（默认500，1688可采购量作为参考）
        stock_match = re.search(r'"canBookCount"\s*:\s*"?(\d+)"?', html)
        if stock_match:
            can_book = int(stock_match.group(1))
            # 跨境店用固定库存，避免超卖；1688可采购量仅作参考
            product.stock = config.DEFAULT_STOCK if can_book > 0 else 0
        else:
            product.stock = config.DEFAULT_STOCK

        # 15. SKU重量（取最大值，单位kg转g）
        sku_weight_match = re.search(r'"skuWeight"\s*:\s*\{([^}]+)\}', html)
        if sku_weight_match:
            weights = re.findall(r':\s*([\d.]+)', sku_weight_match.group(1))
            if weights:
                max_weight_kg = max(float(w) for w in weights)
                if max_weight_kg > 0:
                    product.weight_g = max_weight_kg * 1000

        product.raw_data = {"sku_props": sku_props, "sku_details": sku_details}
        return product

    def _extract_dimensions_from_skus(self, product):
        """从SKU名称提取尺寸（如 45*45CM），估算重量"""
        all_dims = []
        for sku in product.skus:
            name = sku.get("name", "")
            dim_match = re.search(r'(\d+)\s*[*xX×]\s*(\d+)(?:\s*[*xX×]\s*(\d+))?\s*(cm|CM|毫米|mm|MM)?', name)
            if dim_match:
                l = int(dim_match.group(1))
                w = int(dim_match.group(2))
                h = int(dim_match.group(3)) if dim_match.group(3) else 1
                unit = dim_match.group(4) or "cm"
                if unit.lower() in ("cm", "厘米"):
                    all_dims.append((l * 10, w * 10, h * 10))
                else:
                    all_dims.append((l, w, h))

        if all_dims:
            min_dim = min(all_dims, key=lambda x: x[0] * x[1] * x[2])
            product.dimensions_mm = min_dim
            vol_cm3 = (min_dim[0] / 10) * (min_dim[1] / 10) * (min_dim[2] / 10)
            product.weight_g = max(10, vol_cm3 * 0.05)


def fetch_product(url_or_id):
    fetcher = Fetcher1688()
    return fetcher.fetch(url_or_id)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        p = fetch_product(sys.argv[1])
        print(json.dumps(p.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("用法: python fetcher.py <1688商品链接或ID>")
