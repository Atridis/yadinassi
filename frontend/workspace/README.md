# Bounded Orders workspace renderer

Build both closed, dependency-free asset packages with `npm run build` here.
The workspace's five static assets live in `yadinassi/ui/assets/workspace`;
the original standalone form assets remain in `yadinassi/ui/assets/form`.
Source and output SHA-256 hashes are recorded in each build manifest.

The workspace owns one authenticated transport and a serialized RPC queue.
Each live form keeps a separate mounted `FormClient` and keyed DOM, using an
injected session-envelope transport. Switching tabs does not flush, refresh,
save, discard or remount. Hidden drafts and unresolved requests participate in
the aggregate unload guard. A malformed or lost reply locks every mounted form;
there is no reconnect or automatic retry.

The explicit intake-only **Discard new order** action asks the host to abandon
that session. It removes local drafts only after authoritative success. The host
refuses abandonment after a save attempt. Editor discard uses its ordinary form
command. Close every form before closing the workspace.

Unit tests use the existing small DOM contract double, not a real browser.
Run the approved test scope with `node --test test/*.test.mjs`.
Browser layout, actual focus transitions, and real 1C parity require separate
manual validation; these tests do not establish that evidence.
