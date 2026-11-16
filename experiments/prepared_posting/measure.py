"""Actual original Receipt source and SQLite movement replacement."""
import json
from time import perf_counter
import test_python_direct_posting as fixture
from yadinassi.document_posting_values import DocumentWriteMode
f=fixture.DirectPostingTests();f.setUp()
try:
 d=f.document()
 start=perf_counter();d.write(DocumentWriteMode.POSTING);cold=(perf_counter()-start)*1000
 start=perf_counter()
 for _ in range(10):d.write(DocumentWriteMode.POSTING)
 warm=(perf_counter()-start)*1000
 assert f.counts()==(1,1,1)
 schema=f.fixture.context.backend.accumulation_configuration.registers[0]
 rows=f.fixture.context.backend.read_accumulation(schema.identity,d._key).rows
 assert len(rows)==1 and dict(zip((field.name for field in schema.resources),rows[0].resources))['Quantity']==5
 assert d._posting_active is None and f.fixture.context.backend._active is None
 print(json.dumps({'cold_write_ms':cold,'ten_reposts_ms':warm,'control':'1 document/postedstate/movement; quantity5; no active tx'}))
finally:f.doCleanups()
