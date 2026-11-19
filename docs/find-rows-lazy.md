# FindRows: linear semantics and declared lazy indexes

Both the default direct compiler and isolated `native_bare_compiler` support
FindRows/НайтиСтроки with their own exact Structure representation. The default
also accepts the historical exact BSLStructure. Fields resolve once per query;
unknown fields fail explicitly. Empty Structure returns an empty array, as
pinned in `test_value_tables.py`. Results retain original row references and
physical table order. No legacy compiler/runtime fallback is involved.

`T.Indexes.Add("K,V")` declares an exact column set. Only a matching FindRows
builds that index; reordered filter fields select the same declaration. No
index is built by a write. A table epoch invalidates built results after
supported writes; schema version also participates. Rename preserves column
position, deletion removes affected declarations and shifts surviving ones.
Indexes.Clear removes declarations and buckets; Table.Clear invalidates data
but preserves declarations (the next matching query rebuilds an empty bucket).
Declarations are not capped. At most eight cached indexes/200,000 row-position slots
are retained; excess cache use evicts derived buckets, oversized bare tables
use the same linear search. Index declarations return a minimal
column-offset tuple, not the old CollectionIndex object; richer index object
APIs are not implemented here.

Default equality retains exact scalar types, including distinct bool/int/Decimal.
Bare uses its existing Python equality. Unsupported/opaque/nonfinite indexed
values or filters use the same ordered linear search, preserving short-circuit
errors without invoking opaque hash/equality in the default route. Buckets are immutable maps of position tuples, not alternate receiver objects.
Selected positions receive exact-int/range checks without scanning other buckets. Candidate matches are checked
again with the route's equality operation.

Supported mutation paths include row member/numeric/index setters, materialized
cells, table Add/Insert/Delete/Clear/Move/Sort, Fill/LoadColumn, schema operations,
and compiler region row writes/appends. Direct host modification of `rows`,
raw `list.__setitem__`, schema internals or search-cache internals is outside the
index mutation contract. Such private mutation must not be used between queries.
Bare bracket writes invalidate via its setter; reads remain native list slots.
Existing receiver validation and readonly slice mutation checks remain; cache
contents are private derived state, not a new externally supplied capability.

## Cost evidence (one isolated run, not a stable performance guarantee)

`benchmarks/find_rows_linear_lazy.py`; output assertions active, median 3–5
samples. Units milliseconds. Setup/preparation excluded from steady timings.

| N | default BSL scan | default BSL lazy | bare BSL scan | bare BSL lazy | class build | class steady |
|---|---:|---:|---:|---:|---:|---:|
|512|1.3824|0.5275|0.0447|0.0228|2.0561|0.0436|
|4096|7.5630|0.7789|0.3915|0.1656|9.6111|0.3310|

At 4096 rows, full batch writes then search cost 14.200ms; eight interleaved
single writes/searches cost 68.606ms. Lazy rebuild is deliberately poor for
interleaving. Equivalent Python list scan measured 0.352ms (512: 0.0182ms), but
Python equality has a different type contract from default scalar_equal.
The original default BSL repro was unsupported, so these are new linear versus
indexed comparisons, not a fabricated speedup over an executable old route.
No ordinary read/iteration rebuild or new read guard is added. Default public
entry/receiver admission still has its existing costs.

## No-search control against linear commit 429539f

`find_rows_mutation_control.py` ran three alternating fresh-process pairs,
9 samples per process. This does not overwrite the search measurements above.
Add includes clearing the table between samples; read uses ordinary get_member
and iteration with verified sums. All controls assert zero index builds.

Median paired candidate/linear ratios (ranges in parentheses):

| N | unindexed Add | ordinary read/iteration |
|---|---:|---:|
|512|1.051 (0.983–1.072)|1.028 (0.935–1.065)|
|4096|1.055 (0.981–1.072)|0.852 (0.584–0.859)|

With three declarations but no searches, candidate declared/plain median ratios
were Add 0.995/1.015 and reads 0.960/1.016 at 512/4096. The old linear commit
cannot declare indexes, so no fabricated old declared ratio is shown. These
short controls are noisy (especially 4096 read timing); no read speedup is
claimed. There is a small measured Add increase (~5% median), consistent with
added invalidation bookkeeping; declarations do not trigger rebuild work.

Cold cache capacity accounting now sums one retained row_slots integer for each
of at most eight entries, excluding the replaced signature. It never traverses
unrelated buckets. Unavailable (linear-only) entries retain zero slots.
