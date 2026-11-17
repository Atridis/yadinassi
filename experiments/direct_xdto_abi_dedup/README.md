# XDTO ABI requirement deduplication

The original eight module snapshots contain 68 class requirements / 783 fields,
representing 24 distinct requirements / 324 fields on d9607a7a. Initialization
merges only requirements with identical class, MRO and field-value identities.
Original module binding and quota checks retain their order. Conflicting class
snapshots remain separate. Every call checks every unique requirement anew.
The original snapshots hold all referenced objects, preventing identity reuse.

`measure.py xdto BEFORE AFTER` uses seven alternating fresh-process pairs, three
timed runs per case: 100 source local/global factory Create+Value operations,
and a source scalar loop control. Output hashes must agree. This measures a
source execution microbenchmark, not whole-application or native 1C parity.

First isolated run (results_pre_xml.json): local median 448.63 -> 349.02 ms,
global 328.90 -> 244.50 ms, control 106.16 -> 107.97 ms. Raw faster pairs were
4/7 local and 6/7 global; substantial shared-host timing variability means this
series alone is insufficient for acceptance. A confirming run after XML
integration is required before publication.

Safety coverage includes requirement union identity, preservation of module
checks, conflicting MRO/field requirements and warm-check class mutations,
plus existing source XDTO local/global/object/graph security suites.

## Confirming run after XML integration

On 4e0cdeb9 versus candidate 2191e36e: local 423.99 -> 331.47 ms
(21.8% lower), global 247.36 -> 195.02 ms (21.2% lower). Both targets
improved in all seven raw pairs and all seven target/control ratios. The scalar
control was noisy, 82.84 -> 92.37 ms; no claim of improvement is made for it.
The repeat supports the narrow optimization, not a universal application gain.
Timing includes source parsing/compilation via vm.execute, not only ABI checks.

The confirming driver requires clean exclusively owned worktrees, validates
unchanged HEAD/tree/status before and after the run, and records/validates the
actual imported yadinassi.__file__ for each child. Output was written outside
both worktrees until validation completed. Results and sources are retained.

Final integration: 151 XDTO/graph/object/XML/ABI tests pass in normal and
optimized Python. An independent read-only review found no safety blockers.
