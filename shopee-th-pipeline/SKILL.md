---
name: shopee-th-pipeline
description: |
  Shopee泰国站无货源一件代发全链路编排器。串联doubao-product-selection（AI选品）→keyouyun-publisher（1688采集）→shopee-media-localization（素材本地化）→doubao-listing-localization（Listing泰文化）→客优云发布→订单监控→1688代发全流程。
  Use when:
  (1) 用户说"跑一遍选品""今天选什么品""开始上架新品"；
  (2) 需要从选品到发货的完整自动化流水线；
  (3) 定时任务触发选品检查或订单监控。
  Input: 无（自动从飞书选品表读取待处理记录）
  Output: 已上架商品 + 新订单通知
  Do not: 不做从零生成商品图；不做财务建模；不处理非泰国站；不跳过子技能直接凭经验写。
---

# Shopee 泰国站全链路编排

## 核心原则

本技能是**编排器**，不是执行者。每个阶段必须先读取对应子技能的 SKILL.md，严格按其工作流执行，不得凭经验自行发挥。

## 流水线总览

```
阶段1: AI选品          → 阶段2: 1688采集     → 阶段3: 素材本地化
       ↓                        ↓                      ↓
  doubao-product-selection  keyouyun-publisher   shopee-media-localization
  五维打分+硬门槛           Tabbit客优云采集        擦中文+泰文图/视频
  ↓ 写入飞书选品表          ↓ 更新处理状态          ↓ 更新处理状态
  "待采集"                  "素材待处理"            "待翻译Listing"
                                                      ↓
阶段5: 客优云发布        ← 阶段4: Listing泰文化
       ↓                        ↓
  keyouyun-publisher      doubao-listing-localization
  编辑素材+发布            关键词分层+Claim审计+Listing草稿
  ↓ 更新处理状态          ↓ 更新处理状态
  "已上架"                "待审核上架"
       ↓
阶段6: 订单监控（定时）→ 阶段7: 1688代发
  shopee-order-fulfillment  shopee-order-fulfillment
```

## 数据契约

各阶段间通过飞书选品表的"处理状态"字段衔接。完整字段映射和质量门见：
**`references/integration-contract.md`**

---

## 阶段1：AI选品

**子技能**：`doubao-product-selection`
**SKILL路径**：`.skills/doubao-product-selection/SKILL.md`
**触发**：每日定时或用户说"跑选品"。

### 执行步骤

1. **读取子技能**：先 Read `doubao-product-selection/SKILL.md`，理解五维框架。
2. **固定输入参数**（编排器不传用户，用固定值）：
   - 目标平台：Shopee泰国站
   - 预算：¥5000首批测试
   - 货源：1688一件代发
   - 偏好：轻小件(<200g)、高毛利(≥80%)、全年可售
3. **五维打分**：按子技能框架评分，适配为Shopee TH维度（见集成契约）。
4. **硬门槛过滤**：利润率≥80%、成本¥0.3-3、重量≤200g、1688一件代发。
5. **1688验证**：对通过门槛的候选，在1688搜索验证实际代发价和SKU。
6. **写入飞书**：按集成契约的JSON格式，写入选品候选表。
7. **状态**：推荐状态="待复核"，处理状态留空（等用户审批）。
   - 用户在飞书表手动把"推荐状态"改为"已精选"，并把"处理状态"改为"待采集"后，才进入阶段2。
   - 脚本只处理推荐状态="已精选" AND 处理状态="待采集"的记录，不自动跳过审批。

### 飞书写入关键格式（已验证）

- 顶层键：`create_records`
- 每个元素直接是字段Map，**不要包`fields`对象**
- 单选select传字符串（`"已精选"`），不传数组
- datetime传`"YYYY-MM-DD HH:mm:ss"`字符串
- lark-cli：`C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs\924a7238-9cc3-4fde-8763-1a287b815b76\override_dlcs\lark-cli.exe`，用`--as user`

---

## 阶段2：1688采集

**子技能**：`keyouyun-publisher`
**SKILL路径**：`.user_skills/keyouyun-publisher/SKILL.md`
**触发**：飞书选品表中推荐状态="已精选" AND 处理状态="待采集"。

### 执行步骤

