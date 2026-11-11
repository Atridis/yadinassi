# Source-bound stock statement browser acceptance

This separate reviewed-only acquisition covers four flows on the stored full-source
inventory application. It does not modify or replace the earlier stock browser
acquisition. It is a bounded host/UI subset, not native 1C window parity and not
restart recovery for an unknown commit.

## Setup, not UI effects

Before Chromium is launched, a new owned temporary database is created from the
exact `examples/configuration-inventory-application` source and explicit
`accumulation-reference-forms-v1` grant. Setup uses one typed catalog transaction:
52 Products (`P001`–`P052`) and two Warehouses. One actual Receipt with 52 typed lines
is posted through `InventoryRootOperations`; quantities are 1–52 and amounts
10–520. These are explicitly setup writes, never credited as browser actions.
No SQL writes, fake handlers, report service seed or fabricated responses are used.
The existing editable-form boundary is `MAX_TABLE_ROWS=32`. This setup document
intentionally exceeds it to exercise detached report pagination, which has a
separate bound. The acquisition never tries to open the 52-line Receipt as an
editable form and does not raise that limit. Raw-draft lifecycle checks use the
small existing Warehouse `W1` sibling instead.
Raw core15 without the forms grant is separately confirmed unable to launch UI.

The real host starts twice using only `python -m yadinassi --ui --f <owned database>`.
No external configuration directory or grant flag is passed to either launch.

## Four flows and fixed business RPC plan

1. **8 requests:** prepare all filters; Day first page, double-click Next (one RPC),
   Previous; Month first/next; None first/next. Each full result has 52 real rows,
   split 50+2. Original headers, cursor and snapshot binding survive pagination.
   Every scalar/resource and typed date is asserted, with total closing quantity
   1378 and amount 13780. Opening and expense are zero for this receipt-only period;
   receipt and closing equal each product's seeded quantity/amount.
2. **21 requests:** Product chooser over 32 matches returns no partial rows;
   exact `P001` selects its original saved card. Warehouse `W2` excludes all rows;
   opening/canceling its chooser keeps that committed selection. Explicit empty
   differs from All for both dimensions. Exact absent code returns zero choices,
   not an arbitrary fallback. Browser projections expose only labels and local
   choice/setup tokens, never persistent identities.
3. **12 requests:** catalog/open saved Warehouse `W1`; leave its Description as
   a raw unsent `RAW DRAFT`; prepare/read/page and exercise date, periodicity and
   chooser controls. No form OnChange or command request is allowed in this flow.
   Hold one real fetched page response before delivery, with repeated click and
   disabled controls, then release it once to the same owner. A captured retired
   chooser element is clicked after cancellation and must send no request.
   Restore Description locally to its authoritative `Main warehouse` value using
   fill only, without Enter, then genuinely close that same form. This retires the
   setup/pages; clicking the captured retired page element must send no request.
   Prepare/read a fresh report after close. This covers **Close retirement**, not
   OnChange retirement. There is no Save command or assumed no-op Save path.
4. **5 requests:** naturally exit the host (the form is already closed), launch a new host,
   prepare new setup, read None after the receipt moment and fetch its second page,
   then naturally exit again. New setup/snapshot/cursors cannot reuse prior tokens.
   Opening now equals closing; receipt and expense are zero. No unknown-commit or
   host-lost receipt recovery is inferred from this restart.

Presentation assertions add no RPC: each displayed report/page is checked against
its real typed result. Day and Month cells must show the fixture's exact calendar
dates (`2026-11-11 00:00:00` and `2026-11-01 00:00:00`) without timezone conversion.
Generated resource headers are spaced for reading, with their original source
names still visible. The saved table is inside a labelled, keyboard-focusable
region, and every column has `scope=col`. Numeric and reference text remains exact;
the assertions do not import the renderer's date conversion as their oracle.

