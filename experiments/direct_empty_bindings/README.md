# Skip absent direct binding work, without an admission cache

This audit10 slice changes only four decisions:

- Do not enter persistent-routine resolution when the current registry has no
  binding for the requested service name. The ordinary host boundary still checks
  current authority before argument evaluation/call and after the host call.
- Return immediately from constructor/call admission when both sets are empty.
- Return immediately from recursive call validation when the call set is empty.
- Compute the union of server variable layouts only for a server-routine module,
  where it is compared. A client-only module never used that computed union.

No generated callee, wrapper, validation result, registry revision or authorization
is cached. Nonempty constructor checks, current contracts, complete group identity,
prospective registry validation and server initializer validation remain intact.

## Paired measurement

The immutable measured baseline is `ed6feafb30f5a1b734534b21ea5620bed92852b0`;
measured candidate `c162ef44b6aa037745b6c949468d35598c609689` applies only this slice.
The patch was subsequently rebased onto initializer commit `464c6d2f` and its
integrated correctness tests rerun. These timing numbers are the isolated slice
comparison before that rebase, not a claim that the post-rebase absolute times
were measured again.

Seven alternating fresh-process pairs in a coordinated CPU window. Each case
prepares one caller module, warms it once, then measures five executions, each
performing 10000 calls. The table reports the median of each process's median.
Setup, source parsing and compilation are excluded. All result checksums pass.

| Case | Before, ms | After, ms |
|---|---:|---:|
| StrLen, no persistent routines | 65.25 | 55.25 |
| StrLen, unrelated persistent routine | 67.21 | 59.08 |
| Persistent F(X)=X+1, one-function group | 158.13 | 95.00 |
| Persistent F, group of 500 functions | 741.21 | 385.94 |
| Same-module F control | 4.72 | 4.79 |

All seven pairs improved for the first four cases. The same-module control is
noise, not an improvement. The large persistent group remains much slower than a
same-module call: repeated group validation and wrapper creation are deliberately
still present. These results are not overall application/SQLite/UI speed claims.

Reproduce with the same Python and two worktrees:

```sh
python experiments/direct_empty_bindings/measure.py BEFORE AFTER
```

`results.json` contains every sample, baseline version, Python version and exact
result checks. The new empty-binding tests cover missing versus existing routine
bindings, current host registry, constructor replacement and post-call authority
revocation. Existing persistent/initializer tests retain their admission checks.
