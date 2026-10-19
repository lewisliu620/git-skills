"""
飞书多维表格 API 封装（零密钥版 2026-10-19）
================================================
职责：读写商品主表、选品候选表、各配置表。

通道策略（W-01 已拍板：采集器飞书读写全部走 lark-cli --as user，与 1688-worker 一致）：
  1. 主通道 lark-cli --as user：自动发现 sandbox_envs_dir 下 lark-cli.exe，
     record-list / record-batch-create / record-batch-update 走 CLI，无需 app_id/secret；
  2. HTTP 通道（open.feishu.cn tenant_access_token）仅当 .env 配了 FEISHU_APP_ID/SECRET
     时作为 fallback 启用，未配则自动走 lark-cli，不再因 code10003 阻塞落库。

返回结构兼容原接口：
  list_records → [{"record_id": "xxx", "fields": {...}}, ...]
  create_record → 返回 {"code": 0, "data": {"record": {"record_id": "xxx"}}}
  update_record → 返回 {"code": 0}
"""
import json
import os
import subprocess
import time
try:
    import requests  # 仅 HTTP fallback 用；未安装时自动降级 lark-cli 主通道
except ImportError:
    requests = None
from config import config


def _find_lark_cli():
    """自动发现 lark-cli.exe（优先环境变量，其次扫描 sandbox_envs_dir）"""
    env = os.environ.get("LARK_CLI", "")
    if env and os.path.exists(env):
        return env
    envs_root = r"C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs"
    if os.path.isdir(envs_root):
        try:
            for env_name in os.listdir(envs_root):
                p = os.path.join(envs_root, env_name, "override_dlcs", "lark-cli.exe")
                if os.path.exists(p):
                    return p
        except OSError:
            pass
    return None


class LarkCliError(Exception):
    """lark-cli 调用失败"""


