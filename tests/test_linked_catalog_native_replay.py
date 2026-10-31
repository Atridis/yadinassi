"""Captured CONFIG/slots in synthetic transport: not a saved native .1CD image."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts')]
from yadinassi import Interpreter
from yadinassi.database_context import FileDBContext
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.storage import config_catalog_attributes as attrs
from yadinassi.storage import filedb_catalog as catalog
from yadinassi.storage.catalog_reader import read_catalog_rows
import linked_card_fixture as packet
from linked_card_readback import compare
import test_catalog_binding_integration as base
from test_native_1c_db_oracle_config_content_decode_reader import packed
from test_filedb_records import serialize

PATH=Path(__file__).parent/'fixtures/linked_catalog_native.json'
CAPTURE=json.loads(PATH.read_text(encoding='utf-8'))

def image(state, configs=None):
    """Synthetic page placement, native selected content/declarations/raw span."""
    configs=CAPTURE['configs'] if configs is None else configs
    cases=state['physical']['catalogs']; cf=base.config_fixture
    ids=[c['metadata_uuid'] for c in cases]
    payloads=[packed(bytes.fromhex(configs[uid])) for uid in ids]
    entries=cf.entries(refs=ids,payload=payloads[0],tail=((ids[1],payloads[1],0),))
    entries[0]=(ids[0],payloads[0],0)
    value=cf.content_source(entries)
    P=base.P;u32=base.u32
    value.page_count=64;value.size=64*P;value.page(0)[12:16]=u32(64)
    triples=[]
    for case in cases:
        triples.extend('{'+e['uuid']+',"'+e['kind']+'",'+str(e['id'])+'}' for e in case['dbnames']['entries'])
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
        p=case['physical'];head,blob,ind,page=(40,41,42,43) if index==0 else (46,47,48,49)
        descriptions.append((14 if index==0 else 20,(p['table'],0,('Fields',*(tuple(d) for d in p['declarations'])),('Indexes',),('Recordlock','0'),('Files',head,blob,ind))))
        raw=bytes.fromhex(p['raw_hex'])
        value.page(head)[:24]=b'\x1c\xfd'+bytes(14)+len(raw).to_bytes(8,'little')
        value.page(head)[24:28]=u32(page);value.page(page)[:len(raw)]=raw
    value.catalog((2,10,14,20))
    for block,desc in descriptions:
        raw=serialize(desc).encode();value.chain(tuple(range(block,block+(len(raw)+249)//250)),raw)
    return value


class LinkedCatalogNativeReplayTests(unittest.TestCase):
    def test_capture_integrity_and_config_relations(self):
        self.assertEqual(hashlib.sha256(PATH.read_bytes()).hexdigest(),'5a852fa959bfeda65326377f433e64ffa65426c10b9981bf13918d3ca6ebd0e3')
        self.assertEqual(CAPTURE['report_sha256'],'6940e058ec877f0a32946ee50f6d5fa161dd6b716553ea2e23db0c26b86d4499')
        for install in CAPTURE['installations']:
            parsed=[]
            for entry in install['mapping']:
                raw=bytes.fromhex(CAPTURE['configs'][entry['metadata_uuid']])
                parsed.append(attrs.project_linked_catalog_attributes(raw,budget=catalog._Budget(catalog.CatalogLimits())))
                self.assertEqual(parsed[-1].reference_type_uuid,entry['ref_type_uuid'])
            self.assertEqual(len(parsed[0].attributes),5);self.assertEqual(parsed[1].attributes,())
            self.assertEqual(next(a for a in parsed[0].attributes if a.type_token=='#').reference_type_uuid,parsed[1].reference_type_uuid)
            self.assertEqual({a.type_token:a.qualifiers for a in parsed[0].attributes},{'S':(32,1),'N':(9,2,0),'B':(),'D':(),'#':()})

    def test_actual_config_and_rows_through_reader(self):
        for state in CAPTURE['states']:
            value=image(state)
            for case in state['physical']['catalogs']:
                with self.subTest(repeat=state['repeat'],state=state['state'],catalog=case['name']):
                    result=read_catalog_rows(value.read_at,value.size,catalog_name=case['name'])
                    expected=0 if state['state']=='empty' else (3 if len(case['dbnames']['entries'])>1 else 1)
                    self.assertEqual(len(result.rows),expected)

    def test_native_bsl_blocks_via_file_context(self):
        for state in CAPTURE['states']:
            value=image(state);s,_,files=packet.load(state['repeat'])
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory).resolve()/'1Cv8.1CD'
                with path.open('wb') as stream:
                    for number in range(value.page_count):stream.write(value.pages.get(number,bytes(base.P)))
                before=hashlib.sha256(path.read_bytes()).hexdigest()
                for block in packet.BLOCKS:
                    output=[];context=FileDBContext(path.parent)
                    vm=Interpreter(output.append,database_context=context,native_target=LINUX_8_3_27_1508)
                    try:vm.execute(files[block+'.bsl'].decode('utf-8'))
                    finally:vm.close()
                    matched=compare(('\n'.join(output)+'\n').encode(),state['outputs'][block].encode(),s,block)
                    self.assertTrue(matched['matched'],(state['repeat'],state['state'],state['context'],block,matched))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_real_file_context_without_unix_flags_uses_private_seek(self):
        import yadinassi.database_context as module
        class WindowsReadOS:
            seeks=0
            def __getattr__(self,name):
                if name in ('pread','O_NONBLOCK','O_NOFOLLOW','O_DIRECTORY'):raise AttributeError(name)
                return getattr(os,name)
            def lseek(self,*args):
                self.seeks+=1
                return os.lseek(*args)
        state=next(s for s in CAPTURE['states'] if s['repeat']==2 and s['state']=='filled')
        value=image(state);setup,_,files=packet.load(2);proxy=WindowsReadOS();original=module.os
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'1Cv8.1CD'
            with path.open('wb') as stream:
                for number in range(value.page_count):stream.write(value.pages.get(number,bytes(base.P)))
            before=path.read_bytes()
            # No decoder/read_at mocks: exercise production open/read/seek/fstat/close.
            with mock.patch.object(module,'os',proxy):
                for block in packet.BLOCKS:
                    output=[];vm=Interpreter(output.append,database_context=FileDBContext(path.parent),native_target=LINUX_8_3_27_1508)
                    try:vm.execute(files[block+'.bsl'].decode('utf-8'))
                    finally:vm.close()
                    self.assertTrue(compare(('\n'.join(output)+'\n').encode(),state['outputs'][block].encode(),setup,block)['matched'])
            self.assertGreater(proxy.seeks,0);self.assertEqual(path.read_bytes(),before)
        self.assertIs(module.os,original)

    def test_linked_type_grammar_is_closed_and_legacy_is_unchanged(self):
        import test_config_catalog_attributes as invented
        def parse(pattern, linked=True):
            data=invented.document([invented.attribute(pattern=pattern)])
            fn=attrs.project_linked_catalog_attributes if linked else attrs.project_catalog_attributes
            return fn(data,budget=catalog._Budget(catalog.CatalogLimits()))
        for pattern in ('{"Pattern",{"B",0}}','{"Pattern",{"D",0}}',
                        '{"Pattern",{"D",1}}','{"Pattern",{"#"}}',
                        '{"Pattern",{"#","12345678-9abc-def0-1234-56789abcdef0"}}',
                        '{"Pattern",{"#",00000000-0000-0000-0000-000000000000}}',
                        '{"Pattern",{"B"},{"S",32,1}}','{"Pattern",{"UNKNOWN"}}'):
            with self.subTest(pattern=pattern),self.assertRaises(attrs.CatalogAttributeError):parse(pattern)
        for token in ('B','D'):
            with self.assertRaises(attrs.CatalogAttributeError):parse('{"Pattern",{"'+token+'"}}',False)
        for data in (None,bytearray(b'{}')):
            with self.assertRaises(attrs.CatalogAttributeError):attrs.project_linked_catalog_attributes(data,budget=catalog._Budget(catalog.CatalogLimits()))

    def test_ambiguous_or_missing_generated_target_identity_fails_closed(self):
        state=CAPTURE['states'][2];mapping=state['physical']['actual_mapping'];cases=state['physical']['catalogs']
        for replacement in (mapping[0]['ref_type_uuid'],'00000000-0000-0000-0000-000000000000'):
            configs=dict(CAPTURE['configs']);uid=mapping[1]['metadata_uuid']
            raw=bytes.fromhex(configs[uid]);old=mapping[1]['ref_type_uuid'].encode()
            raw=raw.replace(old,replacement.encode(),1);configs[uid]=raw.hex();value=image(state,configs)
            with self.assertRaises(catalog.CatalogError):read_catalog_rows(value.read_at,value.size,catalog_name=cases[0]['name'])
            self.assertFalse(any(offset==43*base.P for offset,_ in value.calls))

    def test_unknown_target_ref_type_never_resolves_as_catalog_uuid(self):
        state=CAPTURE['states'][2];cases=state['physical']['catalogs'];configs=dict(CAPTURE['configs'])
        target=state['physical']['actual_mapping'][1]
        raw=bytes.fromhex(configs[cases[0]['metadata_uuid']])
        raw=raw.replace(b'{"#",'+target['ref_type_uuid'].encode(),b'{"#",'+target['metadata_uuid'].encode())
        configs[cases[0]['metadata_uuid']]=raw.hex();value=image(state,configs)
        with self.assertRaises(catalog.UnsupportedLayout):read_catalog_rows(value.read_at,value.size,catalog_name=cases[0]['name'])

if __name__=='__main__':unittest.main()
