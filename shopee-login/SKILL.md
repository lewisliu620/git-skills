---
name: shopee-login
description: |
  Shopee卖家中心登录自动化（泰国站）。处理语言选择弹窗、主从账号登录、OTP验证码等待人工输入的场景。
  Use when:
  (1) 需要登录Shopee卖家中心查看/操作订单；
  (2) Shopee登录态过期，重定向到accounts.shopee.co.th；
  (3) 定时任务或发货流程需要访问seller.shopee.co.th。
  Input: 无（自动使用已保存的账号密码）。
  Output: 已登录的Tabbit页面，可继续操作卖家后台。
  Do not: 不自动处理OTP验证码（必须等用户输入）；不尝试绕过验证码；不重复登录已登录的页面。
---

# Shopee 卖家中心登录

处理Shopee泰国站卖家中心的完整登录流程，解决语言弹窗、主从账号格式、按钮点击等坑。

## 快速开始

1. 导航到卖家中心目标页 → 自动跳登录页
2. 关闭语言选择弹窗
3. 填账号密码 → 点LOG IN
4. 遇到OTP → 暂停等用户输入
5. 验证登录成功

## 账号信息

- 账号：`YSGX001N:main`（主从账号格式）
- 密码：`Qq#345ed`
- 站点：泰国站 seller.shopee.co.th
- 登录页：accounts.shopee.co.th/seller/login

## 完整登录流程

### Step 1：导航目标页，检查是否需要登录

```javascript
await page.goto("https://seller.shopee.co.th/order/details", { waitUntil: "domcontentloaded" });
await new Promise(r => setTimeout(r, 6000));
const url = page.url();
// 如果url包含accounts.shopee.co.th/login，说明需要登录
const needLogin = url.includes("login") || url.includes("passport");
```

如果已登录，直接跳到 Step 6 验证。

### Step 2：关闭语言选择弹窗（最大坑）

**首次加载登录页必弹语言选择modal**，挡住整个登录表单。

弹窗内容：
- 标题："เลือกภาษา"（选择语言）
- 两个选项按钮：ไทย（泰语）、English

**关闭方法**：用JS找textContent==="English"的元素点击，或坐标点击。

```javascript
// 方法1：JS点击
await page.evaluate(() => {
  const els = [...document.querySelectorAll("button, div, a")].filter(el => 
    el.offsetParent !== null && el.textContent?.trim() === "English"
  );
  if (els.length > 0) els[0].click();
});

// 方法2：如果JS点击无效，用坐标点击（弹窗在页面中间，English按钮约在y=670, x=830）
// await page.mouse.click(830, 670);

await new Promise(r => setTimeout(r, 8000)); // 等页面重新加载
```

### Step 3：确认登录表单可见

语言弹窗关闭后，页面重新加载，应看到：
- 用户名输入框：placeholder="Phone number / Username / Email"，name="loginKey"
- 密码输入框：placeholder="Password"，type="password"，name="password"
- 橙色"LOG IN"大按钮
- 底部"Login with Main/Sub Account"入口

### Step 4：填账号密码并登录

```javascript
await page.locator('input[name="loginKey"]').fill("YSGX001N:main");
await page.locator('input[name="password"]').fill("Qq#345ed");
await new Promise(r => setTimeout(r, 1000));
```

**点LOG IN按钮的坑**：
- 第一个 `button[type="submit"]` 是空按钮（class=VetC8R，无文字），点了没用
- 真正的登录按钮是第二个submit按钮，橙色背景，文字"LOG IN"
- JS `.click()` 可能不触发React事件，用坐标点击更可靠

```javascript
// 找真正的LOG IN按钮坐标
const btnRect = await page.evaluate(() => {
  const btns = [...document.querySelectorAll("button")].filter(b => 
    b.offsetParent !== null && b.textContent?.trim().toUpperCase() === "LOG IN"
  );
  if (btns.length === 0) return null;
  const rect = btns[0].getBoundingClientRect();
  return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
});

if (btnRect) {
  await page.mouse.click(btnRect.x, btnRect.y);
}
```

### Step 5：处理登录结果

等待8秒后检查：

**情况A：登录成功** → URL跳转到seller.shopee.co.th，进入Step 6。

**情况B：登录失败** → 页面显示"Login failed, please try again later"。
- 可能原因：账号格式问题，需要走"Login with Main/Sub Account"入口
- 解决：点底部"Login with Main/Sub Account"链接，看是否有单独的主账号/子账号输入表单

**情况C：OTP验证码** → 页面要求输入短信验证码。
- **必须暂停，报告用户需要输入验证码**
- 不要自动尝试猜测或绕过
- 用 `interaction.request_action` 请用户接管输入OTP

### Step 6：验证登录成功

```javascript
const url = page.url();
const isLoggedIn = url.includes("seller.shopee.co.th") && !url.includes("login");
// 再导航到订单页确认
await page.goto("https://seller.shopee.co.th/order/details", { waitUntil: "domcontentloaded" });
await new Promise(r => setTimeout(r, 5000));
```

## 坑速查表

| 坑 | 解决方案 |
|---|---|
| 首次加载弹语言选择modal | 先点English关闭，等页面重新加载 |
| 第一个submit按钮是空的 | 找文字为"LOG IN"的那个按钮，不是第一个 |
| JS .click()不触发React事件 | 用 page.mouse.click() 坐标点击 |
| 主从账号格式YSGX001N:main | 普通表单登录失败就走底部"Login with Main/Sub Account"入口 |
| OTP验证码 | 必须人工输入，暂停等用户 |
| 登录页是泰文 | 先切English，否则按钮文字乱码不好定位 |
| 页面加载慢 | 语言切换后等8秒，登录后等10秒 |

## 红线

1. **OTP必须人工输入**：验证码是短信发到手机的，不要尝试自动获取或绕过
2. **密码不写入日志**：账号密码只在JS里使用，不输出到result
3. **登录失败3次停**：不要反复重试触发风控，报告用户人工处理
4. **登录成功后保留页面**：finish task时keep=true，不要关掉卖家中心页面
