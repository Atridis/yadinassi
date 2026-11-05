# Catalog ObjectModule pure scalar simulation v1

Status: **local simulation only; native parity = false**. This is a new, separate
infrastructure API. It does not implement ObjectModule activation or automatic
`BeforeWrite` dispatch. It does not call the BSL Interpreter, load source from a
path, accept a host object/backend/callback, or perform file/network/database I/O.
No `CatalogObject.Write`, importer, backend, recovery, CLI, or BSL global is wired
to this module. Existing `module execution unsupported` activation issues remain.

## Public boundary

`simulate_object_module(source: bytes, binding: ObjectModuleBinding,
snapshot: ScalarSnapshot, *, cancel=False) -> SimulationResult`

- Source must be exact bytes, 1 through 16,384 bytes. Every invocation freshly
  calls the existing static analyzer and evaluates only the IR it just produced.
  There is no public entry accepting `ObjectModuleAnalysis`, `IRNode`, AST,
  prevalidated handles, arbitrary paths, or executable Python objects.
- Binding is exact-type checked, bounded, and reconstructed with fresh UUID,
  schema and field instances before the analyzer sees it. All leaves must be
  exact bounded primitives; UUID integer payloads are checked without calling
  their truthiness/hash/equality hooks. The analyzer still checks the source
  hash, identities, schema, complete syntax, scope, call graph and static bounds.
- Binding is a caller commitment, not authenticated metadata provenance. No
  database or archived configuration is consulted. Hashing attacker-supplied
  replacement source into a new binding does not prove ownership or authority.
- `ScalarSnapshot(code, description, values)` is an exact frozen dataclass, with
  an exact tuple in schema field order. Missing, extra, mutable and subclassed
  containers are rejected. All fields are mandatory; there is no partial update.
- Public scalar fields are exact `str`, `bool`, `NumberValue`, or `datetime`, as
  required by the schema. External `Decimal`, `int`, `float`, runtime BSL values,
  catalog references, callables and general Python objects are rejected.
- `NumberValue(text)` contains exact ASCII fixed-point text with optional minus,
  no whitespace, exponent syntax, leading plus, non-ASCII digits, separators,
  NaN or Infinity. Length is checked before regex matching or Decimal creation:
  1 through 60 characters. Constructors do not grant admission; every call checks
  all fields again. Output uses canonical fixed-point text, without insignificant
  fractional zeros or negative zero.
- DateTime is an exact naive `datetime`, second precision, `fold=0`. The value is
  reconstructed without timezone callbacks; invalid fields admitted by Python's
  bytes-based datetime constructor reject with a closed category. No external `Decimal.as_tuple`,
  deepcopy, pickle, generic coercion, or arbitrary equality/hash/repr is used.
- Input Cancel is exact bool. The result contains a new immutable scalar snapshot,
  final bool Cancel, the separate simulation profile and `native_parity=False`.

Frozen dataclasses are not authenticated capabilities. Python code that can
monkeypatch this module/analyzer, change classes, or race `object.__setattr__`
inside the same process is outside this boundary. The private evaluator consumes
only a freshly generated analyzer result; it is not a validator or executor for
fabricated public IR. A future public IR intake would require independent bounded
full validation and source/IR consistency checks, not merely a matching hash.

## Explicit local semantics

This is a deliberately narrow simulation policy, not a claim about 1C behavior.
Every source branch and statement after Return is statically admitted before any
simulation, even though runtime evaluation visits only selected branches.

- Boolean conditions, `NOT`, `AND`, `OR` and conditional expressions require
  exact bool. AND/OR short circuit. Conditional expressions evaluate one arm.
- Decimal arithmetic is numeric-only. String addition requires two strings and
  performs bounded concatenation. No string repetition or implicit coercion.
- Equality/inequality requires identical scalar types. Undefined (`None`) is
  usable in locals and compares equal to Undefined, not to other scalar types.
  Ordered comparisons support only same-type numbers or strings. String ordering
  is Python Unicode codepoint order, not locale-aware/native collation.
- DateTime may be copied and compared for equality, but not ordered or used in
  arithmetic. No date literals or date constructors are added to the language.
- Each helper call has fresh local cells. Non-Val parameters alias the caller's
  initialized local cell; forwarding and repeated actuals preserve that identity.
  Val parameters have separate cells containing immutable scalar values. There
  is no copy-in/copy-out or memoized helper result.
- Return ends only the current procedure, using control flow rather than a
  caught language exception. A helper's Return does not return from its caller.
- All helpers see one private scratch field map. Code/Description lengths and
  Number(12,2,Any), Boolean and DateTime field constraints apply at every write.
  Number(12,2) accepts exact representable values only; it never rounds.
- The root Cancel cell remains bool even when forwarded through references.
  A Val helper parameter named Cancel is an ordinary separate local cell.
- Cancel=True does not stop subsequent simulation, roll back fields or imply a
  commit decision. Later code may change fields or set Cancel=False. The result
  reports the final scratch values and final flag.

