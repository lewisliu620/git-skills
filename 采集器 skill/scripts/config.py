"""
全局配置管理
从 .env 文件读取所有 API Key 和配置项（零依赖：dotenv 缺失时用标准库解析）
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv 未安装时的兜底：手动解析 .env（KEY=VALUE，跳过注释/空行）
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        try:
            with open(_env_path, "r", encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if not _line or _line.startswith("#") or "=" not in _line:
                        continue
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        except OSError:
            pass

class Config:
    # 飞书
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_BASE_TOKEN = os.getenv("FEISHU_BASE_TOKEN", "QsnYbrWpaa6lGfspgLpcihfvnpb")

    # 豆包
    DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
    DOUBAO_BASE_URL = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

    # 腾讯云 COS
    COS_SECRET_ID = os.getenv("COS_SECRET_ID", "")
    COS_SECRET_KEY = os.getenv("COS_SECRET_KEY", "")
    COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")
    COS_BUCKET = os.getenv("COS_BUCKET", "")
    COS_DOMAIN = os.getenv("COS_DOMAIN", "")

    # Yandex
    YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
    YANDEX_BUSINESS_ID = os.getenv("YANDEX_BUSINESS_ID", "")
    YANDEX_CAMPAIGN_ID = os.getenv("YANDEX_CAMPAIGN_ID", "")

    # TikTok Shop
    TIKTOK_APP_KEY = os.getenv("TIKTOK_APP_KEY", "")
    TIKTOK_APP_SECRET = os.getenv("TIKTOK_APP_SECRET", "")

    # Shopee
    SHOPEE_PARTNER_ID = os.getenv("SHOPEE_PARTNER_ID", "")
    SHOPEE_PARTNER_KEY = os.getenv("SHOPEE_PARTNER_KEY", "")

    # 路径
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    SESSION_FILE = os.path.join(BASE_DIR, "1688_session.json")
    IMAGE_CACHE_FILE = os.path.join(BASE_DIR, "processed_images.json")

    # 采集器默认值
    DEFAULT_STOCK = 500              # 默认库存
    DEFAULT_BRAND = "无品牌"          # 默认品牌
    DEFAULT_TIKTOK_BRAND = "No Brand" # TikTok默认品牌
    MAX_DESCRIPTION_LENGTH = 5000    # 描述最大长度
    MAX_DETAIL_IMAGES = 10           # 详情图最大存储数量
    MAX_MAIN_IMAGES = 5              # 主图最大数量

    # 违禁词默认列表（与飞书违禁词配置表一致，飞书配置优先）
    DEFAULT_FORBIDDEN_WORDS = [
        "批发", "跨境", "外贸", "工厂", "出口", "授权",
        "淘宝", "拼多多", "1688", "阿里巴巴", "京东", "天猫", "抖音",
        "工厂直销", "一件代发", "厂家",
    ]

    # 聚合属性
    @property
    def COS_CONFIG(self):
        return {
            "secret_id": self.COS_SECRET_ID,
            "secret_key": self.COS_SECRET_KEY,
            "region": self.COS_REGION,
            "bucket": self.COS_BUCKET,
            "domain": self.COS_DOMAIN,
        }

    @classmethod
    def check_required(cls, keys):
        """检查必要配置是否存在，返回缺失列表"""
        missing = []
        for key in keys:
            if not getattr(cls, key, ""):
                missing.append(key)
        return missing

config = Config()
