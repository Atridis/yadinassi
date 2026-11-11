# Typed input browser acceptance

Prepared acquisition source, not evidence that a browser has run. The dedicated
reviewed branch is `codex/configuration-value-input-browser-reviewed`.

Four scenarios use exactly **25 business RPCs: 8 + 6 + 9 + 2**. Snapshot/hello and
browser attachment traffic are counted separately under the total caps.

1. Quantity `15.125` is submitted as an exact Number string. Invalid local text
   sends no RPC. Hold the actual successful response while double-clicking OK,
   then deliver those same bytes; only one callback applies. Observe an authored CRLF reason as canonical textarea LF; cancel a nonempty
   multiline draft without changing the owner value. Confirm another reason
   untouched and verify its original CRLF in both the wire and authoritative
   response packet, not the unrelated single-line owner editor. Then confirm
   an empty reason.
2. Change Date to `2025-06-07T08:09:10`; verify exact 100-microsecond ticks (10,000/second) without JavaScript Date
   or timezone conversion, with a Pacific/Auckland browser against the UTC host.
   Cancel another date edit. Choose the second opaque
   ValueList row and inspect the authored callback's original-item identity
   message plus returned `urgent` value and cumulative callback count.
3. Keep both an authoritative sibling value and a distinct uncommitted raw draft.
   Input pauses owner/navigation. Escape explicitly cancels. A retained detached
   OK node cannot answer a later interaction. Sibling DOM/raw text survives;
   explicit refresh still obtains its authoritative value. Close both forms and
   verify natural host exit.
4. A fresh host confirms real Number `77.125`; discard that verified server reply
   before delivery. Retained scalar text remains read-only/selectable, and OK,
   Cancel, Enter, Escape and background commands cannot replay or blindly retry.
   Forced owned cleanup here is not claimed as natural shutdown or rollback.

All actions use real DOM and the actual application host. Only the real reply is
held/dropped: no fabricated response, direct callback, mutation of production state
or replacement runtime is used. Completion is read from `result.session/form`, not
invented child updates. Exact scalar/descriptor and opaque-ticket shapes are checked
independently; cancellation has no scalar value payload.

Bounds: RPC96, attachment96, work220 seconds plus20 cleanup. No network retries or
redirects. Chromium's ordinary nonroot sandbox and process identity/census remain
mandatory; no system/security changes. Source binding covers authored example,
runtime, frontend, harness/helpers/contracts and reviewed workflow. Outputs are
four fixed screenshots, bounded result and manifest, with fixed diagnostics only.
No capability URLs, headers, session/ticket identities or raw errors are exported.

Offline static contracts:18. Chromium scenarios:4. No executions occur while
preparing these files. Native keyboard/pixel parity, durable recovery and raw draft
survival across reload are not claimed.
