# Saved document capacity: reviewed Chromium acquisition

This standalone, opt-in route exercises the actual `python -m yadinassi --ui --f
DB` launcher from the database's full `InventoryApplicationConfiguration` source.
It is not a new database grant, a native 1C window-parity claim or restart recovery
for an unknown commit. The source branch and the reviewed branch must name the
same reviewed commit before acquisition. Only a push to
`codex/object-form-preflight-browser-reviewed` triggers the dedicated workflow.

## Owned setup and read-only audit

Before Chromium starts, a fresh owned SQLite database receives two catalog cards
(Product `P1` / Widget and Warehouse `W1` / Main warehouse) in one explicit typed
catalog transaction. Two exact source-granted root operations create Receipt
`R52` with 52 rows through `Post` and Receipt `R1` with one row through `Write`.
The rows use exact catalog keys, unique row identities and Decimal quantities
1 through 52 with amounts ten times quantity. R1 is not posted. These are fixture
setup writes, not effects performed by the browser. No SQL writes, interpreter
source generation or mocked backend are used. A separate core-only profile15
source remains denied by `launch_snapshot()`.

The 52-row document is valid persisted/core data but exceeds the unchanged
`MAX_TABLE_ROWS=32` editor limit. It must not be edited or partially displayed.
The one-row document is the normal-open control; the exact 32-row boundary is
already covered by Python, not this browser acquisition. No limit is increased.

An independent, read-only typed audit verifies the full stored source, profile,
metadata, database/generation binding, all cards and revisions, all 53 saved rows
and all 52 accumulation movements. All business audit rows share one read lease.
Only R52 is posted: saved totals are exactly 1378.000 and 13780.00. The audit uses
neither the report service nor Query/BSL and hashes the typed snapshot. It also
hashes the SQLite file before and after reading. Every flow and natural shutdown
must reproduce the initial typed fingerprint and exact database-file bytes.
UUIDs, record keys, source bytes and mutable drafts never leave the audit helper.

## Three scenarios, 20 business RPCs

1. **Known refusal retains a raw sibling (4 RPCs).** Open Warehouse W1; type
   `RAW DRAFT` without submitting it. Select Receipt R52 through the real catalog
   UI and return to the exact retained owner tab. Opening R52 returns HTTP 200
   with the closed `form_capacity` application error, no form/session allocation,
   unchanged session identities and no unknown/terminal lock. The UI explains
   that nothing was opened or changed and other forms/reports remain available.
   The original Warehouse draft remains editable and unsent.
2. **Repeated delayed refusal, small document and reports (7 RPCs).** Double-click
   the same oversized selection. Exactly one new `openRecord` RPC runs. Hold its
   already-audited real reply, verify busy fencing and retained owner identity,
   then deliver those exact bytes once. No retry or response substitution occurs.
   Open and genuinely close R1; its session is `form-2`, proving the two refusals
   allocated no editor slot. Read the old-three report API's Balance and
   Movements. Check one typed balance group and all 52 movement rows, labels,
   record direction, line numbers, period and exact resource scales.
3. **Natural shutdown/restart (9 RPCs).** Restore Warehouse Description locally
   to its original value without Enter, then genuinely Close it. No OnChange,
   Save, command or write RPC occurs. Naturally close the application and restart
   through `--ui --f`; R52 is still a known refusal, R1 opens as fresh `form-1`,
   closes normally and both reports still work. Finish with natural shutdown.

The exact plan is 4 / 7 / 9 business RPCs, plus two application hellos and three
form hellos: **25 total RPCs**. A retry, unexpected OnChange, Save, additional
snapshot or hidden replay fails the acquisition rather than enlarging the plan.
The old report UI is deliberately used with the unsent owner hidden before
focusing report controls. Catalog navigation is an ordinary user action and the
owner tab/draft is retained; this does not claim the newer statement-control
focus policy. Returning to the owner and restoring the original local text
removes only that local draft. The source BeforeClose handler is not overridden.

## Security, lifetime and finite limits

The source is bound to `QA_SOURCE_SHA`, exact commit/tree and a SHA256 manifest
covering runtime, generated assets, UI source, source configuration, helper,
contract and workflow. A clean checkout is required before and after the run.
Real source-derived form/record capabilities are checked but not exported.
Reports expose readonly labels, not write/reference capabilities. No statement
API, user SQL, direct browser UUID, root receipt resolution or backend fault
injection is part of this acquisition.

The ordinary non-root Linux runner uses pinned Playwright 1.64.1 Chromium with
sandbox enabled; command line, owned process identity, layer1 and seccomp are
checked. Network is strict matching loopback only. Fetches do not follow
redirects or retry. The sole permitted attachment refusal is an exact heartbeat
409/busy during a real pending request. Request and response observations use
already-audited, exact-delivered bytes, never a second evictable CDP body lookup.

Work deadline is 220 seconds plus a separate 20-second cleanup reserve. Caps:
180 RPCs, 96 attachment requests, 35-second RPC fetch, 50-second reply observer,
15-second/16-KiB fixture helper, 10-second held-response gate, 64-KiB request and
result JSON, 256-KiB response, 8-KiB attachment reply, three PNGs of at most 4 MiB
each. Workflow job/acquisition timeouts are 10/5 minutes, not extended runtime
budgets. Only five files may be uploaded: result.json, manifest.json,
preflight-draft.png, preflight-usable.png, preflight-reopened.png.

Diagnostics are fixed phase/reason/method/status categories and bounded byte
counts. No raw exceptions, packet bodies, headers, titles, local paths, tokens
or storage identifiers are printed. The manifest hashes result JSON and each
PNG. Owned process groups and the fresh database/home are removed with verified
cleanup; cleanup uncertainty fails the run. Natural application exits are
observed independently and cannot be replaced by forced teardown success.

The aggregate fixture now declares the fourth StockStatement report as well. These three capacity flows still exercise only the unchanged Balance and Movements requests; the separate four-scenario statement harness covers statement filters and paging.
