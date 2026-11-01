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
from yadinassi.storage.document_reader import read_document_rows
import document_read_fixture as packet
from document_read_readback import compare
import test_catalog_binding_integration as base
from test_native_1c_db_oracle_config_content_decode_reader import packed
from test_filedb_records import serialize

PATH=Path(__file__).parent/'fixtures/document_native.json'
CAPTURE=json.loads(PATH.read_text(encoding='utf-8'))

def image(state, configs=None):
    """Synthetic page placement, native selected content/declarations/raw span."""
    configs=CAPTURE['configs'][str(state['repeat'])] if configs is None else configs
    cases=state['physical']['objects'];cf=base.config_fixture
    # Exact native root pointer and target collection descriptor, no invented
    # cf.entries membership. Only compression/page placement is synthetic.
    entries=[(item['filename'],packed(bytes.fromhex(item['raw_hex'])),0) for item in configs]
    # SYNTHETIC auxiliary descriptor: the bounded native artifact does not
    # include the baseline NativeOracleItems payload. Preserve the exact native
    # root membership and add only this explicitly invented transport fixture.
    # It is NOT stored in CAPTURE or claimed to be native metadata evidence.
    # Final actual-.1CD parity must exercise the real baseline descriptor.
    from uuid import uuid5, NAMESPACE_URL
    baseline='38714509-2186-41ea-a931-c2b85b1cbf7d'
    mapping=state['physical']['actual_mapping'][1]
    auxiliary=bytes.fromhex(configs[3]['raw_hex'])
    auxiliary=auxiliary.replace(mapping['metadata_uuid'].encode(),baseline.encode())
    auxiliary=auxiliary.replace(mapping['ref_type_uuid'].encode(),str(uuid5(NAMESPACE_URL,'yadinassi:synthetic:document-replay-baseline-ref')).encode())
    auxiliary=auxiliary.replace(mapping['name'].encode(),b'NativeOracleItems')
    entries.append((baseline,packed(auxiliary),0))
    value=cf.content_source(entries)
    P=base.P;u32=base.u32
    # Move CONFIG payload pages away from all synthetic table descriptors.
    oldpages=list(value.data_pages)+list(value.blob_pages)
    contents={p:bytes(value.page(p)) for p in oldpages}
    mapping={p:100+i for i,p in enumerate(oldpages)}
    for old,new in mapping.items():value.page(new)[:]=contents[old]
    for header,pages in ((5,value.data_pages),(8,value.blob_pages)):
        for i,p in enumerate(pages):value.page(header)[24+i*4:28+i*4]=u32(mapping[p])
    value.page_count=128;value.size=128*P;value.page(0)[12:16]=u32(128)
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
        p=case['physical'];head,blob,ind,page=(40,41,42,43) if index==0 else (46,47,48,49)
        descriptions.append((14 if index==0 else 20,(p['candidate'],0,('Fields',*(tuple(d) for d in p['declarations'])),('Indexes',),('Recordlock','0'),('Files',head,blob,ind))))
        raw=bytes.fromhex(p['raw_hex'])
        value.page(head)[:24]=b'\x1c\xfd'+bytes(14)+len(raw).to_bytes(8,'little')
        value.page(head)[24:28]=u32(page);value.page(page)[:len(raw)]=raw
    value.catalog((2,10,14,20))
    for block,desc in descriptions:
        raw=serialize(desc).encode();value.chain(tuple(range(block,block+(len(raw)+249)//250)),raw)
    return value

class DocumentNativeReplayTests(unittest.TestCase):
    def test_capture_integrity_and_historical_programs(self):
        self.assertEqual(hashlib.sha256(PATH.read_bytes()).hexdigest(),'2c2a5e7ca5f82722c5da1503d02baa29210474bb47d4e53df0d52d821531ff59')
        self.assertEqual(CAPTURE['report_sha256'],'a879485a6ae04dccc62e59faf84c41704a71a1c890578a1b48246769ed6331e0')
        for repeat,programs in CAPTURE['programs'].items():
            for block,text in programs.items():self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),CAPTURE['program_hashes'][repeat][block])
        for files in CAPTURE['configs'].values():
            self.assertEqual(files[0]['filename'],'root')
            for item in files:self.assertEqual(hashlib.sha256(bytes.fromhex(item['raw_hex'])).hexdigest(),item['sha256'])

    def test_public_fixtures_exclude_session_and_authentication_metadata(self):
        self.assertEqual(set(CAPTURE), {'run','commit','report_sha256','configs',
                                       'programs','program_hashes','states'})
        def check(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    self.assertFalse(any(word in key.casefold() for word in
                        ('audit','token','nonce','password','credential','secret','auth','helper')),
                        'session/authentication metadata must not enter public replay fixtures')
                    check(item)
            elif isinstance(value,list):
                for item in value:check(item)
        check(CAPTURE)
        check(json.loads((PATH.parent/'document_records.json').read_text(encoding='utf-8')))

    def test_actual_config_and_rows_through_reader(self):
        for state in CAPTURE['states']:
            value=image(state);doc=state['physical']['objects'][0]
            with self.subTest(repeat=state['repeat'],state=state['state'],context=state['context']):
                result=read_document_rows(value.read_at,value.size,document_name=doc['name'])
                self.assertEqual(len(result.rows),0 if state['state']=='empty' else 3)
                self.assertEqual(result.identity.metadata_uuid,doc['metadata_uuid'])
                self.assertEqual(result.attributes.reference_type_uuid,state['physical']['actual_mapping'][0]['ref_type_uuid'])
                ref=next(a for a in result.attributes.attributes if a.type_token=='#')
                self.assertEqual(ref.reference_catalog_uuid,state['physical']['actual_mapping'][1]['metadata_uuid'])

    def test_historical_native_bsl_via_file_context(self):
        for state in CAPTURE['states']:
            value=image(state);setup,_,_=packet.load(state['repeat'])
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory).resolve()/'1Cv8.1CD'
                with path.open('wb') as stream:
                    for number in range(value.page_count):stream.write(value.pages.get(number,bytes(base.P)))
                before=hashlib.sha256(path.read_bytes()).hexdigest()
                for block,program in CAPTURE['programs'][str(state['repeat'])].items():
                    output=[];vm=Interpreter(output.append,database_context=FileDBContext(path.parent),native_target=LINUX_8_3_27_1508)
                    try:vm.execute(program)
                    finally:vm.close()
                    matched=compare(('\n'.join(output)+'\n').encode(),state['outputs'][block].encode(),setup,block)
                    self.assertTrue(matched['matched'],(state['repeat'],state['state'],state['context'],block,matched))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_actual_root_membership_cannot_be_replaced_by_filename(self):
        state=CAPTURE['states'][0];configs=copy.deepcopy(CAPTURE['configs']['1']);uid=state['physical']['objects'][0]['metadata_uuid']
        target=configs[1];raw=bytes.fromhex(target['raw_hex'])
        self.assertIn(uid.encode(),raw)
        target['raw_hex']=raw.replace(uid.encode(),b'11111111-1111-1111-1111-111111111111').hex()
        value=image(state,configs)
        with self.assertRaises(catalog.CatalogError):read_document_rows(value.read_at,value.size,document_name=state['physical']['objects'][0]['name'])
        self.assertFalse(any(offset==43*base.P for offset,_ in value.calls))

if __name__=='__main__':unittest.main()
