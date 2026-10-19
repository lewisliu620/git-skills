---
name: shopee-order-fulfillment
description: "Shopee跨境店无货源一件代发发货全流程。从客优云ERP读取待处理订单→以图搜款在1688/拼多多找同款货源→1688代发下单到千恒仓→1688发货后取真实运单号→千恒货代系统录单回填首公里预报→飞书回写。适用于Shopee泰国/菲律宾/马来西亚店的日常发货、新订单待发货审批、发货超时预警、1688采购单跟踪、快递单号回填千恒。当用户说'发货''有订单来了''跟踪1688订单''快递单号录千恒''这个订单怎么处理'时使用本技能。"
---

# Shopee 无货源一件代发发货全流程

## 概述

本技能处理 Lewis（武汉市凡元卓宜商贸有限公司）的 Shopee 跨境店无货源发货闭环：

```
客优云订单 → 以图搜款找1688货源 → 1688代发下单到千恒仓
→ 1688卖家发货 → 从订单详情页取真实运单号
→ 千恒货代系统录单（填运单号+选承运商）→ 首公里预报
→ 飞书回写物流单号 → 千恒贴SLS面单送转运仓 → Shopee自动同步"已发货"
```

**核心原则**：坚决不允许货不对版，必须以订单商品图做以图搜款并点"严格同款"。

## 前置条件

- Tabbit 浏览器已登录客优云（erp.keyouyun.com）、1688（buy.1688.com）、千恒货代（qianheng.huoxiaoyi.com）
- 客优云账号 ID 557049，已授权店铺：SIAM HOME ไทย(TH)、juanyi.th、dingdanduoduo.th、lunlin.th
- 千恒货代两个仓库地址见下方
- 使用 Tabbit CLI（Windows），不是 computer_use_tool
- lark-cli 不写死 env hash（hash 会随环境刷新失效）：脚本 `qianheng-tracking-backfill.ps1` 内 `Resolve-LarkCli` 自动发现（环境变量 LARK_CLI > 已知 envs > 扫描 sandbox_envs_dir 最新 lark-cli.exe）；手动调用时用 `--as user`，找不到就扫描 `C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs\*\override_dlcs\lark-cli.exe`。旧 hash `924a7238` 已失效，勿再写。

## 千恒货代仓库地址

| 仓库 | 地址 | 收件人 | 手机 |
|---|---|---|---|
| 义乌仓（推荐，义乌/金华供应商首选） | 浙江省金华市义乌市城西街道香溪锦园13-102 | 千恒+ID282225 | 15362871061 |
| 东莞仓（广东/珠三角供应商首选） | 广东省东莞市谢岗镇赵林村宝湖路82号巨嘉工业园F栋301 | 千恒商贸云仓+ID282225 | 15362871061 |

**选仓规则**：供应商在浙江/江苏/上海→义乌仓；供应商在广东→东莞仓。其余按距离最近原则。

**代打包费**：2元/单。千恒账户余额不足时无法提交，需提醒用户充值。

## 飞书数据中台

- base_token: `QsnYbrWpaa6lGfspgLpcihfvnpb`
- 关键表：
  - `tbl9S5Xruh3ytOib`：1688采购订单跟踪表
  - `tbluqGOYjMr7oFHT`：订单&货代对账表
  - `tblb4JFvltBmAQQC`：货代基础表（义乌仓/东莞仓）
  - `tblccRoRGPoD8Ulw`：商品资源主表

### 1688采购订单跟踪表字段顺序

| 序号 | 字段名 | 类型 | 说明 |
|---|---|---|---|
| 1 | 1688订单号 | text | 如 3316506422004016259 |
| 2 | 物流单号 | text | 格式"承运商 运单号"，如"申通 773445887926488" |
| 3 | 已通知 | select | 是/否 |
| 4 | 供应商 | text | 如"义乌卓怡塑料制品厂" |
| 5 | 采购状态 | select | 待发货/已发货/已签收 |
| 6 | 商品名 | text | |
| 7 | 备注 | text | |
| 8 | 下单时间 | datetime | |
| 9 | 目标仓库 | select | 千恒义乌仓/千恒东莞仓 |
| 10 | 金额CNY | number | |
| 11 | 关联Shopee订单号 | text | |
| 12 | 发货时间 | datetime | |

