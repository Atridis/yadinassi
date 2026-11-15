# Default snapshot migration experiment

The default is `compiled-strict` with the `snapshot` AST contract. This is a
change of selection, not a claim that every supported BSL program has already
been proven equivalent. The legacy `hybrid` mode remains a different, optional
loop compiler with fallback. Strict snapshot does not silently select it.

## Rollback and boundaries

Use `Interpreter(execution_backend='interpreter')`,
`execution_backend_policy('interpreter')`, or CLI/UI
`--execution-backend interpreter` for explicit rollback. Fresh UI processes
receive the selected backend explicitly, including interpreter rollback.
Context-local policy does not implicitly propagate into arbitrary new Python
threads; hosts must retain their existing explicit runtime-family selection.

An admitted snapshot fixes the version of program syntax. Editing the original
AST does not change an already prepared version. Runtime data, form values,
references, grants and budgets remain live. Dynamic code is admitted separately.
No guard, authority check, timeout, fallback rule or CI partition is relaxed by
this selection change. Explicit native comparison/oracle modes remain explicit.

## What the ordinary full CI proves

`build.yml` runs `scripts.test_partition`, whose reports check the selected test
IDs, missing/duplicate coverage and unittest success. Changing the default makes
unspecified `Interpreter()` construction exercise snapshot. However:

- Tests explicitly selecting interpreter/hybrid keep selecting those modes.
- Python-only tests and tests that never execute BSL are not compiled evidence.
- Helpers, factories and scoped policies affect selection; call-site counting is
  not execution coverage. Native scripts still default to the interpreter oracle.
- A successful process return code is not a witness of compiled execution or
  full semantic equivalence. Existing source-bound triage gaps remain separate.

A static AST inventory on the migration candidate found 895 direct
`Interpreter(...)` calls without `execution_backend`, across 401 test files;
58 explicit compiled-strict calls, 3 interpreter, 1 hybrid, 7 dynamic expressions
and 1 invalid-mode test. These counts exclude aliases, subclasses, embedded
subprocess source strings and runtime invocation multiplicity.

`test_default_snapshot` checks actual compiled block entry and zero fallback for
an unspecified backend, CLI default versus explicit rollback, and explicit
interpreter construction. UI selection tests also verify both modes across
fresh processes. These are representative witnesses, not whole-suite telemetry.

## Admission criteria

Keep this PR Draft until fresh light/native applicability and independent review
are satisfied. Run one ordinary full only when the shared full queue is free.
Require all mandatory six heavy shards, three packages and verdict on the exact
candidate, with admission/source binding verified. Preserve failing tests and
raw evidence; do not pin ordinary tests to interpreter just to make them green.

A green full is strong regression evidence for changing the default, not proof
of universal parity. Release assessment must also classify known snapshot triage
gaps, exercise real form/configuration and dynamic-code boundaries, and review
cold/warm performance separately. The interpreter rollback stays available.