1. **读取子技能**：先 Read `keyouyun-publisher/SKILL.md`。
2. 从飞书记录获取商品关键词或1688链接。
3. Tabbit打开客优云链接采集页，textarea用nativeSetter设值。
4. 勾选"采集并自动发布"→点"开始采集"。
5. 弹窗确认：Shopee全球、武汉市凡元卓宜商贸有限公司、随机店铺、立即发布。
6. 更新飞书处理状态="素材待处理"。

---

## 阶段3：素材本地化

**子技能**：`shopee-media-localization`
**SKILL路径**：`.user_skills/shopee-media-localization/SKILL.md`
**触发**：处理状态="素材待处理"。

### 执行步骤

1. **读取子技能**：先 Read `shopee-media-localization/SKILL.md`。
2. 图片：提取1688主图→`mediakit-cli image erase-image`擦中文→Python PIL加泰文。
3. 视频：probe探测→video-ocr识别中文字幕→erase-video-subtitle擦字幕→text_to_audio_plus泰语配音→mux-audio-video合流→ffmpeg烧录泰文字幕。
4. 产物输出到 `products/<slug>/03-final/`。
5. 更新飞书处理状态="待翻译Listing"。

---

## 阶段4：Listing泰文化

**子技能**：`doubao-listing-localization`
**SKILL路径**：`.skills/doubao-listing-localization/SKILL.md`
**参考文件**：
- `.skills/doubao-listing-localization/references/keyword-taxonomy.md`
- `.skills/doubao-listing-localization/references/output-templates.md`
**触发**：处理状态="待翻译Listing"。

### 执行步骤

1. **读取子技能和参考**：
   - Read `doubao-listing-localization/SKILL.md`
   - Read `references/keyword-taxonomy.md`
   - Read `references/output-templates.md`
2. **建立关键词地图**：按keyword-taxonomy的10类关键词，为商品建立分层词表。
3. **建立Claim Ledger**：按证据声明门，标注每个主张的verified/conditional/blocked状态。
4. **产出Listing草稿表**：标题、描述、后端词、类目、SKU名。
5. **过5个质量门**：证据门、父子变体门、完整性门、一致性门、边界门。
6. 更新飞书处理状态="待审核上架"。

### 泰文描述固定尾部模板

```
🚚 จัดส่งจากประเทศจีน
📣 กดติดตามร้านค้าเพื่อรับคูปองส่วนลด
📣 สินค้าใหม่ ส่วนลดพิเศษ อัพเดตโปรโมชั่น
🔹 สต๊อกไม่ปกติ จะแจ้งเวลาจัดส่งเพิ่มเติม
🌈 หากมีคำขอพิเศษ กรุณาเขียนในคำสั่งซื้อ
💯 สินค้าพร้อมส่ง ประหยัดเวลา
🌼 ขนาดอาจคลาดเคลื่อน ±1-2 ซม. จากการวัดด้วยมือ
🌼 สีอาจแตกต่างจากภาพ เนื่องจากหน้าจอ
```

---

## 阶段5：客优云发布

**子技能**：`keyouyun-publisher`
**触发**：处理状态="待审核上架"。

### 客优云编辑页必须完成

1. 标题替换为阶段4产出的泰文标题
2. 描述替换为阶段4产出的泰文描述
3. 主图替换为`03-final/images/`中的泰文图
4. 视频替换为`03-final/videos/`中的泰文视频
5. **库存改为500**
6. SKU规格名替换为阶段4产出的泰文名，数量与1688一致
7. 类目选择泰国站对应类目
8. 价格按建议售价CNY×4.86换算为THB

### 完成后

更新飞书：处理状态="已上架"，推荐状态="已上架"。
同时在商品资源主表（tblccRoRGPoD8Ulw）创建新记录。

---

## 阶段6：订单监控（定时任务）

**子技能**：`shopee-order-fulfillment`
**触发**：每天 09:00/12:00/18:00/21:00。

1. Tabbit打开客优云待处理订单页。
2. 读取订单号、商品、金额、店铺、下单时间。
3. 对比飞书订单表已有订单号，新订单写入+通知。
4. 已有订单跳过。

---

## 阶段7：1688代发

**子技能**：`shopee-order-fulfillment`
**触发**：用户回复确认发货后。

1. 下载客优云订单商品图。
2. 1688以图搜款，点"严格同款"。
3. 选供应商：主图一致→SKU齐全→距千恒仓最近→价格最低。
4. 代发下单，收货地址填千恒仓库。
5. **支付前必须停**，等用户确认。
6. 1688订单写入飞书跟踪表。