**注意**：没有单独的"承运商"字段，承运商信息写在"物流单号"text字段里。

---

## 完整操作流程

### 步骤1：客优云读取待处理订单

导航到 `https://erp.keyouyun.com/orders/pending`，等待加载后读取：订单号、商品名称/规格、数量、实付金额、店铺、发货截止时间。

#### 1.1 页面结构（重要：不是表格！）

客优云 ERP 是 Vue SPA，订单列表是**卡片式 div 布局，不是 `<table><tr>` 结构**。每次定时任务执行时，AI 必须按以下方式读取，不要猜选择器：

```javascript
// 等待 Vue 渲染完成（至少等 5 秒，不要只用 domcontentloaded）
await page.goto("https://erp.keyouyun.com/orders/pending", { waitUntil: "domcontentloaded" });
await new Promise(r => setTimeout(r, 5000));

// 正确读取所有待处理订单
const orders = await page.evaluate(() => {
  const items = document.querySelectorAll("div.v-order-item.pending-order-item");
  return [...items].filter(el => el.offsetParent !== null).map(el => {
    const orderNo = el.querySelector(".ordersn-copy")?.textContent?.trim() || "";
    // 从整个卡片文本里提取信息
    const text = el.innerText || "";
    return { orderNo, rawText: text.slice(0, 500) };
  });
});
```

**关键选择器**：
| 字段 | 选择器 | 说明 |
|---|---|---|
| 订单项容器 | `div.v-order-item.pending-order-item` | 每个订单一张卡片 |
| 订单号 | `.ordersn-copy`（在卡片内查找） | 如 261013GE6X8FPC |
| 下单时间 | 卡片文本中匹配 `\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}` | 如 2026-10-13 12:30:21 |
| 实付金额 | 卡片文本中匹配 `THB \d+` | 如 THB 107 |
| 店铺 | 卡片文本中 `TH` 标签后 | 如 SIAM HOME |

**以下方式全部验证为错误（会读到空结果）**：
- `document.querySelectorAll("tr")` → 客优云不用表格布局
- `document.querySelectorAll(".table-row")` → 没有这个 class
- `page.locator("table").locator("tr")` → 页面上没有订单表格
- 只等 `domcontentloaded` 就读取 → Vue 还没渲染订单数据

#### 1.2 弹窗处理

页面上有大量空的 `v-dialog__container` 弹窗容器（DOM里存在但不可见），不要被它们干扰。只读取 `offsetParent !== null` 的可见元素。

如果有真正可见的弹窗（如"导入失败"提示），先关闭再读取订单。

### 步骤2：下载订单商品图

从客优云订单页提取 Shopee 商品图 URL，用 `page.fetch` 下载到 `artifactPath("product-1.jpg")`。

### 步骤3：1688 以图搜款（严格同款）

**必须以图搜，禁止以文字标题搜。**

```javascript
await page.goto("https://air.1688.com/kapp/1688-search/pc-image-search/", {waitUntil: "domcontentloaded"});
await page.locator('input[type="file"]').setInputFiles(localImagePath);
await new Promise(r => setTimeout(r, 3000));
// 上传后必须点"搜索图片"按钮，不会自动跳转
await page.evaluate(() => {
  for (const el of document.querySelectorAll('*')) {
    if (el.textContent.trim() === '搜索图片' && el.offsetParent !== null) { el.click(); return; }
  }
});
await new Promise(r => setTimeout(r, 5000));
// 必须点"严格同款"，默认是"找相似"混款
await page.evaluate(() => {
  for (const el of document.querySelectorAll('*')) {
    if (el.textContent.trim() === '严格同款' && el.offsetParent !== null) { el.click(); return; }
  }
});
await new Promise(r => setTimeout(r, 3000));
// 验证"严格同款"已选中：检查按钮是否有 active/selected 样式
const strictActive = await page.evaluate(() => {
  for (const el of document.querySelectorAll('*')) {
    if (el.textContent.trim() === '严格同款' && el.offsetParent !== null) {
      const cls = el.className || '';
      return cls.includes('active') || cls.includes('selected') || cls.includes('on');
    }
  }
  return false;
});
if (!strictActive) { throw new Error('"严格同款"未选中，中止搜款'); }
```

