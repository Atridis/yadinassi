# Direct host access: audit9

Baseline: 31d65378662fa3909565218863986cbec8274495 (single-compilation fix already
included). The real generic host-array route scanned 16 RU/EN namespace aliases
at each owner check; BSLArray.Get additionally built method dictionaries and a
HostFunction only to call the canonical get method.

Two small changes:

* An identity frozenset replaces the singleton linear scan. VALUES retains strong
  references to all canonical objects; no identity reuse or receiver grant cache.
* Exact BSLArray/BSLFixedArray Get/Получить selects existing value.get directly.
  The invocation closure stays: it checks current runtime before the call after
  argument evaluation and again after execution. Canonical checked_index, alias
  identity, FixedArray readonly behavior and Find's typed equality are unchanged.
  No array conversion/copy, new array representation or legacy VM dispatch.

## Measurements

Five alternating before/identity-only/combined rounds on Python 3.12.14, with no
concurrent tests. Baseline methods are reconstructed from the pinned git source;
only these two methods are swapped. Full samples are in results.json.

| Operation, median ms | Before | Identity only | Combined |
|---|---:|---:|---:|
| Prepared processing of 2000 StrSplit tokens via Get | 35.104 | 32.890 | 25.016 |
| Original regex_family, prepared complete replay | 52.423 | 52.795 | 51.691 |
| Actual Kind Description | 9.427 | 8.813 | 8.572 |
| Actual Kind Save | 28.276 | 28.651 | 28.177 |
| Actual Product Description | 8.829 | 8.454 | 8.896 |
| Actual Product Save | 36.627 | 38.727 | 37.193 |

The combined token-processing improvement is **28.7%**, positive in every paired
round. Baseline round 4 had a timing spike (67.19 ms round median); all samples
are retained. The other four round medians are 32.73–37.62 ms, and combined
medians are 24.58–26.22 ms. This is a representative host-array workload, not a
claim of an application-wide gain. Regex and SQLite Save show noise/regressions;
no speedup is claimed for them. The UI worker uses original MainDemoHost/SQLite
flows, verifies saved descriptions and one saved warehouse row. Regex checks all
42 records; the array workload checks sum=10000 and unchanged array identity.

```sh
python experiments/direct_host_access_audit9/measure.py > results.json
```

## Validation

45 targeted tests pass normal and optimized:

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
 test_python_direct_host_values test_python_direct_system_names \
 test_python_direct_database test_python_direct_form_database_admission
```

Independent review: 40 optimized tests pass, no blockers. Tests cover RU/EN Get,
nested identity, mutation visibility, canonical index errors, closed runtime
after argument evaluation, fixed nested readonly values, foreign database
receivers, singleton lookalikes and namespace writes. FixedArray's existing
constructor recursively freezes nested arrays; Get retains the already-created
nested value identity. Constructor semantics were not changed.

The boundary closure was deliberately retained for correctness. No quote_identifier
cache, Map rewrite or locals flush/snapshot was added. Server/NoContext and full
six-scenario direct gaps remain; no native parity or full green CI claim.
