# Configuration reference browser acceptance

This separate opt-in route exercises the authored
`examples/configuration-reference-application` with the real configuration host,
its child server process, SQLite, and sandboxed Chromium. It does not claim native
1C choice-event, posting, or standard-form-write parity.

## Closed acquisition

Only advancing `codex/configuration-reference-browser-reviewed` runs this harness
in `.github/workflows/ui-browser-qa.yml`. The previous seven routes, acquisitions,
and artifact lists are unchanged. No ordinary PR, main push, dispatch, schedule,
native fixture, or user browser is involved. The route keeps pinned actions,
Playwright 1.64.1, `contents: read`, and the existing unprivileged runner.

The harness requires a clean checkout and exact `QA_SOURCE_SHA`, binds the source
commit/tree and file hashes, and repeats those checks after the scenarios. Its
inventory includes all runtime files, the four new reference modules, shared
application/form/attachment sources, the exact example, harness and contracts.
There is no build during acquisition.

## Four scenarios

1. **Catalog reference selection, 20 RPCs.** Create P2 through the real form.
   Filter Categories to C1 and choose it. Open another picker with an unmatched
   filter, cancel, and compare the full typed previous value. Clear and save the
   typed empty, confirm it in a separate read-only SQLite process, then choose C1
   and save again. Reference text remains read-only.
2. **Document references and restart, 23 RPCs.** Create D1 with Category C1 and
   Lines.Product P2, quantity 3.25 and a checked line. Write and close forms, then
   request ordinary application shutdown and verify the owned process group is
   gone without a signal. Independently verify exact CatalogKey types, catalog
   targets, record identities, Decimal quantity, and product price 7.25. Start a
   fresh host on the same owned database and reopen D1 in Chromium.
3. **Retained picker and sibling, 14 RPCs.** Open D2 and submit its dirty header
   draft. Open D1's Category picker, request ordinary connection reconciliation,
   then perform a real browser reload using session resume. The picker ticket,
   owning session and prior typed reference must match. Cancel keeps C1 and D2's
   authoritative dirty draft. Capture the picker at 390 pixels wide. This does
   not claim that unsent input survives document destruction.
4. **Repeated apply and late intents, 10 RPCs.** Filter D1's picker to C2, double
   click Apply, and hold only delivery of the real completed response briefly.
   Late sibling navigation and Close must send no business request or change the
   visible owner. Release the same response once, save D1, then click the retired
   DOM button after switching to D2; it must not retarget the sibling. Dirty D2
   refuses Close, keeps its draft, and is then explicitly written. Close every
   form and the application, verify natural process exit, and independently audit
   both persisted documents, including D2's typed empty Category.

The exact plan is **67 business RPCs**, with a fail-before-admission cap of 100.
Attachment calls have a separate cap of 96 because heartbeats depend on elapsed
wall time. Only a heartbeat's HTTP 409 with the exact attachment-protocol
`{protocol, error: "busy"}` envelope is passed through unchanged: an admitted
business request may hold the server's ownership gate. The bounded `heartbeatBusy`
counter records these replies. No heartbeat or business request is replayed, and
all other refusals remain fatal. Work is limited to 220 seconds, plus 20 seconds for verified cleanup.
No failed or uncertain business request is retried. Network routing admits only
the current exact loopback origin and the existing fixed paths plus `/attachment`.
The wire checks closed action schemas and server-issued picker/choice identities;
it rejects persistent UUIDs in either direction.

## Evidence and limits

Only `result.json`, `manifest.json`, and four PNGs are uploaded:
`reference-product.png`, `reference-document.png`, `reference-resumed.png`, and
`reference-independent.png`. Images and the result are hashed and size-bounded.
Wire-failure diagnostics contain only fixed validation-stage labels, an allowlisted
HTTP status and refusal code, and the in-flight business validation stage. Unknown
values become fixed sentinel labels. The first failure is captured before abort;
concurrent cancellation cannot replace it with a secondary failure. Reference
table-column descriptors and scoped reference values have separate strict shapes.
No database, browser profile, source contents, raw DOM, trace, capability, cookie,
request/response payload, or exception text is exported. Every database and browser
profile is fresh and owned by that invocation. Cleanup verifies process groups
and temporary-directory removal; cleanup failure prevents PASS.

Preparation alone is not browser evidence. The 18 new Python contract tests are
offline source checks. Run them and the six mechanically updated legacy contract
files only after the exact test-count notice. The real four-scenario acquisition
must be launched separately through the reviewed route.
