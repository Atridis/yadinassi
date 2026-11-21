# Owned synchronous file imports in the direct backend

The direct backend now has a bounded file/directory import bridge. It reuses the
canonical loader's path resolution, encoding, collision checks, directory staging
and family-local cache, but never routes imported source or routine bodies through
`visit`, `block`, `call_routine`, or the legacy execution backend.

## Contract

- Imports initialize before module statements. Successful loads are cached by
  canonical path; failed modules are not published. A successfully loaded
  descendant remains cached even if its importing parent later fails.
- Qualified calls use explicit namespace syntax and generated direct routines.
  Module/namespace objects and exported callable objects do not become ordinary
  BSL values or arbitrary Python receivers.
- Public routines, direct exported fields, local shadowing, read-only root names,
  references, default parameters and explicit omitted routine arguments retain
  their existing contract. Procedure/arity errors precede argument effects.
- Routine defaults are evaluated in the callee invocation, including optional
  parameters followed by required parameters. Immutable code does not retain an
  old activation or authorization.
- A child activation is created only after arguments succeed, uses its own module
  state and services, and is released and revoked after invocation. Same-side
  error-handler and Execute/Eval depth state is shared explicitly with the caller.
- Every boundary checks the current family generation, cache/namespace bindings,
  declared routine identity, root contract and caller activation. Closing or
  releasing an owner does not revive old grants on reopening the root.
- Definition-time loader/receiver identities prevent a lazy adapter import from
  blessing an earlier hook replacement. Foreign namespaces/cache state, subclass
  receivers and modified loader hooks are not accepted as capabilities.
- Prepared modules store owned syntax and import-name layout, not loaded modules.
  Preparing performs no file load or module initialization. Execution repeats
  admission and rejects a changed namespace layout before effects.
- Resource bounds are 256 cached/in-flight module slots and depth 64. These are
  Yadinassi safety limits, not claimed native 1C limits.

## Explicit limits

This is not full import-related language parity. Async bodies, Goto, DynamicNew,
unsupported database/service boundaries and imported ThisObject semantics remain
separate gaps. A qualified exported field can be read/written or indexed, but a
nested value suffix such as `Side.ExportedValue.Method()` is not yet routed as an
ordinary value. It fails explicitly rather than granting a generic host-object
adapter. Dual routines remain unavailable through an imported module receiver.

## Verification

All 77 pre-existing `test_imports` tests pass unchanged on the direct route and
in an explicit `compiled-strict` control. New adversarial tests cover
source/AST/prepared routes without VM dispatch, prepare without I/O, stale family
and namespace bindings, hooks installed before lazy adapter import, parent
revocation during argument/body evaluation, child/caller activation expiry,
metadata lifecycle, recursive calls, handler state, resource limits and failed
parent collection.

The old imports-error cohort contains 132 methods. Re-running it on exact parent
`e102e7fa54302e6742983bee41fc7718dfde9331` gives 161 errors; the candidate gives
33 errors and 3 failures. 99 previously failing method identities now pass, with
no new failing identities. This is a targeted cohort, not a whole light-CI result.
Two remaining failures assert legacy child-Interpreter construction counts. The
third exposes the pre-existing direct `FillPropertyValues` behavior: an isolated
Linux-target control without imports also returns `("old",5)` instead of the
legacy `("old",9)`. Those assertions were not weakened or skipped.

The integrated production changes passed 2,164 tests in both normal and optimized
Python 3.12 runs. The final 16-test adversarial suite also passed after splitting
the pre-lazy hook checks into independent fresh subprocesses. Python 3.10 passed
all 93 import tests in both normal and optimized mode.

Alternating frozen-worktree controls compared the parent and candidate using
service calls, scalar arithmetic and repeated prepared activations. Each process
recorded its actual package path and interpreter, with clean HEAD/status checks
before and after. A short activation result suggested overhead, but longer
repeats did not reproduce a stable effect; individual paired ratios remained
noisy. No performance improvement or stable regression is claimed, and no
speculative fast path was added from these measurements.
