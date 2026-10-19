"""
core/dedup.py — #48 候选表去重（纯函数，无飞书依赖）

口径（用户 2026-10-18 拍板）：
  · 去重键 = 1688 OfferID（数字长ID），精确匹配，不用模糊商品名（同名不同款会误删）。
  · 双向去重：① 候选表内已有同 OfferID → 跳过；② 主表「采购链接」已存在同 OfferID
    → 不重复进候选（已全档案采集过的商品不再进选品候选）。
  · OfferID 从采购链接 / offerId 字段 / 任意文本中的 /offer/<id> 或 offer=<id> 提取。

读取候选表/主表现有集合由调用方（lark-cli --as user 或 feishu_api）预取后注入，
本模块保持离线可测；不直接发起飞书请求。
"""
import re

# 1688 offer id：1688 数字ID通常 9-14 位；/offer/数字.html、offerId=数字、裸数字串
_OFFER_URL_RE = re.compile(r"/offer/(\d{6,})")
_OFFER_KV_RE = re.compile(r"offer(?:Id|id)?[=/](\d{6,})")
_BARE_RE = re.compile(r"\b(\d{9,14})\b")


def extract_offer_id(text):
    """
    从链接/字段/任意文本提取 1688 OfferID；提取不到返回 None。
    优先级：/offer/<id> > offerId=<id> > 长数字串。
    """
    if text is None:
        return None
    if isinstance(text, dict):
        text = text.get("link") or text.get("text") or text.get("offerId") or ""
    text = str(text)

    m = _OFFER_URL_RE.search(text)
    if m:
        return m.group(1)
    m = _OFFER_KV_RE.search(text)
    if m:
        return m.group(1)
    m = _BARE_RE.search(text)
    if m:
        return m.group(1)
    return None


def normalize_offer_id(offer_id):
    """去前导零、转字符串；空值返回 None。"""
    if offer_id is None:
        return None
    s = str(offer_id).strip()
    if not s or not s.isdigit():
        return None
    return str(int(s))


class DedupIndex:
    """已见 OfferID 集合，支持从候选表/主表记录批量预加载。"""

    def __init__(self, existing_offer_ids=None):
        self._seen = set()
        for oid in existing_offer_ids or []:
            self.add(oid)

    def add(self, offer_id):
        n = normalize_offer_id(offer_id)
        if n:
            self._seen.add(n)

    def has(self, offer_id):
        n = normalize_offer_id(offer_id)
        return n is not None and n in self._seen

    def size(self):
        return len(self._seen)

    @classmethod
    def from_records(cls, records, link_fields=("采购链接", "1688 OfferID", "参考竞品链接")):
        """
        从飞书记录列表预加载去重集合。
        records: [{"fields": {...}}]；link_fields 为可能承载 offerId 的字段名（按序尝试）。
        """
        index = cls()
        for rec in records or []:
            fields = rec.get("fields", rec) if isinstance(rec, dict) else {}
            for fname in link_fields:
                val = fields.get(fname)
                if val is None:
                    continue
                # 字段可能是 str / url 对象 / list
                candidates = val if isinstance(val, list) else [val]
                for c in candidates:
                    oid = extract_offer_id(c)
                    if oid:
                        index.add(oid)
        return index


def is_duplicate(offer_id, candidate_index: DedupIndex, master_index: DedupIndex = None):
    """
    判定是否重复：候选表内命中，或主表采购链接命中，均视为重复。
    返回 (duplicated: bool, where: str|None)。
    """
    if candidate_index and candidate_index.has(offer_id):
        return True, "candidate"
    if master_index and master_index.has(offer_id):
        return True, "master"
    return False, None
