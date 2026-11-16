# Closed Python scalar execution

The translated backend now admits whole scalar routines and maximal closed
statement ranges in modules or mixed routines. This is not a legacy/compiler
switch or a global removal of guards. The early per-node write-through slot
prototype has been superseded by these closed regions.

## Representation

Eligible regions are ordinary Python functions with local variables and direct
return/break/continue. Decimal arithmetic fast paths preserve BSL helpers for
operators whose semantics differ from Python. An error-location register and one
conversion boundary preserve ordinary exception positions and partial state.
Calls, references, object/collection services, Execute/Eval and await remain explicit
runtime boundaries. A range never speculates through them; the next range resolves
current storage and authority again. No completed service is replayed.

Loops amortize a region entry. Very small routines keep the existing translated
call boundary rather than adding a full lease after generic activation; a static
node threshold controls straight-line specialization. This is not interpreter
fallback. A future direct-call graph is distinct work, not claimed here.

## Admission, lifetime and invalidation

* Admission proves all consumed owned AST nodes **and containers**, source/binding
  budgets, exact scalar values/storage and trusted runtime/hook ABI.
* Policy/context subclasses, custom hooks, detailed instrumentation, references,
  unsupported values and unsuitable live scope use ordinary translated execution.
* Other Python threads, custom signal handlers or registered GC callbacks make
  entry ineligible. These entry filters alone are **not** a TOCTOU guarantee.
* Automatic cyclic GC is suspended during final admission and closed execution;
  the original enabled/disabled state is restored on every exit. Previous results
  and touched values must be exact scalars, avoiding reference-count finalizers
  inside the closed calculation.
* A live lease rechecks scope, family, ABI, node/container authority every 64 loop
  headers and before publication/error/return. Unexpected changes invalidate the
  region and reject explicitly, without replay or publishing uncommitted results.
* Publication uses the ordinary `set_variable` authority service for each write,
  with renewed checks. It does not bypass a policy/reference change after the
  region check. A newly rejected storage boundary fails closed.

This is not an atomic transaction or a claim of arbitrary concurrent VM safety.
Previously permitted writes may remain if a later write is refused. Normal
policy/budget contexts retain their exact per-node accounting. Concurrent
revocation has explicit regression coverage, including threads created **after**
entry, but unrestricted native/unsafe host mutation is not a Python sandbox.

Prepared regions belong to their compilation unit, including retained routine
units. Source/binding accounting and lifetime release include their functions and
owned operands. Ineligible or unprofitable optional plans do not grant authority.

## Evidence and tests

`python_sync_routine_calls` records whole-routine entries. Closed block ranges
record `python_sync_segment_calls` and actual `python_translated_blocks` entries.
Admission-node counts never prove execution; coalesced execution does not claim
observed per-node coverage. Exact node-coverage tests explicitly request
`DETAILED_INLINE_STATS`. Native evidence v3 adds whole-sync calls while preserving
historical v1/v2 validation and immutable source inverses.

Tests cover scalar/operator/error parity, module and local storage replacement,
byref exclusion, exactly-once services, source budgets, retained-unit lifetime,
revoked nodes and containers, partial errors, budget hooks, GC state, and mid-loop
concurrent authority changes. General/instrumented translation remains independently
covered; matching scalar controls alone is not full application or native parity.

`benchmarks/python_scalar_regions.py` is a small warm-loop probe, not the complete
60-case resume2 suite. Use alternating fresh processes, exact commits, the same
pinned environment and no concurrent test/profile load. Keep raw data and report
cold preparation, small-call and collection tradeoffs separately. Exploratory
measurements before the final invalidation checks are not final performance claims.

## Direct fresh collection regions

Closed functions now also translate creation of Array, Map and Structure, their
built-in collection operations, index access, Structure fields and ForEach.
Canonical BSL wrapper identity is preserved, but hot operations manipulate its
Python list/dict directly. They do not call `runtime.call`, construct HostFunction
objects or run per-node VM hooks. Small value-semantic helpers preserve typed map
keys (True and Decimal(1) differ), structure key normalization, bounds, insertion
limits and iterator mutation diagnostics.

The entire newly created graph stays unpublished during the closed region.
Aliases and nested acyclic collections share real storage, not copy-on-write
snapshots. A conservative preparation-time alias/write graph rejects potentially
cyclic stores before any effects. Those programs keep ordinary translated
execution and normal GC; some provably acyclic programs may also decline because
the analysis deliberately does not forget aliases after rebinding. Exact scalar inputs may enter; pre-existing mutable collection inputs,
by-reference Property outputs and first-class extracted methods remain explicit
translated boundaries. This is a broad fresh-graph slice, not a claim that all
collection programs have been converted. Existing foreign objects are never
adopted speculatively and a failed region is never replayed.

Ordinary errors publish the same partial graph and convert at the original source
location. Authority invalidation suppresses unpublished graph results. A weak
identity registry avoids keeping abandoned collections alive; a lease accepts only
its own produced identities during successive output publication. Collection and
constructor registry ABI is audited with the existing scope/authority checks.
External publication still uses ordinary storage authority, not an atomic commit.