---

## 千恒仓库地址

| 仓库 | 地址 | 收件人 | 手机 |
|------|------|--------|------|
| 义乌仓 | 浙江省金华市义乌市城西街道香溪锦园13-102 | 千恒+ID282225 | 15362871061 |
| 东莞仓 | 广东省东莞市谢岗镇赵林村宝湖路82号巨嘉工业园F栋301 | 千恒商贸云仓+ID282225 | 15362871061 |

## 飞书数据中台

base_token: `QsnYbrWpaa6lGfspgLpcihfvnpb`

| 表 | table_id | 用途 |
|----|-----------|------|
| 选品候选表 | tblBsUDHOIEymeLO | AI选品结果+五维打分+处理状态流转 |
| 商品资源主表 | tblccRoRGPoD8Ulw | 已上架商品记录 |
| 订单&货代对账表 | tbluqGOYjMr7oFHT | Shopee订单+物流状态 |
| 1688采购跟踪表 | tbl9S5Xruh3ytOib | 1688代发订单跟踪 |
| 货代基础表 | tblb4JFvltBmAQQC | 千恒仓库地址维护 |

## 阶段5b：直控Shopee卖家后台上架（替代客优云）

> 用户不绑定客优云后，通过Tabbit CLI直控Shopee卖家后台添加商品页。

### 已验证的DOM选择器

| 字段 | 选择器 | 说明 |
|------|--------|------|
| 商品名称 | `input[placeholder="Input"]`（第一个） | 最大180字符 |
| 商品描述 | `textarea`（第一个） | 最大5000字符 |
| 类目 | `.product-category` | 自动匹配 |
| 主图上传 | `input[type="file"][accept="image/*"]` | 最多9张，webp需转jpg |
| 视频上传 | `input[type="file"][accept*="video"]` | MP4，10s-60s，Max 30MB |
| 全球价格 | `input[placeholder*="全球商品价格"]` | THB |
| 商品数量 | `input[placeholder*="商品数量"]` | 固定500 |
| 规格货号 | `input[placeholder*="规格货号"]` | |
| 创建并发布 | `button:has-text("创建并发布")` | |

### 踩坑记录（必须遵守）

1. **全球SKU语言校验**：标题/描述/变体名称必须用英文/简中/繁中，泰文会报错"The global SKU language must be English, Simplified Chinese, Traditional Chinese"。发布后再编辑泰文版本。
2. **品牌是必填下拉选择器**：`.product-brand-item .eds-selector`，显示"请选择"。不是普通input，需要点击后搜索"No Brand"。
3. **视频上传后弹出编辑弹窗**：`eds-modal`含autoplay video，会遮挡所有后续操作。必须先关闭（Escape或force点击关闭按钮），否则品牌选择器等所有控件都无法点击。
4. **force click和JS click都不跳转**：如果有红色错误文字（品牌为空、必填属性为空），发布按钮虽然enabled但不会真正提交。必须先消除所有红色错误。
5. **多个必填属性"请选择"**：类目选定后会出现多个带*号的属性下拉，必须逐一填写。
6. **变体区域有系统预填数据**：打开页面时变体区域可能自动填充不相关的颜色/规格示例数据，需要清空或替换为实际SKU。
7. **Tabbit --timeout-ms最小60000**：不能传30000。
8. **Windows多行JS**：必须写UTF-8无BOM临时文件，用`cmd.exe /d /c "tabbit-cli nodejs ... < temp.js"`重定向stdin。
9. **1688主图是webp格式**：Shopee上传要求jpg，需先转换。
10. **选品记录的SKU规格可能与1688实际SKU不符**：必须以1688详情页实际SKU为准。

## 红线

- **货不对版**：必须以图搜款，禁止凭标题选品
- **中文素材禁止直接上架**：图片擦中文加泰文，视频擦中文字幕加泰语配音
- **泰文标题禁止机翻直译**：用泰国电商地道买家视角
- **库存必须500**：客优云默认库存可能为0
- **SKU必须与1688一致**：规格数量和名称不能随意增删
- **支付前必须停**：1688代发下单涉及真金白银
- **利润率硬门槛80%**：不达标直接淘汰
- **必须读取子技能**：每个阶段先Read对应SKILL.md，不得凭记忆执行
- **必须用Tabbit CLI纯DOM操作**：不允许截图、不允许computer_use_tool GUI操作