### 步骤4：核对同款并选供应商（**核心防错门**）

**不要凭标题判断同款。不要凭文字规格名判断同款。**

> ⚠️ **踩坑案例（2026-10-14）**：Shopee 订单卖的是**方块冰格**（长方形格子），但 1688 以图搜款选了**圆球冰格**（小弹珠33格）。两者文字规格都写"大号圆形粉色(33格)"，但实际商品形态完全不同。根因：没点"严格同款"、没做前6主图肉眼比对就直接下单。

**必须按以下顺序执行，缺一不可：**

1. **截图前6个商品主图**，和订单商品图并排肉眼比对
   - 重点看：商品**形状**（方块/圆球/长条/异形）、**颜色**、**格子数量和排列方式**
   - 文字规格名相同 ≠ 商品相同（"33格"可能是33个方块，也可能是33个圆球）
2. **点进商品详情页**，核对 SKU 列表是否包含订单所有规格
3. **确认多 SKU 在同一家店能一次拍齐**

**供应商筛选优先级**：
1. 主图与订单图**形状完全一致**（不是颜色一致，是形状和结构一致）
2. SKU 包含订单所有规格
3. 供应商距离千恒仓库最近（义乌→义乌仓；广东→东莞仓）
4. 价格最低
5. 加分：密文代发、48h揽收率≥95%、品质达标率≥99%

**形状不一致的硬拦截规则**：如果前6个搜款结果的商品形状与订单图不一致（如订单是方块格、搜出来是圆球格），**停止搜款，不要强行选一个"最接近"的**。改用文字搜索关键词 + 形状筛选，或告知用户找不到同款。

### 步骤5：1688 代发下单

**不要用采购车结算！** 在商品详情页选好 SKU，点"代发下单"直接走一件代发结算。收货地址填千恒仓库地址。**支付前必须停下来让用户确认。**

#### 5.1 SKU 选择（iframe 弹窗，最大坑之一）

点"代发下单"后会弹出全屏 iframe（`fullscreen-drawer-iframe`），URL 含 `sku-panel.html`。

**关键认知：这不是单选按钮，是数量选择器。** 每个 SKU 行右侧有一个加号按钮 `.anticon-plus`，**点加号增加数量**，不是点 SKU 行本身。

```javascript
const skuFrame = page.frames().find(f => f.url().includes('sku-panel'));
// 正确方式：点目标SKU行内的加号按钮
await skuFrame.locator('.expand-view-item', { hasText: '大号圆形粉色' })
  .locator('.anticon-plus').click();
// 数量输入框 .ant-input-number-input 对应值从"0"变成"1"即选中成功
```

**以下方式全部验证为死路**：
- `frame.locator('.expand-view-item', {hasText: SKU名}).click()` → 不触发React事件
- JS `.click()` 点 SKU 行 → cursor 是 auto 不是 pointer，行本身不可点
- 坐标点 SKU 行中间 → 点到了不可交互的文本区域
- `locator.click()` 点 item-label span → 无效

#### 5.2 提交订单（Q-BUTTON 自定义组件，第二个大坑）

SKU 数量选好后，点"代发下单"按钮（iframe 内），会新开标签页跳转到 `order.1688.com/order/smart_make_order.htm`。

在订单确认页，"立即下单"按钮是 **Q-BUTTON 自定义 Web Component**，不是标准 `<button>` 或 `<a>` 标签：

```javascript
// 用 JS 找最深层包含"立即下单"文字的元素
const btn = await page.evaluate(() => {
  for (const el of document.querySelectorAll('*')) {
    const ownText = [...el.childNodes].filter(n => n.nodeType === 3)
      .map(n => n.textContent).join('').trim();
    if (ownText === '立即下单' && el.offsetParent !== null) {
      const rect = el.getBoundingClientRect();
      return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
    }
  }
});
// 用鼠标坐标点击（JS .click() 和 Playwright locator 都无效）
await page.mouse.click(btn.x, btn.y);
```

