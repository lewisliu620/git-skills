# Recovery

Use this reference after pending or interrupted work, an uncertain mutation,
transport loss, a missing receipt, or finish failure, and for explicit instance
selection or launcher and routing failures. Read the relevant section only.
Keep the same task name and request identity until evidence establishes the
outcome. Use the [stable launcher and stdin recipes](../SKILL.md#connect-and-discover).

## Read, do not resubmit

```text
<launcher> receipt --task NAME --request-id ID --wait-ms 60000
<launcher> diagnose --task NAME
```

Every CLI program uses `mutationState: "possible"`: earlier actions may have
completed even when the program fails. For `queued`, `running`, or `TASK_BUSY`,
wait on the same receipt; a client-side wait ending does not establish failure.
For failed or interrupted work, inspect persisted application state before
retrying. Submit corrected code under a new request ID only when evidence rules
out repeating a completed mutation. Reusing an ID only returns its old receipt.
Never change task names, instances, or browser backends to evade pending work.

## Deadline and transport boundaries

When a hard deadline reports `taskTerminated: true`, only that task executor is
terminated; its live tabs and group are retained. Resume that exact group in a
new read-only task, inspect externally visible state, and retry a mutation only
when evidence proves the original operation did not occur.

After a transport close in the same Browser generation, reconnect through the
stable launcher and read the original receipt. The CLI does not replay a fully
sent request on EOF. If the task or receipt is missing, or the response is
`OUTCOME_UNKNOWN`, the receipt cannot establish the mutation outcome. Create a
new read-only task, inspect externally visible state, and never replay the
possible mutation merely because the old receipt is unavailable.

## Read resource results

Read needed resources before `finish`: task cleanup removes receipts and resource
files, while exported artifacts remain. A successful compact response carries
`result.resourceId` and `result.byteLength`. Use the returned ID:

```text
<launcher> resource --task NAME --resource ID --offset 0 --max-bytes 32768
```

Each response contains `data` (a fragment of the result's JSON text), `nextOffset`,
`eof`, and `byteLength`. To reconstruct the full result, start at zero, follow
`nextOffset` until `eof`, concatenate the `data` strings in order, then parse once.
Individual chunks need not be valid JSON. Read only a slice when that suffices.

Offsets are UTF-8 bytes, not JavaScript character indexes. Use each returned
`nextOffset` unchanged; offsets inside a multibyte character are rejected.
`max-bytes` is at most 65536 and must fit the next character. Resource paging does
not recover text already truncated by a page observation or extraction.

## Finish recovery

If finish is interrupted, run `diagnose --task NAME` before deciding whether
another finish is necessary. If `forcedCleanup` is true, inspect `tabsRetained`:
tabs may remain even when `--discard` was requested. `tabsRetained` describes the
finalization policy, not a count. A confirmed-empty implicit page can be removed
before finalization without appearing in `closedTabIds`; use inventory when
exact remaining tabs matter.

## Inventory and acquisition

Inventory can be partial. `total` counts matching tabs; `complete` means the entire
unfiltered inventory was returned. `groupsScope: "returned-tabs"` means each
group's `visibleTabCount` covers only that response. Do not infer missing tabs or
whole-group counts from a filtered or paginated result.

```text
<launcher> tabs --task NAME --cursor TOKEN
<launcher> tabs --task NAME --group ID
```

Continue from `nextCursor` with the same filters and limit until `truncated` is
false when full inventory is needed. Restart on `STALE_CURSOR`. Both `create`
and `tabs` accept `--state available|owned|claimed`, `--window ID`, `--group ID`,
`--limit 1..200`, and `--cursor TOKEN`.

Acquisition is revalidated atomically. Failure prevents program dispatch, but
ownership persists if acquisition succeeds and attachment or code then fails.
Receipts report acquisition state and `codeDispatched`; dispatch alone does not
prove execution. Failed acquisition reports `outcome: "unchanged"` for an atomic
browser rejection, or `"unknown"` when transport loss or session abort prevents
certainty. Standalone `claim` and `resume` remain available when acquisition must
be separate from execution.

## Response details

Pre-submission failures may return `{ok: false, error}` without a receipt.
For submitted programs, the compact `nodejs` response contains:

| Field | Meaning |
| --- | --- |
| `status` | `queued`, `running`, `succeeded`, `failed`, or `interrupted`. |
| `result` | `requestId` plus inline `value`, resource metadata, or failure details; may include `elapsedMs`. |
| `result.mutationState` | Present for non-success; inspect visible state before repeating actions. |
| `task` | Present for a new task or non-success; identifies the task and whether it was reused, sometimes its `groupId`. |
| `transition` | Optional page/document changes; `targetEpoch` and `documentGeneration` are staleness evidence, not durable IDs. |

The `receipt` command returns the durable receipt directly: `status` and
`mutationState` are top-level, and successful `result` is either
`{type: "inline", value}` or `{type: "resource", resourceId, byteLength}`.

Results and receipts use stdout; command errors use stderr. Capture both.
The launcher exits 0 for `succeeded`, 70 for `failed`
or `interrupted`, and 75 for `queued` or `running`. A nonzero exit does not erase
the receipt; read its error fields and recovery guidance.

## Explicit product or instance selection

Without an explicit user request, do not inspect the registry or set an
override. The stable launcher selects the instance for each command.

Pinned nondefault-profile cold startup is unsupported. Open that profile in
Tabbit before using its instance ID; the launcher does not recreate it.

For an explicit request, inspect only the current user's registry with
read-only OS commands and validate records as described below. Normalize only
case and surrounding space, then match exactly one canonical product:
`Tabbit Browser`, `Tabbit Browser Dev`, `Tabbit`, or `Tabbit Dev`. These are not
aliases. If multiple valid records match, show their instance IDs and ask the user.

Preserve any existing `TABBIT_PLAYWRIGHT_INSTANCE` value, then set the selected
uppercase 16-hex ID before the first command (the ID below is illustrative):

```bash
export TABBIT_PLAYWRIGHT_INSTANCE='0123456789ABCDEF'
```

```powershell
$env:TABBIT_PLAYWRIGHT_INSTANCE = '0123456789ABCDEF'
```

Follow the main skill's startup and execution workflow with this override in
effect. Keep it fixed for receipt and resource reads, recovery, and `finish`.
Do not probe with an unpinned launcher or change the ID during the task.
Only after finish is confirmed, restore the previous value. If it was originally
unset, use `unset TABBIT_PLAYWRIGHT_INSTANCE` on POSIX or
`Remove-Item Env:TABBIT_PLAYWRIGHT_INSTANCE` in PowerShell.

### Validate records without repairing them

On macOS, inspect only `$HOME/.local/share/tabbit-playwright/instances`.
The directory must belong to the current user, mode 0700, with no symlink path
components. `<ID>.instance` must be a regular file owned by that user, mode 0600,
with exactly these three lines (placeholders below describe absolute paths):

```text
# tabbit-playwright instance managed by Tabbit Browser
<absolute path to executable tabbit-playwright-cli>
<absolute user-data directory>/LocalAgent/endpoint.json
```

`<ID>` is 16 uppercase hexadecimal characters. The CLI must be an executable
regular file, the user-data directory must exist, and the endpoint path must
have no symlink components; the endpoint itself may be absent while offline.
For product selection, require `<ID>.product` with the same ownership/mode and
exactly two lines, for example:

```text
# tabbit-playwright product managed by Tabbit Browser
Tabbit Browser Dev
```

The second line must be one of the four canonical products above. The launcher
accepts legacy records without a sidecar, but those do not identify a product.

On Windows, inspect only `%LOCALAPPDATA%\Tabbit\LocalAgent\instances` using
`Get-ChildItem`, `Get-Item`, `Get-Acl`, and bounded `Get-Content -Raw`.
`<ID>.json` must be a regular file under that protected root, with no reparse
components. Require the current user as owner and a protected DACL granting
FullControl only to that user and `SYSTEM` (inherited by children for directories).
Its JSON contains exactly these seven fields:

```json
{
  "version": 1,
  "instanceId": "0123456789ABCDEF",
  "product": "Tabbit Browser Dev",
  "cliPath": "C:\\TabbitDev\\tabbit-playwright-cli.exe",
  "browserPath": "C:\\TabbitDev\\tabbit.exe",
  "userDataDir": "C:\\Users\\Alex\\AppData\\Local\\TabbitDev",
  "endpointPath": "C:\\Users\\Alex\\AppData\\Local\\TabbitDev\\LocalAgent\\endpoint.json"
}
```

Paths and ID above are illustrative. The ID must match the filename and first
16 uppercase hex characters of SHA-256 of the UTF-8 endpoint path. Require a
canonical product and absolute paths without `..`, device prefixes, or reparse
components. The endpoint must be `LocalAgent\endpoint.json` below `userDataDir`.
The CLI basename is `tabbit-playwright-cli.exe`; its directory is either the
browser executable’s directory or a `TabbitDance` directory one or two levels
below it. CLI and browser executables must exist as regular files.

Ignore invalid records. Never repair the registry, broaden permissions or ACLs,
require administrator access, disable security controls, or relocate binaries.

## Launcher and routing failures

- **Agent sandbox denial:** request approval for the stable launcher and, only
  for explicit selection, read-only registry access.
- **OS ownership, mode, ACL, endpoint access, quarantine, or signing policy:**
  verify Agent and Browser share an OS user, then relaunch Browser once so it can
  repair its managed integration. Report any remaining denial unchanged.
- **Missing or malformed launcher or registry:** invalid installation.
- **Exit 69:** routing or the runtime is unavailable; check the selected instance.
- **Runtime unavailable:** relaunch Browser once with permission; do not launch
  the service yourself or switch browser backends.
