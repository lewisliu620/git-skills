# Advanced browser operations

Read the matching section only. Run examples through `nodejs` on the intended
owned page, with the same task name and a new request ID. Replace illustrative
selectors, paths, and outputs with observed evidence.

## Frames and observation

`tabbit.observe(options)` discovers controls and frames on `page`.

| Option | Default | Allowed values |
| --- | --- | --- |
| `frames` | `"visible"` | `"none"`, `"visible"`, `"all"` |
| `depth` | 20 | 1–30 |
| `maxChars` | 6000 | 256–20000 |
| `frameMaxChars` | `min(2000, maxChars)` | 256–6000 |
| `maxFrames` | 8 | 1–32, including the main frame |
| `boxes`, `focus` | `true` | `false` omits boxes or focus details |
| `hitTest` | absent | Locator or `{x, y}` |

Discover frames, then act inside an observed `iframe[title="Profile"]`:

```js
return await tabbit.observe({frames: "all", maxFrames: 16, frameMaxChars: 3000});
```

```js
const profile = page.frameLocator('iframe[title="Profile"]');
await profile.getByLabel("Display name", {exact: true}).fill("Alex");
await profile.getByRole("button", {name: "Save", exact: true}).click();
await expect(profile.getByRole("status")).toHaveText("Saved");
return {status: await profile.getByRole("status").textContent()};
```

Check `framesTruncated` and each `snapshotTruncated`. Increase the
relevant limit or inspect a specific frame; resource paging cannot recover text
already truncated by `observe`. Characters bound snapshots, not total response
bytes. Frame IDs are observational labels; select through observed markup,
`page.frame({name})`, or a unique frame URL. Re-resolve detached frames.

## Popups

Install the waiter before clicking; select the popup with `usePage`.

An observed “Open details” link opens a Details page:

```js
const popup = await tabbit.triggerAndWait("popup", () =>
  page.getByRole("link", {name: "Open details", exact: true}).click());
await popup.waitForLoadState("domcontentloaded");
await expect(popup.getByRole("heading", {name: "Details", exact: true})).toBeVisible();
usePage(popup);
return {url: page.url(), title: await page.title()};
```

Expect `{url, title}` in `result.value`; the next call uses the
popup. Return data, not Page objects. Close scratch popups when finished.

## Dialogs

Handle a dialog while its triggering action is pending. The runtime
records `BLOCKING_DIALOG` but does not accept or dismiss it.

The user authorized Apply changes and its known confirmation:

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

Handle prompts with `accept(authorizedText)`; dismiss cancellation.
Do not await `triggerAndWait("dialog", click)` before handling the dialog: the
click may wait for dismissal. Unexpected dialogs require inspection before retry.

## Uploads

Use native file inputs; selecting a file may immediately upload it.

The user requested uploading `/absolute/report.pdf` to this site:

```js
await page.getByLabel("Attachment", {exact: true}).setInputFiles("/absolute/report.pdf");
await expect(page.getByRole("status")).toHaveText("Uploaded report.pdf");
return {uploaded: "report.pdf"};
```

For an observed control that creates a file chooser:

```js
const stop = new AbortController();
try {
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser", {timeout: 10000, signal: stop.signal}),
    page.getByRole("button", {name: "Attach file", exact: true}).click(),
  ]);
  await chooser.setFiles("/absolute/report.pdf");
  await expect(page.getByRole("status")).toHaveText("Uploaded report.pdf");
  return {uploaded: "report.pdf"};
} finally {
  stop.abort();
}
```

Use an existing authorized absolute file path readable by the
runtime. Adapt the application's upload/save confirmation; file selection alone
does not prove persistence. After failure, inspect attachments before retrying.

## Paste

Use `pasteText` for bulk editor/grid text; ordinary typing uses
`fill`, or `pressSequentially` when individual key events matter.

Replace Items with the requested TSV:

```js
const box = page.getByRole("textbox", {name: "Items", exact: true});
const text = "alpha\tbeta\ngamma\tdelta";
await box.fill("");
await box.focus();
const paste = await tabbit.pasteText(text, {
  format: "tsv", requireEditableFocus: true,
});
await expect(box).toHaveValue(text);
return {strategy: paste.strategy, value: await box.inputValue()};
```

Verify values or grid cells; dispatch does not prove acceptance
or persistence. Nonempty text is limited to 1 MiB. Defaults: `format: "text"`,
`requireEditableFocus: false`. Paste is task-local and synthetic (`trusted: false`);
the system clipboard is unchanged.