**以下方式全部验证为死路**：
- `page.locator('button:has-text("立即下单")')` → 超时找不到（不是 button 标签）
- `page.locator('a:has-text("立即下单")')` → 超时找不到
- JS `.click()` → 点到了外层 ASIDE 容器，不是按钮本身
- Playwright `locator.click()` → Q-BUTTON 内部事件不响应

**下单成功标志**：页面跳转到 `air.1688.com/.../cashier.html`（收银台），URL 参数 `orderId=xxx` 即为 1688 订单号。

### 步骤6：跟踪 1688 订单发货

```javascript
// 待发货列表URL（不要用 order_list.htm，会404）
await page.goto("https://trade.1688.com/order/buyer_order_list.htm?trade_status=waitsellersend", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 6000));
```

### 步骤7：从1688订单详情页获取真实运单号

**1688列表页不显示具体运单号**，必须导航到订单详情页：

```javascript
// orderId 是1688订单号
await page.goto(`https://trade.1688.com/order/order_detail.htm?orderId=${orderId}`, {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));
// 在详情页提取承运商和运单号
const tracking = await page.evaluate(() => {
  const text = document.body.innerText;
  // 匹配 "申通 773445887926488" 或 "圆通 YT7649149617449" 格式
  const m = text.match(/(申通|圆通|中通|韵达|极兔|顺丰|京东|百世|EMS)\s*[A-Z]*\s*(\d{10,}|[A-Z]{2}\d{10,})/);
  return m ? { carrier: m[1], no: m[2] } : null;
});
```

**承运商识别**：运单号前缀对应承运商——STO→申通、YTO→圆通、ZTO→中通、YD→韵达、JT→极兔、SF→顺丰。

### 步骤8：千恒货代系统录单（核心步骤）

千恒录单是整个流程最曲折的环节，有大量坑。

#### 8.1 入口

- 我的订单页：`https://qianheng.huoxiaoyi.com/order?platform=shopee&tab=wait_submit`
- 录单入口：**"待提交打包"tab** → 行内"代打包"按钮（class=`J_editPacking`）
- **不是**包裹管理页，那里"未录单"tab为空

#### 8.2 填写快递单号

在弹窗内，用 JS 给所有可见的快递单号 input 填值：

```javascript
const modal = [...document.querySelectorAll(".ivu-modal")].find(
  m => m.offsetParent !== null && m.textContent.includes("代打包")
);
const inputs = [...modal.querySelectorAll("input")].filter(
  inp => inp.offsetParent !== null && (inp.placeholder || "").includes("快递单号")
);
for (const inp of inputs) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(inp, TRACKING_NO);
  inp.dispatchEvent(new Event("input", { bubbles: true }));
  inp.dispatchEvent(new Event("change", { bubbles: true }));
}
```

#### 8.3 选择承运商（iView Select——最大的坑）

**iView Select 下拉组件用 Playwright locator.click() 完全无效**，会报 element not visible。以下方法全部验证为死路：
- `locator.click()` → element not visible
- `page.evaluate(el => el.click())` → selected-value 仍为 null
- 输入物流公司名按 Enter → Select 不是 filterable 模式
- `:visible` CSS pseudo-class → 无效
- `getByPlaceholder("请输入物流公司")` → strict mode violation（有6个匹配元素含隐藏模板div）

**唯一有效方法：坐标点击法**

```javascript
// 1. 先获取物流公司 input 的位置
const selects = [...modal.querySelectorAll("input")].filter(
  inp => inp.offsetParent !== null && (inp.placeholder || "").includes("物流公司")
);
const rect = selects[0].getBoundingClientRect();
// 2. 用 page.mouse.click 展开下拉
await page.mouse.click(rect.x + rect.width/2, rect.y + rect.height/2);
await page.waitForTimeout(1000);
// 3. 在展开的下拉中找到承运商选项，再坐标点击
const options = [...document.querySelectorAll(".ivu-select-dropdown li, .ivu-select-item")].filter(
  li => li.offsetParent !== null && li.textContent.trim() === "圆通速递"
);
const optRect = options[0].getBoundingClientRect();
await page.mouse.click(optRect.x + optRect.width/2, optRect.y + optRect.height/2);
```

