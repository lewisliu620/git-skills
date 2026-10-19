"""
Shopee 平台适配器（泰国站）
通过 Tabbit CLI 操控浏览器上架，不依赖 Shopee Open API。
图片视频先下载到本地，再由 Tabbit 脚本上传到 Shopee 卖家后台。
"""
import os
import json
import subprocess
import tempfile
import requests as http_requests
from config import config
from platforms.base import PlatformAdapter


class ShopeeAdapter(PlatformAdapter):
    platform_name = "Shopee"
    target_language = "th"
    currency = "THB"

    # 泰国站店铺（实际店铺名登录后探测确认）
    SHOPS = ["default"]

    # Tabbit CLI 路径
    TABBIT_CLI = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Tabbit", "LocalAgent", "bin", "tabbit-cli.exe"
    )

    def __init__(self):
        super().__init__()
        self.partner_id = config.SHOPEE_PARTNER_ID
        self.partner_key = config.SHOPEE_PARTNER_KEY
        # 本地素材缓存目录
        self.media_dir = os.path.join(config.TEMP_DIR, "shopee_media")
        os.makedirs(self.media_dir, exist_ok=True)

    def _download_file(self, url, suffix):
        """下载远程文件到本地，返回本地路径"""
        if not url:
            return None
        local_path = os.path.join(self.media_dir, f"{os.urandom(8).hex()}{suffix}")
        try:
            resp = http_requests.get(url, timeout=30)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                return local_path
        except Exception as e:
            print(f"[Shopee] 下载失败 {url}: {e}")
        return None

    def upload_media(self, image_urls, video_url):
        """
        下载图片和视频到本地，返回本地文件路径列表。
        Shopee 后台上传需要本地文件，不能直接传URL。
        """
        local_images = []
        for i, url in enumerate(image_urls[:9]):  # Shopee最多9张图
            path = self._download_file(url, ".jpg")
            if path:
                local_images.append(path)

        local_video = None
        if video_url:
            local_video = self._download_file(video_url, ".mp4")

        return {
            "images": local_images,
            "video": local_video,
        }

    def _run_tabbit(self, js_code, request_id, task_name="Shopee上架"):
        """执行 Tabbit CLI JS 脚本，返回解析后的 JSON"""
        # Windows: 写 UTF-8 无 BOM 临时文件，用 cmd.exe 重定向 stdin
        js_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        )
        try:
            js_file.write(js_code)
            js_file.close()

            cmd = (
                f'"{self.TABBIT_CLI}" nodejs '
                f'--task "{task_name}" '
                f'--request-id "{request_id}" '
                f'--timeout-ms 120000 '
                f'< "{js_file.name}"'
            )
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", cmd],
                capture_output=True, text=True, timeout=150
            )
            output = result.stdout.strip()
            # Tabbit 返回 JSON
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"success": False, "raw": output, "error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Tabbit 执行超时"}
        finally:
            os.unlink(js_file.name)

    def create_listing(self, product, description, media):
        """
        通过 Tabbit CLI 在 Shopee 卖家后台创建商品。
        逐店铺架，每店调用一次上架脚本。
        """
        if not media.get("images"):
            return None, "没有可用的本地图片素材"

        results = []
        errors = []

        for shop in self.SHOPS:
            js = self._build_listing_js(product, description, media, shop)
            result = self._run_tabbit(js, f"publish-{shop}-{product.offer_id}")
            if result.get("success"):
                results.append(shop)
            else:
                errors.append(f"{shop}: {result.get('error', '未知错误')}")

        if results:
            return {"published_shops": results}, None
        return None, "; ".join(errors) if errors else "所有店铺上架失败"

    def _build_listing_js(self, product, description, media, shop):
        """
        构造在 Shopee 卖家后台填写商品表单的 JS。
        选择器已于 2026-10-13 通过 Tabbit CLI 实际探测验证。

        已验证的 DOM 选择器：
        - 商品名称: input[placeholder="Input"]  (class=eds-input__input)
        - 商品描述: textarea.eds-input__inner
        - 类目触发器: .product-category-placeholder (文本"Please set category")
        - 类目弹窗搜索框: input[placeholder="请输入至少 1 个字"]
        - 图片上传: input[type="file"][accept="image/*"] (class=eds-upload__input)
        - 视频上传: input[type="file"][accept="video/mp4"] (class=eds-upload__input)
        - 创建按钮: button:has-text("创建")
        - 创建并发布按钮: button:has-text("创建并发布")
        - 添加商品页 URL: https://seller.shopee.cn/portal/mtsku/new?cnsc_shop_id=1764487938

        注意：销售资料（价格/SKU/库存）需先选类目后才渲染，
        类目选择后需等待页面刷新再填价格。
        """
        title_th = getattr(product, "title_th", "") or self.translate(product.title)
        price_thb = getattr(product, "price_thb", 0)
        stock = getattr(product, "stock", config.DEFAULT_STOCK)
        category_th = getattr(product, "category_th", "")
        images = media["images"]
        video = media.get("video")

        # 转义 JS 字符串中的特殊字符
        title_js = title_th.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        desc_js = description.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        category_js = category_th.replace("\\", "\\\\").replace('"', '\\"')

        images_json = json.dumps(images)
        video_path = video if video else ""

        return f"""
// ===== Shopee 卖家后台自动上架脚本 =====
// 目标店铺: {shop}
// 生成时间: 2026-10-13

const result = {{ steps: [], errors: [] }};

// Step 1: 导航到添加商品页
await page.goto("https://seller.shopee.cn/portal/mtsku/new?cnsc_shop_id=1764487938", {{
  waitUntil: "domcontentloaded", timeout: 45000
}});
await new Promise(r => setTimeout(r, 5000));
result.steps.push("导航到添加商品页");

// Step 2: 上传商品图片
try {{
  const imageInput = page.locator('input[type="file"][accept="image/*"]');
  const imagePaths = {images_json};
  if (imagePaths.length > 0) {{
    await imageInput.setInputFiles(imagePaths);
    await new Promise(r => setTimeout(r, 5000));
    result.steps.push(`上传${{imagePaths.length}}张图片`);
  }}
}} catch(e) {{
  result.errors.push("图片上传失败: " + e.message);
}}

// Step 3: 上传商品视频（如有）
try {{
  const videoPath = "{video_path}";
  if (videoPath) {{
    const videoInput = page.locator('input[type="file"][accept="video/mp4"]');
    await videoInput.setInputFiles(videoPath);
    await new Promise(r => setTimeout(r, 8000));
    result.steps.push("上传视频");
  }}
}} catch(e) {{
  result.errors.push("视频上传失败: " + e.message);
}}

// Step 4: 填写商品名称
try {{
  const titleInput = page.locator('input[placeholder="Input"]');
  await titleInput.fill("{title_js[:180]}");
  result.steps.push("填写商品名称");
}} catch(e) {{
  result.errors.push("商品名称填写失败: " + e.message);
}}

// Step 5: 填写商品描述
try {{
  const descInput = page.locator('textarea.eds-input__inner');
  await descInput.fill("{desc_js[:5000]}");
  result.steps.push("填写商品描述");
}} catch(e) {{
  result.errors.push("商品描述填写失败: " + e.message);
}}

// Step 6: 选择类目
try {{
  await page.locator('.product-category-placeholder').click();
  await new Promise(r => setTimeout(r, 2000));
  // 在类目弹窗搜索框输入类目关键词
  const catSearch = page.locator('input[placeholder="请输入至少 1 个字"]');
  await catSearch.fill("{category_js}");
  await new Promise(r => setTimeout(r, 2000));
  // 点击搜索结果第一个类目
  const firstCat = page.locator('.eds-cascader-menu__listitem, .category-list-item, li').first();
  await firstCat.click();
  await new Promise(r => setTimeout(r, 3000));
  result.steps.push("选择类目");
}} catch(e) {{
  result.errors.push("类目选择失败: " + e.message);
}}

// Step 7: 填写销售资料（价格/SKU/库存）
// TODO: 类目选择后销售资料tab会渲染价格字段，需进一步探测具体选择器
// 已知左侧步骤导航：基本信息 / 销售资料 / 运费 / 其他
try {{
  // 点击"销售资料"步骤
  await page.locator('a:has-text("销售资料"), [role="link"]:has-text("销售资料")').first().click();
  await new Promise(r => setTimeout(r, 3000));
  // TODO: 探测价格输入框、SKU规格、库存字段后补充
  result.steps.push("切换到销售资料tab（价格字段待探测）");
}} catch(e) {{
  result.errors.push("销售资料tab切换失败: " + e.message);
}}

// Step 8: 点击"创建并发布"
try {{
  const publishBtn = page.locator('button:has-text("创建并发布")');
  // 按钮可能初始disabled，等待可用
  await publishBtn.waitFor({{state: "visible", timeout: 10000}});
  await new Promise(r => setTimeout(r, 2000));
  await publishBtn.click();
  await new Promise(r => setTimeout(r, 10000));
  result.steps.push("点击创建并发布");
}} catch(e) {{
  result.errors.push("发布按钮点击失败: " + e.message);
}}

result.finalUrl = page.url();
result.success = result.errors.length === 0;
return result;
"""

    def update_price(self, offer_id, price):
        """更新价格（通过 Tabbit 进入编辑页修改）"""
        js = f"""
// TODO: Phase 2 实现价格更新
return {{offerId: "{offer_id}", price: {price}, action: "update_price"}};
"""
        return self._run_tabbit(js, f"price-{offer_id}")
