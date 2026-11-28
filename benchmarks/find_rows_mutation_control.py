"""Run in each checkout; compare with the linear commit, no searches in controls."""
import json,statistics,time
from decimal import Decimal
from yadinassi.collections.plain_value_table_runtime import BSLValueTable

def median(fn):
    samples=[]
    for _ in range(9):
        start=time.perf_counter();fn();samples.append(time.perf_counter()-start)
    return statistics.median(samples)

def make(declared):
    t=BSLValueTable()
    for k in ('K','V','W'):t.columns.add(k)
    if declared:
        for k in ('K','V','K,V'):t.indexes.add(k)
    return t

results=[]
for n in (512,4096):
    for declared in (False,True):
        try:t=make(declared)
        except NotImplementedError:
            results.append(dict(n=n,declarations=3,unsupported=True));continue
        def add():
            t.clear()
            for _ in range(n):t.add()
            assert len(t.rows)==n
            if hasattr(t,'_search'):assert t._search.builds==0
        add_s=median(add)
        for i,row in enumerate(t.rows):row.set_member('K',Decimal(i))
        def read():
            total=sum((row.get_member('K') for row in t),Decimal(0))
            assert total==n*(n-1)//2
            if hasattr(t,'_search'):assert t._search.builds==0
        read_s=median(read)
        results.append(dict(n=n,declarations=3 if declared else 0,add_seconds=add_s,read_iteration_seconds=read_s))
print(json.dumps(results))
