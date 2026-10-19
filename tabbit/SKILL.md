---
name: tabbit
description: Use for browser navigation, inspection, interaction, and visual verification through Tabbit's installed CLI.
---

# Tabbit Browser

`tabbit-cli` lets you send Playwright code to tabs you control in Tabbit Browser
to carry out browsing tasks.

## Connect and discover

Use the installed stable launcher; call it `<launcher>` below:

- POSIX: `"$HOME/.local/bin/tabbit-cli"`
- Windows PowerShell: `& "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"`
- Windows CMD: `"%LOCALAPPDATA%\Tabbit\LocalAgent\bin\tabbit-cli.exe"`

The launcher selects the browser instance, launching it when necessary. Never
invoke a CLI inside an application bundle or versioned runtime directory, read
`endpoint.json`, or start the Browser-owned Runtime Service directly.
For an explicitly requested product or instance, follow
[instance selection](references/recovery.md#explicit-product-or-instance-selection)
before the first command; keep it pinned through `finish`, then restore the
previous override.

**The task name becomes the visible title of its tab group.** Choose a short,
human-readable name such as `"Update profile"` or `"Compare laptop prices"`,
quote it, and reuse it for every call in that task, including `finish`. Avoid
opaque IDs or timestamps as task names. All tabs owned by the task share one
group. Resuming an existing group initially preserves its title; creating a new
tab can rename it to the task name. For this workflow:

| Value | Purpose |
| --- | --- |
| `Update profile` | Task name reused in commands and visible title of a newly formed task group. |
| Observed group ID | Identity used by `--group` when resuming; never substitute the title. |

Normal workflow: choose a task name → open or acquire the intended tabs → observe
→ act and verify → read results or files → close scratch tabs → `finish`.
The examples below use illustrative IDs, labels, and URLs; replace them with the
user's destination and observed evidence. The main skill covers this workflow;
references provide additional options and exceptional recovery procedures.

| Starting point | First action |
| --- | --- |
| Existing user tab or retained group | `create --task NAME`, inspect inventory, then `nodejs --tab ID` or `--group ID`. |
| Known new destination | Run `nodejs` without selectors and navigate its provided `page` with `page.goto(url)`. |
| Continuing this task | Reuse its name and current `page`; `usePage(otherPage)` selects another owned page. |
| Availability or runtime diagnostics | Run `diagnose`; add `--task NAME` for task-specific limits and ownership. |

### Open a known new destination

Run `nodejs` directly; it creates the task and supplies its initial page. Navigate
that page instead of opening an unnecessary extra tab:

```bash
tabbit_cli="$HOME/.local/bin/tabbit-cli"
"$tabbit_cli" nodejs --task "Read example" --request-id open-example <<'JS'
await page.goto("https://example.com/", {waitUntil: "domcontentloaded"});
return await tabbit.observe({frames: "none", maxChars: 4000});
JS
```

Reuse `"Read example"` for subsequent calls and finish it when the reading is done.
Use `context.newPage()` for additional tabs, not for replacing the initial page.

### Complete workflow on an existing user tab

`create` creates or reuses a task and returns inventory without opening or
acquiring tabs. First inspect that inventory:

```bash
tabbit_cli="$HOME/.local/bin/tabbit-cli"
"$tabbit_cli" create --task "Update profile"
```

An illustrative inventory excerpt:

```json
{"currentTabId":17,"focusedWindowId":3,"tabs":[{"tabId":17,"windowId":3,"title":"Profile","url":"https://app.example.test/profile","state":"available","group":null}],"truncated":false}
```

Acquire the tab selected from that inventory and inspect its controls:

```bash
"$tabbit_cli" nodejs --task "Update profile" --tab 17 --request-id inspect-profile <<'JS'
return await tabbit.observe({frames: "none", maxChars: 4000});
JS
```

Suppose inspection of the profile tab showed these controls, and the user asked
to change their display name to Alex:

```text
- textbox "Display name" [ref=e2]: Robin
- button "Save" [ref=e3]
```

Continue on the same task and page with a new request ID. This application shows
“Saved” and restores the persisted name on reload:

```bash
"$tabbit_cli" nodejs --task "Update profile" --request-id save-profile <<'JS'
const name = page.getByRole("textbox", {name: "Display name", exact: true});
await name.fill("Alex");
await page.getByRole("button", {name: "Save", exact: true}).click();
await expect(page.getByRole("status")).toHaveText("Saved");
await page.reload({waitUntil: "domcontentloaded"});
await expect(name).toHaveValue("Alex");
return {persistedName: await name.inputValue()};
JS
```

The successful value is in `result.value`:

```json
{"status":"succeeded","result":{"requestId":"save-profile","value":{"persistedName":"Alex"}}}
```

Finish using the same task name to release ownership and retain the user's tab:

```bash
"$tabbit_cli" finish --task "Update profile"
```

```json
{"finished":true,"keep":true,"forcedCleanup":false,"closedTabIds":[]}
```

After that response, report “Display name changed to Alex; the profile tab is
retained.” This completes the workflow. If a command is pending or failed, resolve
its outcome before finishing; do not blindly run the next command.

Adapt verification to the application; an unsaved field value alone does
not prove persistence. When the user requested only a draft, fill and verify it
without submitting, then retain the page for their review. When saving or
submitting is already authorized, continue without adding an approval step.

### Windows multiline invocation

On Windows PowerShell, create the task and inspect its inventory, then use a UTF-8
temporary file and CMD redirection for JavaScript stdin so PowerShell does not
rewrite the program. Do not pipe a here-string or use `echo` or a console PTY.
Write multiline code to the file with UTF-8 encoding without a BOM:

```powershell
$tabbitCli = "$env:LOCALAPPDATA\Tabbit\LocalAgent\bin\tabbit-cli.exe"
& $tabbitCli create --task "Update profile"
# Replace 17 below with the selected inventory tab ID.
$program = [IO.Path]::GetTempFileName()
$code = @'
return await tabbit.observe({frames: "none", maxChars: 4000});
'@
try {
  [IO.File]::WriteAllText($program, $code, [Text.UTF8Encoding]::new($false))
  cmd.exe /d /c "`"$tabbitCli`" nodejs --task `"Update profile`" --tab 17 --request-id inspect-profile < `"$program`""
} finally {
  Remove-Item $program -ErrorAction SilentlyContinue
}
```

## Own the right tabs

For “this tab,” use inventory's `currentTabId` when present; otherwise match the
requested title and URL. `currentTabId` and `focusedWindowId` are null when no
eligible browser window is focused; per-window `active` flags remain available.
Ownership is relative to this task: `available` means unowned, `owned` means this
task owns it, and `claimed` means another task owns it.

Repeat `--tab` to acquire multiple tabs in one window; do not combine it with
`--group`. Group acquisition takes every current member or fails, preserving its
ID and initially its title. Creating another tab can rename the group to the task
name. `page` becomes the first requested tab, or the first group member in
tab-strip order, even when reusing a task.

Only owned tabs appear in `pages()` and `context.pages()`. Inventory tab IDs differ
from runtime page labels. If inventory is truncated, continue with
`tabs --task NAME --cursor TOKEN`, using its `nextCursor` and the same filters and
limit. Do not infer missing tabs or whole-group counts from a partial page.

To resume a retained group, use its observed ID. This example selects the Profile
page among the group's owned pages and keeps it current for the next call:

```bash
"$tabbit_cli" nodejs --task "Update profile" --group 0123456789ABCDEF0123456789ABCDEF --request-id inspect-group <<'JS'
const matches = pages().filter(p => p.url() === "https://app.example.test/profile");
assert.equal(matches.length, 1);
usePage(matches[0]);
return await tabbit.observe({frames: "none", maxChars: 4000});
JS
```

Do not rely on Back/Forward to preserve page state: task-owned tabs have BFCache
disabled. If you will need the current page's state later (for example, an unsaved
form or loaded search results), keep it open and use `context.newPage()` for the
next destination. Reuse the current tab when its state is no longer needed.