**承运商映射**（飞书简称 → 千恒下拉选项完整名称）：

| 飞书简称 | 千恒下拉选项 |
|---|---|
| 申通 | 申通快递 |
| 圆通 | 圆通速递 |
| 中通 | 中通快递 |
| 韵达 | 韵达快递 |
| 极兔 | 极兔速递 |
| 顺丰 | 顺丰速运 |
| 京东 | 京东物流 |
| 百世 | 百世快递 |
| EMS | EMS物流 |

#### 8.4 多SKU订单的处理

一个Shopee订单可能对应多个SKU（如雪糕模具含积木款+雪人款），每个SKU行都需要填快递单号和选承运商。

**禁止点"应用到全部"按钮**——它会在第二个SKU下多创建一行空记录，导致第二个SKU变成两行，其中一行物流公司为空，提交时报错"此订单所有商品均未填写出货信息"。

正确做法：逐行手动填写每个SKU的快递单号和承运商。

#### 8.5 删除多余行

如果误点了"应用到全部"导致多出行，点该行右侧的"删除"链接（JS click 即可），删到每个SKU只剩一行。

#### 8.6 提交

```javascript
await page.locator(".J_orderEditorDialogSubmit").click();
await page.waitForTimeout(5000);
// 验证成功：弹窗关闭
const modalOpen = [...document.querySelectorAll(".ivu-modal")].some(
  m => m.offsetParent !== null && m.textContent.includes("代打包")
);
// modalOpen === false 即提交成功
```

#### 8.7 验证

刷新页面，确认：
- "待提交打包"数量减少
- "已提交待处理"数量增加
- 底部首公里预报行显示"【首公里预报】圆通速递 YT7649149617449"

### 步骤9：飞书回写

```powershell
$larkCli = "lark-cli路径"
$json = '{"update_records":{"<record_id>":{"物流单号":"申通 773445887926488"}}}'
$tmpJson = "$env:TEMP\update.json"
[System.IO.File]::WriteAllText($tmpJson, $json, (New-Object System.Text.UTF8Encoding $false))
& $larkCli base +record-batch-update --base-token QsnYbrWpaa6lGfspgLpcihfvnpb --table-id tbl9S5Xruh3ytOib --json "@$tmpJson" --as user
```

**注意**：没有"承运商"字段，承运商信息写在"物流单号"text字段里。

### 步骤10：通知用户

通过飞书消息通知：商品名称、1688运单号、承运商、千恒提交状态。如果千恒余额不足，提醒充值。

---

## 自动化脚本（#50 千恒录单固化）

本 skill 附带 `qianheng-tracking-backfill.ps1`，把步骤8的录单动作固化为可复用脚本，单条/批量均可，默认 DryRun 只列不提交。

```powershell
# 批量预览（只读飞书，不提交千恒）：列出待录单 + 跳过原因
.\qianheng-tracking-backfill.ps1 -Batch -DryRun

# 批量真实提交（千恒已登录时）：逐条提交，遇登录失效立即中断
.\qianheng-tracking-backfill.ps1 -Batch

# 单条模式（指定订单/承运商简称/真实运单号）
.\qianheng-tracking-backfill.ps1 -ShopeeOrderId 2610109QQ0S3WC -Carrier 申通 -TrackingNo 773445887926488
```

**待录单筛选口径（批量，已固化）**：仅「采购状态=已发货」且「物流单号可解析出承运商+真实运单号」且「有关联Shopee订单号」才进待录单；已取消、待发货/未付款（无单号）、缺单号、缺Shopee号一律跳过并打印原因。承运商简称优先匹配，运单号前缀（STO/YTO/ZTO/YD/JT/SF/JD/BD/EMS）兜底。

