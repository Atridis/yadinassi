# Owned form-result browser acquisition

This separate reviewed route observes four real Chromium flows of the authored
`examples/configuration-form-results` application. It is **not native lifecycle parity**.
The host runs with `--application-host --browser-session`. No callback or event
handler is invoked directly by the harness, and no synthetic response is substituted.

## Four flows and exact request plan

1. The startup owner opens its owned chooser, a user changes Result text, and
   Use value closes it. The real completed response is held briefly while a
   repeated button click is attempted. One owner update carries the Structure
   result and `Completion count: 1`; the owner resumes after child retirement.
2. While a child is live, the owner's input, Open chooser and Close are paused.
   Keep chooser open causes the real BeforeClose refusal: the child remains and
   there is no completion update. Clearing it and using ordinary Close delivers
   Undefined, not the previously refused selection, with one completion.
3. A second retained owner holds unsubmitted raw text while another owner opens
   and completes a child. The independent input and exact raw text survive.
   An explicit Refresh state discards that draft, then both forms and the host
   close naturally with exit code zero. A same-owner conflicting raw draft is not a browser claim:
   ordinary Open chooser flushes its visible drafts and the owned pause disables
   further edits. Same-field conflict/recovery remains covered by JS regressions.
4. A fresh host has an independent raw draft. The real Use value response is
   verified to contain child retirement, owner update and one completion, then
   deliberately dropped before delivery. The renderer locks, preserves selectable
   raw-text copies, and sends no further business event for disabled actions or
   Refresh. No callback is retried. The fault host needs forced owned cleanup;
   this is not natural shutdown or durable recovery evidence.

The exact business request plan is **3 + 5 + 6 + 3 = 17** events. Startup's source
OpenForm is not a browser RPC. Hello/snapshot reads and attachment requests are
counted separately. The finite request plan rejects accidental extra writes.
The report observes the in-process AdditionalParameters counter through the
source-authored message; it does not expose that object or claim generic identity
semantics beyond this flow. No native timing, modal-window or durable callback
recovery claims are made.

## Route, isolation and bounds

Only a reviewed push to `codex/configuration-results-browser-reviewed` triggers
`.github/workflows/configuration-results-browser-qa.yml`. Existing browser/native
routes are untouched. This route does not run on PRs or use write permissions.
Locked Playwright 1.64.1 and its matching Chromium run on an ordinary non-root
Linux runner with the sandbox enabled, without system/security changes.

The harness rejects a dirty checkout, binds exact commit/tree and all runtime,
frontend, example, harness, contract, workflow and documentation hashes, and
checks those bindings again at completion. Only owned host/browser process groups
and runner temporary directories are cleaned. A 220-second work deadline plus
20-second cleanup reserve, 96 RPCs and 96 attachment requests are hard bounds.
Fetches have no retry and no redirect. The only delayed/dropped reply is a real
server response. Heartbeat busy refusals pass through unchanged without replay.

Public artifacts are exactly four named PNGs, redacted result JSON and a SHA-256
manifest. Only fixed labels, booleans, counts and source digests leave the harness.
Synthetic example text can appear in screenshots. Capability URLs, raw payloads,
private callback objects, paths, process IDs, environment values, raw errors,
browser storage/profile, database files and native material are never artifacts.
Review every screenshot along with the exact source-bound result before claiming
visual acceptance. Preparing this route does not run tests or acquire a browser.

Command assertions use the exact bounded response bytes already audited by the
route, keyed to and compared with the delivered browser request. They do not
read the same body again through CDP after delivery, when Chromium may have
evicted it. This observer change does not retry RPCs, synthesize responses or
replace the response with current DOM/application state.


The four scenarios passed in [run 43005548423](https://github.com/Atridis/yadinassi/actions/runs/43005548423)
on source tree `4395466cb3f2a8e6148125b6f7daa7b788845361`, with 17 business RPCs
and 28 total RPCs. All 283 source hashes and four image hashes were checked;
Chromium namespace/Seccomp sandbox and natural host shutdown were observed.
This includes the real confirmed Close response lost before browser delivery:
flat owned-capability forms remained copy-only navigable without reopening the
transport or replaying any action.
