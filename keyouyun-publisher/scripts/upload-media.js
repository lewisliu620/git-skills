/**
 * 客优云编辑器上传图片+视频脚本
 * 零截图，纯DOM操作
 * 
 * 使用方式：AI读取本文件，替换 {{VARIABLE}} 占位符，
 * 然后通过 tabbit-cli nodejs --stdin 执行。
 * 
 * 输入变量：
 *   {{OFFER_ID}}       - 1688 offer ID
 *   {{IMAGE_PATHS}}    - 本地图片路径数组JSON（如 ["C:/img1.jpg","C:/img2.jpg"]）
 *   {{VIDEO_PATH}}     - 本地视频路径（如 "C:/video.mp4"）
 * 
 * 返回：JSON {success, message, imagesUploaded, videoUploaded}
 */

// ===== 配置区（AI替换以下变量）=====
const OFFER_ID = "{{OFFER_ID}}";
const IMAGE_PATHS = {{IMAGE_PATHS}};
const VIDEO_PATH = "{{VIDEO_PATH}}";
// ====================================

// 步骤1：打开商品编辑器（同edit-product步骤1-4）
await page.goto("https://erp.keyouyun.com/drafts/collection", {waitUntil: "domcontentloaded"});
await new Promise(r => setTimeout(r, 5000));
await page.locator(".el-dialog__headerbtn").first().click({timeout: 2000}).catch(()=>{});
await new Promise(r => setTimeout(r, 1000));

// 搜索offer ID
await page.evaluate((oid) => {
  const searchInput = document.querySelector('input[placeholder*="搜索"], input[type="text"]');
  if (searchInput) {
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeSetter.call(searchInput, oid);
    searchInput.dispatchEvent(new Event('input', {bubbles: true}));
  }
}, OFFER_ID);
await new Promise(r => setTimeout(r, 2000));

// 点击"发布到Shopee"
await page.evaluate((oid) => {
  const rows = document.querySelectorAll('tr, .el-table__row');
  for (const row of rows) {
    if (row.textContent.includes(oid)) {
      const links = [...row.querySelectorAll('a, span, button')].filter(el =>
        el.textContent.trim() === '发布到Shopee'
      );
      if (links.length > 0) { links[0].click(); return; }
    }
  }
}, OFFER_ID);
await new Promise(r => setTimeout(r, 3000));

// 选全球站→确定
await page.evaluate(() => {
  const els = [...document.querySelectorAll('*')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '全球站' && el.offsetHeight < 40
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

// 步骤2：先清空原有图片
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button, a, span')].filter(el =>
    el.offsetParent !== null && el.textContent.includes('清空所有图片') && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[0].click();
});
await new Promise(r => setTimeout(r, 2000));

// 确认清空弹窗
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(el =>
    el.offsetParent !== null && (el.textContent.trim() === '确定' || el.textContent.trim() === '是') && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 2000));

// 步骤3：上传本地图片（通过下拉菜单→本地上传→filechooser）
let imagesUploaded = 0;
for (const imgPath of IMAGE_PATHS) {
  try {
    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser", {timeout: 5000}),
      page.evaluate(() => {
        const els = [...document.querySelectorAll('*')].filter(el =>
          el.offsetParent !== null && el.textContent.trim() === '选取图片' && el.offsetHeight < 40
        );
        if (els.length > 0) els[0].click();
      })
    ]);
    await new Promise(r => setTimeout(r, 1000));
    await page.evaluate(() => {
      const els = [...document.querySelectorAll('*')].filter(el =>
        el.offsetParent !== null && el.textContent.trim() === '本地上传' && el.offsetHeight < 40
      );
      if (els.length > 0) els[0].click();
    });
    await chooser.setFiles(imgPath);
    imagesUploaded++;
    await new Promise(r => setTimeout(r, 2000));
  } catch(e) {
    // filechooser失败，继续下一张
  }
}

// 步骤4：上传本地视频
let videoUploaded = false;
if (VIDEO_PATH) {
  try {
    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser", {timeout: 5000}),
      page.evaluate(() => {
        // 点击视频区域的"+"号
        const plusBtns = [...document.querySelectorAll('*')].filter(el =>
          el.offsetParent !== null && el.textContent.trim() === '+' && el.offsetHeight < 50
        );
        if (plusBtns.length > 0) plusBtns[plusBtns.length - 1].click();
      })
    ]);
    await new Promise(r => setTimeout(r, 1000));
    await page.evaluate(() => {
      const els = [...document.querySelectorAll('*')].filter(el =>
        el.offsetParent !== null && el.textContent.trim() === '本地上传' && el.offsetHeight < 40
      );
      if (els.length > 0) els[0].click();
    });
    await chooser.setFiles(VIDEO_PATH);
    videoUploaded = true;
    await new Promise(r => setTimeout(r, 3000));
  } catch(e) {
    // 视频上传失败
  }
}

// 步骤5：点保存
await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')].filter(el =>
    el.offsetParent !== null && el.textContent.trim() === '保存' && el.offsetHeight < 40
  );
  if (btns.length > 0) btns[btns.length - 1].click();
});
await new Promise(r => setTimeout(r, 3000));

const toastText = await page.evaluate(() => {
  const toasts = document.querySelectorAll('.el-message, [class*="success"]');
  return [...toasts].map(t => t.textContent.trim()).filter(Boolean).slice(0, 3);
});

return {
  success: true,
  message: "素材上传完成",
  imagesUploaded: imagesUploaded,
  videoUploaded: videoUploaded,
  toast: toastText
};
