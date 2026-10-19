---
name: keyouyun-publisher
description: "客优云ERP自动化商品采集与发布。支持从1688/淘宝/拼多多链接采集商品、自动去水印、一键发布到Shopee全球商品及各站点店铺（泰国/菲律宾/马来西亚等）。含商品素材评审标准（图片/视频/本地化/合规）、编辑页素材替换全流程坑位、SKU精简策略。适用于跨境电商商品上架自动化、批量采集发布、商品信息同步、1688货源一键铺货Shopee等场景。当用户需要通过客优云采集商品链接并发布到Shopee时使用本技能。"
---

# 客优云商品采集发布自动化

## 概述

通过客优云ERP（https://erp.keyouyun.com）实现从1688商品链接采集到Shopee一键发布的全流程自动化。

**操作工具**：Tabbit CLI（Windows），不是 computer_use_tool。

## 前置条件

- 客优云已登录（账号 ID 557049，已授权 Shopee 店铺：juanyi.th、dingdanduoduo.th、lunlin.th、SIAM HOME ไทย TH）
- 商户：武汉市凡元卓宜商贸有限公司
- 1688 商品链接已准备好
- Tabbit CLI launcher：`& "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"`

## Windows Tabbit 调用模板（必须严格遵守）

```powershell
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
$program = [IO.Path]::GetTempFileName()
$code = @'
await page.goto("https://erp.keyouyun.com/drafts/collection", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));
return await tabbit.observe({frames: "none", maxChars: 6000});
'@
[IO.File]::WriteAllText($program, $code, [Text.UTF8Encoding]::new($false))
cmd.exe /d /c "`"$tabbitCli`" nodejs --task `"任务名`" --request-id step1 < `"$program`""
Remove-Item $program -ErrorAction SilentlyContinue
```

**关键规则**：
- 每次 nodejs 调用用**新 request-id**（复用旧ID返回旧receipt不执行）
- JS 硬超时 60 秒，复杂批量操作必须分批，单次不超过 30 个动作
- lexical 变量跨调用重置，用 `globalThis` 存状态
- 截图后用 `Read` 工具打开 `result.nextAction.path` 看
- PowerShell here-string 传 JS 会破坏编码，**必须写 UTF-8 无 BOM 临时文件再 cmd 重定向 stdin**

---

## 第一阶段：链接采集（从1688到草稿箱）

### 步骤1：进入链接采集页面

```javascript
await page.goto("https://erp.keyouyun.com/drafts/collection", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));
```

### 步骤2：输入1688链接并采集

**客优云 textarea 定位死路**：
- `page.getByRole("textbox", {name: "..."})` 因 accessible name 不匹配而超时

**可行方式**：
```javascript
await page.evaluate(() => {
  const tas = document.querySelectorAll('textarea');
  for (const t of tas) {
    if (t.offsetParent !== null && t.offsetHeight > 30) {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(t, 'https://detail.1688.com/offer/xxxxx.html');
      t.dispatchEvent(new Event('input', {bubbles: true}));
      t.dispatchEvent(new Event('change', {bubbles: true}));
      break;
    }
  }
});
```

### 步骤3：勾选"采集并自动发布"+ 点击"开始采集"

**坑**："采集并自动发布"是 generic div（选项），不是 button。需先勾选（向上找父元素3层后 click），再点"开始采集"按钮。

### 步骤4：配置自动发布弹窗

弹窗打开后：
1. **平台**：必须选"Shopee全球"（不是本土，不是TikTok）
2. **商户复选框正确位置**：对话框中"全选"下方扁平列表项"□ 武汉市凡元卓宜商贸有限公司"，**不是**展开树状面板里的复选框
3. **发布方式**：发布到随机店铺
4. **发布时机**：立即发布
5. **自动处理**：删除禁用词 + 删除超出字符

### 步骤5：确认发布结果

