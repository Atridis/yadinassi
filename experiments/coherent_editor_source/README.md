# One current source snapshot per editor verification

Run from repository root:

```sh
PYTHONPATH=.:tests python experiments/coherent_editor_source/measure.py
```

The measurement script is byte-identical to the preceding canonical-validation
UI harness. It creates a real main-demo database, seeds dependencies, opens the
original kind/product editor, then measures four Description changes and four
Save commands per catalog. Setup and the first save are excluded. Saved text and
released SQL transaction state are checked.

Five alternating fresh-process pairs compare baseline 01306fc2 (public tree
07d52635) with this candidate. CPython and exact changed runtime file hashes are
in environment.json; raw samples and controls are in results.json. Shared Linux
host, no CPU isolation. Per-process medians are summarized across five pairs.

Final median milliseconds (baseline → candidate):

| Catalog | Description | Save |
|---|---:|---:|
| Номенклатура (object policy) | 17.507 → 11.844 | 50.720 → 46.595 |
| ВидыНоменклатуры (no object policy) | 22.362 → 23.201 | 41.343 → 43.839 |

The product actions improve about 1.48× and 1.09× respectively. The kind control
is 4–6% slower in this run; its verification already skipped the second read when
no object policy was present, so no analogous benefit is claimed. All twenty
catalog/process controls matched. These are shared-host measurements, not
performance thresholds or universal speedup guarantees.