## Snapshot references across a rerender

Prefer semantic locators. Normalize a fresh snapshot ref before
a known DOM replacement.

Observed Save ref `e3` must survive the checkbox's action-bar rerender;
the user requested enabling updates and saving:

```js
const save = await page.locator("aria-ref=e3").normalize();
await page.getByRole("checkbox", {name: "Email me updates", exact: true}).check();
await save.click();
await expect(page.getByRole("status")).toHaveText("Saved");
return {status: await page.getByRole("status").textContent()};
```

Normalized locators re-resolve test IDs, roles, and user-facing attributes, not
permanent identity. Re-observe after navigation or changed attributes; never
invent refs. Store the locator on `globalThis` if it must survive another call.

## An action whose transition is unknown

`triggerAndObserve` detects page, URL, navigation, frame, or render
changes in that priority order.

Continue shows Confirmation preview on this or a new page:

```js
const transition = await tabbit.triggerAndObserve(() =>
  page.getByRole("button", {name: "Continue", exact: true}).click(),
  {timeoutMs: 10000, activatePage: true});
await expect(page.getByRole("heading", {name: "Confirmation preview", exact: true})).toBeVisible();
return {transition};
```

Transition shape: `{kind, url, pageId?, activated?, frame?}`.
`activatePage` selects a new page but does not wait for content; use native waits.
For unknown destinations, inspect the transition first. Locate child frames by
returned name/URL before acting.

Defaults: `timeoutMs: 30000`, `activatePage: false`, `settleMs: 120` (0–2000),
`pollMs: 25` (10–500). Signals accumulate through `settleMs`.
For known page/popup/navigation/URL events use `triggerAndWait`; all accept
`timeoutMs`. URL requires `url`; navigation/URL also accept `waitUntil`.

## Browser-network requests

`page.fetch` uses browser CORS, CSP, and cookies.

Read an endpoint observed in this application's workflow:

```js
const response = await page.fetch("/api/orders?limit=20", {as: "json"});
assert(response.ok, `HTTP ${response.status}`);
return response.json;
```

Results contain HTTP metadata and `text`, `json`, or `path`, not
`APIResponse`. HTTP errors return `ok: false`; network, parsing, timeout, and
size failures reject. Defaults: `method: "GET"`, `timeoutMs: 20000` including body.

Relative URLs resolve against `document.baseURI`; only HTTP(S) is supported.
Credentials default to `"same-origin"`; `"omit"`/`"include"` are also accepted.
Options are `{method, headers, body, as, savePath, maxBytes, timeoutMs, credentials}`;
`body` must be a string and `as` is `"text"`, `"json"`, or `"file"`.
Without `as`, textual responses up to 256 KiB return inline text; other responses
require `savePath`. `as: "file"` forces file output; `maxBytes` can lower the
8 MiB limit. `artifactPath(name)` requires a plain filename ≤128 characters;
same name means same path, and fetch never overwrites files.

Native `page.request` / `context.request` use Node HTTP. Browser downloads need
an exposed HTTP(S) URL: this connection delivers no Playwright download events.
Do not wait for `download`/`downloadsDelta`. Without a URL, verify through an
authorized native download UI or hand off to the user.

## Rate limits and interaction diagnostics

`result.issuesDelta` reports `SITE_RATE_LIMITED` for every owned-page HTTP 429,
with or without `Retry-After`. HTTP 503 requires a valid `Retry-After`. This
includes fetch/XHR/subresources and excludes native
`page.request`/`context.request`. Reporting does not wait or retry. Defer the
reported `origin` until Unix-millisecond `timestamp + details.retryAfterMs`;
null means no usable delay. `details.status` contains the HTTP status.

Inspect a failed Save action, then act on its reported blockers:

```js
return await tabbit.actionability(page.getByRole("button", {name: "Save", exact: true}));
```

`tabbit.focusInfo()` reports focus; `tabbit.hitTest(locatorOrPoint)`
reports the hit target. Use diagnostics to choose native actions, not replace them.
Record observed login walls before handoff:

```js
reportIssue("AUTHENTICATION_REQUIRED");
return {blocked: "login required", url: page.url()};
```

Also reportable: `SITE_ACCESS_BLOCKED`, `BROWSER_ERROR_PAGE`. Report only observed
conditions; an authorized protected flow can continue within its scope.