- 刷新采集列表页，查看商品状态是否变为"已发布"
- **⚠️ 发布≠上线**：点"发布"出现绿色"操作成功"只是创建了发布任务，商品可能在审核队列中
- **必须切到"在线商品"标签**（/offers/lists/online）确认商品真正出现在线上，0条说明未上线

---

## 第二阶段：草稿箱编辑（素材本地化替换）

### 进入编辑页

草稿箱 URL：`https://erp.keyouyun.com/offers/lists/collections/platform/10`

**坑**：
- 同一1688链接会采集出**多条记录**（中文标题+泰文标题各一条），必须通过左侧记录列表点击正确条目
- 坐标点击打开的可能是错误商品（如剥玉米神器），**必须通过商品货源ID文本定位**

```javascript
// 点击左侧列表中特定商品ID的条目
await page.evaluate(() => {
  const els = [...document.querySelectorAll("*")].filter(el =>
    el.offsetParent !== null && el.textContent.includes("2109211777935806464") && el.offsetHeight < 50
  );
  if (els.length > 0) els[0].click();
});
await new Promise(r => setTimeout(r, 3000));
```

### 编辑对话框结构（重要！）

- 左侧标签（产品信息/图片信息/SKU信息/产品描述/物流信息/其他信息）**是锚点导航，不是切换标签**
- 实际内容在**同一长滚动页**上，点左侧标签只是滚动定位
- 编辑对话框右上角 X 按钮可能点两次都不关闭——这是正常的，不要反复点

### 图片上传（已验证正确路径）

**死路**：
- 直接点"+"号 → 不触发 filechooser
- `input[type="file"]` 在 DOM 中返回空数组（客优云用组件级上传）
- `page.waitForEvent("filechooser")` 直接点"选取图片"主按钮 → 超时

**✅ 正确路径**：
1. 点"选取图片"**下拉箭头**展开下拉菜单
2. 点"本地上传"（4个选项中的第一个）
3. filechooser 事件触发 → `chooser.setFiles(localPath)`

```javascript
const [chooser] = await Promise.all([
  page.waitForEvent("filechooser"),
  page.evaluate(() => {
    // 点"选取图片"下拉箭头
    const els = [...document.querySelectorAll("*")].filter(el =>
      el.offsetParent !== null && el.textContent.trim() === "选取图片" && el.offsetHeight < 40
    );
    if (els.length > 0) els[0].click();
  })
]);
// 等下拉菜单出来后点"本地上传"
await new Promise(r => setTimeout(r, 1000));
await page.evaluate(() => {
  const els = [...document.querySelectorAll("*")].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === "本地上传" && el.offsetHeight < 40
  );
  if (els.length > 0) els[0].click();
});
await chooser.setFiles("C:/path/to/thai-image.jpg");
```

### 视频上传（已验证正确路径）

1. 产品视频区域点"+"号占位框
2. 展开下拉菜单（4个选项：本地上传/视频银行/采集视频/图生视频）
3. 点"本地上传" → filechooser 触发 → setFiles

### 删除原有素材

- **删除图片**：点"清空所有图片"按钮，9张中文原图全部清除
- **删除视频**：点视频缩略图右上角 X 按钮（坐标点击），不是文字按钮

### 保存草稿

素材就绪后点右下角"保存"按钮，出现绿色"操作成功"toast。

---

## 第三阶段：SKU 精简（重点坑位）

### 问题

客优云采集1688商品时，会自动采集同供应商**所有款式**的SKU，而不仅仅是当前链接的款式。

**实例**：1688 offer 900268371014 实际只有13个SKU，客优云采集了59个（包含同店铺其他款式）。

### 死路

| 方法 | 结果 |
|---|---|
| 点"删除超出的SKU"按钮 | SKU数量不变（这个按钮是删除超出字符限制的SKU名称，不是删除多余SKU） |
| 关闭"设置销售属性"开关 | 编辑对话框意外关闭回到列表页，重新打开后开关仍为开启 |
| JS循环逐个删除不在白名单中的SKU | 60秒硬超时被终止（删除每个SKU需要等动画+确认弹窗） |
| 坐标点击垃圾桶图标 | 不可靠，每个SKU行的删除按钮位置不固定 |

