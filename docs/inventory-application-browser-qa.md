# Stock application Chromium acceptance

This is a reviewed opt-in acquisition, not an automatic PR check. It exercises
real UI requests against a fresh owned SQLite database containing the exact full
`InventoryApplicationConfiguration` source from
`examples/configuration-inventory-application`. It never seeds business rows.
Products, warehouses, receipt and issue records are created by actual forms.
Each host is launched with `python -m yadinassi --ui --f <owned database>`;
no external source directory or manually selected UI profile reaches the launcher.
A separate fresh core-only physical15 database must refuse `launch_snapshot()`.

## Four fixed flows

1. Create Product P1 (Widget) and Warehouse W1 (Main warehouse) through catalog
   forms. Choose both header and tabular-section references with issued picker
   tickets. Write receipt R1, quantity 10.50 and amount 105, and independently
   verify saved typed references, an unposted document and no stock movements.
2. Post R1. Balance exactly at 12:00:00 excludes the movement, while 12:00:01
   includes it. Create/post issue I1 for 3.25 and 32.50. Balance is 7.25; a
   Turnovers interval with both endpoints exactly 12:00:00 includes both records.
   Check raw Movements, Undo I1, inspect restored balance, then Post I1 again.
   Change its form quantity to 99 without writing. Read-only Balance still shows
   7.25, while the unsaved form value and independent saved audit are unchanged.
3. Double-click Post with quantity 99. The authored shortage handler rejects
   exactly one request and the saved document/movement audit remains identical.
   Dirty Close form is refused and Close application cannot bypass live forms.
   Open R1 twice while holding only the genuine `openRecord` response, navigate
   back to I1, then release the response: one open and the same active owner,
   with its unsaved quantity retained. Restore 3.25 and double-click Write:
   one request, one revision increment, no movement replay. Close the saved I1.
4. Close R1 and naturally shut down the first host. Start a new host from the
   same stored source, reopen I1, verify typed reference presentations and 3.25,
   read Balance again and compare an independent audit. Close normally a second
   time. This is persisted reopen, **not restart recovery for an unknown commit**.

The exact business request plan is 23 + 23 + 7 + 7 = **60**. It includes catalog
navigation, open, all edits and commands, begin/apply reference selection,
report reads, form closes and application closes. Hello/snapshot reads alone are
excluded from this plan, but counted toward the total RPC ceiling. Browser-only
navigation, repeated suppressed clicks and the local application-close refusal
must not add business requests.

## Independent audit and honest limits

The helper creates only empty databases. The audit reopens the database with
`read_only=True`, validates the full stored-source launch snapshot, then borrows
`DocumentView` and the typed accumulation read port from one read owner.
All business audit rows share one read lease: catalogs, document images, recorder
movements and the fixed revision SELECT. Exact CatalogKey/DocumentKey identities,
Decimal resources, datetime periods and accumulation directions are checked
inside that process. Report aggregation code, Query, BSL handlers and UI state
are not used by the audit. Its small decimal totals are calculated independently.
A before/after database-file SHA256 verifies that the helper itself did not write.
This checks the declared business slice, not journal contents or every SQL table.

The report wire contains plain scalar cells or presentation-only Catalog/Document
cells. A label is not a reference/write capability. Requests contain only a
manifest report name and exact period strings, not SQL, persistent keys or BSL.
The harness verifies report tables have no editing controls. Source/schema/lease
faults and oversized refusals belong to the focused Python contracts, not an
invented browser fault switch. No DOM or application state is replaced, and no
callback, response or posting result is synthesized. The only response gate delays
and subsequently delivers the exact real `openRecord` response.

No native StandardCommand/window parity, automatic retry, unknown-commit
resolution, crash/restart receipt recovery or durable request-envelope claim is
made. The authored negative-stock rule is configuration code, not a general
platform inventory policy.

## Ownership, bounds and acquisition route

- Ordinary non-root Linux runner, existing Playwright 1.64.1 package lock and
  pinned workflow actions. Only `codex/inventory-application-browser-reviewed`
  triggers `.github/workflows/inventory-application-browser-qa.yml`.
