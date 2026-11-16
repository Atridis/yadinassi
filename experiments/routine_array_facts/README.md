# Private routine array facts

```sh
PYTHONPATH=. python experiments/routine_array_facts/measure.py
```

Run the identical script from baseline and candidate working directories using
the same Python/dependencies. Five alternating fresh-process pairs, median of
three repetitions per cell. Each kernel builds 10,000 values and checks sum
49,995,000. Cases: module control, private routine with literal loop bound, and
routine with unknown Val N bound. That last case is deliberately measured as an
unsupported-specialization control, not hidden in the optimized aggregate.

Prepared excludes initial prepare but includes execute_prepared admission;
execute_source includes parse/compile. No hard performance thresholds. Runtime
SHA256, Python details and raw results are in environment.json and paired.json.