class FeishuAPI:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self):
        self.app_id = config.FEISHU_APP_ID
        self.app_secret = config.FEISHU_APP_SECRET
        self.base_token = config.FEISHU_BASE_TOKEN
        self._tenant_token = None
        self._token_expire = 0
        self._lark_cli = _find_lark_cli()
        self._http_ok = bool(self.app_id and self.app_secret and requests)

    # ================= lark-cli 通道（主通道） =================

    def _lark(self, args, timeout=120):
        """调 lark-cli --as user，返回 (exit_code, stdout)"""
        if not self._lark_cli:
            raise LarkCliError("未找到 lark-cli.exe（sandbox_envs_dir 扫描失败）")
        full = [self._lark_cli, "--as", "user"] + args
        proc = subprocess.run(full, capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    @staticmethod
    def _write_json_tmp(payload):
        """写临时 JSON 文件（lark-cli --json @file 用），返回路径"""
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lark_tmp.json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return tmp

    def _parse_record_list(self, out):
        """解析 lark-cli +record-list --format json 输出 → items 结构"""
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            raise LarkCliError(f"record-list 输出非 JSON: {out[:300]}")
        inner = data.get("data", {})
        rows = inner.get("data", [])            # 二维矩阵：行 x 列
        fields = inner.get("fields", [])        # 列名（顺序对应）
        record_ids = inner.get("record_id_list", [])
        items = []
        for i, row in enumerate(rows):
            rec = dict(zip(fields, row))
            items.append({
                "record_id": record_ids[i] if i < len(record_ids) else "",
                "fields": rec,
            })
        return items

    # ===== 表结构 =====

    def list_tables(self):
        """列出所有表"""
        code, out = self._lark(["base", "+table-list", "--base-token", self.base_token, "--format", "json"])
        if code != 0:
            raise LarkCliError(f"table-list 失败: {out[:300]}")
        data = json.loads(out)
        return data.get("data", {}).get("tables", data.get("data", {}).get("items", []))

    def list_fields(self, table_id):
        """列出表的所有字段"""
        code, out = self._lark(["base", "+field-list", "--base-token", self.base_token,
                                "--table-id", table_id, "--format", "json"])
        if code != 0:
            raise LarkCliError(f"field-list 失败: {out[:300]}")
        data = json.loads(out)
        return data.get("data", {}).get("fields", [])

    # ===== 记录读写 =====

    def list_records(self, table_id, filter_expr=None, page_size=100):
        """读取记录，兼容原 HTTP 通道返回 items 结构"""
        # HTTP 通道仅在 .env 已配凭证时尝试；否则直接走 lark-cli
        if self._http_ok:
            try:
                return self._list_records_http(table_id, filter_expr, page_size)
            except Exception as e:
                print(f"[飞书] HTTP 通道失败({e})，降级 lark-cli")
        code, out = self._lark(["base", "+record-list", "--base-token", self.base_token,
                                "--table-id", table_id, "--format", "json",
                                "--limit", str(page_size)])
        if code != 0:
            raise LarkCliError(f"record-list 失败: {out[:300]}")
        return self._parse_record_list(out)

    def _list_records_http(self, table_id, filter_expr=None, page_size=100):
        """原 HTTP 通道（保留，仅 .env 已配凭证时用）"""
        params = {"page_size": page_size}
        if filter_expr:
            params["filter"] = filter_expr
        resp = requests.get(
            f"{self.BASE_URL}/bitable/v1/apps/{self.base_token}/tables/{table_id}/records",
            headers=self._headers(), params=params, timeout=15)
        return resp.json().get("data", {}).get("items", [])

    def get_record(self, table_id, record_id):
        """读取单条记录"""
        if self._http_ok:
            try:
                resp = requests.get(
                    f"{self.BASE_URL}/bitable/v1/apps/{self.base_token}/tables/{table_id}/records/{record_id}",
                    headers=self._headers(), timeout=10)
                return resp.json().get("data", {}).get("record", {})
            except Exception as e:
                print(f"[飞书] HTTP get_record 失败({e})，降级 lark-cli")
        records = self.list_records(table_id, page_size=200)
        for r in records:
            if r.get("record_id") == record_id:
                return r
        return {}

    def create_record(self, table_id, fields):
        """创建单条记录"""
        tmp = self._write_json_tmp({"create_records": [fields]})
        try:
            code, out = self._lark(["base", "+record-batch-create", "--base-token", self.base_token,
                                    "--table-id", table_id, "--json", f"@{tmp}"])
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if code != 0:
            raise LarkCliError(f"record-create 失败: {out[:300]}")
        data = json.loads(out)
        rid_list = data.get("data", {}).get("record_id_list", [])
        return {"code": 0, "data": {"record": {"record_id": rid_list[0] if rid_list else ""}}}

    def batch_create_records(self, table_id, records):
        """批量创建记录，records 是 fields dict 的列表"""
        tmp = self._write_json_tmp({"create_records": records})
        try:
            code, out = self._lark(["base", "+record-batch-create", "--base-token", self.base_token,
                                    "--table-id", table_id, "--json", f"@{tmp}"])
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if code != 0:
            raise LarkCliError(f"record-batch-create 失败: {out[:300]}")
        data = json.loads(out)
        return {"code": 0, "data": {"record_id_list": data.get("data", {}).get("record_id_list", [])}}

    def update_record(self, table_id, record_id, fields):
        """更新单条记录"""
        tmp = self._write_json_tmp({"update_records": {record_id: fields}})
        try:
            code, out = self._lark(["base", "+record-batch-update", "--base-token", self.base_token,
                                    "--table-id", table_id, "--json", f"@{tmp}"])
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if code != 0:
            raise LarkCliError(f"record-update 失败: {out[:300]}")
        return {"code": 0}

    def batch_update_records(self, table_id, updates):
        """批量更新，updates = [{"record_id": "xxx", "fields": {...}}, ...]"""
        payload = {"update_records": {}}
        for u in updates:
            payload["update_records"][u["record_id"]] = u["fields"]
        tmp = self._write_json_tmp(payload)
        try:
            code, out = self._lark(["base", "+record-batch-update", "--base-token", self.base_token,
                                    "--table-id", table_id, "--json", f"@{tmp}"])
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if code != 0:
            raise LarkCliError(f"record-batch-update 失败: {out[:300]}")
        return {"code": 0}

    # ===== 配置表读取（带缓存，兼容原接口） =====

    _config_cache = {}

    def load_config_table(self, table_id, force_refresh=False):
        """读取配置表全部记录（fields 列表），缓存5分钟"""
        cache_key = f"config_{table_id}"
        if not force_refresh and cache_key in self._config_cache:
            cached = self._config_cache[cache_key]
            if time.time() - cached["time"] < 300:
                return cached["data"]
        records = self.list_records(table_id, page_size=200)
        data = [r.get("fields", {}) for r in records]
        self._config_cache[cache_key] = {"data": data, "time": time.time()}
        return data

    def load_forbidden_words(self, table_id, platform=None):
        """读取违禁词，可按平台过滤"""
        words = self.load_config_table(table_id)
        if platform:
            result = []
            for w in words:
                platforms = w.get("适用平台", [])
                if "全部平台" in platforms or platform in platforms:
                    if w.get("是否启用", False):
                        result.append(w)
            return result
        return [w for w in words if w.get("是否启用", False)]

    def load_platform_rules(self, table_id, platform):
        """读取某平台的上架规则（含全部平台通用规则）"""
        rules = self.load_config_table(table_id)
        result = []
        for r in rules:
            if not r.get("是否启用", False):
                continue
            rule_platform = r.get("平台", [""])[0] if isinstance(r.get("平台"), list) else r.get("平台", "")
            if rule_platform == "全部平台" or rule_platform == platform:
                result.append(r)
        return result

    def load_description_template(self, table_id, platform):
        """读取某平台的描述模板"""
        templates = self.load_config_table(table_id)
        for t in templates:
            if not t.get("是否启用", False):
                continue
            t_platform = t.get("平台", [""])[0] if isinstance(t.get("平台"), list) else t.get("平台", "")
            if t_platform == platform:
                return t.get("模板内容", "")
        return ""

    def load_field_mapping(self, table_id):
        """读取字段映射表，返回 {通用字段: {平台: api字段}}"""
        mappings = self.load_config_table(table_id)
        result = {}
        for m in mappings:
            generic = m.get("通用字段", "")
            if generic:
                result[generic] = {
                    "Yandex Market": m.get("Yandex Market", ""),
                    "TikTok Shop": m.get("TikTok Shop", ""),
                    "Shopee": m.get("Shopee", ""),
                }
        return result

    # ===== HTTP 辅助（仅 .env 已配凭证时使用） =====

    def _get_tenant_token(self):
        """获取 tenant_access_token，带缓存"""
        if self._tenant_token and time.time() < self._token_expire - 60:
            return self._tenant_token
        resp = requests.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10
        )
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"飞书 token 获取失败: {data}")
        self._tenant_token = data["tenant_access_token"]
        self._token_expire = time.time() + data["expire"]
        return self._tenant_token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._get_tenant_token()}",
            "Content-Type": "application/json",
        }


# 表 ID 常量（与已搭建的多维表格一致）
TABLE_IDS = {
    "product": "tblccRoRGPoD8Ulw",           # 商品资源主表
    "candidate": "tblBsUDHOIEymeLO",         # AI每日选品候选表
    "selection_rules": "tblBSvTC5VJgZ8Z0",   # 选品规则配置表
    "forbidden_words": "tblmN0jNQElECYJC",   # 违禁词配置表
    "platform_rules": "tblJ2kvnqrOxGjzg",    # 平台上架规则配置表
    "description_templates": "tbl72etWf3aNVkl7",  # 描述模板配置表
    "field_mapping": "tblyhZKudTfmqgWn",     # 平台字段映射表
    "orders": "tbluqGOYjMr7oFHT",            # 订单对账表
}

feishu = FeishuAPI()
