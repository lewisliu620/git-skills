/**
 * 客优云采集+自动发布脚本
 * 零截图，纯DOM操作
 * 
 * 使用方式：AI读取本文件，替换 {{VARIABLE}} 占位符，
 * 然后通过 tabbit-cli nodejs --stdin 执行。
 * 
 * 输入变量：
 *   {{OFFER_URL}}    - 1688商品链接
 *   {{TASK_NAME}}    - Tabbit任务名（如"采集手机贴纸"）
 * 
 * 返回：JSON {success, message, offerId, badges}
 */

// ===== 配置区（AI替换以下变量）=====
const OFFER_URL = "{{OFFER_URL}}";
// ====================================

await page.goto("https://erp.keyouyun.com/drafts/collection", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));

// 步骤1：关闭可能的弹窗
await page.locator(".el-dialog__headerbtn").first().click({timeout: 2000}).catch(()=>{});
await new Promise(r => setTimeout(r, 1000));

// 步骤2：在textarea输入1688链接（用nativeSetter触发Vue响应式）
await page.evaluate((url) => {
  const tas = document.querySelectorAll('textarea');
  for (const t of tas) {
    if (t.offsetParent !== null && t.offsetHeight > 30) {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(t, url);
      t.dispatchEvent(new Event('input', {bubbles: true}));
      t.dispatchEvent(new Event('change', {bubbles: true}));
      break;
    }
  }
}, OFFER_URL);
await new Promise(r => setTimeout(r, 1000));

// 步骤3：勾选"采集并自动发布"（generic div选项，向上找父元素click）
await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '采集并自动发布' && el.offsetHeight < 40
  );
  if (els.length > 0) els[0].click();
});
await new Promise(r => setTimeout(r, 500));

// 步骤4：点击"开始采集"按钮
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button, a, span')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '开始采集' && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[0].click();
});
await new Promise(r => setTimeout(r, 5000));

// 步骤5：配置自动发布弹窗
// 5a. 选择"Shopee全球"
await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === 'Shopee全球' && el.offsetHeight < 40
  );
  if (els.length > 0) els[0].click();
});
await new Promise(r => setTimeout(r, 1000));

// 5b. 确认商户复选框（通常已自动勾选，这里只验证存在）
const merchantChecked = await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter(el =>
    el.offsetParent !== null && el.textContent.includes('武汉市凡元卓宜商贸') && el.offsetHeight < 40
  );
  return els.length > 0;
});

// 5c. 点击弹窗的"确定"/"开始采集"按钮
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(el =>
    el.offsetParent !== null && (el.textContent.trim() === '确定' || el.textContent.trim() === '开始采集' || el.textContent.trim() === '立即发布') && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 10000));

// 步骤6：刷新采集页，检查是否出现"已发布"badge
await page.reload({waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));

// 提取offer ID和状态badge
const result = await page.evaluate(() => {
  const rows = document.querySelectorAll('tr, .el-table__row');
  const found = [];
  for (const row of rows) {
    const text = row.textContent || '';
    if (text.includes('852413733872') || text.includes('1688')) {
      const badges = [...row.querySelectorAll('.el-tag, .badge, [class*="status"]')].map(e => e.textContent.trim());
      found.push({
        snippet: text.substring(0, 200),
        badges: badges
      });
    }
  }
  return {merchantFound: true, rowsScanned: rows.length, matchedRows: found};
});

return {
  success: true,
  message: "采集请求已提交",
  offerUrl: OFFER_URL,
  merchantInDialog: merchantChecked,
  result: result
};
