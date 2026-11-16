import json,time,hashlib
from pathlib import Path
from test_main_demo_host import MainDemoHostTests
from yadinassi.ui.protocol import CatalogRef
rows=[]
f=MainDemoHostTests();f.setUp()
try:
 owner=f.host.owner
 kind=next(c for c in f.config.catalogs if c.name=='ВидыНоменклатуры');owner.select(str(kind.identity));owner.open();editor=owner.editor
 for i in range(6):
  t=time.perf_counter_ns();editor.change('InputData1','  Kind '+str(i)+'  ');changed=(time.perf_counter_ns()-t)/1e6
  t=time.perf_counter_ns();owner.event('command',control='SaveButton');saved=(time.perf_counter_ns()-t)/1e6
  assert editor.snapshot()['saveState']=='saved' and editor.object.get_member('Description')=='Kind '+str(i)
  rows.append(dict(profile='kind',iteration=i,description_ms=changed,save_ms=saved))
 owner.event('closeCard')
 kind=owner.catalogs.get_member('ВидыНоменклатуры').create_item();kind.set_member('Description','Товары');kind.write()
 warehouse=owner.catalogs.get_member('Склады').create_item();warehouse.set_member('Description','Основной');warehouse.write()
 def ref(obj):
  v=obj.get_member('Ref');return CatalogRef(str(v.value_type.metadata_uuid),str(v.reference_uuid))
 product=next(c for c in f.config.catalogs if c.name=='Номенклатура');owner.select(str(product.identity));owner.open();editor=owner.editor
 def control(name):return next(v['control'] for v in editor.snapshot()['fields'] if v['name']==name)
 editor.change(control('Description'),'Product');editor.change(control('ВидНоменклатуры'),ref(kind))
 editor.row_event('addRow','Склады');row=editor.snapshot()['sections'][0]['rows'][0]['id'];editor.row_event('changeRow','Склады',row,ref(warehouse))
 description=control('Description')
 for i in range(6):
  t=time.perf_counter_ns();editor.change(description,'  Product '+str(i)+'  ');changed=(time.perf_counter_ns()-t)/1e6
  t=time.perf_counter_ns();owner.event('command',control='SaveButton');saved=(time.perf_counter_ns()-t)/1e6
  assert editor.snapshot()['saveState']=='saved' and editor.object.get_member('Description')=='Product '+str(i)
  rows.append(dict(profile='product',iteration=i,description_ms=changed,save_ms=saved))
 value=editor.object.get_member('Ref');saved=value.get_object(value)
 assert saved.get_member('Склады').count()==1 and saved.get_member('Description')=='Product 5'
 print(json.dumps(dict(samples=rows,hashes={p:hashlib.sha256(Path('yadinassi',p).read_bytes()).hexdigest() for p in ('form_module_analysis.py','form_event_simulation.py')})))
finally:f.doCleanups()
