> Chronological research ledger. Earlier sections describe earlier variants,
> not current guarantees. [Current Draft review guide](experimental-naked-review.md)
> is the entry point. Publication adds a safe huge-index diagnostic regression
> (no Decimal-to-int expansion while formatting an error): 150 focused tests
> pass normally and under `-O` on the publication tree.

# Naked translator: semantic restoration ledger (isolated, unpublished)

This is an experiment, not production admission or a globally minimal runtime.
No VM dispatch, provenance walker, graph reconstruction or blanket fallback was
restored. Each row records an observed contract and the chosen local mechanism.

| Observation | Local mechanism | Why not raw Python / limitation |
|---|---|---|
| Extra Get/Set/Insert/Delete arguments lost effects | Compiler-known invalid argc emits receiver/argument evaluation followed by a simple catchable TypeError | Correct calls receive no arity wrapper. Unavailable methods reject before arguments. Exact native/Python arity wording intentionally differs; synthetic signature stubs were removed for simplicity |
| Map.Delete() deleted an Undefined-key instead of failing | Same invalid-argc path | No dummy None argument is substituted |
| Set(-1, Host()) rejected before Host | Small actual Set operation receives evaluated key/value before checking bounds | Python's function argument evaluation preserves order; no VM node wrapper. Statement-level expression lowering could avoid this function but is not implemented/measured |
| Structure.Get/Map.Set and unknown native methods were admitted or fatal | Compile-known allowed native kinds replace the existing type branch; error branch raises the native catchable diagnostic | Valid calls get no new resolver. Foreign objects still go through explicit capabilities |
| Grouped source routine lost byref writes | Unwrap grouped direct callees consistently in compiler analysis and emission | Actual Interpreter confirms grouped direct-call semantics, including Structure.Count; earlier contrary review hypothesis was withdrawn |
| Map member was incorrectly treated as key indexing | Known Map property read/write produces the proper error; Map index access stays separate | Does not widen host reflection or change Map key equality |
| Structure field case, spelling, duplicates | Tagged dict stores casefold key -> (original spelling, value), actual-key validation, one composition version | Plain dict + lowercased key loses observable spelling. No sidecar/lifetime graph. Static dot reads fold at compile time; writes still pass through the small structure operation |
| Array method extracted then receiver variable reassigned | Canonical HostFunction bound to the original list, allocated only at extraction | Compiler substitution using the current variable is incorrect. Direct native calls still bypass extraction machinery |
| Collection used as condition; numeric AND/OR returned operand | Narrow bool/Decimal truth conversion in boolean contexts | Literal bool/Decimal cases fold during compilation. Count/UBound return Decimal when scalar repairs are enabled |
| Find treated True and 1, or distinct equal lists, as equal | One linear typed lookup at actual Find; collections use identity | Returns Decimal index or Undefined. Arbitrary host equality callbacks are not implicitly invoked |
| String-left addition exposed Python formatting | Native collection labels plus existing pure numeric/boolean presentation and surrogate-safe concatenation | Existing algorithms are called only at this operation; no old VM dispatch. Unsupported host __str__ remains denied |
| UCA ordering versus raw Python | Two isolated measured alternatives; final sorting/key policy is pending the user's follow-up about sorted(key=...) | No production comparator, native fixture, grouping, filter or collection-key policy has been changed |

## String evidence and boundaries

The historical Windows fixtures are genuine owner captures from 1C
8.3.27.2342, according to `tests/fixtures/native_windows/README.md` and
`integrational_tests/meta.md`. We did not run a fresh real-1C measurement here.
Specific captured evidence: `numbers.out` records `Min("a","A")="a"`,
`Min("я","Я")="я"`, and the source-backed `"a"<"A"` result true while equality
is false. Python codepoint order reverses those case comparisons.
`strings.out` independently records case-insensitive StrCompare("ЁЖ","ёж")=0.
StrCompare is not the `<` operator and is not silently changed by this experiment.

Separately verified against the current Interpreter (not labelled real 1C):
`apple<Banana`, `арбуз<Банан`, `ё<ж`, and `a_b<a-b` are true under its UCA order
and false under native Python order. Both order `1, 10, 2` lexically rather than
as natural numbers. Ordinary mixed-case and Russian words are affected, not only
rare Unicode characters. Thus switching order can change branching, Min/Max,
range boundaries and which result is selected first, not just display order.

Exact equality, Map keys and typed Find are separate contracts: `A` versus `a`
and composed `é` versus decomposed `é` remain distinct. A sorting key must not
become a grouping/filter/equality key automatically. Existing ValueTable and
query key semantics were not modified.

