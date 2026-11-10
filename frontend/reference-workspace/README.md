# Reference Orders renderer

Opt-in, dependency-free browser client for `yadinassi-reference-orders/1`.
The existing Orders workspace and shared `mountForm` remain unchanged. One order
and one child choice form are supported. Only bounded display text, scalar form
values, opaque session IDs and local row IDs reach this client. Catalog references
and the selected order's persistent identity stay on the server.

Run `npm run build` here to produce the five closed static assets in
`yadinassi/ui/assets/reference-workspace`. The deterministic manifest hashes every
production source and output; no registry installation, CDN or external script is
needed. After approval of the exact test count, run
`node --test frontend/reference-workspace/test/*.test.mjs` from the repository root.

Customer and product buttons use ordinary `mountForm` commands: all owner drafts
are validated and flushed before the command opens a choice. The retained owner
is inert and inside a disabled fieldset while its child is live. The child has a
separate mounted form, dialog label and focus containment. Choose, Cancel and
Close use ordinary form events. Only an authoritative closed-child response
removes the child; the owner remains frozen until its ordinary read-only
`mountForm.refresh()` finishes. There is no unsolicited owner snapshot, custom
reference codec, arbitrary package selection or browser-side reference object.

The transport serializes all sessions, validates exact envelopes and revisions,
rejects crossed owners and reused session identities, and locks every form after
loss or uncertainty. No command, completion or refresh is replayed. Raw drafts,
server dirty state, open choices and pending recovery participate in the unload
guard. Discard is an explicit server-declared ordinary form command; the shell
cannot silently abandon an owner.

Tests use a small DOM contract double. They verify the interaction protocol,
state boundaries, generated assets and label identities, not browser layout,
actual native focus behavior or real 1C parity. Those require separate manual
validation.
