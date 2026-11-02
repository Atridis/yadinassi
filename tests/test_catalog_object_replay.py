"""Minimal logical reference model is explicit, separate from native XML import."""
from pathlib import Path
import sys,unittest,json,subprocess,tempfile,os
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from catalog_object_behavior import replay as model,fixture
from yadinassi.configuration_xml import import_configuration

class CatalogObjectReplayTests(unittest.TestCase):
    def test_model_schema_matches_owned_catalog_but_not_full_import_claim(self):
        setup,assets=fixture.load_saved();files=model.logical_model_files(setup);config=import_configuration(files)
        self.assertEqual(config.activation_issues,());self.assertEqual(len(config.catalogs),1)
        schema=config.catalogs[0]
        self.assertEqual((str(schema.identity),schema.name,schema.code_length,schema.description_length,schema.fields),(setup.metadata_uuid,setup.name,8,64,()))
        self.assertNotEqual(files['Catalogs/'+setup.name+'.xml'],assets['generated/Catalog.xml'])
        self.assertFalse(model.METADATA_IMPORT_PARITY_CLAIMED)
        self.assertEqual(model.COMPARISON_SCOPE,'owned-catalog-object-logical-reference-model')
    def test_behavior_property_mismatch_refuses_model_construction(self):
        setup,assets=fixture.load_saved();raw=assets['generated/Catalog.xml']
        changes=((b'<Hierarchical>false',b'<Hierarchical>true'),(b'<Owners/>',b'<Owners>Other</Owners>'),
                 (b'<CheckUnique>true',b'<CheckUnique>false'),(b'<Autonumbering>false',b'<Autonumbering>true'),
                 (b'<CodeAllowedLength>Variable',b'<CodeAllowedLength>Fixed'),
                 (b'<xr:FillChecking>DontCheck',b'<xr:FillChecking>ShowError'),
                 (b'<ChildObjects/>',b'<ChildObjects><ObjectModule>Hook</ObjectModule></ChildObjects>'))
        for before,after in changes:
            changed=raw.replace(before,after);self.assertNotEqual(changed,raw)
            with self.subTest(after=after),patch.object(model.packet,'render_xml',return_value=changed),self.assertRaises(ValueError):
                model.logical_model_files(setup)

    def test_actual_runtime_all24_rows_are_json_safe_and_repeatable(self):
        before=fixture.load_saved()[1]
        first=model.replay();second=model.replay()
        self.assertEqual(first,second);self.assertEqual(len(first),24)
        self.assertEqual(json.loads(json.dumps(first)),first)
        self.assertIs(type(first[17]),int);self.assertEqual(first[17],1)
        self.assertIs(first[13],False);self.assertIs(first[18],False)
        self.assertEqual(first[19],'first-update')
        self.assertEqual(fixture.load_saved()[1],before)
    def test_cold_import_tests_only_from_unrelated_directory(self):
        env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'tests')
        run=subprocess.run([sys.executable,'-c','import test_catalog_object_replay'],cwd=tempfile.gettempdir(),env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__':unittest.main()
