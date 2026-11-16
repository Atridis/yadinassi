# Owned identity and leaf dispatch experiment

Baseline: `777bdb3a5c55543751a6b13b743e2bb808217c65`.
Candidate implementation: `39e162f0186ad17f5849a505edee793f421a97c6`,
tree `d42b6a80641945ff1fc09f4caf54fb5156424482`.
All measured source trees were clean. This later evidence commit changes no runtime.

## Result: retain separately, no demonstrated general speedup

44 sequential fresh-process samples on the same shared unpinned host/venv:
ABBA strict for all six fixtures, additional BAAB for collections and strings,
and one explicit interpreter control per source/fixture. A=baseline, B=candidate.
Each process uses -I -B and a new empty pycache prefix. See orchestration scripts
(machine-local paths retained), environment and raw samples, including CPU times,
source/fixture hashes, outputs and counters. Observation timeouts55s/35s are not
acceptance thresholds. Production gate remains20s.

| Strict workload | Baseline median s | Candidate median s | Change | Samples/source |
| --- | ---: | ---: | ---: | ---: |
| collections | 23.500796 | 22.836154 | -2.83% | 4 |
| functions | 2.001440 | 1.916399 | -4.25% | 2 |
| values | 3.809735 | 3.718855 | -2.39% | 2 |
| numbers | 1.538459 | 1.497672 | -2.65% | 2 |
| strings | 1.379822 | 1.516851 | +9.93% | 4 |
| dates | 1.161944 | 1.129602 | -2.78% | 2 |

Collections ranges overlap: baseline23.063103–23.849780s,
candidate22.519664–23.971092s. Strings regression in the main series cannot be
discarded. A separate six-run strings diagnostic (baseline/full/ablation reversed)
flipped full-candidate versus baseline ordering; small samples/host drift prevent
causal attribution. Ablation `94655f21f7d9492b1ddfcb74a0ce49ecf7469c19`
removes combined identity guard while retaining preparation/leaf changes. It is
diagnostic only, not an independently validated release candidate.

All six fixture outputs match between sources and explicit interpreter controls.
Strict translated counters are positive and recorded fallback/rejection/helper
counters zero; interpreter compiler stats empty. This is local equality, not
native compiled parity. Strict original20s collections gate still FAILS at
20.007867s. gate JSON binds exact clean source, fixture and harness SHA to explicit
compiled-strict; generic error string is `interpreter_timeout`.

Candidate remains a separate experiment; it is not included in PR336 on the
strength of these measurements. No universal or substantial speedup is claimed.

## Change and safety checks

Combined verification reads exact private type, current weak registration and
provenance, then current VM versions/origin/view identity on every entry. Kind is
consumed immediately for accounting; no proof is cached across a hook or yield.
Pre-hook leaf resolution still requires post-hook verification. Default returns
remain verify_node→None and _verify_owned_identity→original. Mutable/FULL monitor,
guards, live rights, budgets, byref and strict no-fallback remain intact.

Preparation root/module filters determine kind once per node with identity-only
comparisons. Leaf dispatch avoids empty-dict allocation and repeats type() once
less; local-leaf precedence remains intact.

401 compiler/runtime tests PASS27.932s;137 contract/context tests PASS3.462s.
Suites overlap and must not be added as unique tests. The broad suite ran before
one additional mutable test was added; the latter is included in137. Independent
review49/49 PASS1.048s plus mutable/OwnedList probes, no concrete blocking findings.
New tests cover hook-time plan/provenance/version revocation, fabricated/foreign
identity, snapshot/FULL/mutable contracts, local-leaf precedence and original
return semantics. No full/heavy CI was launched. Native/light results for777bdb
must not be attributed to candidate39e162.

Raw samples SHA256:
`c58ddbf5a13e21d44b29b49f00ec3797a2ca7d3fe96eb6992a3dcc6abf5b46cf`.
All saved file hashes are in checksums.json. Offline executor's unpublished work
remains of unknown availability and was not overwritten.
