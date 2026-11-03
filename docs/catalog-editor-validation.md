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

## Actual browser acceptance

**8 of 8 actual browser scenarios passed and all three screenshots were inspected.**
The accepted [GitHub-hosted acquisition](https://github.com/Atridis/yadinassi/actions/runs/41540067548)
used source `4cd655e3b42ff567ab8a53d917c6727f6c75ae31`, tree
`24ce595d5b47888b53518ed71ce51b5315c9fa5d`. Its UI runtime, renderer source and
prebuilt assets are byte-identical to PR195 source
`2fc271a913ec7ade6ffcc1d8534a1b6febb5205c` (tree
`4359f1fd6f5af91e8f3e56448e3eb0d9a6a8f049`).

- Chromium `156.0.8078.4`, Playwright `1.64.1`; non-root runner, sandbox explicitly
  enabled, own-process command checked, layer-1 sandbox and seccomp-BPF verified.
- Real visible list/card, duplicate correction and create, scalar edit/save,
  repeated Save, dirty-close/discard, reload/reattach, read-only reference and narrow
  layout, then process close/relaunch and durable reopen. No mocked RPC.
- Independent post-close backend audit confirmed two categories, three products,
  exact decimal/date/Boolean values and the preserved reference. Diagnostics empty.
- Artifact `13186381322` contains only two JSON reports and three PNGs. ZIP SHA-256:
  `6443dfbf7912d41bd45b785ee467bf0a70e9e3f3dfd493a1f662f668c748900f`.
  Independent source/artifact/visual review receipt SHA-256:
  `8bf62c2a400e30608cc77324b224cd3764ddf338e5ab9c45c73b3d0542e2edd6`.
- Desktop and narrow layouts were readable without blocking overlap or clipping.
  TODO: the decorative fullwidth plus before New record is a missing glyph with
  this runner's font; the visible label and action work. This is cosmetic.

The acquisition workflow is opt-in for `codex/ui-browser-reviewed` only, not a
default PR/main GUI job. See [the reviewed harness](catalog-browser-qa.md).

### Historical blocked attempts

The first local attempt completed **0 of 8** scenarios and produced no screenshots.
The owned sandbox-enabled Chromium process failed before page creation because
this execution environment refused a required socket operation. The one approved
execution-environment escalation then failed during read-only mount setup,
before the QA command ran. No browser security flags were weakened and no further
bypass/retry was attempted. These are environment blockers, not evidence that the
application itself fails or passes its browser flows.

The first hosted acquisition `41539026234` likewise stopped at 0/8 because its
command-line diagnostic required an automation flag not added by the pinned
Playwright version. The reviewed own-process diagnostic fixed that observation
without changing launch/security flags, before the successful run above.

## Integration with current main

The composition retains the accepted UI runtime/assets unchanged and incorporates
main `c2e33b12516713c57b7626d7faf82277fe35ed5d`, tree
`053163b4abfc3aac44da18edcdb6adfec10c1159`, including HTTP and catalog Query.
The exact provenance inventory is now **110 files**: main's 101 plus four UI Python
modules and five packaged assets. The closed asset allowlist and protocol limits
are unchanged. The 107-file count above describes the original UI-only checkpoint.
Composition tests, full CI and source-bound native provenance are separate gates;
the earlier browser acquisition is not represented as a new run on this union.

This is an experimental bounded scalar autoform editor, **not a completed GUI MVP,
full managed-form compatibility, native standard Write/FormData or native GUI event
parity**. See [the executable contract and limits](catalog-editor.md).
