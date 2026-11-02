# Catalog editor validation checkpoint

The reviewed runtime/UI source checkpoint is local commit
`8d84369d5bc1ea05d549321812250f41bbcd9d43`, tree
`a6c75af014bff8677f2762505cfb80180625d1e7`, based on main
`f2509f0386422b50f4990cf1b3a882a40a1b9978`. The publication preserves all
39 reviewed file hashes and additionally carries the exact PR192 diagnostic
test blob `dc06d93262708e08e2872ba86745d0d11bc22eb9` plus this note.

## Verified locally

- Real owned SQLite create/edit/save/close/reopen; exact decimal/date/Boolean
  fields, preserved read-only references, original-revision conflicts, repeated
  Save, cancel/close and exact uncertain-intent resolution.
- Independent source review closed four integrity/lifecycle findings: aggregate
  text patch ordering, whole pipe-exchange deadline, adoption only after scalar
  patch installation, and retaining uncertainty after transient resolution errors.
- Changed-seam gates: 50 normal + 50 optimized Python tests, then final 30 + 30
  after the last editor/renderer changes; 12 independent JS client tests. Earlier
  broader 83 + 83 runs preceded those reviewed fixes, not a final full-suite claim.
- Deterministic prebuilt assets and exact 107-file runtime provenance. Final wheel
  built without network, installed in an isolated target, resources/hash/entrypoint
  checked outside the source checkout with existing project dependencies.

## Still open: actual browser acceptance

**0 of 8 planned browser scenarios executed. No screenshots or visual acceptance.**
The owned sandbox-enabled Chromium process failed before page creation because
this execution environment refused a required socket operation. The one approved
execution-environment escalation then failed during read-only mount setup,
before the QA command ran. No browser security flags were weakened and no further
bypass/retry was attempted. These are environment blockers, not evidence that the
application itself fails or passes its browser flows.

The pending gate covers visible list/card navigation, create/duplicate correction,
edit/save, repeated Save, dirty-close/discard, same-tab capability reattachment,
close/relaunch/durable reopen and narrow-screen layout. It needs a functioning
permitted browser environment. CI/headless tests are not substitutes for this gate.
No GUI actions have been silently added to CI. Full CI/composed-source native
provenance gates are also separate from the local tests above.

This is an experimental bounded scalar autoform editor, **not a completed GUI MVP,
full managed-form compatibility, native standard Write/FormData or native GUI event
parity**. See [the executable contract and limits](catalog-editor.md).
