# Cached source-reference addresses

The live-state emitter now creates one `_SlotReference(state, key)` in a generated
Python local for each static module name used as a source-reference argument.
This replaces repeated allocation, not live binding semantics. There is no
runtime cache dictionary, VM dispatcher, added guard layer or cross-run cache.

Every binding still checks whether the variable exists and whether its current
value is a canonical `Reference`. Canonical references get a fresh forwarding
wrapper, exactly as before. Caching that binding decision would be wrong:
`F(x); ReplaceXWithCanonicalReference(); F(x)` must make the second call write
through the newly installed getter/setter, not overwrite the dictionary slot.
The address cache handles that transition and transitions back to ordinary
values. Aliases, retained host references, callback deletion, error partial
state and repeated prepared-plan runs have focused tests.

Tradeoff: each module invocation eagerly allocates one slot per static name,
even when the source routine using that name is never called. It never reads
that name during allocation, so an undefined variable still fails at argument
binding, before callee effects, rather than during module setup. Private local
reference cells, indexed/attribute references and dynamic host references are
unchanged.

## Measurement

Seven alternating process pairs, 10,000 iterations each, no thresholds. The
public default API includes parsing/preparation; the prepared variant excludes
preparation. Result controls agree in every case. Scripts and raw results are
in [`experiments/direct_cached_refs/`](https://github.com/Atridis/yadinassi/tree/713fb157cac984d8918681524848efa5f64f6b70/experiments/direct_cached_refs).

| Case | Public before / after ms | Prepared before / after ms |
| --- | --- | --- |
| Source byref | 13.082 / 10.599 | 7.197 / 5.903 |
| Source by-value | 5.119 / 4.851 | 3.130 / 3.343 |
| Arithmetic | 3.534 / 3.276 | 2.381 / 2.464 |

Byref median time falls about 19% public and 18% prepared. Public paired
before/after ratios range 1.098–2.142; prepared range 0.967–1.497, including one
reversal. This is measured evidence, not a universal speed guarantee. By-value
and arithmetic generated hot paths do not change; their differences are noise,
not claimed improvements. Forty-seven focused tests pass. No broad compatibility
or security sandbox claim is added.
