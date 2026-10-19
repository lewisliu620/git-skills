# 微信表情开放平台发布 SOP（浏览器协助，已验证跑通）

前置事实：**业界无 tabbit 表情发布 CLI**（"Tabbit"实为美团推出的 AI 原生浏览器，与表情发布无关）；微信表情开放平台无官方 CLI/API，投稿仅支持网页后台手动提交。发布必须走 `browser-use-automation`（computer_use_tool plane="bu"），登录与最终提交由用户亲自完成。

## 流程

1. **打开投稿后台**：`https://sticker.weixin.qq.com/cgi-bin/mmemoticonwebnode-bin/pages/stickerPage/detail`。
2. **登录交接**：点登录出现微信扫码弹窗 → `interaction.request_action`（type=browserControl）交用户扫码 → 重新快照确认已登录。
3. **选静态表情**：JS 点击 `input[type=radio][value="true"]`。
4. **批量上传 16 主图**：`bu.upload_file('input[type=file][name="file"][accept="image/png,image/jpeg,image/jpg,image/gif"]', [paths])`；页面自动生成缩略图并出现 16 行含义词输入框。
5. **上传横幅/封面/图标**：分别对 `style*="width: 167px"` / `96px` / `56px` 的 `.uploader__new input`。
6. **填含义词**：16 个 input 按顺序填（值必须与 process.py 的 CAPTIONS 一致，不得重复）。
7. **填文本**：名称（≤8 字）、介绍（≤80 字）、版权（≤10 字）；开启赞赏后补引导语（≥5 字）。
8. **选字段**：类型=卡通表情/其他（radio value="1"）、主题=工作/职场、下载地区=全球（value="DEF"）；风格勾选 2 项（日常/软萌可爱）；角色/内容下拉 → 宠物/动物角色 → 猫。
9. **勾选接受赞赏**：JS label click。若弹"艺术家信息未添加完整"→ 先去艺术家资料页（见下）补全再回来勾选（返回后表单不保留草稿，需重新走 3–8）。
10. **上传赞赏图**（勾选后出现）：引导图 → `style*="width: 128px"` 的 input；致谢图 → `style*="width: 96px"` 且 accept 含 gif 的 input（勿与封面混淆）。
11. **保存**：点「保存」按钮（页面停留、字段保留即成功）。
12. **提交交接**：展示完整表单摘要 → `interaction.request_action` 交用户核对并点击「提交」→ 核对跳转 `/home?t=stiker/result` 出现"表情提交成功，请耐心等待审核"。

## 艺术家资料页（开启赞赏前提）

- 入口：提交表单里接受赞赏被拦截时跳转，或直接访问 `/cgi-bin/mmemoticon-bin/userpage`。
- 头像 **必须 640×640**（可用封面图 LANCZOS 放大生成）；主页横幅 ≤80KB；名称 + 介绍 50–80 字。
- 提交按钮激活机制：需 bannerUrl/studioName/headUrl/desc 四项校验全部通过（btn_disabled → btn_primary）。上传成功会把 FileId 写入 `#headUrl`/`#bannerUrl` 的 value；填完文本后用 `$('#studioName').trigger('keyup'); $('#desc').trigger('keyup'); $('#studioName').trigger('change'); $('#desc').trigger('change')` 刷新校验再点提交。
- 提交后跳转 userpage，提示"信息已提交，将和你提交的表情一起审核"。

## 表单返回丢失

表情专辑表单**不保留草稿**：离开再返回需重新执行 3–10 全流程（可用同一脚本顺序重跑）。

## 发布后

- 审核周期约 1–7 个工作日；期间可在「我的作品」修改/撤回。
- 结果归档：更新方案文档第 8 章「待办」（平台上传标记已完成），新增「发布记录」小节（提交结果、投稿内容、平台字段、艺术家资料、机制备忘）。