Production `compiled-strict` and `interpreter` remain unchanged. Their current
comparison semantics must be checked together when an experimental policy is
integrated: a fast path and fallback must not silently select different orders.
The standalone variant presently uses Python string operators inside a narrow
scalar admission helper; it does not invoke unknown host comparison callbacks.
Its selection is provisional pending the sorted(key=...) investigation.

## Verification scope and remaining issues

The initial UCA-assisted experiment matched all 38 fixed-corpus status/value/
effect controls and 37 exact diagnostics. The retained error is Map composition
mutation leaking Python's iterator RuntimeError rather than the BSL diagnostic.
Do not count a deliberate alternative string order as a reference-equivalent pass.
The native-order variant must report that disagreement separately.

Expanded integrated Structure/method tests exposed and motivated additional
Map-property and Property source-position repairs after the fixed corpus passed.
A passing 38-case corpus is not full language coverage. Dynamic HostFunction
reference signatures, some protocol markers, resource/provenance/authority VM
integration and other earlier experimental gaps remain unsupported. No full
light/heavy or real configuration has been run through this backend.

Costs are recorded separately for error-only compile paths, raw alternatives
that are semantically wrong, warm operation overhead and end-to-end workloads.
The earlier approximately 3 microseconds UCA versus 15 nanoseconds raw result is
one warm comparison of short strings, not sorting a list. `sorted(key=...)`
computes one key per element and needs its own measurement.

### Follow-up decisions and measurements

Keep-it-simple direction applies beyond sorting. Error-only synthetic Python
signatures and qualified-name tables have been removed. Invalid argc now evaluates
receiver and arguments, then raises a clear TypeError; exact implementation-specific
wording differs deliberately. The tests retain effect order and catchability,
not a fabricated matching message. Real native fixtures are untouched.

Known Map iterator RuntimeError is now translated only around `next()` of the
native Map iterator. RuntimeError from the loop body or a host service is not
relabelled. Native Python timing for composition changes remains the limitation;
no Map version registry was added. This restores catchability, not just wording.

The sorting follow-up measured Python `sorted` on 10,000 synthetic strings:
raw 2.84 ms, lower-key 4.64 ms, casefold-key 4.13 ms, simple Russian ё-key 15.52 ms,
existing ValueTable UCA6 key 161.86 ms. These are separate from the UCA10 operator
experiment. On the chosen native-backed pair sample, raw/lower/ё/UCA6 matched
136/142/149/153 of 153 relations. None of those counts proves general equivalence;
selection of an application sorting key remains explicit, not a silent change
to relational operators, equality, grouping or filters.

For associative serialization, pair order is not required. Do not sort merely to
match 1C emission order. Contents, distinct typed keys and values, roundtrip and
format compatibility still must be verified; normalizing through a Python dict
must not collapse Boolean/Number keys or hide lost entries. The isolated backend
does not yet implement the complete native serializer, so this is an integration
requirement, not a claim of completed serialization compatibility.

### Identity-safe native/host split

A concrete exploit was reproduced before the final run: a host metaclass whose
`__eq__` always returns True impersonated a native list in `type(x) in types`,
and `obj.Add(7)` invoked an unauthorized host `append`. The existing type branches
now compare integer type identities. Known classes remain strongly referenced by
the generated namespace/module, so this is neither a persistent authorization
registry nor a permission cache. No host equality/hash hook participates.
Adversarial tests cover methods, indexing, iteration and scalar admission. This
repair protects an actual capability boundary, not an implementation diagnostic.

Final review also replaced `isinstance(x, Decimal)` in array numeric adapters
with exact native Decimal admission: a Decimal subclass had executed its own
`to_integral_value`/`__int__` without host authorization. No new adapter layer
was needed. Dead prototype `_method/_new/_get/_set/_iterate` helpers were removed.
A separate ordinary contract probe restored missing Map index -> Undefined using
Python `dict.get`; Structure missing-field behavior remains an error.

Final focused verification for this checkpoint: 113 tests pass normally and
under `-O`; 13 unchanged-production smoke tests pass. The frozen 38-case corpus
has 37 exact reference matches plus the explicitly separate native-string-order
variant difference. There is no remaining accidental diagnostic difference in
that corpus. This is not a full suite pass or production readiness.

