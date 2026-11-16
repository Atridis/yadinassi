"""Original UI Description and Save actions on a real main-demo database."""
import json,statistics
from time import perf_counter
from test_main_demo_host import MainDemoHostTests
from yadinassi.ui.protocol import CatalogRef
f=MainDemoHostTests();f.setUp();out={}
try:
 owner=f.host.owner
 def ref(obj):
  value=obj.get_member('Ref');return CatalogRef(str(value.value_type.metadata_uuid),str(value.reference_uuid))
 kind=owner.catalogs.get_member('ВидыНоменклатуры').create_item();kind.set_member('Description','Kind');kind.write()
 warehouse=owner.catalogs.get_member('Склады').create_item();warehouse.set_member('Description','Warehouse');warehouse.write()
 for catalog in ('ВидыНоменклатуры','Номенклатура'):
  schema=next(c for c in f.config.catalogs if c.name==catalog);owner.select(str(schema.identity));owner.open();editor=owner.editor
  def change(name,value):
   field=next(x for x in editor.snapshot()['fields'] if x['name']==name);editor.change(field['control'],value)
  change('Description','  Initial  ')
  if catalog=='Номенклатура':
   change('ВидНоменклатуры',ref(kind));editor.row_event('addRow','Склады')
   row=editor.snapshot()['sections'][0]['rows'][0]['id'];editor.row_event('changeRow','Склады',row,ref(warehouse))
  owner.event('command',control='SaveButton')
  edits=[];saves=[]
  for i in range(4):
   start=perf_counter();change('Description','  Item '+str(i)+'  ');edits.append((perf_counter()-start)*1000)
   start=perf_counter();owner.event('command',control='SaveButton');saves.append((perf_counter()-start)*1000)
   assert editor.snapshot()['saveState']=='saved'
  reference=editor.object.get_member('Ref');saved=reference.get_object(reference)
  assert saved.get_member('Description')=='Item 3'
  assert owner.backend._active is None
  out[catalog]={'description_ms':statistics.median(edits),'save_ms':statistics.median(saves),'description_samples_ms':edits,'save_samples_ms':saves,'control':'saved Item 3; no active transaction'}
  owner.event('closeCard')
 print(json.dumps(out))
finally:f.doCleanups()
