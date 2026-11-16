# Actual SQLite BeforeWrite measurement

From each checkout, with the same CPython environment and dependencies:

```sh
PYTHONPATH=.:tests python experiments/direct_prepared_validator/measure.py
```

For the baseline, run the candidate's identical measure.py using an absolute
path but keep the baseline checkout as cwd and `PYTHONPATH=.:tests`.

`paired.json` contains five alternating fresh-process pairs. Setup is excluded;
`cold_write_ms` includes the first validator compile and real write.
`ten_warm_updates_ms` is the total of ten subsequent actual SQLite updates, not
per-operation time. The database is temporary and all data are synthetic.
See `docs/prepared-catalog-validator.md` for results and limitations.
