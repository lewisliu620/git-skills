# 技能集成契约

本文件定义编排器与两个源技能之间的数据契约、质量门和触发条件。

---

## 阶段1 → doubao-product-selection 集成

### 何时调用
编排器在以下情况必须先读取 `C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\.doubaowork\agent_mode\workspace\.skills\doubao-product-selection\SKILL.md`，严格按其五维框架执行，不得凭经验自行打分。

### 输入参数（编排器固定传入）

| 参数 | 值 | 说明 |
|------|-----|------|
| 目标平台 | Shopee 泰国站 | 跨境B2C，非国内电商 |
| 预算范围 | ¥5000首批测试 | 无货源模式，每品首单1-5件 |
| 货源优势 | 1688一件代发，义乌/东莞千恒仓 | 无自有工厂 |
| 经验背景 | Shopee跨境新手 | 轻小件优先 |
| 特殊偏好 | 轻小件(<200g)、高毛利(≥80%)、全年可售 | 禁季节性品 |

### 五维打分适配（源技能 → Shopee TH）

源技能五维：市场需求、竞争度、利润空间、季节性、复购率。

编排器适配为飞书表字段：

| 源技能维度 | 飞书字段 | 权重 | Shopee TH评分要点 |
|-----------|----------|------|-------------------|
| 市场需求 | 需求分 | 25% | 泰国Shopee搜索热度、TikTok泰国话题量、社媒讨论度 |
| 竞争度 | 竞争分 | 20% | 泰国站同款数量越少分越高；头部卖家集中度低加分 |
| 利润空间 | 利润分 | 30% | (售价THB/4.86 - 成本CNY - SLS运费3.5) / 售价 ≥ 80%才给≥8分 |
| 季节性 | 合规分 | 10% | 全年可售给高分；仅雨季/泼水节短窗口给低分；需FDA/TISI认证的扣分 |
| 复购率 | 可代发分 | 15% | 消耗品(美甲贴/发饰)复购高加分；1688一件代发支持、48h揽收加分 |

### 硬门槛（不达标直接淘汰，不写入飞书）

- 采购成本 ¥0.3 - 3.0
- 建议售价 39-199 THB（≈¥8-41，汇率4.86）
- **预估利润率 ≥ 80%**
- 重量 ≤ 200g
- 1688有一件代发
- 非禁售品类（化妆品需FDA、电子需NBTC）

### 输出契约 → 飞书选品表

源技能输出3-5个候选品类，编排器将每个候选转为一条飞书记录：

```json
{
  "create_records": [{
    "商品名称": "<源技能输出的细分方向>",
    "类目": "<源技能输出的品类>",
    "目标站点": "泰国Shopee",
    "采购成本CNY": <1688搜索验证后的实际代发价>,
    "代发价CNY": <同采购成本>,
    "建议售价CNY": <THB售价 / 4.86>,
    "预估利润CNY": <售价CNY - 成本 - 3.5>,
    "利润率": <利润 / 售价>,
    "SLS运费CNY": 3.5,
    "需求分": <0-10>,
    "竞争分": <0-10>,
    "利润分": <0-10>,
    "可代发分": <0-10>,
    "合规分": <0-10>,
    "综合分": <加权总分>,
    "推荐状态": "待复核",
    "处理状态": null,
    "选品日期": "<YYYY-MM-DD HH:mm:ss>",
    "人工备注": "<源技能的机会点+风险点摘要>"
  }]
}
```

### 质量门
- [ ] 每个候选都有源技能五维评分表
- [ ] 综合分 = 需求×0.25 + 竞争×0.2 + 利润×0.3 + 代发×0.15 + 合规×0.1
- [ ] 利润率 ≥ 0.80
- [ ] 飞书写入成功返回 record_id_list
- [ ] 无超过3个候选（每次最多3个）

---

## 阶段4 → doubao-listing-localization 集成

