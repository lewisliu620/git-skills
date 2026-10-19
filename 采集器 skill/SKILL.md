---
name: 采集器 skill
description: |
  1688 商品采集与多平台上架自动化工具。从 1688 采集商品信息（标题/价格/SKU/图片/视频/属性/描述），经规则校验后写入飞书多维表格，选品确认后异步执行 AI 处理（图片翻译/视频字幕/描述翻译），支持 Yandex Market、TikTok Shop、Shopee 多平台上架。
  Use when:
  (1) 用户说"采集商品""采集1688""上架商品""跑采集器"；
  (2) 用户提供 1688 商品链接要求采集入库；
  (3) 用户要求启动守护进程自动采集；
  (4) 用户要求更新 1688 登录态/cookie；
  (5) 用户询问采集器状态、字段、配置。
  Input: 1688 商品链接或 ID，或飞书表格中状态为"待采集"的记录。
  Output: 飞书多维表格商品记录（含标题/价格/SKU/图片/视频/属性/描述/品牌/货号/类目/库存），状态流转为"待选品"。
  Do not: 不自动付款下单；不在采集阶段执行 AI 处理（节省 token）；不修改用户已确认的选品结果；不泄露 cookie 和 API Key。
---

# 采集器 skill

1688 商品采集 → 飞书选品审批 → AI 异步处理 → 多平台上架的全流程自动化工具。

## 快速开始

```
# 1. 配置环境变量（首次）
复制 scripts/.env.example 为 scripts/.env，填入飞书 App ID/Secret

# 2. 获取 1688 登录态
python scripts/update_cookie.py
（浏览器打开后手动登录，脚本自动保存 cookie）

# 3. 启动守护进程（推荐，全自动）
python scripts/daemon.py

# 4. 手动采集单个商品
python scripts/main.py <1688商品链接>
```

守护进程启动后，全程只需在飞书表格操作：填链接 → 自动采集 → 人工选品确认 → 自动 AI 处理。

## 核心职责

1. **1688 商品采集**：移动端 m.1688.com 绕过 x5sec 风控，采集标题、价格、SKU、主图、详情图、视频、商品属性（品牌/货号/材质/产地等27项）、描述、重量、类目
2. **选品规则校验**：基于飞书「选品规则配置表」的硬性/软性规则，自动淘汰不合格商品（如必须有商品视频、必须支持一件代发）
3. **飞书多维表格联动**：采集结果写入商品主表，状态机流转（待采集→待选品→选品确认→待翻译Listing→已上架）
4. **AI 异步处理**：选品确认后触发，批量执行图片 OCR 翻译+重绘、视频 ASR 字幕+压制、描述清洗+翻译，结果上传 COS 后回写飞书
5. **多平台上架适配**：Yandex Market / TikTok Shop / Shopee 平台适配器，平台特性显性化维护在飞书配置表

## 工作流程

### 采集字段清单

| 字段 | 来源 | 说明 |
|------|------|------|
| 中文标题 | offerInfoModel | 商品标题 |
| 采购价CNY | offerInfoModel | 最低采购价 |
| SKU数量 | skuProps/specAttrs | SKU 规格数量 |
| 主图链接 | offerImages | 第1张主图（URL类型） |
| 附图链接 | offerImages | 第2-5张主图（换行分隔） |
| 详情图链接 | detailUrl content | 详情页图片（过滤gif，最多20张） |
| 视频链接 | videoUrl | 商品视频直链 |
| 包裹重量g | skuWeight | 各SKU重量取最大值 |
| 商品描述中文 | detailUrl content | 详情页文字（清洗违禁词后） |
| 品牌 | propsList | 无品牌填"无品牌" |
| 商品属性JSON | propsList | 全部属性（JSON格式） |
| 库存 | canBookCount | 默认500（跨境店固定库存） |
| 货号 | propsList | 商品编码 |
| 1688类目 | postCategoryId | 1688类目ID |
| 平台类目ID | AI推荐 | 选品确认后由AI推荐Yandex/TikTok/Shopee类目 |

### 状态机

商品主表「处理状态」10个状态：
- 待采集 → 待选品 → 选品确认 → 素材待处理 → 素材处理中 → 待翻译Listing → 待审核上架 → 已上架
- 规则淘汰（未通过选品规则）
- 处理失败（采集或AI处理异常）

「AI处理状态」独立字段：待处理/处理中/已完成/失败

### 守护进程模式

`daemon.py` 同时轮询两类任务：
1. **待采集**：处理状态=待采集 → 自动调用1688采集 → 状态变为待选品
2. **待AI处理**：处理状态=选品确认 且 AI处理状态=待处理 → 自动调用豆包API批量处理 → 状态变为待翻译Listing