### ✅ 推荐方案

**方案A（推荐）：关闭"设置销售属性"开关，变成单规格商品**

对于"5张装"这类打包商品，不需要买家选款式，直接变成单规格：
1. 向上滚动到 SKU 信息区域顶部
2. 找到"设置销售属性"开关
3. 关闭它
4. **注意**：关闭后编辑对话框可能关闭，需要重新打开确认开关状态
5. 重新打开后变成单SKU，库存直接设500

**方案B：分批删除**

如果必须保留多规格：
1. 每批JS删除10-15个SKU（不超过60秒）
2. 每批结束后保存草稿
3. 重新打开继续删除
4. 删除前先用 `page.evaluate()` 提取所有SKU名称文本，对比1688实际SKU列表

### 核对1688实际SKU

必须截图1688商品页确认实际SKU列表，不能信客优云采集的SKU。

---

## 第四阶段：库存、类别、描述填写

### 库存设置

- 单规格商品：库存直接填数字（如500）
- 多规格商品：每个SKU都要单独设库存
- 位置：编辑页"产品价格"或"SKU信息"区域下方

### 类别翻译

客优云采集的类别是中文，需要翻译成泰文：
- 美甲贴纸 → `สติกเกอร์ติดเล็บ`
- 在"产品信息"区域找到类别字段，直接填入泰文

### 商品描述模板（泰文版）

固定货运文案（所有商品通用）：

```
ที่มา：จีน
สไตล์：（按商品填）
วัสดุ：（按商品填）

🔹 ส่วนลดค่าจัดส่งไม่ประจำสำหรับสินค้าทุกชิ้นในร้าน (รายละเอียดเพิ่มเติมที่หน้าหลักร้าน)
📣 กดติดตามร้านของเราเพื่อรับคูปองส่วนลดจำกัดเวลา
📣 สินค้าใหม่ ลดราคาพิเศษ ไม่พลาดการอัปเดตโปรโมชั่นล่าสุด
📣 รายละเอียดกิจกรรมอยู่ที่หน้าหลักร้าน
🔹 หากสต็อกสินค้าผิดปกติ เวลาจัดส่งจะแจ้งให้ทราบภายหลัง
【🌈 หากคุณมีข้อกำหนดพิเศษ กรุณาฝากข้อความในคำสั่งซื้อ (ไม่ใช่ในแชท) ขอบคุณที่ซื้อสินค้าค่ะ 🌈】
💯 สินค้าทุกชิ้นในสต็อกพร้อมจัดส่งทันที ประหยัดเวลาและสะดวกสบาย
🌼 【แจ้งการจัดส่ง】：
📣 ขนาดดังกล่าวอาจมีความคลาดเคลื่อนเล็กน้อยเป็นเซนติเมตรจากการวัดด้วยมือ ทุกอย่างเป็นไปตามผลิตภัณฑ์จริง
📣 สินค้าอาจมีความแตกต่างจากภาพถ่ายหรือสีที่หน้าจอ ทั้งนี้ให้ยึดตามสีของผลิตภัณฑ์จริง
📣 ปรึกษาออนไลน์รวดเร็ว ยินดีตอบทุกข้อสงสัย ใช้ประโยชน์จากแชทอย่างเต็มที่ มีผู้เชี่ยวชาญคอยให้บริการค่ะ
```

---

## 素材本地化工具链（与 shopee-media-localization 配合）

### 图片本地化流程

1. `mediakit-cli image erase-image` 擦除1688主图中文文字
2. Python PIL + Tahoma字体（tahomabd.ttf粗体）加泰语文案
3. Tahoma支持泰语渲染，无需额外安装字体

### 视频本地化流程

