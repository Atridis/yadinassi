# One snapshot for informational product preparation

`ProductEventBoundary.prepare_object` borrows an existing list/write view unchanged,
or opens one checked manager read view for the whole original object handler.
Every referenced catalog still checks database, generation and target schema.
The owned view closes on success, handler failure and child construction failure;
borrowed views remain caller-owned. Nothing is cached across operations. Source
admission and the actual transactional writer are unchanged; no VM fallback.

Reproduce from repository root:

```
python experiments/preparation_read_view/measure.py
PYTHONPATH=tests python -m unittest test_python_direct_preparation_view test_product_form_events test_product_list_check test_python_direct_prepared_form_events
```

The benchmark alternates the exact baseline method from commit `7e2d5123` with
this implementation on the same current checkout, after warming both. It uses
real SQLite with the original object/form source and logical test schema, seven
pairs and 1/32 distinct saved warehouses. Result/cancellation and closed-view
controls are checked. This is informational preparation only, not the whole UI
Save action, browser parity, or native 1C. Raw samples are in `results.json`.
Warm median: one warehouse 1.730 -> 1.622 ms (small/noisy); 32 warehouses
20.990 -> 9.444 ms. No threshold is asserted.

36 focused tests pass in normal and optimized Python, including existing list
borrowed-snapshot/source checks, fresh changed warehouse, no writes, and cleanup
on read/constructor failures.
