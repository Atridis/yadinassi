# Typed scalar browser acceptance

This opt-in acquisition exercises `examples/configuration-scalar-editors` through
the real configuration host, its owned child server, SQLite and sandboxed
Chromium. It covers the bounded typed scalar editor contract, not native 1C GUI
parity, posting or a broader Date/Time storage profile.

## Exact reviewed route

Only advancing `codex/scalar-editor-browser-reviewed` starts this acquisition in
`.github/workflows/ui-browser-qa.yml`. All eight previous reviewed routes and
their artifact allowlists remain. No ordinary PR, main push, manual dispatch,
schedule, native job or user browser is involved. Actions remain pinned,
Playwright remains 1.64.1, permissions remain `contents: read`, and Chromium must
run with its verified sandbox under an ordinary non-root Linux account.

The checkout must be clean and `QA_SOURCE_SHA` must equal HEAD. The report binds
the commit, tree and tracked-file hashes, including the exact example, Python
projection, shared frontend sources, all four rebuilt bundles, acquisition,
contracts and this document. The same binding and clean state are checked again
after acquisition. The harness does not build or install anything itself.

## Four real scenarios, 56 business RPCs

1. **Product DateTime and preflight, 13 RPCs.** Create P2, edit AvailableDate to
   `2024-02-29T23:45:17` and save. A separate read-only process verifies the stored
   naive Python datetime and Decimal price. Excess price precision and an
   81-unit title are tested separately; each blocks Save without an RPC and
   leaves its complete raw text. Correct `8.5000` is sent once and the host's
   `8.50` is displayed. Clear AvailableDate to the existing typed zero, save,
   independently verify `datetime(1,1,1)`, then close the product normally.
2. **Document dates, references and real restart, 29 RPCs.** Create D1 with
   header `2024-03-10T02:30:00`, first-line DeliveryDate
   `2024-11-03T01:30:00`, and second-line DeliveryDate
   `2024-03-31T02:30:00`. These DST-looking values remain naive calendar values.
   Category C1, Product P2, exact quantities, labels and a checkbox coexist with
   date edits. Write, close both the document and Welcome, request ordinary
   application shutdown, and verify natural host exit. Independently audit typed
   datetime, Decimal, Boolean and CatalogKey values, start a new host on the same
   owned database, and reopen D1 through the catalog list.
3. **Isolated invalid drafts and retained tabs, 7 RPCs.** Create dirty sibling
   D2. On D1 test invalid calendar text, negative Quantity, excess fractional
   precision and an 81-unit Note independently. Each raw draft blocks Write,
   row selection and reference choice before any business request. Invalid date
   also blocks Close. Date and Note drafts survive switching application tabs.
   Corrections use exactly one normal Date, Quantity and Note event, respectively.
   Host snapshots must preserve both reference identities. No reload is used to
   suggest that unsent browser text survives document destruction.
4. **Held real reply and ordinary shutdown, 7 RPCs.** Double click D1's Write,
   holding delivery of the single real response only after the server completes
   it, the wire checker accepts it and its verified status is exactly `saved`.
   Navigate to D2 while it is held. Application Close and the originating
   form's disabled Close send nothing. Releasing that same response once must
   leave D2 visible and its dirty Note unchanged. D2's authored BeforeClose
   refuses closure; explicitly write D2, close every form normally, shut down
   the application, verify natural exit, and independently audit both documents.
   No forced discard or business replay is used to achieve PASS.

Each scenario has a cumulative exact RPC assertion. The hard cap is 100 business
RPCs, checked before admission. Attachment traffic has a separate cap of 96 for
elapsed-time-dependent heartbeats. Only a heartbeat HTTP 409 with the exact
`{protocol: "yadinassi-browser-attachment/1", error: "busy"}` envelope is delivered
unchanged; all other refusals remain fatal. Neither business nor attachment
requests are retried. Work is bounded to 220 seconds, followed by a separate
20-second verified-cleanup reserve.

Each intercepted business fetch uses the existing production transport's
35-second bound. The browser response observer is registered before the click
and allows 50 seconds: the click's existing 10-second bound plus that fetch and
a 5-second response-delivery reserve.
Both waits are clipped to the remaining global work budget. A 10-second
observer or 15-second business fetch could otherwise impose an artificial
cutoff below the production transport's deadline. Production still aborts its
own request after 35 seconds; attachment fetches retain their 15-second bound.
This is not a retry and does not extend the acquisition or cleanup deadlines.