Use `usePage(otherPage)` to change the task's current page without bringing the
browser to the foreground. For acquisition failures or inventory details, see
[inventory and acquisition](references/recovery.md#inventory-and-acquisition).

## Submit coherent programs

```text
<launcher> nodejs --task NAME --request-id ID [--tab ID... | --group ID] [--timeout-ms MS]
```

Use a new request ID for each new program. Reusing an ID returns the original
receipt without running code. IDs contain 1–128 ASCII letters, digits, `.`, `_`,
or `-`, starting with a letter or digit.

Programs default to 60 seconds; `--timeout-ms` accepts 60,000–180,000 ms. Allow time
for the entire sequence. Native Playwright operations default to 30 seconds;
their timeout options, including `timeout: 0`, never extend the program deadline.

Programs support top-level `await` and `return`. Lexical variables reset between
calls; use `globalThis` for intentional task state. Globals include `assert`,
`expect`, `browser`, `context`, `page`, `pages()`, `usePage(page)`,
`artifactPath(name)`, `reportIssue(code)`, and `tabbit`. Return bounded JSON-safe
data, not Page objects, locators, or handles. `document` and `window` are available
inside page evaluation callbacks; pass Node values as arguments because those
callbacks do not capture surrounding variables.

Unless a shell command is shown, JavaScript examples below are the contents of
a `nodejs` program: send them through stdin on the intended task, using a new
request ID for each call. Reuse the current page unless the example selects one.

Batch navigation, extraction, and verification when the next steps are known;
return when new evidence requires judgment. Keep mutations to one business object
sequential. Start with the single-page and paginated workflows below; use
concurrency when the sources are already known and independent.

Use `expect(...).toEqual(...)` for structural comparisons of returned data:

```js
const actual = await page.evaluate(() => ({items: [1, 2, 3]}));
expect(actual).toEqual({items: [1, 2, 3]});
```

`assert` is Node’s strict assertion module. Its `deepEqual` checks prototypes,
so equal objects from browser APIs can fail against literals in the program’s
separate JavaScript realm.

## Observe and act

| Need | Surface |
| --- | --- |
| Known control | Native semantic locators and actions. |
| Unknown accessible structure | `tabbit.observe({frames: "none", maxChars: 4000})`. |
| Known data or aggregation | Bounded `page.evaluate()` or `locator.evaluateAll()`. |
| Cross-frame structure | `tabbit.observe({maxChars: 6000})`; see [frames](references/advanced-operations.md#frames-and-observation). |
| Layout or canvas | Return `await page.screenshot({fullPage: false})`, then open `result.nextAction.path` with the host image viewer. |

For screenshots, use the returned path; a requested path is only a naming hint.
Observe before choosing unfamiliar targets; use actual labels or fresh snapshot
refs. `observe` bounds snapshot characters, not total response bytes. Check its
truncation flags and narrow the observation when needed. Resource paging cannot
recover text already truncated by observation. ARIA snapshot `depth` limits
nesting, not output size.

Use `fill` for field replacement and `pressSequentially` when individual key
events matter. Wait for relevant application state with native locator, `expect`,
or `waitForFunction` waits. Verify application-visible state after mutations;
a dispatch receipt alone does not prove success or persistence.

### Fill and verify common controls

Other common controls use native Playwright methods. These examples assume the
labels were observed and the edits are authorized:

```js
await page.getByLabel("Email", {exact: true}).fill("alex@example.com");
await page.getByRole("combobox", {name: "Country", exact: true})
  .selectOption({label: "Canada"});
await page.getByRole("checkbox", {name: "Email updates", exact: true}).check();
await expect(page.getByLabel("Email", {exact: true})).toHaveValue("alex@example.com");
await expect(page.getByRole("combobox", {name: "Country", exact: true})).toHaveValue("CA");
await expect(page.getByRole("checkbox", {name: "Email updates", exact: true})).toBeChecked();
return {filled: true, submitted: false};
```

Use `hover()` for an observed hover control. Native clicks already scroll their
targets into view; use `scrollIntoViewIfNeeded()` when inspecting off-screen content.

### Search and wait for the new results

Inspection found a searchbox named Search. This application updates a heading
with the submitted query once its result list is ready. Wait for that query-specific
state so an old result list is not mistaken for the new one:

```js
const search = page.getByRole("searchbox", {name: "Search", exact: true});
await search.fill("release notes");
await search.press("Enter");
await expect(page.getByRole("heading", {
  name: 'Search results for "release notes"', exact: true,
})).toBeVisible();
return await tabbit.observe({frames: "none", maxChars: 4000});
```

Use the resulting observation to choose links or extract fields. For another
site, replace the heading with its observed signal that the new data is ready;
URL change or a permanently visible “Results” heading alone may be insufficient.

### Read structured page data

Use observed markup and pass values into the browser callback. This example
returns a bounded, deduplicated sample, not a claim of complete coverage:

```js
return await page.locator("main a[href]").evaluateAll((links, {limit}) => {
  const items = [...new Map(links.map(a => [a.href, {
    title: (a.textContent || "").trim(), url: a.href,
  }])).values()];
  return {items: items.slice(0, limit), totalOnPage: items.length,
    truncated: items.length > limit};
}, {limit: 20});
```

### Switch pages, handle popups, and work in frames

Install popup waiters before the click, wait for useful content, then select the
new page so subsequent calls continue there:

```js
const popup = await tabbit.triggerAndWait("popup", () =>
  page.getByRole("link", {name: "Open details", exact: true}).click());
await expect(popup.getByRole("heading", {name: "Details", exact: true})).toBeVisible();
usePage(popup);
return {url: page.url(), title: await page.title()};
```

For controls in an observed iframe, use a frame locator:

```js
const profile = page.frameLocator('iframe[title="Profile"]');
return {name: await profile.getByLabel("Display name", {exact: true}).inputValue()};
```

Use `tabbit.observe({frames: "all", maxChars: 6000})` to discover frame content.
Check `framesTruncated` and each frame's `snapshotTruncated`. Use observed iframe
attributes, frame names, or unique URLs; frame labels are not durable identity.

### Paste text and upload files

For normal fields, prefer `fill`. To paste a TSV block into an already focused
editable, dispatch task-local synthetic paste and verify acceptance:

```js
const box = page.getByRole("textbox", {name: "Items", exact: true});
const text = "alpha\tbeta\ngamma\tdelta";
await box.fill("");
await box.focus();
const paste = await tabbit.pasteText(text, {format: "tsv", requireEditableFocus: true});
await expect(box).toHaveValue(text);
return {strategy: paste.strategy, value: await box.inputValue()};
```

Paste is synthetic (`trusted: false`), leaves the system clipboard unchanged,
and accepts nonempty text up to 1 MiB. For grids, verify the resulting cells.

Upload an authorized local file through an observed input; selection may upload
immediately. Verify the application's attachment state:

```js
await page.getByLabel("Attachment", {exact: true}).setInputFiles("/absolute/report.pdf");
await expect(page.getByRole("status")).toHaveText("Uploaded report.pdf");
return {uploaded: "report.pdf"};
```

### Handle a confirmation dialog

For an authorized Apply changes operation, handle its known confirmation while
the click is pending; awaiting `triggerAndWait("dialog", click)` first can block:

```js
const stop = new AbortController();
const handled = page.waitForEvent("dialog", {
  timeout: 10000, signal: stop.signal,
}).then(async dialog => {
  const expected = dialog.type() === "confirm" && dialog.message() === "Apply changes?";
  if (expected) await dialog.accept();
  else await dialog.dismiss();
  assert(expected, "Unexpected dialog dismissed");
});
try {
  await Promise.all([
    handled,
    page.getByRole("button", {name: "Apply changes", exact: true}).click(),
  ]);
  await expect(page.getByRole("status")).toHaveText("Saved");
  return {saved: true};
} finally {
  stop.abort();
}
```

Dismiss unexpected dialogs and inspect the page before retrying. For a prompt,
use `dialog.accept(authorizedText)` when its response is authorized.

### Inspect screenshots and use visual input

`page.screenshot()` produces PNG artifact receipts only; JPEG is unsupported.
Locator screenshots keep Playwright’s native Buffer return value.

```js
return await page.screenshot({fullPage: false});
```

Open the exact `result.nextAction.path` with the host image viewer before making
a visual judgment or choosing coordinates. The receipt is not a Playwright
Buffer. Coordinates use CSS pixels; account for device scale or viewer resizing
when reading image pixels. For a canvas lacking useful DOM controls, after
inspection establishes the target position:

```js
await page.mouse.click(420, 260);
await page.keyboard.insertText("Quarterly plan");
return await page.screenshot({fullPage: false});
```

Open the resulting screenshot and verify the edit. Prefer semantic locators when
available. See advanced operations for [file choosers](references/advanced-operations.md#uploads),
[refs across rerenders](references/advanced-operations.md#snapshot-references-across-a-rerender),
and [ambiguous transitions](references/advanced-operations.md#an-action-whose-transition-is-unknown).

Stop before an unauthorized send, publish, purchase, or delete. Login, CAPTCHA,
payment, and sensitive values require user action or an authorized protected flow.

## Fetch files and data

Use `page.fetch` for an exposed HTTP(S) file or API URL. It uses the calling page's
browser network context, including CORS, CSP, and cookies. Native `page.request`
and `context.request` use Node HTTP. This connection delivers no Playwright
download events; do not wait for `download` or expect `downloadsDelta`. Without a
file URL, verify through an authorized native download UI or hand off to the user.

Pass relative links directly to honor `document.baseURI`, including `<base>`.
Use `as: "file"` and an unused artifact filename; `savePath` alone does not force
file output, and existing files are never overwritten:

```js
const href = await page.getByRole("link", {name: /view pdf/i}).getAttribute("href");
assert(href);
const result = await page.fetch(href, {
  as: "file", savePath: artifactPath("paper-01.pdf"), timeoutMs: 15_000,
});
assert(result.ok, `HTTP ${result.status}`);
assert.match(result.contentType ?? "", /pdf/i);
return {path: result.path, bytes: result.bytes, url: result.url};
```

Read the returned file and deliver its path. For an observed JSON endpoint:

```js
const response = await page.fetch("/api/orders?limit=20", {as: "json"});
assert(response.ok, `HTTP ${response.status}`);
return response.json;
```

`page.fetch` defaults to GET, same-origin credentials, a 20-second timeout
covering the body, and an 8 MiB response limit. HTTP errors return `ok: false`;
network, parsing, timeout, and size failures reject. Results contain `text`,
`json`, or `path`, not an `APIResponse`. See [browser-network options](references/advanced-operations.md#browser-network-requests)
for additional request settings.

Check `result.issuesDelta` for `SITE_RATE_LIMITED`: defer its origin until
`issue.timestamp + issue.details.retryAfterMs` when a delay is provided. A null
delay means no usable retry time was supplied. For owned-page responses, every
HTTP 429 is reported; HTTP 503 requires a valid `Retry-After`. Native Node HTTP
requests are excluded. The runtime does not pause or retry. For failed input, inspect current state before retrying; `tabbit.actionability(locator)`, `tabbit.focusInfo()`, and
`tabbit.hitTest(locatorOrPoint)` provide targeted diagnostics.

For an observed login wall that requires the user, return the page's URL and
record the issue, then finish while retaining that page:

```js
reportIssue("AUTHENTICATION_REQUIRED");
return {blocked: "login required", url: page.url()};
```

Other reportable codes are `SITE_ACCESS_BLOCKED` and `BROWSER_ERROR_PAGE`; report
only observed conditions. An already authorized protected flow may continue.

## Extract complete evidence

For lists, counts, extrema, or rankings, define the candidate set and inclusion
rule. A bounded sample is not a complete answer. The following workflow collects
all issues under the current Open filter, deduplicating by absolute issue URL.

### Collect a paginated list across calls

Inspection established a server-rendered “Open issues” page, issue links matching
`main a.issue-link[href]`, and at most one `a[rel="next"]` link, absent only on the
last page. These are this site's completion signals; do not assume them elsewhere.
Navigate to the first page and initialize once in the current task:

```js
await expect(page.getByRole("heading", {name: "Open issues", exact: true})).toBeVisible();
globalThis.issueScan = {items: new Map(), visited: new Set(), nextUrl: page.url()};
return {startUrl: globalThis.issueScan.nextUrl};
```

Run this program under a new request ID. It processes at most two pages per call;
`globalThis.issueScan` preserves the accumulated items and continuation:

```js
const scan = globalThis.issueScan;
assert(scan, "Initialize the scan on the first page");
for (let i = 0; scan.nextUrl && i < 2; i++) {
  const url = scan.nextUrl;
  assert(!scan.visited.has(url), "Pagination returned to a visited page");
  await page.goto(url, {waitUntil: "domcontentloaded"});
  await expect(page.getByRole("heading", {name: "Open issues", exact: true})).toBeVisible();
  const rows = await page.locator("main a.issue-link[href]").evaluateAll(links =>
    links.map(a => ({title: (a.textContent || "").trim(), url: a.href})));
  const nextUrl = await page.locator('a[rel="next"]').evaluateAll(links => {
    if (links.length > 1) throw new Error("Ambiguous next page");
    return links[0]?.href ?? null;
  });
  for (const row of rows) scan.items.set(row.url, row);
  scan.visited.add(url);
  scan.nextUrl = nextUrl;
}
return {items: [...scan.items.values()], unique: scan.items.size,
  pagesRead: scan.visited.size, complete: scan.nextUrl === null, nextUrl: scan.nextUrl};
```

A partial result might report `pagesRead: 2`, `unique: 35`, `complete: false`, and
a `nextUrl` for page 3. Run the same batch under a **new request ID**, without
reinitializing the scan. When `complete: true`, `items` contains the deduplicated
collection; read resource chunks if the result is large, then finish the task.

Report “35 unique open issues across 3 pages” only if those are the final verified
counts. If stopped early or a page fails, report partial coverage and the last
confirmed page count. A visited URL cycle is an error, not a completion signal.
For client-rendered lists, wait for each page's data-ready signal before reading
rows or treating an absent Next link as the end. For infinite scroll, use the
application's observed end marker or total count instead of assuming that one
unchanged scroll means completion.

### Collect independent sources concurrently

For independent sources, keep concurrency small and return failures
alongside results. This example closes each scratch tab in `finally`:

```js
const urls = ["https://example.com/", "https://example.org/"];
const settled = await Promise.allSettled(urls.map(async (url) => {
  const tab = await context.newPage();
  try {
    await tab.goto(url, {waitUntil: "domcontentloaded"});
    return await tab.locator("main").evaluate((main) => ({
      title: document.title,
      url: location.href,
      text: (main.innerText || "").slice(0, 4000),
    }));
  } finally {
    await tab.close();
  }
}));
return settled.map((item, index) => item.status === "fulfilled"
  ? item.value : {url: urls[index], error: String(item.reason)});
```

## Read results and recover normal failures

For submitted programs, `nodejs` returns `status` and `result.requestId`.
Small successful values are in `result.value`; the saved-profile example returns:

```json
{"status":"succeeded","result":{"requestId":"save-profile","value":{"persistedName":"Alex"}}}
```

Read that outcome directly; do not routinely request another receipt. JSON is
written to stdout for results and receipts; command errors such as validation,
routing, or resource-read failures use stderr. Capture both streams. Exit codes
are 0 for `succeeded`, 70 for `failed` or `interrupted`, and 75 for `queued` or
`running`. Pre-submission validation or
routing failures can instead return `{ok: false, error}` without a receipt.

### Pending or failed programs

For `queued` or `running`, wait on the original request; do not submit the program
again or invent a new request ID to bypass pending work:

```bash
"$tabbit_cli" receipt --task "Update profile" --request-id save-profile --wait-ms 60000
```

Repeat that wait if still pending. `receipt` returns the durable receipt directly:
`status` and `mutationState` are top-level, and successful `result` contains
`{type: "inline", value}` or `{type: "resource", resourceId, byteLength}`.

Every submitted program has `mutationState: "possible"`. A failed program may
have saved the profile before a later step failed. Inspect persisted state with
a new read-only program before deciding whether to repeat the mutation:

```bash
"$tabbit_cli" nodejs --task "Update profile" --request-id verify-profile <<'JS'
await page.reload({waitUntil: "domcontentloaded"});
const name = page.getByRole("textbox", {name: "Display name", exact: true});
await expect(name).toBeVisible();
return {persistedName: await name.inputValue()};
JS
```

If Alex is already persisted, do not save again. Otherwise resolve the failure
and use a new request ID for corrected code. For `taskTerminated`, transport loss,
missing receipts, or uncertain acquisition, use [recovery](references/recovery.md)
before continuing; do not replay an operation just because its receipt is missing.

### Large results

Results over 16 KiB return `result.resourceId` and `result.byteLength`. Read the
returned ID before finishing. This illustrative 18,021-byte result begins with
`{"text":"` followed by multibyte Chinese characters; small chunks show why
`nextOffset` matters:

```bash
"$tabbit_cli" resource --task "Read example" --resource result-example --offset 0 --max-bytes 11
```

```json
{"resourceId":"result-example","offset":0,"data":"{\"text\":\"","nextOffset":9,"eof":false,"byteLength":18021,"offsetUnit":"byte","encoding":"utf-8"}
```

The next character needs three bytes, so only nine bytes fit. Use the returned
`nextOffset: 9`, not `0 + 11`:

```bash
"$tabbit_cli" resource --task "Read example" --resource result-example --offset 9 --max-bytes 11
```

```json
{"resourceId":"result-example","offset":9,"data":"汉汉汉","nextOffset":18,"eof":false,"byteLength":18021,"offsetUnit":"byte","encoding":"utf-8"}
```

Continue from 18, following each `nextOffset` until `eof`. Concatenate the `data`
strings in order and parse once; individual chunks need not be valid JSON. In
normal use, request up to 65536 bytes per chunk rather than these tiny teaching
chunks. Offsets are UTF-8 bytes, and `max-bytes` must fit the next character.
Read only a slice when sufficient for the task.

## Finish every completed task

**Finish using the same task name after results are verified and needed resources
have been read.** Do not leave a completed task owning the user's tabs. Finishing
removes task receipts and resource files; exported artifacts remain.

Plain finish releases ownership and retains remaining tabs as a resumable group.
Use it for the profile workflow, for a draft the user will review, or for a page
where the user needs to sign in:

```bash
"$tabbit_cli" finish --task "Update profile"
```

On Windows:

```powershell
& $tabbitCli finish --task "Update profile"
```

Wait for the response before reporting the task released. A normal response
excerpt is:

```json
{"finished":true,"keep":true,"forcedCleanup":false,"closedTabIds":[]}
```

Close unneeded task-created scratch tabs before finish. Preserve acquired or
resumed user tabs, including blank ones, unless closing them was requested.
For the `"Read example"` task above, if its only page was created for this task
and is no longer needed, close it and then finish:

```bash
"$tabbit_cli" nodejs --task "Read example" --request-id close-scratch <<'JS'
await page.close();
return {remainingOwnedPages: pages().length};
JS
"$tabbit_cli" finish --task "Read example"
```

Use `page.close()` only for a page whose ownership and purpose you have verified.
Normal finish automatically removes a confirmed-empty implicit initial page;
a modified `about:blank` page is retained.

Use `--discard` only when closing **all task-owned tabs** was requested. It also
closes acquired/resumed user tabs and dissolves the task's group:

```bash
"$tabbit_cli" finish --task "Update profile" --discard
```

Do not run both finish variants: choose the appropriate one and call it once.
If `forcedCleanup` is true, inspect `tabsRetained` before claiming tabs closed;
forced cleanup can retain tabs even with `--discard`. If finish was interrupted,
run `diagnose --task NAME` before deciding whether to repeat it. When an instance
was explicitly pinned, restore the previous override only after finish is
confirmed. See [finish recovery](references/recovery.md#finish-recovery) for
exceptional finalization outcomes.
