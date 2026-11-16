> Historical review surface for snapshot 5c9157ed. The next broad direct-state
> slice and associative serialization integration are described in
> [the current audit report](direct-python-audit.md). Earlier test counts and
> benchmark files below refer to their own recorded source, not the new tree.

# UNSAFE research branch: direct BSL to Python, NOT FOR MERGE

This Draft is a review surface for Codex, not the next production backend.
Production dispatch, default backend, native fixtures and CI policy are unchanged.
Both preparation and execution require explicit
`YADINASSI_UNSAFE_COLLECTION_ABLATION=1`. Run only trusted disposable fixtures.
Do not point this experiment at external code or expose it as a service.

## What is in this snapshot

Direct Python functions/control flow and native list/dict operations, with
individually selectable repairs documented in `experimental-semantic-ledger.md`.
BSL routine and variable namespaces are distinct. Dynamic canonical HostFunction
arguments use lexical Python cells and actual Reference objects only where the
live argument metadata requires them. Services bind once. Typed Map keys,
Structure names, array methods and selected scalar/error semantics have concrete
regressions. Array construction/Insert resource limits are narrow arithmetic
checks; no production VM collection-dispatch wrapper is imported.

SharedBoundaryContext fixes nested/concurrent loop-header counter reset; the
legacy context remains an intentionally weaker comparison variant. Literal
native Python string ordering is a documented experiment variant, not a claim
of exact 1C collation or a policy decision for production/grouping/filtering.

## Important missing contracts

- No complete source admission, generated-source/aggregate/retained-unit budget,
  ownership/release lifecycle, mutable-AST monitoring or VM authority integration.
- Loop-header budget is **not** exact AST/NoContext execution accounting.
- Module values are snapshots, not the VM's live module namespace. Host writes
  and retained references do not yet have full module-state parity.
- Private locals do not publish VM scope; full configuration/import/system-value
  resolution and all interpreter service markers are not implemented.
- Dynamic `obj.Method(...)` reference-signature discovery is not implemented.
- Same Program object's output/last_state telemetry is not thread-safe.
- Full BSL/native compatibility and end-to-end performance are not established.

The unfinished authoritative-module adapter is deliberately excluded. Its first
correctness prototype made a synthetic module loop about 11x slower, so it is
not being presented as an acceptable solution. Likewise no admission prototype
is smuggled in as a finished security boundary.


## Trusted local resource policy (clarification)

Artificial collection allocation caps are **not a required repair for trusted
local execution**. The current benchmark explicitly excludes `resource_bounds`.
Native Python allocation failures/OOM remain possible; this is not a sandbox.
Do not restore an element-count quota merely to satisfy a test of our own quota.

The bounded helper remains an explicitly selected diagnostic/control variant,
not the default trusted policy or proof of a globally minimal safety requirement.
Its origin is local Yadinassi policy: Insert growth in commit `23a4d3617` and
Array construction/dimension limits in `301cecc24` (2026-10-18). The source itself
states these are not native-1C limits. In production they are constructor/growth
limits, not a maximum collection size: ordinary Add still appends. They were not
conditioned on shared hosting. Shared-host isolation is a separate contract to
specify, not a reason to impose the same quota on every local program.

Small tests prove that the trusted variant does not inherit a patched quota;
they do not allocate dangerous sizes or attempt to provoke an actual OOM.
Required BSL shape/index/type semantics remain a separate question from quota
policy. Production #336 is unchanged by this research clarification.

## Reproduce locally

Install the repository's normal pinned dependencies in an isolated environment.
From the checkout root:

```sh
PYTHONPATH=.:tests python -m unittest discover -s tests -p 'test_experimental_naked*.py'
PYTHONPATH=.:tests python -O -m unittest discover -s tests -p 'test_experimental_naked*.py'
PYTHONPATH=. python experiments/naked_translation/benchmark.py
```

At the current checkpoint the prepared source passes 152 focused tests both normally and
under `-O`. Full/light/native CI is NOT claimed. The earlier frozen checkpoint's
38-case differential corpus had 37 exact interpreter matches and one explicit
native-string-order difference. These interpreter controls are not fresh real
1C evidence. Historical benchmark samples in the ledger name their own scope;
re-run the included small paired benchmark for the current checkout.

## Codex review brief

Start from direct Python, not from restoring the previous VM wrapper stack.
For every proposed restoration: give a concrete failing program, its observable
semantic/security requirement, the smallest simpler alternative, and paired
cost with equal results. Keep actual safety requirements; do not hide gaps via
blanket eligibility gates, silent fallback, disabled tests or changed native
fixtures. Prefer compile-time lowering and Python data structures. Do not claim
a globally minimal implementation without evidence. Investigate cheaper live
module storage, narrow admission/lifetime contracts, and service boundaries;
separate demonstrated correctness from hypotheses. Do not merge this Draft or
connect it to production dispatch merely because focused tests pass.
