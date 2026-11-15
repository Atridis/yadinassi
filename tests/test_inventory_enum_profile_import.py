"""Explicit fresh enum profile CLI/preflight, never a migration or auto-grant."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from yadinassi.configuration_profile_import import prepare_files,prepare_directory,create_prepared
from yadinassi.configuration_inventory_enums import PROFILE
from yadinassi.configuration_diagnostics import ImportRefusal
from yadinassi.runtime import Interpreter
from test_configuration_inventory_enums import source,FIXTURE

ROOT=Path(__file__).resolve().parents[1]

class InventoryEnumProfileImportTests(unittest.TestCase):
    def test_explicit_preflight_reports_exact_fresh_format(self):
        prepared=prepare_files(source(),profile=PROFILE)
        self.assertEqual(prepared.files,tuple(sorted(source().items())))
        report=prepared.report()
        self.assertTrue(report['ready']);self.assertEqual(report['storage_format'],16)
        self.assertEqual((report['catalogs'],report['documents'],report['registers']),(2,2,1))

    def test_directory_preflight_matches_retained_bytes(self):
        a=prepare_directory(FIXTURE,profile=PROFILE);b=prepare_files(source(),profile=PROFILE)
        self.assertEqual(a,b)

    def test_fresh_create_uses_typed_canonical_namespace(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            path=Path(directory)/'owned.sqlite'
            context=create_prepared(path,prepare_files(source(),profile=PROFILE))
            try:
                vm=Interpreter(database_context=context)
                try:self.assertTrue(vm.execute('Catalogs.Products.CreateItem().Unit.IsEmpty()'))
                finally:vm.close()
            finally:context.close()

    def test_old_profile_cannot_silently_activate_enum_source(self):
        for profile in ('accumulation-balance-scalar-v1','accumulation-reference-v1'):
            with self.assertRaises((ValueError,ImportRefusal)):prepare_files(source(),profile=profile)

    def test_profile_options_remain_closed(self):
        for options in ({'activate':False},{'module_runtime':'commonmodules-v1'},{'numbering_policy':'automatic'}):
            with self.assertRaises(ImportRefusal):prepare_files(source(),profile=PROFILE,**options)

    def test_tampered_retained_source_refused_before_destination(self):
        prepared=prepare_files(source(),profile=PROFILE)
        files=dict(prepared.files);files['Enums/Units.xml']=b'<not-configuration/>'
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            path=Path(directory)/'absent.sqlite'
            with self.assertRaises((ValueError,ImportRefusal)):
                create_prepared(path,replace(prepared,files=tuple(sorted(files.items()))))
            self.assertFalse(path.exists())

    def test_cli_explicit_preflight_and_fresh_create(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            path=Path(directory)/'owned.sqlite'
            env=dict(os.environ,PYTHONPATH=str(ROOT))
            check=subprocess.run([sys.executable,'-m','yadinassi','--check-xml',str(FIXTURE),
                '--source-profile',PROFILE,'--report-json'],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(check.returncode,0,check.stderr)
            self.assertEqual(json.loads(check.stdout)['storage_format'],16)
            create=subprocess.run([sys.executable,'-m','yadinassi','--create-db',str(path),
                '--import-xml',str(FIXTURE),'--source-profile',PROFILE],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(create.returncode,0,create.stderr)
            self.assertTrue(path.is_file())