### 何时调用
编排器在素材本地化完成后（处理状态="待翻译Listing"），必须先读取：
1. `C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\.doubaowork\agent_mode\workspace\.skills\doubao-listing-localization\SKILL.md`
2. `references\keyword-taxonomy.md`
3. `references\output-templates.md`

然后按其工作流执行Listing创建。

### 输入参数（编排器固定传入）

| 参数 | 值 |
|------|-----|
| Platform | Shopee |
| Site / language | Thailand / Thai (th-TH) |
| Product / category | <从飞书选品记录获取> |
| Core attributes | <从1688商品页提取的材质/尺寸/颜色/包装数量> |
| Keyword source | 1688中文标题 + 竞品Shopee TH标题 |
| Requested fields | Title, Description, Backend search terms, Category, SKU names |
| Fulfillment mode | SLS跨境直邮 |

### 关键词分层（按 keyword-taxonomy.md）

为每个商品建立关键词地图：

| 关键词 | 类型 | 用途 | 置信度 |
|--------|------|------|--------|
| <泰语品类核心词> | Core product term | 标题前半 | High |
| <属性词：材质/尺寸/数量> | Attribute term | 标题后半 + Bullet | High |
| <使用场景词> | Use-case term | 描述 + 图片文案 | Medium |
| <受众词：女性/学生/妈妈> | Audience term | 标签 + 后端词 | Medium |
| <长尾词组合> | Long-tail term | 后端搜索词 | Medium |
| <品牌/IP/绝对化词> | Cautious/blocked | 禁止使用 | - |

### Claim Ledger（按源技能质量门1）

| 主张 | 来源 | 证据范围 | 状态 | 处理 |
|------|------|----------|------|------|
| 如"防水" | 1688详情页标注 | 产品族 | verified | 可用于标题/描述 |
| 如"安全无毒" | 未提供检测报告 | - | blocked | 删除，不使用 |
| 如"适合送礼" | 场景推断 | - | conditional | 放描述，不进标题 |

### Listing Draft Table（按 output-templates.md）

| 字段 | 草稿 | 说明 |
|------|------|------|
| Title | `<品类词> <核心属性> <使用场景> <卖点>` | ≤120字符，地道泰语电商用语 |
| Description | 产品特点→规格→使用方法→固定尾部模板 | 结构化段落 |
| Backend terms | <空格分隔的长尾词> | 不重复标题词 |
| Category TH | <1688中文类目对应的Shopee TH类目路径> | 发布时选择 |
| SKU names TH | <中文规格名翻译为泰文> | 与1688 SKU一一对应 |

### 泰文标题公式

```
[Core product term] + [Attribute term] + [Use-case term] + [Selling point]
```

示例（美甲贴纸）：
- 错误（直译）：`สติกเกอร์ติดเล็บ ฝรั่งเศส ใหม่ น่ารัก`
- 正确（买家视角）：`สติกเกอร์ติดเล็บลายการ์ตูน กันน้ำ ติดง่าย อยู่นาน สำหรับสาวๆ`

### 泰文描述结构

1. 产品特点（3-5个bullet，泰语）
2. 规格参数（材质、尺寸、重量、包装数量）
3. 使用方法（简短步骤）
4. 固定尾部模板（见SKILL.md阶段4）

### 质量门（按源技能5个强制门）

1. **Evidence Gate**：所有主张有来源标注；blocked主张不进最终文案
2. **Parent/Child Gate**：SKU规格与1688一致，不臆造规格
3. **Completeness Gate**：标题+描述+后端词+类目+SKU名全部产出
4. **Consistency Gate**：标题关键词与后端词不矛盾；规格描述与SKU表一致
5. **Boundary Gate**：不写物流/税务/广告策略，只产出Listing内容

### 输出契约 → 客优云编辑页

| Listing字段 | 填入客优云位置 |
|-------------|---------------|
| Title | 商品标题输入框 |
| Description | 商品描述富文本框 |
| Backend terms | 搜索关键词字段 |
| Category TH | 类目选择器 |
| SKU names TH | SKU规格名（中文→泰文） |

完成后更新飞书处理状态="待审核上架"。
