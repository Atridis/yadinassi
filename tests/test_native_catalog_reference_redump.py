"""Real injected XML/redump identity path; only the native batch process is stubbed.

These are invented dumps, not native compilation or Catalog-reference evidence.
"""
from pathlib import Path, PurePosixPath
import os
import shutil
import tempfile
import unittest
from unittest import mock
import uuid

import test_native_1c_db_oracle_stage as stages
import inject_metadata as metadata
import catalog_reference_identity as reference
from snapshots import OracleError

ROOT=Path(__file__).resolve().parents[1]


class ReferenceRedumpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        if os.name=='nt':
            patch=mock.patch.object(metadata,'Path',PurePosixPath)
            patch.start();self.addCleanup(patch.stop)

    def backend(self,options):
        root=self.root/('case-'+str(len(list(self.root.iterdir()))));root.mkdir()
        source=root/'native-empty';source.mkdir()
        shutil.copyfile(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml',source/'Configuration.xml')
        (source/'ConfigDumpInfo.xml').write_text('synthetic bookkeeping',encoding='utf-8')
        native=stages.stage.Native(stages.NONCE,stages.provenance(),**options)
        native.root=root;native.v1=root/'metadata-v1';native.v2=root/'metadata-v2'
        kwargs={'catalog_field_matrix':native.catalog_field_matrix}
        if native.reference_case is not None:kwargs['reference_case']=native.reference_case
        metadata.inject(source,native.v1,nonce=native.nonce,
            evidence=PurePosixPath('/tmp/onec-db-oracle/evidence'),**kwargs)
        metadata.promote_v2(native.v1,native.v2,catalog_field_matrix=native.catalog_field_matrix)
        native.redump_mutation=None
        def batch(database,args,label,user):
            self.assertEqual((args[0],args[2:],label),('/DumpConfigToFiles',['-Format','Hierarchical'],'redump'))
            target=Path(args[1])
            shutil.copytree(native.v1 if native.redump_version==1 else native.v2,target)
            if native.redump_mutation is not None:native.redump_mutation(target)
            native.counter+=1
        native.batch=mock.Mock(side_effect=batch)
        return native

    def redump(self,native,stage,version=1):
        native.stage=stage;native.redump_version=version
        native.redump(native.root/'synthetic-database',version,user=None if stage=='seed_v1' else metadata.SETUP_USER)
        self.assertFalse(list(native.root.glob('redump-*')))

    def test_both_reference_cases_seed_then_baseline_create_real_manifest(self):
        for case in reference.CASES:
            with self.subTest(case=case):
                native=self.backend({'reference_case':case})
                self.redump(native,'seed_v1')
                self.assertIsNotNone(native.identity_manifest)
                self.assertFalse(native.identity_baseline_verified)
                saved=native.identity_manifest
                self.assertEqual(len(saved.catalogs),3)
                self.assertEqual(saved.nonce,native.nonce)
                self.redump(native,'baseline')
                self.assertEqual(native.identity_manifest,saved)
                self.assertTrue(native.identity_baseline_verified)
                self.assertEqual(native.batch.call_count,2)

    def test_legacy_binding_and_default_keep_their_identity_behavior(self):
        bound=self.backend({'catalog_readonly_binding':True})
        self.redump(bound,'seed_v1');self.redump(bound,'baseline')
        self.assertIsNotNone(bound.identity_manifest);self.assertTrue(bound.identity_baseline_verified)
        ordinary=self.backend({})
        self.redump(ordinary,'seed_v1');self.redump(ordinary,'baseline')
        self.assertIsNone(ordinary.identity_manifest);self.assertFalse(ordinary.identity_baseline_verified)

    def test_baseline_without_seed_and_repeated_seed_reject(self):
        for case in reference.CASES:
            native=self.backend({'reference_case':case})
            with self.subTest(case=case),self.assertRaises(OracleError) as caught:self.redump(native,'baseline')
            self.assertEqual(caught.exception.kind,'metadata_rejected')
            self.assertIsNone(native.identity_manifest);self.assertFalse(native.identity_baseline_verified)
            self.assertFalse(list(native.root.glob('redump-*')))
            self.redump(native,'seed_v1')
            saved=native.identity_manifest
            with self.assertRaises(OracleError):self.redump(native,'seed_v1')
            self.assertEqual(native.identity_manifest,saved);self.assertFalse(native.identity_baseline_verified)

    def test_unverified_module_or_catalog_cannot_enable_baseline(self):
        def module(root):
            path=root/'CommonModules/NativeOracleServer/Ext/Module.bsl'
            path.write_bytes(path.read_bytes()+b'\n// altered synthetic module\n')
        def catalog(root):
            path=root/'Catalogs/NativeOracleItems.xml'
            raw=path.read_bytes();self.assertIn(b'<v8:Digits>9</v8:Digits>',raw)
            path.write_bytes(raw.replace(b'<v8:Digits>9</v8:Digits>',b'<v8:Digits>8</v8:Digits>',1))
        for case in reference.CASES:
            for mutate in (module,catalog):
                native=self.backend({'reference_case':case});self.redump(native,'seed_v1')
                saved=native.identity_manifest;native.redump_mutation=mutate
                with self.subTest(case=case,mutation=mutate.__name__),self.assertRaises(OracleError) as caught:self.redump(native,'baseline')
                self.assertEqual(caught.exception.kind,'metadata_rejected')
                self.assertEqual(native.identity_manifest,saved);self.assertFalse(native.identity_baseline_verified)
                self.assertFalse(list(native.root.glob('redump-*')))

    def test_verified_but_changed_identity_does_not_replace_seed_manifest(self):
        for case in reference.CASES:
            native=self.backend({'reference_case':case});self.redump(native,'seed_v1')
            saved=native.identity_manifest
            path=native.v1/'Catalogs/NativeOracleItems.xml';raw=path.read_text(encoding='utf-8-sig')
            key=saved.catalogs[0].key
            self.assertIn(key,raw);path.write_text(raw.replace(key,str(uuid.uuid4())),encoding='utf-8-sig')
            # The batch stub copies the changed expected dump exactly. Ordinary
            # verify_redump therefore passes; the retained seed join must reject.
            metadata.verify_redump(native.v1,native.v1,version=1,catalog_field_matrix=True)
            with self.subTest(case=case),self.assertRaises(OracleError) as caught:self.redump(native,'baseline')
            self.assertEqual(caught.exception.kind,'metadata_rejected')
            self.assertEqual(native.identity_manifest,saved);self.assertFalse(native.identity_baseline_verified)

    def test_other_stage_or_version_cannot_create_manifest(self):
        for case in reference.CASES:
            native=self.backend({'reference_case':case})
            self.redump(native,'create');self.redump(native,'baseline',2)
            self.assertIsNone(native.identity_manifest);self.assertFalse(native.identity_baseline_verified)

if __name__=='__main__':unittest.main()
