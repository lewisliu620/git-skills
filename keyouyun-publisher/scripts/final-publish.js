/**
 * 客优云最终发布脚本
 * 零截图，纯DOM操作
 * 
 * 使用方式：AI读取本文件，替换 {{VARIABLE}} 占位符，
 * 然后通过 tabbit-cli nodejs --stdin 执行。
 * 
 * 输入变量：
 *   {{OFFER_ID}} - 1688 offer ID
 * 
 * 返回：JSON {success, message, badges}
 */

// ===== 配置区 =====
const OFFER_ID = "{{OFFER_ID}}";
// ==================

// 步骤1：在编辑器中点右下角蓝色"发布"按钮
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button, a')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '发布' && el.offsetHeight < 50
  );
  // 取最后一个（右下角的发布按钮，不是左侧的导航链接）
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 5000));

// 步骤2：在发布确认弹窗中确认配置
// 2a. 平台应该已经是Shopee全球（之前选过）
// 2b. 商户应该已勾选
// 2c. 点弹窗最后的"发布"或"确定"按钮
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(el =>
    el.offsetParent !== null && (el.textContent.trim() === '发布' || el.textContent.trim() === '确定' || el.textContent.trim() === '立即发布') && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 10000));

// 步骤3：检查绿色成功toast
const toastText = await page.evaluate(() => {
  const toasts = document.querySelectorAll('.el-message, [class*="success"], [class*="toast"]');
  return [...toasts].map(t => t.textContent.trim()).filter(Boolean).slice(0, 5);
});

// 步骤4：关闭编辑器，回到采集页验证"已发布"badge
await page.goto("https://erp.keyouyun.com/drafts/collection", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));

// 搜索offer ID
await page.evaluate((oid) => {
  const searchInput = document.querySelector('input[placeholder*="搜索"], input[type="text"]');
  if (searchInput) {
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeSetter.call(searchInput, oid);
    searchInput.dispatchEvent(new Event('input', {bubbles: true}));
  }
}, OFFER_ID);
await new Promise(r => setTimeout(r, 3000));

// 读取该行badge
const badges = await page.evaluate((oid) => {
  const rows = document.querySelectorAll('tr, .el-table__row');
  for (const row of rows) {
    if (row.textContent.includes(oid)) {
      const tags = [...row.querySelectorAll('.el-tag, .badge, [class*="status"], span')].map(e => e.textContent.trim()).filter(t => t.length > 0 && t.length < 20);
      return tags;
    }
  }
  return [];
}, OFFER_ID);

const published = badges.some(b => b.includes('已发布') || b.includes('发布成功'));

return {
  success: published,
  message: published ? "发布成功，商品已提交到Shopee" : "发布请求已提交，等待验证",
  offerId: OFFER_ID,
  toast: toastText,
  badges: badges
};