**登录失效前置拦截（已固化）**：导航千恒后先读页面内文，命中「登录失效/授权过期/请重新登录」立即返回 authExpired，不填单号、不点承运商、不提交，退出码2；批量模式遇此中断，不继续刷失败。

**成功判据（已固化，不只看弹窗关闭）**：提交后必须同时满足「代打包弹窗关闭」AND「页面首公里预报行出现 承运商完整名+运单号」；只关弹窗但无首公里预报 → 判为未完全成功，转人工核对。

**仍需人工/重登后校准的页面动作**：待提交打包队列里按 Shopee 订单号定位行、点 `J_editPacking`、逐SKU填单号、坐标点选 iView 承运商、点 `J_orderEditorDialogSubmit` 提交——这些在千恒登录态失效期间未实测，重登后需现场探针校准选择器；已固化的坑（坐标点选、禁"应用到全部"、入口是待提交打包代打包、提交class、首公里预报校验）见步骤8。

**2026-10-19 实测修复（已固化）**：千恒已登录，真实 Batch 跑通。修复了三处：
1. **Tabbit top-level 无 document** → `Submit-ToQianheng` 全部 JS 重写为 `context.newPage()` + `page.evaluate()` 形态（DOM 读取/点击包进 evaluate），废弃复用 tabId 逻辑；
2. **request-id 必须每次唯一** → 所有 `find-/fill-/pos-/sel-/submit-` 后追加 `$(Get-Random)`，复用旧 request-id 会返回旧 receipt 不执行（导致误判"document is not defined"陈旧结果）；
3. **.ps1 必须 UTF-8 with BOM** → 无 BOM 时 PowerShell 5.1 按 ANSI 解析中文报语法错误（"表达式或语句中包含意外的标记"）；用字节级补回 BOM（EF BB BF）修复。
验证结论：压蒜器/雪糕模具因不在千恒待提交队列被正确判"已录跳过"（不重复提交）；千恒当前余额 4.00、代打包费 2元/单，**余额不足时提交会被千恒拒绝，需用户充值后才可真实录单**。

---

## 自动化监控 worker（1688 发货监控 + 运单号回写 + 千恒回填）

`D:\AI\电商\1688-worker\worker.py` 是独立于 Tabbit 定时任务的本机 worker，覆盖「飞书读待发货 → 浏览器核对 1688 订单 → 详情页取运单号 → 回写飞书 → 推 CloudBase → 千恒录单回填 → 飞书通知 Lewis」。Windows 计划任务已注册 4 个（`Doubao-1688-Worker-0900/1200/1800/2100`，09/12/18/21 点）。

**数据流**：
```
飞书「1688采购订单跟踪表」(tbl9S5Xruh3ytOib, 采购状态=待发货 且 已通知=否)
  → Tabbit 浏览器打开 1688 待发货列表 (air.1688.com/.../buyer-order-list.html?trade_status=waitsellersend)
  → ★监听 mtop 接口响应解析订单号（SPA 数据在接口里，不在 DOM）★
    订单号不在待发货列表 = 疑似已发货 → 详情页 (air.1688.com/app/ctf-page/trade-order-detail/index.html?orderId=xxx)
    ★监听 deliveryorderservice 接口取 承运商+运单号★
  → 回写飞书：采购状态=已发货、物流单号="承运商 运单号"、发货时间=毫秒戳、已通知=是
  → 推 CloudBase (cb-sync.js push-result)
  → ★千恒录单回填（2026-10-19 固化接入 worker 步骤4.5）★：对已发货且有关联 Shopee 订单号的记录，
    自动调 qianheng-tracking-backfill.ps1 单条模式（-ShopeeOrderId -Carrier -TrackingNo），
    千恒侧失败不影响 1688 状态回写；结果（提交成功/已录跳过/登录失效）入队通知
  → 飞书消息通知 Lewis
```

