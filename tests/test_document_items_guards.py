"""Ordinary identity/ownership and closed-consumer regressions for Items."""
import copy,unittest,tempfile
from pathlib import Path
from decimal import Decimal
from uuid import UUID
from test_document_items_replay import CAPTURE,image
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage.document_reader import read_document_rows
from yadinassi.storage.config_document_metadata import project_document_metadata
from yadinassi.storage.config_catalog_attributes import CatalogAttributeError
from yadinassi import Interpreter
from yadinassi.database_context import FileDBContext

class ItemsGuards(unittest.TestCase):
 def parse(self,raw):return project_document_metadata(raw,budget=c._Budget(c.CatalogLimits()))
 def test_generated_type_identity_and_column_paths_both_orders(self):
  for state in (CAPTURE['states'][0],CAPTURE['states'][4]):
   configs=CAPTURE['configs'][str(state['repeat'])];raw=bytes.fromhex(configs[2]['raw_hex']);identity,_=self.parse(raw)
   section=identity.sections[0];mapping=state['physical']['actual_mapping']['section']
   for key in ('metadata_uuid','name','type_uuid','value_uuid','row_type_uuid','row_value_uuid'):
    self.assertEqual(getattr(section,key),mapping[key])
   self.assertEqual(section.line_number_length,5)
   self.assertEqual([(a.name,a.metadata_uuid) for a in section.attributes],[(a['name'],a['metadata_uuid']) for a in mapping['columns']])
 def test_section_count_type_collision_and_quoted_header_refused(self):
  state=CAPTURE['states'][0];mapping=state['physical']['actual_mapping']['section'];raw=bytes.fromhex(CAPTURE['configs']['1'][2]['raw_hex'])
  for before,after in ((b'21c53e09-8950-4b5e-a6a0-1054f1bbc274,1',b'21c53e09-8950-4b5e-a6a0-1054f1bbc274,2'),
     (mapping['row_type_uuid'].encode(),mapping['type_uuid'].encode()),(b'{11,',b'{"11",')):
   changed=raw.replace(before,after,1);self.assertNotEqual(changed,raw)
   with self.assertRaises(CatalogAttributeError):self.parse(changed)
 def test_section_collision_and_reference_target_do_not_bypass_snapshot(self):
  state=CAPTURE['states'][0];mapping=state['physical']['actual_mapping'];configs=CAPTURE['configs']['1']
  for before,after in ((b'"Items"',b'"Number"'),(mapping['section']['type_uuid'].encode(),mapping['objects'][0]['ref_type_uuid'].encode()),
     (mapping['objects'][1]['ref_type_uuid'].encode(),mapping['objects'][1]['metadata_uuid'].encode())):
   changed=copy.deepcopy(configs);raw=bytes.fromhex(changed[2]['raw_hex']);new=raw.replace(before,after);self.assertNotEqual(raw,new)
   changed[2]['raw_hex']=new.hex();v=image(state,changed)
   with self.assertRaises(c.CatalogError):read_document_rows(v.read_at,v.size,document_name=mapping['objects'][0]['name'])
 def test_orphan_owner_is_rejected_by_same_graph_coordinator(self):
  state=copy.deepcopy(CAPTURE['states'][0]);p=state['physical']['objects'][2]['physical'];raw=bytearray.fromhex(p['raw_hex'])
  raw[122:138]=bytes.fromhex('0123456789abcdef0123456789abcdef');p['raw_hex']=raw.hex();v=image(state)
  with self.assertRaises(c.InvalidStructure) as got:read_document_rows(v.read_at,v.size,document_name=state['physical']['objects'][0]['name'])
  self.assertEqual(got.exception.code,'document_lines_owner')
 def test_readonly_and_unsupported_consumers_fail_in_bsl(self):
  state=CAPTURE['states'][0];v=image(state);name=state['physical']['objects'][0]['name'];lines=[]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();(root/'1Cv8.1CD').write_bytes(v.read_at(0,v.size));vm=Interpreter(output=lines.append,database_context=FileDBContext(root))
   code=f'S=Documents.{name}.FindByNumber("20").Items; R=S.Get(0); T=TypeOf(S); '
   for expr in ('S.Add()','S.Clear()','S.Sort("Amount")','S.Unload()','S[0]=R','R.Amount=0','R.LineNumber=4',
                'ValueToStringInternal(S)','ValueToStringInternal(R)','ValueToStringInternal(T)','New TypeDescription(T)','New(T)'):
    code+='Try '+expr+'; Message("bad"); Except Message("closed"); EndTry; '
   try:vm.execute(code)
   finally:vm.close()
  self.assertEqual(lines,['closed']*12)

if __name__=='__main__':unittest.main()
