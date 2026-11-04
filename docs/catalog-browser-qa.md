# Opt-in catalog browser acquisition

This is a **reviewed, opt-in acquisition**, not a default PR/main CI test.
The accepted source-bound run is recorded in the
[catalog editor validation checkpoint](catalog-editor-validation.md).
The previous local environment failed
before page creation (0/8); its sandbox and filesystem restrictions are unchanged.
The separate `Reviewed catalog browser acceptance` workflow runs only when an
approved commit advances `codex/ui-browser-reviewed` in `Atridis/yadinassi`.

## Environment and authority

- One ordinary non-root GitHub-hosted `ubuntu-22.04` VM, not a privileged container.
  No sudo, sysctl, namespace, AppArmor, sandbox or filesystem-policy changes.
- Official npm `playwright` and `playwright-core` **1.64.1**, exact lockfile SHA-512
  integrity; `npm ci --ignore-scripts`. The reviewed Playwright CLI downloads only
  its version-bound Chromium/Chrome-for-Testing browser (revision **1248**,
  **156.0.8078.4**) and bundled FFmpeg helper (**1013**, not used by this harness), without `install-deps` or system package changes. Downloads
  during setup use the official npm registry, Python package index and browser
  vendor distribution endpoints; browser application traffic is only loopback.
- A single launch with `channel: 'chromium'`, `chromiumSandbox: true`; no custom
  browser flags, security bypasses, fallback browser, retries or external browsing.
  The browser PID comes only from its own CDP `SystemInfo.getProcessInfo`; same-UID
  and exact Playwright executable checks precede a bounded read of its Linux
  `/proc/<pid>/cmdline` (never an arbitrary PID/path). Only the verdict is exported,
  not raw argv or profile paths. The command line is checked for disabling flags,
  then `chrome://sandbox` must
  report a layer-1 sandbox plus seccomp-BPF. Unknown or negative status fails
  closed before any application scenario. Runner identity must be non-root.
- Exact `github.sha` checkout, read-only repository permission, no repository
  secrets, checkout credentials not persisted. Browser/runtime subprocesses
  receive an allowlisted environment, not CI tokens/proxies/debug hooks.
- Existing committed prebuilt Preact assets are served unchanged by the real
  `yadinassi.ui.local_app --f` launcher and persistent runtime child. No rebuild,
  mocked RPC, injected application state, SQL, native installation or user DB.

The public APIs document that Playwright sandboxing defaults to **false**, so the
explicit true value is mandatory. Browser versions are paired with Playwright;
using an arbitrary system Chromium is deliberately avoided. See official
[launch options](https://playwright.dev/docs/api/class-browsertype),
[browser installation](https://playwright.dev/docs/browsers),
[version-bound browser manifest](https://github.com/microsoft/playwright/blob/v1.64.1/packages/playwright-core/browsers.json)
and [GitHub-hosted VM documentation](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners).
Runner support does not guarantee this particular acquisition will succeed.

## Eight actual event flows

1. Launch with an emulated light OS preference and empty browser storage; verify
   the default theme is Dark. Choose Categories, inspect list, open an existing
   record and verify the full-width desktop sidebar, records and editor occupy
   three non-overlapping, vertically aligned columns at 1320 px. Catalog/record
   navigation is disabled with a visible explanation while editing. Return.
2. Create: duplicate code rejected; local draft retained; correct code and save.
3. Edit/save the created description and existing product's String, exact Number,
   Boolean and whole-second Date through visible controls.
4. Repeat completed Save twice: both report No changes, not duplicate creation.
5. With a dirty field, switch Light, Dark and System through the visible theme
   control. Verify the draft survives every switch and no RPC is sent. System
   follows the emulated OS light/dark changes without RPC or draft loss. Verify
   the desktop list preview and locked navigation; leave an explicit Light theme.
   Dirty close: dismiss confirmation and retain draft, then explicit discard and
   reopen unchanged persisted values.
6. Reload under an emulated dark OS preference: explicit Light survives, while
   the missing in-memory capability is reported. Verify local storage contains
   only `yadinassi.catalog.theme=light`, session storage is empty and no cookies
   exist. Return to the original launch URL in the same tab and reattach without
   replaying a write; theme and the storage-only preference contract still hold.
7. Existing reference remains visible/read-only. Restore Dark without RPC and
   capture the full-width desktop workspace. After reload, the records panel
   explains that returning to records refreshes its memory-only list preview.
   Capture a 390 px narrow viewport, asserting no horizontal overflow and that
   the editor appears before any visible sidebar/records panels.
8. Close database/process, reopen the same SQLite file in a fresh launcher,
   verify values again in the UI and close cleanly. Independent read-only backend
   audit after close checks exact row counts, scalars and preserved reference.

These assertions extend the same eight scenarios, not a ninth flow or another
browser acquisition. OS color preference is emulated through the browser API;
application state, theme storage and RPC responses are never injected or mocked.
Theme switches use the visible select. Only request counts and storage verdicts
are checked; request bodies, cookie values and storage contents are not exported.
The existing three screenshots show default-dark list, dark desktop editor and
narrow dark editor states. Light/System behavior is asserted in the same report.
Earlier accepted screenshots do not validate this redesigned UI; a new reviewed,
source-bound acquisition and inspection of all three images are still required.

The fixture is independently authored official XML from `tests/ui_catalog_fixture.py`,
materialized as a fresh owned temporary SQLite database using public backend APIs.
The import source is not a native/user configuration capture. No SQLite database
or browser profile is uploaded. Cleanup is bounded, and failure is not reported as
successful cleanup. Maximum acquisition time is four minutes, with per-action,
per-scenario and process-cleanup bounds; the job has a ten-minute setup envelope.

## Evidence and acceptance

The only uploaded files are `result.json`, `manifest.json`, `list.png`, `editor.png`
and `narrow.png` (14-day retention). No trace/HAR, raw request headers, launch URL,
profile, database, environment dump or full console stream. Diagnostics are bounded
and capabilities redacted. The result binds the exact Git commit/tree and SHA-256
of runtime files, prebuilt assets, fixture, harness and workflow. The manifest binds
result bytes and screenshots. Non-completed scenarios are never counted as passed.

A successful workflow alone does **not** close visual acceptance: independently
inspect all three actual screenshots and the eight-flow/source-bound report.
That can close this bounded catalog UI gate, not native GUI-event parity, standard
FormData/Write compatibility, remote client/server readiness or support for every
1C configuration. A failed/blocked sandbox acquisition leaves the GUI gate open.

## Offline checks (do not start a browser)

```
node --test tests/browser_ui/support.test.mjs
PYTHONPATH=tests:scripts python -m unittest test_ui_browser_qa_contract -v
PYTHONPATH=tests:scripts python -O -m unittest test_ui_browser_qa_contract -v
```

These validate admission/redaction/budgets/source policy and real owned fixture
create/reopen/audit. They do not substitute for any of the eight browser flows.
Publishing/advancing the opt-in branch is a separate reviewed execution step.

## First hosted acquisition (diagnostic failure, not acceptance)

Run `41539026234`, source `61852af36de6e74a0c069ea247d16abe04f4df70`,
launched browser 156.0.8078.4 with `chromiumSandbox: true`, but stopped at **0/8**
before the sandbox-status page or application flows. The original
`Browser.getBrowserCommandLine` diagnostic requires `--enable-automation`, which
Playwright 1.64.1 no longer adds. The reviewed replacement above observes the own
browser process without adding flags or weakening the sandbox/status checks.
No screenshots existed; the two-JSON failed report remains separate evidence.
