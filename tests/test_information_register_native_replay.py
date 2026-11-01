"""Native selected bytes/programs in synthetic transport, not a saved native DB.

All five CONFIG descriptors are actual; no invented auxiliary metadata. Public
fixture excludes installations, sessions and authentication/audit material.
"""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts')]
from yadinassi import Interpreter
from yadinassi.database_context import FileDBContext
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.storage.information_register_reader import read_information_register_rows
from linked_card_packet.base import scalar_wire
import test_catalog_binding_integration as base
from test_native_1c_db_oracle_config_content_decode_reader import packed
from test_filedb_records import serialize
PATH=Path(__file__).parent/'fixtures/information_register_native.json'
CAPTURE=json.loads(PATH.read_text(encoding='utf-8'))

def image(state, configs=None):
    """Synthetic page placement, native selected content/declarations/raw span."""
    configs=CAPTURE['configs'][str(state['repeat'])] if configs is None else configs
    cases=state['physical']['objects'];cf=base.config_fixture
    # Exact native root pointer and target collection descriptor, no invented
    # cf.entries membership. Only compression/page placement is synthetic.
    entries=[(item['filename'],packed(bytes.fromhex(item['raw_hex'])),0) for item in configs]
    value=cf.content_source(entries)
    P=base.P;u32=base.u32
    # Move CONFIG payload pages away from all synthetic table descriptors.
    oldpages=list(value.data_pages)+list(value.blob_pages)
    contents={p:bytes(value.page(p)) for p in oldpages}
    mapping={p:100+i for i,p in enumerate(oldpages)}
    for old,new in mapping.items():value.page(new)[:]=contents[old]
    for header,pages in ((5,value.data_pages),(8,value.blob_pages)):
        for i,p in enumerate(pages):value.page(header)[24+i*4:28+i*4]=u32(mapping[p])
    value.page_count=512;value.size=512*P;value.page(0)[12:16]=u32(512)
    triples=[]
    for case in state['physical']['dbnames']['groups']:
        triples.extend('{'+e['uuid']+',"'+e['kind']+'",'+str(e['id'])+'}' for e in case['entries'])
    db=('\ufeff{0,{'+str(len(triples))+','+','.join(triples)+'}}').encode()
    params=base.params_fixture.source()
    compressed=packed(db)
    params.page(10)[301+276:301+287]=bytes.fromhex('1'+str(len(compressed)).zfill(20)+'0')
    params.page(10)[301+287:301+295]=u32(1)+u32(len(compressed))
    chunks=[compressed[i:i+250] for i in range(0,len(compressed),250)]
    params.page(8)[16:24]=((len(chunks)+1)*256).to_bytes(8,'little')
    params.page(11)[:]=bytes(P)
    for i,chunk in enumerate(chunks,1):
        offset=i*256;next_id=i+1 if i<len(chunks) else 0
        params.page(11)[offset:offset+6]=u32(next_id)+len(chunk).to_bytes(2,'little')
        params.page(11)[offset+6:offset+6+len(chunk)]=chunk
    for old,new in ((5,30),(8,31),(9,34),(10,32),(11,33)):value.page(new)[:]=params.page(old)
    value.page(30)[24:28]=u32(32);value.page(31)[24:28]=u32(33);value.page(32)[1:5]=u32(0)
    descriptions=[(10,('PARAMS',0,('Fields',*base.params_fixture.policy.DECLARATIONS),('Indexes',),('Recordlock','0'),('Files',30,31,34)))]
    for index,case in enumerate(cases):
        p=case['physical'];head,blob,ind,page=((40,41,42,43),(46,47,48,49),(52,53,54,55))[index]
        descriptions.append(((14,20,24)[index],(p['candidate'],0,('Fields',*(tuple(d) for d in p['declarations'])),('Indexes',),('Recordlock','0'),('Files',head,blob,ind))))
        raw=bytes.fromhex(p['raw_hex'])
        value.page(head)[:24]=b'\x1c\xfd'+bytes(14)+len(raw).to_bytes(8,'little')
        value.page(head)[24:28]=u32(page);value.page(page)[:len(raw)]=raw
    value.catalog((2,10,14,20))
    for block,desc in descriptions:
        raw=serialize(desc).encode();value.chain(tuple(range(block,block+(len(raw)+249)//250)),raw)
    return value

class InformationRegisterNativeReplayTests(unittest.TestCase):
 def test_public_fixture_positive_allowlist_and_source_hashes(self):
  self.assertEqual(hashlib.sha256(PATH.read_bytes()).hexdigest(),'cf40e267b056e6a4b6ec6997ed2ad36e613e493b89b9b1496c7c9eb49cb111d5')
  self.assertEqual(set(CAPTURE),{'run','commit','report_sha256','configs','programs','program_hashes','states'})
  self.assertEqual(CAPTURE['report_sha256'],'7210f4bec77919d2e77a667b4ae159bf7fdc70fbbb5be97f4e82b7d5a9fdbf5d')
  self.assertEqual(set(CAPTURE['configs']),{'1','2'});self.assertEqual(len(CAPTURE['states']),8)
  for files in CAPTURE['configs'].values():
   self.assertEqual(len(files),5);self.assertEqual(files[0]['filename'],'root')
   for item in files:
    self.assertEqual(set(item),{'filename','raw_hex','sha256'})
    self.assertEqual(hashlib.sha256(bytes.fromhex(item['raw_hex'])).hexdigest(),item['sha256'])
  for repeat,programs in CAPTURE['programs'].items():
   self.assertEqual(set(programs),{'get','cursor','filter','types'})
   for block,text in programs.items():self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),CAPTURE['program_hashes'][repeat][block])
  for state in CAPTURE['states']:
   self.assertEqual(set(state),{'repeat','state','context','physical','outputs'})
   self.assertEqual(set(state['physical']),{'objects','dbnames'})
   self.assertEqual(set(state['physical']['dbnames']),{'groups'})
   for group in state['physical']['dbnames']['groups']:
    self.assertEqual(set(group),{'entries'})
    for entry in group['entries']:self.assertEqual(set(entry),{'uuid','kind','id','ordinal'})
   for obj in state['physical']['objects']:
    self.assertEqual(set(obj),{'name','metadata_uuid','physical'})
    self.assertEqual(set(obj['physical']),{'candidate','declarations','raw_hex'})
  def no_private_keys(value):
   if isinstance(value,dict):
    for key,item in value.items():
     self.assertFalse(any(word in key.casefold() for word in ('audit','token','nonce','password','credential','secret','auth','session','helper','installation')))
     no_private_keys(item)
   elif isinstance(value,list):
    for item in value:no_private_keys(item)
  no_private_keys(CAPTURE)
 def test_actual_five_config_descriptors_and_register_rows(self):
  for state in CAPTURE['states']:
   v=image(state);register=state['physical']['objects'][0]
   result=read_information_register_rows(v.read_at,v.size,register_name=register['name'])
   self.assertEqual(result.identity.metadata_uuid,register['metadata_uuid'])
   self.assertEqual(len(result.rows),0 if state['state']=='empty' else 3)
 def test_actual_root_membership_required_before_row_access(self):
  import copy
  from yadinassi.storage.filedb_catalog import CatalogError
  state=CAPTURE['states'][0];configs=copy.deepcopy(CAPTURE['configs']['1']);register=state['physical']['objects'][0]
  raw=bytes.fromhex(configs[1]['raw_hex']);self.assertIn(register['metadata_uuid'].encode(),raw)
  configs[1]['raw_hex']=raw.replace(register['metadata_uuid'].encode(),b'11111111-1111-4111-8111-111111111111').hex()
  v=image(state,configs)
  with self.assertRaises(CatalogError):read_information_register_rows(v.read_at,v.size,register_name=register['name'])
  self.assertFalse(any(offset==43*base.P for offset,_ in v.calls))
 def test_all_32_historical_native_programs_through_public_interpreter(self):
  for state in CAPTURE['states']:
   v=image(state)
   with tempfile.TemporaryDirectory() as directory:
    directory=Path(directory).resolve();path=directory/'1Cv8.1CD';path.write_bytes(v.read_at(0,v.size));before=hashlib.sha256(path.read_bytes()).hexdigest()
    for block,text in CAPTURE['programs'][str(state['repeat'])].items():
     lines=[];vm=Interpreter(output=lines.append,database_context=FileDBContext(directory),native_target=LINUX_8_3_27_1508)
     try:vm.execute(text)
     finally:vm.close()
     actual=('\n'.join(lines)+'\n').encode('ascii')
     with self.subTest(repeat=state['repeat'],state=state['state'],context=state['context'],block=block):
      self.assertEqual(scalar_wire.validate_output(actual),scalar_wire.validate_output(state['outputs'][block].encode()))
    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
if __name__=='__main__':unittest.main()
