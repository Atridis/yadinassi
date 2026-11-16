# Actual source-bound posting measurement

```sh
PYTHONPATH=.:tests python experiments/prepared_posting/measure.py
```

Run identical script from each checkout with identical Python/dependencies. For
baseline, use the candidate script's absolute path but baseline cwd/PYTHONPATH.
Five alternating fresh-process pairs. Setup/seed excluded; first original
main-demo Receipt posting timed separately, then ten real reposts replace its
movements through the existing SQLite writer. Checks: one document, posted state
and movement, Quantity=5, no active transaction. Warm totals are ten operations,
not per-operation timings. Raw data/runtime hashes are recorded alongside.
