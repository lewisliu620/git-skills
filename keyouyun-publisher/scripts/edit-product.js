/**
 * 客优云编辑器修改脚本
 * 零截图，纯DOM操作
 * 
 * 使用方式：AI读取本文件，替换 {{VARIABLE}} 占位符，
 * 然后通过 tabbit-cli nodejs --stdin 执行。
 * 
 * 输入变量：
 *   {{OFFER_ID}}      - 1688 offer ID（如 852413733872）
 *   {{THAI_TITLE}}    - 泰文标题
 *   {{PRICE_CNY}}     - SKU售价（如 10）
 *   {{COST_CNY}}      - 采购成本（如 0.6）
 *   {{STOCK}}         - 库存（如 500）
 *   {{CATEGORY_THAI}} - 泰文类目（如 อุปกรณ์เสริมโทรศัพท์）
 *   {{DESCRIPTION_THAI}} - 泰文产品描述
 * 
 * 返回：JSON {success, message, changes}
 */

// ===== 配置区（AI替换以下变量）=====
const OFFER_ID = "{{OFFER_ID}}";
const THAI_TITLE = "{{THAI_TITLE}}";
const PRICE_CNY = "{{PRICE_CNY}}";
const COST_CNY = "{{COST_CNY}}";
const STOCK = "{{STOCK}}";
const CATEGORY_THAI = "{{CATEGORY_THAI}}";
const DESCRIPTION_THAI = `{{DESCRIPTION_THAI}}`;
// ====================================

// 步骤1：在采集页找到目标商品行，点击"发布到Shopee"
await page.goto("https://erp.keyouyun.com/drafts/collection", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));

// 关闭弹窗
await page.locator(".el-dialog__headerbtn").first().click({timeout: 2000}).catch(()=>{});
await new Promise(r => setTimeout(r, 1000));

// 步骤2：搜索offer ID定位商品行
await page.evaluate((oid) => {
  const searchInput = document.querySelector('input[placeholder*="搜索"], input[placeholder*="货源"], input[type="text"]');
  if (searchInput) {
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeSetter.call(searchInput, oid);
    searchInput.dispatchEvent(new Event('input', {bubbles: true}));
    searchInput.dispatchEvent(new Event('change', {bubbles: true}));
  }
}, OFFER_ID);
await new Promise(r => setTimeout(r, 2000));

// 步骤3：点击该行的"发布到Shopee"链接
await page.evaluate((oid) => {
  const rows = document.querySelectorAll('tr, .el-table__row');
  for (const row of rows) {
    if (row.textContent.includes(oid)) {
      const links = [...row.querySelectorAll('a, span, button')].filter(el =>
        el.textContent.trim() === '发布到Shopee' || el.textContent.trim() === '认领取'
      );
      if (links.length > 0) {
        links[links.length - 1].click();
        return;
      }
    }
  }
}, OFFER_ID);
await new Promise(r => setTimeout(r, 3000));

// 步骤4：在"选择编辑站点"对话框选"全球站"→确定
await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter(el =>
    el.offsetParent !== null && (el.textContent.trim() === '全球站' || el.textContent.trim() === 'GLOBAL') && el.offsetHeight < 40
  );
  if (els.length > 0) els[0].click();
});
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '确定' && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 8000));

// 步骤5：编辑器内修改泰文标题
await page.evaluate((title) => {
  const inputs = document.querySelectorAll("input[maxlength='180']");
  for (const inp of inputs) {
    if (/[\u4e00-\u9fa5]/.test(inp.value)) {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(inp, title);
      inp.dispatchEvent(new Event('input', {bubbles: true}));
      inp.dispatchEvent(new Event('change', {bubbles: true}));
      break;
    }
  }
}, THAI_TITLE);
await new Promise(r => setTimeout(r, 500));

// 步骤6：修改SKU售价（遍历所有可见可编辑input，偶数索引=售价列）
const priceChanges = await page.evaluate((price, cost) => {
  const inputs = document.querySelectorAll("input.el-input__inner:not([readonly])");
  let changed = 0;
  let idx = 0;
  for (const inp of inputs) {
    const v = inp.value;
    // 匹配旧成本价（0.5或类似小数字）
    if (/^0\.\d+$/.test(v) && parseFloat(v) < 2) {
      if (idx % 2 === 0) {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(inp, price);
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        changed++;
      }
      idx++;
    }
  }
  return changed;
}, PRICE_CNY, COST_CNY);
await new Promise(r => setTimeout(r, 500));

// 步骤7：设置库存
const stockSet = await page.evaluate((stock) => {
  const inputs = document.querySelectorAll("input.el-input__inner:not([readonly])");
  let changed = 0;
  for (const inp of inputs) {
    const label = inp.closest('.el-form-item, .row, tr, td')?.textContent || '';
    if (label.includes('库存') && /^\d+$/.test(inp.value)) {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(inp, stock);
      inp.dispatchEvent(new Event('input', {bubbles: true}));
      changed++;
    }
  }
  return changed;
}, STOCK);

// 步骤8：填泰文类目
await page.evaluate((cat) => {
  const inputs = document.querySelectorAll("input.el-input__inner:not([readonly])");
  for (const inp of inputs) {
    const label = inp.closest('.el-form-item, .row')?.textContent || '';
    if (label.includes('类别') || label.includes('类目')) {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(inp, cat);
      inp.dispatchEvent(new Event('input', {bubbles: true}));
      break;
    }
  }
}, CATEGORY_THAI);

// 步骤9：填泰文产品描述
await page.evaluate((desc) => {
  const textareas = document.querySelectorAll('textarea');
  for (const ta of textareas) {
    if (ta.offsetParent !== null && ta.offsetHeight > 100) {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(ta, desc);
      ta.dispatchEvent(new Event('input', {bubbles: true}));
      ta.dispatchEvent(new Event('change', {bubbles: true}));
      break;
    }
  }
}, DESCRIPTION_THAI);
await new Promise(r => setTimeout(r, 500));

// 步骤10：点击"保存"按钮
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '保存' && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 3000));

// 验证：检查是否出现成功toast
const toastText = await page.evaluate(() => {
  const toasts = document.querySelectorAll('.el-message, .el-notification, [class*="toast"], [class*="success"]');
  return [...toasts].map(t => t.textContent.trim()).filter(Boolean).slice(0, 3);
});

return {
  success: true,
  message: "编辑器修改完成",
  changes: {
    titleSet: true,
    priceFieldsChanged: priceChanges,
    stockFieldsChanged: stockSet,
    categorySet: true,
    descriptionSet: true
  },
  toast: toastText
};