**worker 千恒回填函数**：`backfill_qianheng(shopee_order_id, carrier_short, tracking_no)`，调用 ps1 单条模式，按退出码解析：0=成功或已录跳过、1=未完全成功、2=登录失效；千恒登录失效会单独入队提醒「千恒登录态已失效，请重新登录」，不影响 1688 主链路继续。

**worker 退出码**：0=正常完成；1=本次被阻塞（风控/登录失效已发提醒，下轮自动再试）。

**关键实现约束（已实测固化）**：
- 浏览器通道用 Tabbit CLI（`--task 1688-worker --request-id <每次新id> --timeout-ms 90000`），JS 经 stdin 传入
- ★读取方式=拦截 mtop 接口响应，不读 DOM innerText★：列表接口 `mtop.1688.trading.dataline.service`（订单号正则 `/entryId[\\"]*:[\\"]*(\d{16,})/g`，19位），详情接口 `mtop.1688.deliveryorderservice.querydeliveryorderpacklist`（承运商+logisticsIndex 取运单号）；计数 `waitSellerSendGoodCount` 区分真空列表(=0)与解析遗漏(>0)
- 风控检测优先于一切：body 命中「验证码/滑块/_____tmd_____/punish」→ 判 PUNISH，发提醒不硬刷
- 登录失效检测：URL 命中 login/passport → 发「1688登录态已失效，请重新登录」
- 读不到运单号保守跳过（下轮再确认），不误标已发货
- 飞书消息用 `im +messages-send --user-id ou_1553e162fbb3505885745120dda34f0a --text @file`（文件方式避免命令行中文转义坑）

**已知待人工动作**：1688 触发 x5sec 滑块验证码时，需用户到 Tabbit 浏览器手动完成一次验证（拖动滑块），之后数据接口自动恢复，worker 下轮自动继续。

---

## Tabbit CLI Windows 关键坑

### 多行 JS 写法

PowerShell 会破坏 here-string 编码。必须：
1. 写 UTF-8 **无 BOM** 临时文件
2. 用 `cmd.exe /d /c "... < program.js"` 重定向 stdin

```powershell
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
$program = [IO.Path]::GetTempFileName()
$code = @'
// JS code here
'@
[IO.File]::WriteAllText($program, $code, [Text.UTF8Encoding]::new($false))
cmd.exe /d /c "`"$tabbitCli`" nodejs --task `"任务名`" --request-id step1 < `"$program`""
Remove-Item $program -ErrorAction SilentlyContinue
```

### 其他坑速查表