- **220 seconds** work plus **20 seconds** cleanup; at most **180 RPC** and
  **96 attachment exchanges**, 35-second RPC fetch and 50-second reply observer,
  each bounded by the remaining global deadline. No redirects/retries.
- Loopback launch origin only; `/attachment` is the one additional closed route.
  The exact heartbeat 409/busy envelope is accepted during an in-flight RPC,
  not generalized to other errors and never retried.
- Real Chromium sandbox stays enabled, verified by command line and
  `chrome://sandbox`. Direct owned child PID, UID, start time, executable,
  process-group and owned profile checks remain fail closed. There is no system
  security change, fallback browser, broad process kill or unowned cleanup.
- Absolute runner-owned RUNNER_TEMP, short private child HOME/TMPDIR; no fixed
  `/tmp` path, user profile or shared native/provenance fixture.
- Requests at most 64 KiB, observed replies at most 256 KiB, attachment replies
  at most 8 KiB; fixed helper subprocess output at most 16 KiB.
- Exactly four PNGs, each at most 4 MiB, plus `result.json` (at most 64 KiB) and
  `manifest.json`. Fresh artifact directory and exclusive writes reject stale
  output. The manifest records source tree, result SHA256 and screenshot hashes.
- Both startup and completion verify exact commit, clean checkout and hashes of
  runtime, generated assets, forms/frontend, authored source, acquisition files,
  relevant tests, this document and reviewed workflow. Final PASS requires
  natural host exits, all four completed flows and verified owned cleanup.

Only fixed phases, closed diagnostics, counts, version/source digests and the
four authored-data screenshots are uploaded. Launch URLs, attachment credentials,
raw exceptions, environment variables, database files, response bodies and process
identifiers are never published. A failed or incomplete flow remains FAIL.

Preparation uses syntax/AST checks only. Offline contract execution and the four
Chromium scenarios require a separately communicated count and reviewed route.

## First acquisition diagnosis

The first reviewed run reached 27 RPCs (23 business requests plus handshakes)
before scenario 1 failed, with the sandbox verified and no wire failure. It did
not acquire a screenshot or establish acceptance. One separately announced
offline diagnostic reproduced those 23 real controller/server form actions and
ran the exact embedded audit unchanged: the audit and scenario-1 assertions
passed. This does not prove the browser path passed and does not justify changing
runtime semantics.

Follow-up diagnostics distinguish fixed command/outcome, fixture, individual
audit-assertion and screenshot stages. Only exact allowlisted assertion reasons
and the closed command-outcome vocabulary can enter the result; no raw assertion
actual/expected values, subprocess errors or storage values are exported. The
request plan, acquisition bounds and required assertions remain unchanged.

The second acquisition again stopped at 27 RPCs, before the command-outcome
checkpoint, and therefore before the audit. Its closed diagnostic does not prove
the exact browser exception. The stock observer now follows the established
layout/value-input acquisition pattern: retain each bounded, already audited real
response and consume it only after the exact matching browser request is delivered.
Bindings include the entire request, response ID and current launch origin; the
map is bounded by the existing 180-RPC ceiling and cleared only for a new host.
The command, report, shortage and dirty-close checks no longer ask CDP to read a
response body a second time. They still inspect the original response, not current
UI state, and issue no extra fetch or retry. Additional closed click/wait/read
stages, exception classes and observer categories preserve uncertainty rather
than asserting that CDP body eviction was demonstrated by the previous artifacts.

After the exact-request observer correction, scenario 1 passed with its screenshot.
The next acquisition stopped after a saved Post, before the first report RPC.
Report tab/fill/click/wait/read/assert stages and closed malformed/unsupported
input categories now distinguish that seam. Native datetime-local inputs are
filled using normalized HTML values (zero seconds omitted); the actual request
and response must still carry the exact original 19-character whole-second
boundaries, including 12:00:00. No browser state is injected. The persisted reopen
quantity assertion uses the declared scale-three spelling 3.250, consistent with
the observed stored receipt quantity 10.500. No report numeric assertion, period
meaning, runtime behavior, request count or time limit is relaxed.