默认轮询间隔5分钟，支持 `--interval` 自定义，`--once` 单次执行。

### Cookie 管理

- `update_cookie.py`：playwright 打开浏览器，用户登录后自动检测并保存 cookie
- 守护进程每次轮询前自动检测 cookie 有效性
- 检测到过期时发送飞书提醒并跳过本次采集
- 采集失败时异常信息明确提示运行 `python update_cookie.py`

### 通道一致性（防串味，2026-10-18 固化）

- tabbit 桥回传的 `offerId` 非空时必须等于请求 OfferID，否则判定为浏览器残留/前台另一商品的 SSR data（串味），抛 `MISMATCHED_OFFER`，**拒绝静默落库**；不得用入参 OfferID 盖到错误商品上。
- requests 移动端兜底在 0 cookie/未登录时会被 x5sec 拦截，此时直接提示 `python update_cookie.py`，不硬采、不反复触发风控。
- 单链核对务必比对回传标题/供应商/类目与目标商品一致，再进入组装。

### 飞书写入通道与 lark-cli 传参坑（#49/#57 固化，零密钥）

- 读候选表/主表去重、状态闸门、回写候选表全走本地 `lark-cli --as user`（本人 OAuth），插件只吃组装好的 product；插件内不存 appId/appSecret、不直连飞书。lark-cli 不写死 env hash，自动扫描 `sandbox_envs_dir\envs\*\override_dlcs\lark-cli.exe` 取最新。
- **PowerShell 内联 `--json '{"name":...}'` 会被吞掉双引号**，报 `invalid JSON object near byte 2 (invalid character 'n'...)`；复杂/含中文 JSON 一律 `--json @file`，不要内联。
- **`--json @file` 有内置路径白名单**（cwd、`~/AppData/Local/Temp`、`~/files`、`~/.doubao`、`~/super_doubao`、`~/Doubao`、`~/doubao`），项目目录 `D:\AI\电商` 不在白名单，会报 `outside the built-in allowlist`；把 JSON 写到 `$env:LOCALAPPDATA\Temp` 再 `@file`。
- 文件用 node 写 UTF-8 无 BOM（`require('fs').writeFileSync(path, JSON.stringify(obj), 'utf8')`），勿用 `Out-File`（带 BOM 致 JSON.parse 报错）；读回时 `.replace(/^\uFEFF/,'')` 去 BOM。
- `--jq` 表达式含竖线 `|`、引号会被 PowerShell 拆成位置参数（`positional arguments are not supported`），改把结果存文件用 node 过滤。
- 先 `--dry-run` 验 body 再正式写；写后 `+field-list`/`+record-get` 回读核对，写成功不等于完成。

### 采集落库全链路坑（2026-10-19 W-01~W-04 固化，已真实验证）

- **feishu_api.py 主通道已改为 lark-cli --as user（零密钥）**：list_records/create_record/update_record/load_config_table 全走本地 CLI；HTTP tenant_token 通道降级为 .env 有凭证时的 fallback。config.py 零依赖（python-dotenv 缺失时标准库解析 .env）。requests 未装时 feishu_api 用 try/except 容错导入。
- **S0 闸门已在采集前接入**（main.py process_from_feishu）：先预取候选表+主表全量建去重索引 → 逐条 screen_candidate。`duplicate`→推荐状态=已淘汰+备注；`reject`→推荐状态=已淘汰+处理状态=规则淘汰+备注；`pending_price`→保持待采集+备注待定价原因；只有 `pass` 才进全量采集。Shopee 竞品链接（无1688货源）会在闸门正确 REJECT，不会误采集。
- **主表链接字段全是 text 类型**：采购链接/主图链接/附图链接/详情图链接一律传**纯字符串**，传 `{link,text}` dict 会报 `invalid_request 800010701 (2 issues)` 校验失败。
- **落库必带 1688 OfferID**：主表字段 fldCFqWvho 已建；main.py/daemon.py 落库 fields 必须含 `"1688 OfferID": product.offer_id`，否则主表记录无法被 S0 去重索引命中。
- **W-04 兜底补全**：collect_pipeline._fill_missing_via_requests 会在 tabbit 直出页缺字段时用 requests 移动端页补 描述/重量(skuWeight max kg→g)/视频(videoUrl)/品牌+货号(propsList)/供应商/起批量；**引用 fetcher 私有函数 `_extract_json_arr` 必须显式 `from .fetcher import _extract_json_arr`**，否则被 try/except 静默吞掉、补全无声失败（品牌/货号一直为"无"）。
- **result_to_product 必须赋 p.brand**（`p.attributes.get("品牌","")`），仅依赖 W-04 补全会因检查条件而漏。
- **daemon cookie 失效不再跳过采集**：采集主通道是 tabbit 已登录浏览器，不依赖 requests cookie；cookie 失效只提示不跳过，requests 兜底失败时才需要 update_cookie.py。
- **rule_checker S2 项降级软提醒**：规则名含 视频/一件代发/代发/重量/千克/kg/起批/起订 时，即使配置为「硬性规则」也不构成 hard_fail（S0 口径：S2 复核项不淘汰，全量采集后复核）。
- **Python 环境缺 requests 会崩**：`pip install requests` 后 fetcher/collect_pipeline 才能跑（tabbit 主通道采集+requests 兜底补全均依赖）。