| 坑 | 解决方案 |
|---|---|
| **1688 订单列表/详情页被 x5sec 滑块验证码拦截（实测 2026-10-18）** | **导航后读 body.innerText，命中「验证码/滑块/拖动/_____tmd_____/punish/x5sec」即判风控；不要重试硬刷，发飞书提醒「1688需人工过验证码」，冷却后（≥30min）worker 下轮自动再试。列表页被拦 URL 特征 `trade.1688.com/.../_____tmd_____/punish?x5secdata=`** |
| **1688 订单详情页是 SPA** | **`trade.1688.com/order/order_detail.htm` 会跳转到 `air.1688.com/app/ctf-page/trade-order-detail/index.html?orderId=xxx`；必须等 SPA 渲染（轮询 bodyLen>50 且无 punish，最多10次×3s），直接读 6s 后 innerText 为空** |
| **1688 数据接口与页面不同步** | **页面能打开（登录态有效）≠ 数据接口可用；SPA 的 mtop 数据调用被 x5sec 拦时页面只有探针/骨架，bodyLen<300 无订单内容，此时同样判风控处理** |
| **★1688 SPA 订单数据在 mtop 接口响应里，不在 DOM innerText（实测 2026-10-18 关键突破）** | **air.1688.com 列表/详情页只渲染框架，innerText 恒为探针文本（bodyLen≈260）；真实数据在浏览器内自发请求 `h5api.m.1688.com/h5/mtop.1688.trading.dataline.service` 响应里。正确通道=Tabbit 页面上挂 `tab.on('response')` 监听，正则从响应 body 解析 JSON；列表订单号正则 `/entryId[\\"]*:[\\"]*(\d{16,})/g`（订单号是 19 位，`\d{16}` 会截断）；计数接口含 `waitSellerSendGoodCount`（>0 有单但解析遗漏→保守跳过下轮；=0 才是真空列表→逐单详情页确认）** |
| **★1688 运单号从详情页接口取，不读 DOM（实测 2026-10-18）** | **详情页 SPA innerText 同样读不到；监听 `mtop.1688.deliveryorderservice.querydeliveryorderpacklist` 响应，正则 `"logisticsCompanyName":"([^"]+)"` 取承运商（如"申通快递(STO)"→简称申通）、`"logisticsIndex":"([^"]+)"` 取"LPxxx_运单号"后半段为运单号；未命中=订单尚未实际发货，保守跳过下轮，不误标** |
| **★1688 订单号是 19 位** | **形如 3316533566047016259；所有正则用 `\d{16,}` 或 `\d{19}`，`\d{16}` 只匹配前 16 位会截断错判** |
| `pages()` 返回 Page 对象不能 JSON 化 | for 循环 await `p.title()`/`p.url()` |
| 每次 JS 程序 lexical 变量重置 | 用 `globalThis` 存跨调用状态 |
| 新 request-id 必须每次新 | 复用旧 request-id 返回旧 receipt 不执行 |
| 1688 图搜上传后不跳转 | 必须点"搜索图片"文字按钮 |
| 图搜默认找相似混款 | 必须点"严格同款" |
| 1688 订单列表 `order_list.htm` 404 | 用 `buyer_order_list.htm?trade_status=waitsellersend` |
| **1688列表页不显示运单号** | **必须进 order_detail.htm?orderId=xxx 详情页** |
| **千恒 iView Select locator.click 无效** | **用 page.mouse.click 坐标点击** |
| **千恒"应用到全部"会多创建空行** | **禁止使用，逐行手动填** |
| **千恒录单入口不是包裹管理页** | **是"我的订单→待提交打包→代打包"按钮** |
| **防重复录单（红线）** | **只在"待提交打包"队列按 Shopee 订单号定位到可见行才提交；队列找不到=已录/已签收，直接跳过。禁止硬导航 `tab=has_process` 抓全文去重——SPA 重导会被重置成"已处理(0)/暂无数据"，读空反而漏判导致重复提交** |
| **tabbit top-level 无 document/window** | **goto/等待可在顶层，取 body.innerText/DOM 必须包进 `page.evaluate(()=>{...})`，否则报 `document is not defined`（exit 70）** |
| **千恒提交按钮 class** | **`J_orderEditorDialogSubmit`** |
| **1688代发iframe内SKU选择** | **点行内加号按钮 `.anticon-plus` 加数量，不是点SKU行** |
| **1688"立即下单"是Q-BUTTON组件** | **不是标准button/a，必须用 page.mouse.click 坐标点击** |
| **客优云订单不是表格布局** | **是 div.v-order-item.pending-order-item 卡片，订单号在 .ordersn-copy** |
| **客优云页面加载后至少等5秒** | **domcontentloaded 后 Vue 还要异步渲染订单数据** |
| PowerShell .ps1 中文乱码 | 保存为 UTF-8 with BOM |
| `--timeout-ms` 最小 60000 | 默认60秒，复杂操作加 `--timeout-ms 120000` |

## 金额换算

- THB→CNY 汇率 ≈ 4.86
- 1688 采购成本 + 千恒代打包费2元 ≈ 总成本
- Shopee 售价 - 总成本 - 平台佣金 - 物流费 = 利润

## 停止条件

- **支付前必须停**：1688 结算页涉及真金白银
- **登录墙**：1688/客优云/千恒登录态失效时 reportIssue("AUTHENTICATION_REQUIRED")
- **货不对版（形状不一致）**：图搜结果前6个主图的商品**形状**与订单图不一致时（如方块格 vs 圆球格），不要强行下单，不要选"最接近"的，停止搜款并告知用户
- **"严格同款"未选中**：如果验证按钮没有 active 状态，中止搜款
- **千恒余额不足**：提醒用户充值，不要反复重试提交
