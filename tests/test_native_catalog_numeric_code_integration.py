"""Closed opt-in wiring and native observer sidecar mechanics; no native run."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_metadata as old
import catalog_numeric_code_measurement as m
import inputs

class NumericCodeIntegrationTests(unittest.TestCase):
    def setUp(self):
        old.MetadataTest.setUp(self)

    def test_both_cases_full_inject_promote_redump(self):
        for case,(length,_,_) in m.CASES.items():
            v1=self.root/case;v2=self.root/(case+'v2')
            old.m.inject(self.source,v1,nonce=old.NONCE,evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'),numeric_case=case)
            old.m.inspect(v1,1,numeric_case=case)
            old.m.promote_v2(v1,v2,numeric_case=case)
            self.assertEqual(old.m.inspect(v2,2,numeric_case=case)['payload_length'],64)
            old.m.verify_redump(v1,v1,1,numeric_case=case)
            old.m.verify_redump(v2,v2,2,numeric_case=case)
            self.assertEqual(len(list((v1/'Catalogs').glob('*.xml'))),1)
            for root in (v1,v2):
                self.assertIn(f'<CodeLength>{length}</CodeLength>',(root/'Catalogs/NativeOracleItems.xml').read_text(encoding='utf-8-sig'))
                self.assertNotIn('@@',(root/'CommonModules/NativeOracleServer/Ext/Module.bsl').read_text(encoding='utf-8-sig'))
                with self.assertRaises(ValueError):old.m.inspect(root,1 if root==v1 else 2)
            original=(v1/'Catalogs/NativeOracleItems.xml').read_bytes()
            (v1/'Catalogs/NativeOracleItems.xml').write_bytes(original.replace(b'<CodeLength>'+str(length).encode()+b'</CodeLength>',b'<CodeLength>2</CodeLength>'))
            with self.assertRaises(ValueError):old.m.inspect(v1,1,numeric_case=case)

    def test_exact_numeric_metadata_and_mode_selection(self):
        target=self.root/'numeric'
        old.m.inject(self.source,target,nonce=old.NONCE,evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'),numeric_case='number3')
        path=target/'Catalogs/NativeOracleItems.xml';original=path.read_bytes()
        for before,after in ((b'<CodeType>Number</CodeType>',b'<CodeType>String</CodeType>'),(b'<Autonumbering>false</Autonumbering>',b'<Autonumbering>true</Autonumbering>'),(b'<DescriptionLength>8</DescriptionLength>',b'<DescriptionLength>0</DescriptionLength>')):
            with self.subTest(before=before):
                self.assertIn(before,original);path.write_bytes(original.replace(before,after))
                with self.assertRaises(ValueError):old.m.inspect(target,1,numeric_case='number3')
        path.write_bytes(original)
        for other in ({'description_case':'description8'},{'catalog_field_matrix':True},{'numeric_case':'number4'}):
            options={'numeric_case':'number3'};options.update(other)
            with self.subTest(options=options),self.assertRaises(ValueError):
                old.m.inspect(target,1,**options)