### #52 类目语义映射（上架前预锁 Shopee 叶子类目ID）

目的：建草稿前把商品对到 Shopee 叶子类目ID，解除"类目ID空缺"输入缺口，争取一次选中。纯本地规则词典+字典，无网络、无飞书请求。

四态决策（`core/category_mapper.py::map_category`）：
- `auto`：显式规则词典命中（关键词全含、未触发 must_not），可直接回填叶子ID；
- `candidates`：规则未覆盖/无专叶（如厨房小工具），只给 top3 候选，**不自动写ID**，人工选；
- `blocked_forbidden`：命中带电/电池/充电/食品(禁售)/化妆品/医疗器械等前置词，不给类目，交 S0 淘汰；
- `none`：模糊无匹配，人工指定，不臆造。

用法（读表走 lark-cli --as user，零密钥；本模块不直连飞书）：
```
# 1) lark-cli 导出主表 record-list JSON（先读 data.fields 再按位置取值，勿猜中文字段名）
# 2) dry-run（默认，不写飞书）
python scripts/map_categories.py --input master.json
# 3) 确认 auto 清单后生成回写体（仅 auto 项，已填类目ID的行跳过，不覆盖）
python scripts/map_categories.py --input master.json --write
# 4) 用 lark-cli base +record-batch-update 提交 category-write.json，并 +record-get 回读
```

已固化坑：
- **「食品级硅胶」≠食品**：禁售检测前先剥离"食品级/可食用级/食用级"材质词，不得把食品级日用硅胶判成食品禁售。
- **车载/充电/无线充 must_not**：手机支架规则必须排除"车载/汽车/充电/无线充/磁吸充电"，且含"充电/电池/电动"直接 blocked_forbidden（带电不进S0上架）。
- **Shopee泰国树厨房小工具无专叶**：压蒜器/冰格/挖球勺/玉米刨在"餐饮用品"下无独立叶子，走 family fallback 给 101244餐具/101248其他/101242碗 候选，人工确认，不自动落。
- 规则词典 `RULES` 可扩：新增品类时在词典补"关键词→真实叶子ID"，叶子ID必须取自 categories-flat.json，禁止臆造。

### #53 AI选品（豆包工作=worker，本地S0复核，候选待人工审批）

分工（不单独引入模型，不调外部选品API）：
- **AI（豆包工作本身）**：看真实1688候选，结合泰国市场给「建议售价CNY」（THB÷4.86）与需求/竞争/代发主观判断；本地不反推售价、不臆造OfferID/价格。
- **本地确定性**：`core/s0_screen.py` 复核去重(OfferID)、利润率≥80%(`profit_model`)、采购价<100、禁售词；缺建议售价→`pending_price`（未定价，不淘汰不放行）。
- 只把 `pass` 项生成候选表记录，**处理状态=待审批**，人工审批后才进全量采集/上架；不做全量采集、不自动发布。

用法：
```
# 1) lark-cli --as user 预取候选表 tblBsUDHOIEymeLO + 主表 tblccRoRGPoD8Ulw（去重注入）
# 2) AI把真实候选写进 picked.json（offer_id/商品名称/采购成本CNY/建议售价CNY/sku_names/weight_g/has_video/类目）
python scripts/ai_pick.py --candidates picked.json \
  --candidates-file candidates.json --master-file master.json          # dry-run 看判定
python scripts/ai_pick.py --candidates picked.json --create             # pass项生成候选表batch-create体
# 3) lark-cli +record-batch-create 提交 candidate-create.json，+record-list 回读
```