Seven alternating trials of eight independently selected repair combinations
across fourteen established workloads produced 784 matching numeric controls.
Targeted operation costs (2,000 iterations unless stated otherwise): Structure
field access/update 0.775 -> 2.670 ms versus the case-sensitive raw dict variant;
typed Find over 16 elements 1.426 -> 3.103 ms; numeric truth 0.638 -> 0.792 ms.
Extracted bound method calls take 3.706 ms; the old variant fails that scenario,
so it is not a valid speed comparator. No universal speedup is claimed.
The identity-safe admission microcheck measured approximately 92/103 ns for
list/map versus the exploitable equality check's 66/75 ns, including common
Python loop/call overhead. The security difference is real; this is not an
end-to-end application timing.

Final runtime hashes and all raw measurements are recorded with the isolated
experiment results, alongside the script, controls and unsupported variants.
No real native fixture or production comparison/serialization implementation
was edited, and this checkpoint is not published.

## Isolated dynamic-reference and resource-boundary checkpoint

This checkpoint is still opt-in and unsafe for production. No native fixtures,
production translator or string/serialization policy were changed.

| Reproduced failure | Added mechanism | Simpler alternative / limit |
| --- | --- | --- |
| Canonical HostFunction byref was rejected; aliases and live metadata are observable | `dynamic_host_refs`: ordinary lexical Python cells only for possible Name actuals; canonical `Reference` only when current per-argument metadata requests it | Raw values fail alias/write tests; universal `_Cell.value` is avoidable. Non-lvalues stay raw values. Direct `obj.Method(...)` signature discovery is not implemented. |
| Nested `Program.run` resets the outer header budget | `SharedBoundaryContext.enter/leave`; reset only when no activation is active | Legacy BoundaryContext remains a diagnostic variant, not a repaired concurrent context. |
| Overlapping entries must not each reset or overspend the common budget | Short lock around entry, charge, revocation and exit, never around user callbacks | This is loop-header accounting, NOT exact AST-node accounting. No claim that a lock is globally minimal. |
| Direct New Array / Insert bypass real resource limits | `resource_bounds`: bounded slot/child-array arithmetic before int conversion/allocation; same helper for extracted Insert | No BSLArray wrapper, object registry or VM dispatch. Enormous Decimal exponents are rejected before integer expansion. |
| Full shape traversal for no-argument Array was expensive | Empty allocation proof plus two live-limit checks, then native `[]` | No dimensions, slots or child arrays need traversal. Exact resource diagnostic wording under invalid custom limits is not preserved. |

Dynamic HostFunction and its metadata are trusted embedding capabilities, as in
the interpreter. BSL cannot manufacture an arbitrary callable capability. Metadata
is read per argument, not snapshotted before an earlier argument's callback.
Omitted arguments are rejected before argument effects. The targeted differential
suite uses the current interpreter as its reference, **not a real-1C run**.

Measured local costs: 100k integer increments with lexical cells 3.78 ms versus
10.70 ms with universal `_Cell`; ordinary fast locals 4.03 ms in the same small
probe (noise, not a claim lexical cells are faster). 1000 dynamic value calls
1.611 -> 1.724 ms; 1000 reference calls including writes 1.997 ms. Empty native
Array: old value-only helper 107 ns, bounded proof 175 ns, canonical BSLArray
1855 ns. Explicit Decimal zero still traverses validation, 893 -> 1611 ns.

Seven alternating paired runs of 10000 loop iterations / 10001 charged headers:
legacy context 3.109 ms, shared/concurrent accounting 4.942 ms. This approximately
59% overhead is disclosed; concurrency correctness is demonstrated, global
minimality is not. Numeric results match in every measured execution.

Verification: 149 focused tests pass normally and under `-O`. New tests cover
canonical ref identity, non-lvalue arguments, live signature mutation, aliases,
undefined Name, omissions, explicit constructors, array bounds before host call,
nested/concurrent budget entry, cleanup after exceptions/revocation, wrong-thread
exit, resource caps before allocation, extracted Insert and argument effects.
Independent review found no blocking shared-accounting/resource-integration issue;
it identified an exact-message difference for invalid custom caps, documented
above rather than restored solely for text fidelity.

Remaining consequential gaps: module values are still final-copy snapshots;
retained References update lexical cells but not that exported snapshot. Host
callbacks do not yet share all live module writes. Same Program object execution
is not claimed thread-safe for `last_state`/`output` telemetry. No complete VM
scope/retained-unit ownership/admission caps or exact NoContext AST metering is
provided by this checkpoint. Those are not replaced by the header budget. No
security/compatibility completeness or production readiness is claimed.
