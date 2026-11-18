# One compiled generator

Production Python-direct compilation now uses the direct Python AST generator
for modules, side-specific routines, source-owned callbacks, configuration,
posting, preparation and Execute/Eval. Unsupported compilation fails explicitly;
there is no retry through a text generator or interpreter. The separately
selected legacy interpreter remains supported.

`yadinassi.experimental_naked_collections` retains shared runtime values and the
`Program` container at their original identities. It no longer exposes
`prepare`, `compile_source` or `execute`. Its historical name does not imply a
second compiler. Other historically named helper modules remain where the new
AST compiler actually uses their value, reference or boundary semantics.

The old text generator is isolated in `tests/retired_text_compiler.py` for
historical repair and differential tests. It imports shared canonical runtime
objects, rather than cloning classes. Packaging includes only `yadinassi*`;
production neither imports nor discovers the oracle. Tripwires install a raising
fake at the removed production attribute, so a reintroduced caller still fails.
No tests are skipped to accomplish the retirement.

The execution-layer benchmark rejects `--bsl-route experimental`, even if the
old experiment environment variable is set. Use the public default/prepared
routes. Whole generated-source and AST compilation audit events occur genuinely
before effects. This does not restore historical per-fragment byte-event traces
or claim that those traces are identical to the retired text compiler.