## Numeric and resource bounds

The static analyzer retains all existing source/token/AST/nesting/procedure/local
and expanded-call-graph limits. In particular, source is 16 KiB, AST 2,048 nodes,
AST depth 48, procedures 16, parameters 8, locals 32 per procedure, and conservative
acyclic expanded syntax 8,192 nodes. No loops, recursive calls, host calls or
language exception handling are admitted.

The simulation adds independent limits:

- 8,192 runtime steps, charged before expression/statement evaluation, procedure
  setup, argument binding, and input field admission. Runtime costs deliberately
  do not rely on the analyzer's public `expanded_nodes` field.
- Call depth 16; expression and block depth each 48. The fresh analyzer graph is
  acyclic. Python RecursionError is also translated to resource_limit; there is
  no guarantee against arbitrary ambient recursion limits or process-wide OOM.
- Strings at most 1,024 Unicode characters; input strings must encode as UTF-8.
  Concatenation checks combined size and its byte budget before allocation.
- A cumulative 1,048,576-byte scalar-processing allowance. String cost is four
  bytes per character, conservatively covering UTF-8. Numeric and input scalar
  costs are also charged. This is an explicit admission/processing policy, not a
  measurement of Python allocator bytes or a process memory limit. Values/cells
  are additionally bounded by the finite fields, frame sizes and call depth.
- Private Decimal values are finite and normalized to at most 38 coefficient
  digits and at most 18 fractional places. Intermediate operations are checked
  before another operation can consume their result. Number(12,2) fields apply
  their narrower range and scale at every assignment and at input admission.
- Every simulation uses a fresh explicit Decimal Context: precision 80,
  ROUND_HALF_EVEN, Emin=-80, Emax=80, capitals=1, clamp=0, clear flags, and traps
  for Clamped, DivisionByZero, FloatOperation, Inexact, InvalidOperation, Overflow,
  Rounded, Subnormal and Underflow. Neither ambient Context nor DefaultContext
  supplies omitted settings; the caller's context/flags are restored on exit.
- Arithmetic uses explicit Context methods. Inexact division such as 1/3 fails;
  it does not silently round. `%` follows Decimal remainder with dividend sign.
  The rounding constant is explicit but no trapped rounding is accepted.

Before Decimal allocation, public numeric text has a bounded length and ASCII
grammar. IR literal numbers are also checked as bounded text. Their source was
already bounded before the lexer created its own numeric literals. Thus private
`as_tuple()` only sees bounded internally constructed/precision-limited numbers,
never an unbounded caller-supplied Decimal. The implementation does not depend on
CPython-specific `Decimal.__sizeof__` for safe admission.

## Failure and isolation

Closed error categories are invalid_input, source_rejected, invalid_ir,
type_mismatch, numeric_limit, division_by_zero, field_limit and resource_limit.
Messages contain neither supplied values/source/paths nor underlying exception
text. There is no successful partial result on failure. Inputs are not mutated;
partially changed private scratch state is discarded.

This is **copy isolation**, not native transactional atomicity, handler rollback,
write recovery, or protection from hostile Python already running in the same
process. KeyboardInterrupt, SystemExit and unexpected programming errors are not
swallowed as Cancel or converted into a successful snapshot. Only expected
analysis/decimal failures and recursion exhaustion are handled at their stated
boundaries. There is no wall-clock sandbox promise.

Importing the existing `yadinassi` package already imports its Interpreter. The
isolation claim is that simulation never invokes it or other I/O/backend APIs,
not that package imports themselves perform no filesystem reads.

## Verification and native gates

`tests/test_object_module_simulation.py` supplies local semantic, aliasing,
admission, hostile-value, numeric/context, budget, isolation and no-I/O tests.
Preparation of tests is not a test result. Independent security review and an
explicit approved command/count must precede execution. No 1C or Docker run is
needed to test this intentionally local simulation profile.

Adding the analyzer and simulation sources to the current catalog stack changes
the source inventory from 119 to **121**: 112 runtime package files plus nine
project/native files. Catalog schemas containing tabular sections are rejected
instead of being silently reduced to a scalar-only schema. The two
preprocessor budget test modules and UI asset provenance test update only their
exact inventory expectations.
The 512-file limit, complete aggregate hashing, source drift checks, native
observations and provenance fixtures are unchanged. A changed aggregate source
hash must be computed from actual bytes, not copied from older evidence.

Before any later automatic Object.Write integration, the independent gates in
`catalog-object-module-static-profile.md` still apply: owned native seed and
observations for dispatch, Cancel/exception effects on detached buffers, stale
and duplicate ordering, helpers/scalar conversion; metadata ownership inventory;
and separately reviewed receiver/reentrancy/transaction/recovery behavior.
In particular, uncertain-commit recovery must not replay a handler. This simulator
does not satisfy, bypass or weaken those gates and acquires no native evidence.