已固化坑：
- **1688未登录时匿名PC搜索被降级**：结果错乱（与关键词不符）、商品卡片JS不渲染、offer链接只在IM参数里，拿不到干净候选池；此时不硬爬、不触发风控，改为：用户在Tabbit登录1688买家号，或提供一批真实候选链接，AI再逐个定价复核。
- **已登录PC泛词搜索同样被算法投放污染（2026-10-18实测）**：搜"收纳盒/冰箱收纳盒/收纳盒一件代发"返回的全是化妆品、妇科凝胶、止痒膏、成人用品、卸妆油等禁售/无关投放流，相关性不可控，且搜索卡片只有起批价、缺SKU/视频/真实阶梯价/代发资质，不足以跑S0。**结论：PC搜索页只作线索池，不能自动批量捞候选；S0判定必须开详情走 #47 offer.collect 全字段。** 干净候选优先来源：①用户直接给1688详情链接；②用户在1688筛好"一件代发/跨境专供/销量排序"后给链接清单。
- 已探明PC搜索卡片选择器（专用代发/跨境市场可复用）：卡片容器 `div.gridCell--PjMmdJiZ`；标题链接 `a.offerCard--dMshu5T4`（offerId 取其 href `/offer/<id>.html`）；供应商 `a.descItem--cSPn7Xp1`；价格 `[class*=hoverPrices]`；成交"N+件"；代发标签"一件代发/代发包邮"。价格文本常分行（`¥ | 5 | 新人价`），正则需合并数字。
- 候选必须来自真实采集/真实链接，禁止用编造OfferID、编造采购价充数。
- 选品80%利润率是准入门槛，与上架30%毛利定价是两套，勿混。

### 描述清洗规则

自动去除：
- 违禁词：批发、跨境、外贸、工厂、出口、授权、淘宝、拼多多、1688、阿里巴巴、京东、天猫、抖音、工厂直销、一件代发、厂家
- 营销话术：点击购买、立即抢购、限时优惠、秒杀、包邮、特价、清仓、厂家直销、量大从优、支持定制、来样加工、OEM、ODM

### 默认值配置（config.py）

- `DEFAULT_STOCK = 500`：默认库存
- `DEFAULT_BRAND = "无品牌"`：默认品牌
- `DEFAULT_TIKTOK_BRAND = "No Brand"`：TikTok 默认品牌
- `MAX_DESCRIPTION_LENGTH = 5000`：描述最大长度
- `MAX_DETAIL_IMAGES = 10`：详情图最大存储数量

## 项目结构

```
collector-skill/
├── SKILL.md                    # 本文件
├── scripts/                    # 可执行代码
│   ├── daemon.py               # 统一守护进程（推荐）
│   ├── main.py                 # 采集主调度器（手动模式）
│   ├── update_cookie.py        # 1688 Cookie 自动更新
│   ├── ai_processor.py         # AI 批量处理模块
│   ├── poll_feishu.py          # AI 处理轮询脚本
│   ├── config.py               # 全局配置
│   ├── feishu_api.py           # 飞书多维表格 API 封装
│   ├── requirements.txt        # Python 依赖
│   ├── .env.example            # 环境变量模板
│   ├── core/                   # 核心层（平台无关，纯函数/离线可测）
│   │   ├── fetcher.py          # 1688 采集（移动端绕过风控）
│   │   ├── s0_screen.py        # #48 S0硬筛（去重/利润率≥80%/采购价/禁售）
│   │   ├── profit_model.py     # #48 利润率模型+SLS两档
│   │   ├── dedup.py           # #48 OfferID精确去重
│   │   ├── category_mapper.py  # #52 中文标题/类目→Shopee叶子ID语义映射
│   │   ├── rule_checker.py     # 选品规则校验
│   │   ├── image_processor.py  # 图片快速预检+缓存
│   │   ├── video_processor.py  # 视频元数据检查
│   │   └── description_cleaner.py  # 描述清洗
│   └── platforms/              # 平台适配层
│       ├── base.py             # 适配器基类
│       ├── yandex.py           # Yandex Market
│       ├── tiktok.py           # TikTok Shop
│       └── shopee.py           # Shopee
└── references/                 # 详细文档
    └── 飞书配置说明.md          # 多维表格9张表结构
```

## 红线

1. **不自动付款**：1688 下单只填地址不付款，人工确认支付
2. **采集阶段不做 AI**：AI 处理只在选品确认后触发，节省 token
3. **不泄露敏感信息**：cookie、API Key、Secret 不写入文档或回复
4. **不修改已确认选品**：用户选品确认后不自动更改商品数据
5. **cookie 过期不硬采**：检测到过期立即停止并提醒，不反复尝试触发风控
6. **库存固定 500**：跨境店不用 1688 实时库存，避免超卖
