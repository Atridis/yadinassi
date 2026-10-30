"""Closed opt-in wiring and native observer sidecar mechanics; no native run."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_metadata as old
import catalog_description_measurement as m
import inputs

class DescriptionIntegrationTests(unittest.TestCase):
    def setUp(self):
        old.MetadataTest.setUp(self)

    def test_both_cases_full_inject_promote_redump(self):
        for case,(length,_,_) in m.CASES.items():
            v1=self.root/case;v2=self.root/(case+'v2')
            old.m.inject(self.source,v1,nonce=old.NONCE,evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'),description_case=case)
            old.m.inspect(v1,1,description_case=case)
            old.m.promote_v2(v1,v2,description_case=case)
            self.assertEqual(old.m.inspect(v2,2,description_case=case)['payload_length'],64)
            old.m.verify_redump(v1,v1,1,description_case=case)
            old.m.verify_redump(v2,v2,2,description_case=case)
            self.assertEqual(len(list((v1/'Catalogs').glob('*.xml'))),1)
            for root in (v1,v2):
                self.assertIn(f'<DescriptionLength>{length}</DescriptionLength>',(root/'Catalogs/NativeOracleItems.xml').read_text(encoding='utf-8-sig'))
                self.assertNotIn('@@',(root/'CommonModules/NativeOracleServer/Ext/Module.bsl').read_text(encoding='utf-8-sig'))
                with self.assertRaises(ValueError):old.m.inspect(root,1 if root==v1 else 2)
            original=(v1/'Catalogs/NativeOracleItems.xml').read_bytes()
            (v1/'Catalogs/NativeOracleItems.xml').write_bytes(original.replace(b'<DescriptionLength>'+str(length).encode()+b'</DescriptionLength>',b'<DescriptionLength>0</DescriptionLength>'))
            with self.assertRaises(ValueError):old.m.inspect(v1,1,description_case=case)

    def test_description_selectors_exclude_all_old_modes(self):
        for case in (True,8,17,'8','description0',[],{}):
            with self.assertRaises(Exception):inputs.inventory(description_case=case)
        for flag in ('record_metadata','record_reader','catalog_readonly_binding','config_catalog_field_matrix','config_catalog_attribute_binding'):
            with self.assertRaises(Exception):inputs.inventory(description_case='description8',**{flag:True})
        with self.assertRaises(Exception):inputs.inventory(description_case='description8',reference_case='distinct_a')
        for extra in ({'catalog_field_matrix':True},{'reference_case':'distinct_a'}):
            with self.assertRaises(ValueError):old.m.inject(self.source,self.target,nonce=old.NONCE,evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'),description_case='description8',**extra)
        self.assertEqual(len(inputs.CATALOG_DESCRIPTION_SOURCE_FILES),41)
        self.assertEqual(len(inputs.CATALOG_CODEC_SOURCE_FILES),42)
        self.assertEqual(len(inputs.CATALOG_ROWS_SOURCE_FILES),43)
        self.assertTrue(set(inputs.CATALOG_BINDING_SOURCE_FILES)<=set(inputs.CATALOG_DESCRIPTION_SOURCE_FILES))

    def test_unselected_renderer_preserves_historical_crlf_normalization(self):
        original=old.m.ROOT
        temporary=self.root/'templates';(temporary/'modules').mkdir(parents=True)
        source=(original/'modules/SessionModule.bsl').read_text(encoding='utf-8-sig')
        (temporary/'modules/SessionModule.bsl').write_bytes(source.replace('\n','\r\n').encode('utf-8-sig'))
        expected=old.m._module('SessionModule.bsl',old.NONCE,'/tmp/onec-db-oracle/evidence')
        with mock.patch.object(old.m,'ROOT',temporary):
            actual=old.m._module('SessionModule.bsl',old.NONCE,'/tmp/onec-db-oracle/evidence')
        self.assertEqual(actual,expected)
        pinned=(m.ROOT/'modules/NativeOracleServer.bsl').read_bytes()
        with self.assertRaises(ValueError):
            m.transform(pinned.replace(b'\n',b'\r\n'),name='modules/NativeOracleServer.bsl',case='description8')

    def test_observe_absent_is_not_present_empty(self):
        for present in (False,True):
            data=dict(schema=2,nonce='a'*32,token='b'*32,case='description8',operation='observe',present=present,actual_description='')
            w=m.validate_witness(json.dumps(data).encode(),nonce='a'*32,token='b'*32,case='description8',operation='observe')
            self.assertIs(w.present,present)
            if not present:
                data['actual_description']='unexpected'
                with self.assertRaises(ValueError):m.validate_witness(json.dumps(data).encode(),nonce='a'*32,token='b'*32,case='description8',operation='observe')
        raw=m.transform((m.ROOT/'modules/NativeOracleServer.bsl').read_bytes(),name='modules/NativeOracleServer.bsl',case='description8').decode()
        self.assertIn('Операция = "update" Или Операция = "observe" Тогда',raw)
        self.assertIn('2, @@NONCE@@',raw)

if __name__=='__main__':unittest.main()