Exactly **46 business RPCs** are required. Only ordinary application/form
hello/snapshot reads are excluded from that plan, not setup/page requests. The
hard cap remains 180 total RPCs. No retry, skipped assertion or cap extension is
used to accommodate a slow or failing stage.

### Read-only form lifecycle

The existing view's input listener removes a raw draft when its value again equals
its authoritative snapshot. Close is a `data-form-action` control, so the preceding
blur does not flush a change; even a fallback change with no draft sends no RPC.
The normal close path validates an empty changes list and sends only `form.event`
close. The source form initializes `Dirty = False` and only its `Changed` callback
sets it true; no such callback is dispatched here. BeforeClose is not bypassed.
The acquisition asserts the exact owner SID, completed retirement and zero change
and command requests, then compares the independent audit. This does not claim
catalog Save is a no-op when field values are unchanged.

## Independent audit and boundaries

One read-only helper opens a source-bound launch snapshot, checks exact profile,
full files, metadata, database/generation binding, then reads every catalog,
document, section and movement row in one existing read lease. It checks exact
CatalogKey/DocumentKey, DateTime, Decimal and accumulation direction types and
creates a private-state fingerprint. Persistent keys are hashed in process, not
published. Audits before browser work, after each flow and around restart must
match exactly, including card/document revisions and all source/schema identities.
Each audit also proves the database file bytes did not change during that audit;
its file SHA256 is compared with the initial audit across all flows and restart.
It does not execute `InventoryReports`, Query, BSL or a posting handler.

Reports, choices and pages never write. The tests distinguish UI drafts from
saved rows, display-only labels from capabilities, empty references from no
filter, and detached pagination from a new read. They do not prove behavior under
concurrent external writers, outcome uncertainty injection or native modal UI.

## Execution and safety limits

The standalone `inventory-statement-browser-qa.yml` runs only on explicit reviewed
branch `codex/inventory-statement-browser-reviewed`, with repository read permission
and immutable commit checkout, no persisted credentials. It follows the existing
pinned Playwright 1.64.1 lock/install route without modifying system security.

- 220 seconds of work plus 20 seconds of owned cleanup; workflow acquisition 5 min.
- 180 RPC requests, 96 attachment requests; fetch 35 s, reply observer 50 s.
- Fixture subprocess 15 s and 16 KiB output, bounded by the remaining work budget.
- Strict verified Chromium sandbox on an ordinary non-root Linux runner.
- Only the owned loopback origin and exact attachment protocol; no redirects/retry.
- The sole attachment exception is an exact heartbeat HTTP 409 `busy` response.
- Real audited response bytes are held in a bounded exact-request map, then delivered
  unchanged. There is no second CDP response-body lookup and no fake response/state.
- Four PNGs, maximum 4 MiB each, and bounded redacted JSON result/manifest only.
- Process UID/direct-parent/group/start identity verified before cleanup signals;
  cleanup failure makes the verdict fail. Temporary profile, database and host
  files remain owned by this run and are removed, never uploaded.

`result.json` pins commit/tree and hashes the relevant runtime, frontend/assets,
source fixture, helper, contracts and standalone route. `manifest.json` binds that
result and the four PNG hashes. Files use exclusive creation, so stale evidence
cannot be silently overwritten. Diagnostics use closed phase/reason/class labels,
not raw exceptions, paths, responses, credentials or identifiers. On wire failure,
the first cause is retained before cleanup: closed request/fetch/status/body/json/
projection/privacy/observer/delivery stage, allowlisted method/status/reason and
capped byte counts only. Concurrent attachment failure cannot overwrite it. No
packet, body, headers, assertion actual/expected or exception string is exported.

Screenshots: `statement-pages.png`, `statement-filters.png`,
`statement-fences.png`, `statement-reopened.png`.

Fixture SHA256: `48092d41dc960d2b711443ad588b5e8b43fa94a8b8af93300fc708973dd6d8fa`
