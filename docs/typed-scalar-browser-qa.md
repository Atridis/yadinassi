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
   it. Navigate to D2 while it is held. Application Close and the originating
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

Date/table inputs must be inside the screenshot viewport, not merely present in
hidden navigation. PNGs are capped at 4 MiB each and the report at 64 KiB. Failure
diagnostics use fixed phase/stage/status/refusal labels only. No database, raw
request/reply, DOM dump, exception text, URL, capability, identity, trace, video,
profile or source contents are exported. Process ownership, group disappearance
and owned-directory removal are verified; cleanup failure prevents PASS.

Preparation and static contracts are not browser evidence. The 22 new offline
contract tests and mechanically adjusted legacy route contracts require their
own exact-count notice before execution. Real Chromium acquisition is a separate
four-scenario run on the exact reviewed route.
