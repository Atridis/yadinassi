# Owned dialog browser acceptance

Prepared source-only lane; no browser or native result is claimed by this file.
Dedicated reviewed push route: codex/configuration-dialogs-browser-reviewed.

Four scenarios, with exactly 17 business RPCs (2 + 6 + 6 + 3):
1. Ask confirmation, retain a real Yes response while double-clicking; owner
   stays paused until delivery. Exactly one callback and shared parameters.
2. No, Cancel, warning Continue; greeting unchanged, cumulative count 2/3/4.
   Escape sends no answer in this host UI; not native Escape parity.
3. Independent owner raw draft and DOM identity survive first-owner Yes/count5.
   Explicit refresh discards that draft, both forms close, host exits naturally.
4. Fresh host, independent raw copy, real confirmed Yes response discarded before
   delivery. Family locks copy-only; no replay, refresh or mutation follows.

The example control is QuestionButton, not AskButton. WarningButton dismiss is
`application.answerDialog` with answer=dismiss. Callback results are read from
result.session/form, with updates=[], not owned-child completion updates.
Question callback arity2 and warning arity1 are evidenced by application results;
this does not replace native acquisition or claim native input parity.

RPC cap96, attachment cap96, work220s plus cleanup20s. No transport retries or
fabricated replies. Audited response bytes are retained until consumed; delayed
and dropped responses come from the actual backend. All XML/example, runtime,
frontend, helpers, harness and workflow sources are hash-bound. Only fixed
failure codes/counts are exported. Four fixed screenshots plus result.json and
manifest.json; no capability URLs, headers or error stacks. The ordinary nonroot
Chromium sandbox and owned process cleanup are mandatory. Forced owned cleanup
after the fault scenario is not evidence of natural application shutdown.

Offline contract count:16. Chromium scenario count:4. No tests/browser/install/CI
were run while preparing this source. Enter/default/X native behavior and durable
callback recovery are not claimed.