1. `mediakit-cli video probe-video-metadata` 探测视频信息
2. `mediakit-cli video video-ocr` 识别中文字幕时间轴
3. `mediakit-cli video erase-video-subtitle` 擦除中文字幕
4. `text_to_audio_plus` 生成泰语年轻女性电商配音
5. `mediakit-cli editing extract-audio` 提取原音轨
6. **⚠️ PowerShell传泰文JSON编码会失败** → 改用本地 ffmpeg `subtitles` 滤镜烧录泰文字幕
7. `mediakit-cli editing mux-audio-video` 替换音轨

**死路**：
- `mediakit-cli editing add-subtitle-to-video --subtitles <泰文JSON>`：PowerShell传参编码破坏JSON
- IOPaint pip安装：imghdr模块在Python 3.13被移除

---

## 商品素材评审标准（发布前必检）

### 图片评审

| 检查项 | Shopee标准 | 不通过处理 |
|---|---|---|
| 图片数量 | 至少3张，建议6-9张 | 不足时从1688详情页补采 |
| 图片尺寸 | 建议800×800px，JPG/PNG，≤2M/张 | 小图放弃使用 |
| 商品占比 | ≥70%画面 | 裁剪 |
| 水印/Logo | 无1688水印、无中文Logo | AI擦除 |
| 中文文字 | **图片中无任何中文** | 擦除+加泰文overlay |
| 实物一致性 | 与实物完全一致 | 不一致则放弃该货源 |

### 视频评审

| 检查项 | Shopee标准 | 不通过处理 |
|---|---|---|
| 视频时长 | 10-60秒 | 太短则补拍 |
| 分辨率 | ≤1280×1280px，MP4，<30MB | 太低则不用 |
| 中文语音/字幕 | **无中文语音、无中文字幕** | 擦字幕+泰语配音+烧泰文字幕 |
| 侵权 | 无第三方Logo/肖像 | 有则弃用 |

### 语言本地化（红线）

| 检查项 | 标准 |
|---|---|
| 标题语言 | 泰国站**必须泰文**，不允许中文标题直接发布 |
| 描述语言 | **全部泰文**，>50%非泰文会被删除+罚分 |
| 图片文字 | **不允许使用原1688中文素材**，必须本地化 |
| 视频语言 | 必须泰语配音+泰文字幕 |

---

## 常见错误排查

| 错误现象 | 原因 | 解决方案 |
|---|---|---|
| 点击发布无反应 | 未选择商户 | 对话框内"全选"下方扁平列表项勾选商户 |
| 提示"店铺是必须的" | 选了指定店铺但未勾选 | 切换到"发布到随机店铺" |
| 平台变成TikTok | 下拉框选项点错 | 重新选"Shopee全球" |
| textarea填不进值 | accessible name不匹配 | 用querySelectorAll+nativeSetter |
| 采集后列表看不到 | 数据异步处理中 | 等15秒后刷新 |
| 点"选取图片"不弹filechooser | 没展开下拉菜单 | 先点下拉箭头→点"本地上传" |
| `input[type=file]`返回空 | 客优云用组件级上传 | 走下拉菜单路径，不要找input |
| SKU数量太多 | 客优云采集同供应商所有款式 | 关闭"设置销售属性"变单规格 |
| "删除超出的SKU"不生效 | 这个按钮删的是超长SKU名称 | 分批JS删除或关闭开关 |
| 在线商品页0条 | "操作成功"只是创建任务 | 等待审核，或检查发布队列 |
| 编辑对话框滚动困难 | 内容区是自定义滚动容器 | 用`page.evaluate()`提取innerText，不依赖视觉滚动 |
| JS批量操作60秒超时 | 硬限制 | 分批，每批不超过30个动作 |
| 泰文JSON传参乱码 | PowerShell编码问题 | 写UTF-8无BOM文件，或用本地ffmpeg |
| 发布后在线商品页/全部商品页均0条 | Shopee API异步处理，全球商品创建+店铺同步需几分钟~十几分钟 | **看采集页"已发布"badge判断是否提交成功**，不要用在线列表判断失败 |
| `.el-dropdown-menu__item:has-text('同步店铺商品')` strict mode violation | 同时匹配"同步店铺商品"和"同步店铺商品评价" | 用`.filter({hasText:'...'}).first()`精确取第一个 |
| 品牌下拉框Playwright click()超时 | 被`.pro-modal-dialog-modal`遮罩拦截 | 用JS `el.click()`打开，再用`.el-select-dropdown__item:has-text('NoBrand')`选择 |
| 切换草稿后泰文标题变回中文 | 编辑器草稿不保留未保存修改 | **每次打开编辑器都要重新设置泰文标题** |
| 同步店铺商品对话框"暂无数据" | 店铺未在同步列表中授权 | 不影响发布提交，Shopee后台自行同步 |
| Element UI checkbox `.check()`超时 | 实际input[type="checkbox"]是hidden的 | 用JS `el.click()`或点击父label元素 |

