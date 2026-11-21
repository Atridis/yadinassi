> Historical research snapshot, not current publication status. Some listed gaps
> were fixed in later experiments. See [current Draft review guide](experimental-naked-review.md)
> and [chronological ledger](experimental-semantic-ledger.md) for current limits.

# UNSAFE naked direct-collection experiment

This is not a production backend, safety fix, or a shippable alternative.
`experimental_naked_collections` is never imported by production dispatch.
Preparation and execution both require the explicit environment switch
`YADINASSI_UNSAFE_COLLECTION_ABLATION=1`. Only disposable trusted local fixtures
were executed. Current PR CI was not interrupted; this experiment was not pushed.

## Starting point

A separate emitter translates whole synchronous modules/routines, loops,
conditionals, Try/Return, and native list/dict operations directly to Python.
Ordinary hot Add/Count/Get/Insert/index/ForEach code has no CollectionRegion,
HostFunction, VM hook, provenance, ABI, lease or `_method` dispatch. Helpers for
ambiguous/first-class operations do not establish full BSL compatibility.
Incoming native collections, aliases and cycles are not silently routed back to
the existing safe backend. Unsupported cases are reported rather than omitted.

Native representation is intentionally not the canonical external wrapper ABI.
The independent differential harness normalizes representation while preserving
bool distinctions, object aliases/cycles, missing variables and partial effects.

## Restore only demonstrated obligations

Each repair is independently selectable in `prepare(source, repairs=(...))`.
The empty default generates byte-identical source to the frozen bare emitter for
all 38 differential probes. No source-error layer, byref mechanism, resource cap,
GC suppression, policy/provenance/authority checks or unrelated repair was added.

| Flag | Reproduced failure | Added mechanism | Targeted timing, bare → repair |
|---|---|---|---:|
| typed_map_keys | True/1 and False/0 collapse; array identity keys unhashable | Map-only typed/identity key tokens retaining original keys | 1k inserts+gets: 0.806 → 1.506 ms |
| array_index_contract | Negative, Boolean and fractional indices accepted | Number/integrality/nonnegative/bounds check at actual list index | 2k indexed reads plus construction: 0.804 → 1.161 ms |
| array_insert_shape | Insert at 3 into empty array yields length1 instead of4 | Insertion position validation and Undefined padding | 2k in-bounds inserts: 0.886 → 1.233 ms |
| constructor_bounds | Negative array dimension silently accepted | Dimension number/integrality/nonnegative validation | 1k 50-item constructions: 0.328 → 1.100 ms |

The repair timing matrix uses seven alternating fresh-process trials, six
variants and twelve workloads; all 504 result controls agree. Submillisecond
numbers are noisy and the machine is not CPU-pinned. Unrelated-flag fluctuations
are not claimed as causal speedups. Preparation/cold startup are excluded.

## Differential results (fixed corpus)

| Variant | Same values/effects and success/error status | Exact including diagnostics |
|---|---:|---:|
| Bare | 22/38 | 18/38 |
| Typed keys | 24/38 | 20/38 |
| Index contract | 25/38 | 18/38 |
| Insert shape | 23/38 | 19/38 |
| Constructor bounds | 23/38 | 18/38 |
| All four | 29/38 | 21/38 |

Seven semantic failures are addressed. Error type/source/message remain separate
unrepaired obligations even when a newly rejected operation has the right effects.
These are not production-suite pass rates and do not prove a global minimum.

## Breadth, security and remaining work

Final prepare-only coverage of all 31 repository BSL fixture files: 6 prepared,
25 explicitly unsupported (including other object families and Execute). These
files were not executed. The earlier helper prototype prepared26 by deferring
unsupported constructors until runtime; that was not genuine broader support.

Remaining differential failures include Structure case semantics, Property
reference outputs, first-class method values, BSL truth conversion, presentation,
string ordering, typed Array.Find and routine byref. Eight separately added
boundary probes expose host reflection and byref alias/multiple/indexed/callback
failures; default arguments, scalar Val and collection Val alias controls pass.

Standalone has no shared VM authority interface: assignment policy, exact node
budgets, source budgets and prepared-source revocation are not enforced. A harmless
private host sentinel is accessible here but rejected by the production API.
Those are missing boundary contracts, NOT evidence that safety may be dropped.
The explicit opt-in protects production dispatch; it does not make the experiment
safe for untrusted programs or real configurations.

The prior broad ablation's 1,241 failing cases also establish byref, exception,
policy, lifetime and budget obligations. Neither that evidence nor these probes
justify rebuilding every removed per-node wrapper. Next work must add explicit
reference slots and source-aware error/service/authority boundaries, each with
failing tests first and separate cost measurements. No claim is made that the
four current repairs are complete or that their implementations are minimal.