The held-write scenario uses that same response-wait budget to reach the hold,
not a separate 10-second cutoff. Its exact originating session and Write command
consume the one hold gate at admission. The completed, validated response is
held for at most five seconds while synchronous native DOM clicks test late
navigation and Close. Those clicks do not remove `disabled` or `inert`, force
input, or wait for Playwright actionability on a disabled button. The originating
Close must still be disabled. Sibling navigation is checked immediately, without
a 10-second polling wait inside the five-second hold. Release happens in
`finally`; the matching real browser response and normal idle state are then
awaited before checking the retained sibling. No request is replayed.

## Safety and evidence

All network traffic is restricted to the current exact loopback origin and the
existing fixed asset/RPC paths plus `/attachment`. Tagged Date inputs are whole
seconds within the conservative scalar editor envelope. References use their
separate server-issued picker capabilities, not editable reference values or
UUIDs. Scalar descriptors have closed type-specific shapes. The existing
configuration-reference harness now accepts those optional descriptors while
retaining strict scoped reference-value validation and its original scenarios.

The seed/audit Python program has fixed modes and touches only this invocation's
fresh owned database. Audits use a new read-only SQLite backend and require the
database file hash to remain unchanged. DeliveryDate and Product are located by
schema field names, not old positional indices. No JavaScript Date parser,
timezone conversion, storage expansion or production workaround is used.

Only these artifacts are allowed:

- `result.json` and `manifest.json`, source-bound and hashed.
- `scalar-product.png`, showing the editable leap-day value and price.
- `scalar-document.png`, showing reopened editable header and table dates.
- `scalar-invalid.png`, showing retained invalid calendar text with the table.
- `scalar-independent.png`, showing the dirty sibling after refused Close.

Date/table inputs must be wholly inside the unchanged 1440×1100 viewport and
inside every clipping ancestor, including the table's horizontal scrollport.
Evidence capture uses ordinary scrolling to reveal the requested table column,
then aligns the topmost requested field with the top of the viewport. It does
not focus inputs, change drafts, resize the viewport or rewrite the UI. Merely
scrolling a header "if needed" is insufficient when it is already visible near
the bottom and the rows are still below the viewport. The safe screenshot is
taken before the visibility assertion so that a framing failure retains useful
diagnostic pixels; the assertion still fails the scenario and the run.

PNGs are capped at 4 MiB each and the report at 64 KiB. Failure diagnostics use
fixed phase/stage/status/refusal labels only. Separate phases identify typed
audit, restart, reopen, exact field checks, reference snapshots and evidence
capture. Known assertion codes match their fixed first line only; any appended
actual/expected diff is discarded. The current or last Save helper records its
fixed command/stage and separate booleans for request admission, body acceptance
by the wire checker, completed response delivery and a matching browser response.
Its verified StatusLabel is reduced to `saved`, `unchanged`, `rejected`,
`uncertain`, `committed` or `other`, with `not_received` before body acceptance.
Admission alone never implies a completed response. Both that verified status
and the visible field must be exactly `saved`; body acceptance alone also does
not imply that the frontend accepted or rendered it. No database, raw
request/reply, DOM dump, exception text, URL, capability, identity, trace, video,
profile or source contents are exported. Process ownership, group disappearance
and owned-directory removal are verified; cleanup failure prevents PASS.

The held flow separately records only the same closed status vocabulary and
booleans for admission, accepted body, entered hold, requested release, completed
delivery and matching browser response. Fixed phases distinguish waiting for
that reply, switching to the sibling, attempted late Close, release/receipt,
sibling verification, refused Close, evidence, each subsequent Save/Close and
ordinary application shutdown. Neither request count nor admission alone is
reported as proof that a completed reply was held or delivered.

Preparation and static contracts are not browser evidence. The 28 new offline
contract tests and mechanically adjusted legacy route contracts require their
own exact-count notice before execution. Real Chromium acquisition is a separate
four-scenario run on the exact reviewed route.