---

## 已验证编辑器操作路径（2026-10 猫咪贴纸实战）

### 打开编辑器的正确路径

1. 采集页（/drafts/collection）插件采集tab，找到目标商品行
2. 若Shopee圆点为灰色（未认领），点击操作列**"认领取"**链接 → 圆点变绿
3. 点击操作列**"发布到Shopee"**链接 → 弹出"选择编辑站点"对话框 → 选**全球站** → 点确定
4. 编辑器弹窗打开，右下角有蓝色**"发布"**按钮

### 编辑器内精准定位方法

**商品名称输入框**：
```javascript
// 遍历所有 input[maxlength='180']，通过value含中文精确定位
const inputs = await page.locator("input[maxlength='180']").all();
for (const inp of inputs) {
  const v = await inp.inputValue();
  if (/[\u4e00-\u9fa5]/.test(v)) {
    await inp.fill("泰文标题");
    break;
  }
}
```

**SKU售价修改**：
```javascript
// 遍历所有可见可编辑input，筛选value="0.5"的字段（每SKU两个：售价+成本价）
// 偶数索引=售价列，奇数索引=采集成本价
const priceInputs = await page.locator("input.el-input__inner:not([readonly])").all();
let idx = 0;
for (const inp of priceInputs) {
  const v = await inp.inputValue();
  if (v === "0.5") {
    if (idx % 2 === 0) {
      await inp.fill("20"); // 售价改为20 CNY
    }
    idx++;
  }
}
```

**品牌下拉框**：
```javascript
// 枚举所有可见.el-select，品牌select特征为input placeholder="请选择"且value为空
// 用JS .click()打开（Playwright原生click被遮罩拦截）
await page.evaluate(() => {
  const selects = document.querySelectorAll('.el-select');
  for (const s of selects) {
    const input = s.querySelector('input[placeholder="请选择"]');
    if (input && !input.value) { s.click(); break; }
  }
});
await page.locator(".el-select-dropdown__item:has-text('NoBrand')").click();
```

### 发布对话框确认项

| 配置项 | 正确值 |
|---|---|
| 平台 | Shopee全球 |
| 商户 | 武汉市凡元卓宜商贸有限公司（通常已自动勾选） |
| 发布方式 | 发布到随机店铺 |
| 发布时机 | 立即发布 |
| 自动处理 | 删除禁用词 + 删除超出字符 |

### 发布成功判断标准

**不要**用在线商品页/全部商品页/待发布页/发布失败页判断——这些页面在发布后立即查看均为0条（Shopee API异步处理）。

**正确判断**：
1. 点击发布后出现绿色toast"操作成功"
2. 采集页对应商品行显示**"已发布"**badge + Shopee圆点变绿
3. 这表示发布请求已成功提交给Shopee API，后续由Shopee异步处理

---

## 发布后回写飞书

```powershell
$larkCli = "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\sandbox_envs_dir\envs\924a7238-9cc3-4fde-8763-1a287b815b76\override_dlcs\lark-cli.exe"
$json = '{"update_records":{"<record_id>":{"状态":["已上架"],"备注":"客优云自动发布，日期"}}}'
[System.IO.File]::WriteAllText("$env:TEMP\update.json", $json, [Text.UTF8Encoding]::new($false))
& $larkCli base +record-batch-update --base-token QsnYbrWpaa6lGfspgLpcihfvnpb --table-id tblccRoRGPoD8Ulw --json "@$env:TEMP\update.json" --as user
```

