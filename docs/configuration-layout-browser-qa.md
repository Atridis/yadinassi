# Nested configuration layout browser acquisition

This is a four-flow, opt-in Chromium observation of the committed
`examples/configuration-forms/layouts` application. It is **not native layout parity**.
Groups, horizontal wrapping, tab selection, focus retention and draft recovery
are renderer-owned. Inactive page fencing is **not server authorization**:
server admission separately enforces BSL Visible/Enabled/ReadOnly ancestry.
The acquisition neither exports a native 1C form nor emulates CurrentPage events.

## Reviewed route and limits

Only a reviewed push to `codex/configuration-layout-browser-reviewed` triggers
`.github/workflows/configuration-layout-browser-qa.yml`. It does not change the
other browser routes, run on pull requests, dispatch native jobs or request
write permissions. The route uses the existing locked Playwright 1.64.1 package,
Chromium sandbox and ordinary non-root Linux runner. No install or acquisition
has occurred merely because the route is present.

The harness rejects a dirty checkout and binds commit, tree and all relevant
runtime, renderer, fixture, harness, contract, workflow and documentation bytes.
The plain configuration launcher explicitly uses `--browser-session` so its
attachment URL and writer-generation protocol match the harness. It launches
only its own host and browser process groups; it uses an owned
runner temporary directory and restores the parent TMPDIR after browser launch.
The request origin/path and payload admission, attachment-generation checks,
96 RPC / 96 attachment ceilings, no retries, 220-second work deadline and
20-second cleanup reserve are fixed. The delayed response is the exact fetched
server response, never fabricated JSON.

## Four flows

1. Nested vertical/horizontal groups and accessible tabs retain raw text, the
   input node, focus and selection. Commands and Close cannot flush a draft on
   another page. Returning and explicitly applying updates the BSL summary.
2. A real completed command response is held briefly. Repeated click dispatches
   once; busy page clicks are ignored, not queued. A source command sets and
   clears group ReadOnly, and child effective state restores correctly.
3. Two retained instances keep independent page selection and drafts. BSL page
   visibility changes force deterministic fallback. Keyboard tabs and a 390px
   viewport are observed. Both forms close and the host exits naturally with
   code zero before the fault scenario starts a fresh host.
4. A completed real change response is verified then dropped before browser
   delivery. Transport lock stays in force. Local page inspection and exact,
   selectable raw-text copies remain available, while change/command/Close
   attempts dispatch nothing. This last fault host requires forced owned cleanup;
   that cleanup is not reported as natural shutdown or receipt recovery.

The exact business request plan has 3 + 3 + 8 + 2 = 16 events; hello/snapshot
reads and bounded attachment traffic are counted separately. Reference/table
page cases, nested Pages and malicious replica topology remain in Python/JS
regressions, not this ordinary String-form browser fixture.

## Evidence

Only four named PNGs, a redacted result and their SHA-256 manifest are uploaded
for 14 days. Synthetic fixture text can appear in screenshots. Raw RPC payloads,
capabilities, browser profiles, cookies, storage dumps, database files, native
material, paths, process IDs and exception details are never artifacts.
A report is PASS only when every flow and exact request plan passes, source
bindings remain unchanged, sandbox evidence is verified and cleanup completes.
Review the screenshots as well as the report before asserting visual acceptance.
