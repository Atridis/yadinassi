# DB-independent module facts

Run from each checkout with the same dependencies:

```sh
PYTHONPATH=.:tests python experiments/db_independent_facts/measure.py
```

For baseline, use the candidate's identical script via absolute path with the
baseline checkout as cwd and PYTHONPATH. Setup of a real temporary SQLite
main-demo database is excluded. Numeric and array kernels have 10,000 iterations;
results are checked every run. `prepared` excludes initial prepare, but includes
execute_prepared admission; `execute_source` includes parse/prepare/execute.
Each cell is the median of three runs. `paired.json` records five alternating
fresh-process baseline/candidate pairs. Plain and database-enabled VMs run the
same pure code: this measures computation with DB capabilities, not SQL speed.
Final runtime hashes and shared-host Python details are in environment.json.
