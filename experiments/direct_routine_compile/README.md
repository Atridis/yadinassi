# One compilation for persistent routines

Baseline 6b060d62740a14ac549feea7de63259a17771bbe compiled the entire module,
then compiled its declarations again to get exportable functions. Both phases
ran source lowering and Python source-map compilation. This caused the measured
cold regex regression. The direct compiler now emits a private bind-only argument:
after creating routine definitions it can return exports before executing module
statements. Global initialization is skipped in that mode. The same code object
serves normal execution and fresh per-execution binding; no VM/closure is cached.
The stored plan copy explicitly has no last_state/output.

Final five alternating pairs on the unchanged regex source: median **843.19 to
485.87 ms (-42.4%)**, including three fresh Interpreter/execute/close operations per
process, excluding process startup/import/source read. All 42 records are checked.
This restores most of the cold cost introduced in the previous slice, not a
promise of faster general execution. No validation processes overlapped the
saved final run. Raw results: results.json.

Reproduce using before/after worktrees and the same Python:

```sh
python experiments/direct_routine_compile/measure.py BEFORE_WORKTREE AFTER_WORKTREE
```

118 targeted tests pass normal and -O; independent review passed 66 optimized
tests. Coverage includes one compilation for source/prepared declarations,
code-only persistent state, live globals, byref, no module replay, definition
source diagnostics, prospective admission, original regex reuse, managed profile
and neighboring configuration/database/form boundaries. Full six-scenario server
and NoContext limitations are unchanged. No full CI/native parity claim.