**注意**：
- JSON文件必须用无BOM的UTF8编码
- select字段值必须是已存在选项（热销/新品/高利润/低竞争/潜力）
- 飞书商品主表 table_id: tblccRoRGPoD8Ulw

---

## 固化脚本（零截图，纯CLI执行）

> **硬约束：不允许page.screenshot()，不允许Read图片。**
> AI只负责读飞书数据→替换脚本占位符→运行脚本→看JSON返回。

### 脚本清单

| 脚本 | 作用 | 输入 |
|---|---|---|
| `scripts/collect-and-publish.js` | 输入1688链接→自动采集→配置弹窗→提交发布 | OFFER_URL |
| `scripts/edit-product.js` | 打开编辑器→设泰文标题→改SKU价格→设库存→填类目→填描述 | OFFER_ID + 标题/价格/库存/类目/描述 |
| `scripts/upload-media.js` | 清空原图→上传泰文图片→上传泰文视频→保存 | OFFER_ID + 图片路径数组 + 视频路径 |
| `scripts/final-publish.js` | 点右下角发布→确认弹窗→验证"已发布"badge | OFFER_ID |
| `scripts/publish-to-shopee.ps1` | PowerShell封装，一键跑全流程 | 全部参数 |

### 执行方式

```powershell
# 一键全流程
& "C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Default\.doubaowork\agent_mode\workspace\.user_skills\keyouyun-publisher\scripts\publish-to-shopee.ps1" `
  -OfferUrl "https://detail.1688.com/offer/852413733872.html" `
  -ThaiTitle "สติกเกอร์..." -PriceCNY 10 -CostCNY 0.6 -Stock 500 `
  -CategoryThai "อุปกรณ์เสริมโทรศัพท์" `
  -ImagePaths '["C:/localized/img1.jpg","C:/localized/img2.jpg"]' `
  -VideoPath "C:/localized/video_th.mp4" `
  -TaskName "发布手机贴纸" -Step all

# 分步执行
-Step collect   # 只采集
-Step edit      # 只编辑
-Step upload    # 只上传素材
-Step publish   # 只发布
```

### 数据来源硬规矩（2026-10-13踩坑后固化）

1. **价格必须从飞书选品表读，不允许凭记忆或臆测**
   - 采购成本CNY = 飞书"采购成本CNY"字段
   - SLS运费CNY = 飞书"SLS运费CNY"字段（不是旧数据3.5，按商品重量算）
   - 建议售价CNY = 飞书"建议售价CNY"字段
   - 利润率必须≥80%
2. **类目必须从飞书选品表读**，不要自己选"文具>标签贴纸"
3. **1688链接必须用飞书选品表中的参考链接**，不要自己搜一个类似商品就上
4. **视频必须上传本地化后的泰文视频**，不允许跳过视频步骤
5. **SKU规格名称必须trim()首尾空格**
6. **库存必须设为500**

### 新踩坑（2026-10-13猫咪贴纸实战）

| 错误 | 原因 | 正确做法 |
|---|---|---|
| 售价翻倍（设了20应为10） | 没读飞书选品表，凭记忆 | 必须先lark-cli读飞书记录，用返回的价格 |
| SLS运费用了3.5 | 旧数据残留 | 按飞书SLS运费字段，轻小件只有1元 |
| 类目选了文具 | 自己判断 | 按飞书选品表类目字段执行 |
| 视频没上传 | 跳过了素材本地化步骤 | 脚本upload-media.js必须执行 |
| SKU规格有首尾空格 | 没做trim | 脚本里加trim() |
| 库存没设500 | 漏了这步 | 脚本edit-product.js里固定设500 |
| 积分消耗10% | 每步截图+Read图片 | 零截图，纯page.evaluate()操作DOM |
