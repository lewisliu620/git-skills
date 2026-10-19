# 飞书文档插入图片操作手册

> 怎么把图片插在正文中间，不是堆在末尾？

## 目录

- 核心原理：为什么media-insert只能插末尾
- 完整操作流程：插入→找位置→移动，3步
- 批量插入多张图：必须串行不能并发
- 常见坑：5个容易踩的坑
- 快速验证：怎么确认图插对位置了

---

## 核心原理

`docs +media-insert` 只能在**文档末尾**插入图片。
要把图片移到中间位置，分两步：
1. 先media-insert插到末尾
2. 再用`docs +update --command block_move_after`移到目标位置

---

## 完整操作流程

### Step 1：先把图片插到文档末尾

```bash
lark-cli docs +media-insert --doc "<doc_id>" --file "<图片路径>" --align center --caption "<图注>" --as user
```

**参数说明**：
- `--doc`：飞书文档token或URL
- `--file`：本地图片路径
- `--align center`：居中对齐
- `--caption`：图片下面的说明文字

**返回结果**：会返回插入的图片block_id，记下来。

---

### Step 2：找到目标位置的block_id

你要把图插在哪个章节标题后面，就找那个标题的block_id：

```bash
lark-cli docs +fetch --doc "<doc_id>" --detail with-ids --scope keyword --keyword "<章节标题关键词>" --as user
```

**例子**：找"大模型到底在干嘛"这个标题的block_id：
```bash
lark-cli docs +fetch --doc "Tg1FdR2XHo8qFYxA9JycneU3nhg" --detail with-ids --scope keyword --keyword "大模型到底在干嘛" --as user
```

在返回结果里找`<h2 id="...">`，那个id就是标题的block_id。

---

### Step 3：把图片移到目标位置

```bash
lark-cli docs +update --doc "<doc_id>" --command block_move_after --block-id "<目标标题block_id>" --src-block-ids "<图片block_id>" --as user
```

**参数说明**：
- `--block-id`：你要把图插在哪个block后面（目标标题）
- `--src-block-ids`：要移动的图片block_id（源block）

**例子**：
```bash
lark-cli docs +update --doc "Tg1FdR2XHo8qFYxA9JycneU3nhg" --command block_move_after --block-id "doxcnUPJCmg2AFsKi5o3DjYefkL" --src-block-ids "doxcnOLQeDCofiY1Iyy3g61A2Hg" --as user
```

---

## 批量插入多张图

### 顺序很重要
1. 先把所有图片都插到文档末尾（按顺序插）
2. 然后逐个找到目标位置，逐个移动
3. **批量插入必须串行，不能并发**——同一个文档同时插多张会冲突

### 正确顺序
```bash
# 第一张图插末尾
lark-cli docs +media-insert --doc xxx --file 图1.png --as user

# 第二张图插末尾（等第一张完成再执行）
lark-cli docs +media-insert --doc xxx --file 图2.png --as user

# 第三张图插末尾
lark-cli docs +media-insert --doc xxx --file 图3.png --as user

# 然后逐个移动到对应位置
lark-cli docs +update --doc xxx --command block_move_after --block-id 标题1 --src-block-ids 图1 --as user
lark-cli docs +update --doc xxx --command block_move_after --block-id 标题2 --src-block-ids 图2 --as user
lark-cli docs +update --doc xxx --command block_move_after --block-id 标题3 --src-block-ids 图3 --as user
```

---

## 常见坑

1. **图都堆在末尾**——就是因为没做第三步block_move_after
2. **找不到block_id**——用`docs +fetch --detail with-ids --scope keyword`搜
3. **移动失败**——检查src-block-ids是不是图片的block_id，不是别的
4. **批量插入冲突**——一定要串行，等上一张插完再插下一张
5. **图插错位置了**——再fetch一下看最新的block_id，重新移动

---

## 快速验证

插完图后，fetch一下文档，看图是不是在对应章节旁边：
```bash
lark-cli docs +fetch --doc "<doc_id>" --as user
```

看返回的内容里，图片是不是在对应标题后面，而不是全在末尾。
