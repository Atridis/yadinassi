# Posting application browser acquisition

Prepared opt-in harness: `tests/browser_ui/posting_application_browser_qa.mjs`.
Static contracts: 19 unittest methods. Browser acquisition: exactly 4 Chromium flows.
Preparation is not evidence of a successful run. The existing reviewed-browser workflow gains only the explicit `codex/posting-application-browser-reviewed` branch route and its closed artifact allowlist. No ordinary PR/main trigger is added.

1. Typed date/header/section edits, Write → Post → UndoPosting. Independent read-only SQLite queries verify the exact tagged scalar values, document date, authoritative Posted state and recorder-owned movement rows after each operation.
2. Double Write and double Open selected, a deliberately held successful open-record response followed by navigation to the dirty sibling, preservation of that sibling, dirty form and application close fences. The held reply is a harness network barrier, not a production fault switch or a retry.
3. The example's source `Note = "cancel"` BeforeWrite cancellation. The independent document/posting/movement query snapshot before/after must remain identical. This compares only the selected business columns, not journal, metadata or every database table.
4. Close every saved form, natural application/child-process shutdown, reopen the persisted database, verify typed values and unchanged SQL snapshot, then natural shutdown again. Forced cleanup cannot satisfy natural-shutdown acceptance.

The example uses the explicit closed `PostingApplication.xml` host manifest extension and fresh-only `document-recorder-forms-v1` physical13 profile. It does not claim native StandardCommand/FormWrite parity, AdditionalProperties continuity or same-object movement-buffer retention. Browser tests do not inject unknown commits or prove cross-process receipt recovery. Recovery fault cases remain in the separate Python/JavaScript suites; no production fault switch is introduced.

## Execution gate

Do not run until the exact focused contracts and 4 browser flows have been notified and explicitly released by the coordinator. Freeze and commit the whole source tree first. Run contracts separately before browser acquisition. The reviewed CI route reuses the existing pinned dependency and version-bound Chromium install steps, without changing security settings. Local preparation does not install or launch anything. Do not substitute a user browser. The harness refuses root execution and requires actual Chromium sandbox status and owned process identity checks.

The CI route uses its absolute owned `RUNNER_TEMP`, like the scalar/reference harnesses. For an authorized local run, set `RUNNER_TEMP` and `TMPDIR` to `/workspace/scratch/a04d1e5bf46b/ui-test-tmp`, `QA_PYTHON` to the approved existing Python interpreter and `QA_SOURCE_SHA` to the exact clean HEAD. Launch from the checkout using `node tests/browser_ui/posting_application_browser_qa.mjs`. A pre-existing artifact directory is rejected, not overwritten. The workspace path and owned short profile prefix must satisfy Chromium's Unix socket path budget.

The 220-second work limit has a separate 20-second cleanup reserve. Requests, response bodies, process output and artifact sizes are bounded. No network request may leave the owned loopback application origin. RPC fetches have zero redirects and retries. UUID/private host envelope leakage is rejected; record/form capabilities remain opaque. The independent SQLite helper does not transmit its internal database identifiers to the browser or report.

Artifacts are exactly four named PNG screenshots, `result.json` and `manifest.json`, under the owned runner artifact directory. Source commit/tree and file hashes, sandbox result, fixed-label verdicts and screenshot hashes are retained. Raw errors, environment, capability URLs, payloads and persistent identifiers are not logged. Source binding is checked before and after acquisition. No generated evidence is included in the repository.

## Exact business RPC plan

Expected business requests by flow are **12, 11, 5, 5**, total **33**. This excludes only application/form hello and snapshot reads, not rejected commands or form closes. Each ordered flow trace is asserted against the source plan; extra requests fail rather than enlarge the cap. The double-click checks independently assert exactly one Write and one Open selected RPC. The held reply must leave the original opaque form owner active. Local application-close refusal must display its exact notice, retain all panels and dispatch no business request.

RPC fetch timeout is 35 seconds and the response observer is 50 seconds, both clipped by the unchanged 220-second global work deadline. The 180 RPC and 96 attachment request caps remain unchanged. Only a heartbeat 409 response with exact `protocol`/`error` keys, expected attachment protocol and `error = busy` is accepted and delivered unchanged; no request is retried. Other refusals fail acquisition.
