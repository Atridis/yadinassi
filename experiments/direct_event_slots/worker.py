"""Real SQLite product list/editor alternation; run with PYTHONPATH=tests:."""
import json,time,statistics
import test_product_list_check as fixture
f=fixture.ProductListCheckTests();f.setUp()
rows=[]
try:
    ref=f.saved()
    for i in range(9):
        f.check(ref)
        f.app.event('openCard',reference=ref)
        start=time.perf_counter_ns()
        control=next(x['control'] for x in f.app.editor.snapshot()['fields'] if x['name']=='Description')
        f.app.editor.change(control,'  Cable updated  ')
        elapsed=(time.perf_counter_ns()-start)/1e6
        assert next(x for x in f.app.editor.snapshot()['fields'] if x['name']=='Description')['inputText']=='Cable updated'
        f.app.event('command',control='CancelButton')
        rows.append(elapsed)
finally:f.doCleanups()
print(json.dumps({'description_ms':rows,'warm_median_ms':statistics.median(rows[1:])}))
