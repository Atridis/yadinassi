# One compiled generator

Production Python-direct compilation now uses the direct Python AST generator
for modules, side-specific routines, source-owned callbacks, configuration,
posting, preparation and Execute/Eval. Unsupported compilation fails explicitly;
there is no retry through a text generator or interpreter. The legacy
interpreter is no longer available.

`yadinassi.execution.codegen.experimental_naked_collections` retains shared runtime values and the
`Program` container at their original identities. It no longer exposes
`prepare`, `compile_source` or `execute`. Its historical name does not imply a
second compiler. Other historically named helper modules remain where the new
AST compiler actually uses their value, reference or boundary semantics.

The old text generator and oracle are not shipped, including in tests.
[Their archived source](https://github.com/Atridis/yadinassi/blob/713fb157cac984d8918681524848efa5f64f6b70/tests/retired_text_compiler.py)
can reproduce old experiments, but is not an execution or test option.
Tests of observable behavior use the direct engine and independent expectations;
production isolation tests still reject imports of test code or the old emitter.

The execution-layer benchmark rejects `--bsl-route experimental`, even if the
old experiment environment variable is set. Use the public default/prepared
routes. Whole generated-source and AST compilation audit events occur genuinely
before effects. This does not restore historical per-fragment byte-event traces
or claim that those traces are identical to the retired text compiler.
