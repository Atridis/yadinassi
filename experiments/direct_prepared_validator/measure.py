"""Real SQLite product updates. Run each revision in a fresh process."""
import json
from time import perf_counter
from test_python_direct_catalog_preparation import DirectCatalogPreparationTests
f=DirectCatalogPreparationTests();f.setUp()
try:
    start=perf_counter();f.card.write();cold=perf_counter()-start
    start=perf_counter()
    for i in range(10):
        f.card.set_member('Наименование','  Product '+str(i)+'  ');f.card.write()
    elapsed=perf_counter()-start
    ref=f.card.get_member('Ссылка');saved=ref.get_object(ref)
    assert saved.get_member('Наименование')=='Product 9'
    assert saved.get_member('Склады').count()==1
    assert f.db.backend._active is None
    print(json.dumps({'cold_write_ms':cold*1000,'ten_warm_updates_ms':elapsed*1000,'control':'Product 9; one warehouse; no active tx'}))
finally:f.doCleanups()
