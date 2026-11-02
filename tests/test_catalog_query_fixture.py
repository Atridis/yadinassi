"""Strict owned XML fixture and labelled logical Query replay, not native proof."""
from pathlib import Path
import sys
import unittest
import tempfile
import subprocess
import shutil
from dataclasses import replace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from catalog_query_behavior import fixture as f, replay, packet
from test_catalog_object_fixture import baseline


class CatalogQueryFixtureTests(unittest.TestCase):
    def test_saved_install_preserves_baseline_and_has_only_scoped_rights(self):
        setup, assets = f.load_saved(); files = baseline(); original = dict(files)
        actual, expected = f.prepare(files)
        self.assertEqual(actual, setup); self.assertEqual(files, original)
        self.assertEqual(set(expected)-set(files), {'Catalogs/'+setup.name+'.xml'})
        for path in set(files)-{'Configuration.xml', f.ROLE_FILES[1]}:
            self.assertEqual(expected[path], files[path])
        self.assertTrue(f.verify_redump(expected, dict(expected)))
        rights,_=f._xml(expected[f.ROLE_FILES[1]]);rn='{'+f.RIGHTS+'}'
        obj=rights.findall(rn+'object')[-1]
        self.assertEqual([n.find(rn+'name').text for n in obj.findall(rn+'right')], ['Read','Insert','Update'])

    def test_semantic_field_or_right_or_module_change_is_not_normalized(self):
        setup,expected=f.prepare(baseline());name='Catalogs/'+setup.name+'.xml'
        for old,new in ((b'<v8:Digits>12</v8:Digits>',b'<v8:Digits>13</v8:Digits>'),
                        (b'xmlns:xs="http://www.w3.org/2001/XMLSchema"',b'xmlns:xs="urn:foreign"'),
                        (b'<FillChecking>DontCheck</FillChecking>',b'<FillChecking>ShowError</FillChecking>')):
            changed=dict(expected);changed[name]=changed[name].replace(old,new)
            self.assertNotEqual(changed[name],expected[name])
            with self.assertRaises(ValueError):f.verify_redump(expected,changed)
        changed=dict(expected);changed['Ext/Foreign.bsl']=b'// foreign'
        with self.assertRaises(ValueError):f.verify_redump(expected,changed)
        changed=dict(expected);changed[f.ROLE_FILES[1]]=changed[f.ROLE_FILES[1]].replace(b'<name>Insert</name>',b'<name>Delete</name>')
        with self.assertRaises(ValueError):f.verify_redump(expected,changed)

    def test_field_and_record_id_collision_with_baseline_refused(self):
        setup,_=f.load_saved(); files=baseline()
        config,_=f._xml(files['Configuration.xml']);identity=config[0].get('uuid')
        for changed in (replace(setup,field_ids=(identity,*setup.field_ids[1:])),
                        replace(setup,record_ids=(identity,*setup.record_ids[1:]))):
            with self.assertRaises(ValueError):f._baseline(files,changed)

    def test_cold_staged_fixture_import_and_saved_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copytree(ROOT/'scripts/catalog_query_behavior',root/'catalog_query_behavior',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(ROOT/'scripts/native_1c_bootstrap/inject_modules.py',root/'inject_modules.py')
            code='import sys;sys.path.insert(0,'+repr(str(root))+');from catalog_query_behavior.fixture import load_saved;load_saved()'
            result=subprocess.run([sys.executable,'-I','-c',code],cwd=directory,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        with patch.dict(f.ASSET_HASHES,{'packet.py':'0'*64}),self.assertRaises(ValueError):f.load_saved()

    def test_logical_model_replay_preserves_actual_source_and_observes_24(self):
        setup,assets=f.load_saved();before=dict(assets)
        rows=replay.replay()
        self.assertEqual(len(rows),24)
        self.assertIs(type(rows[18]),int)
        self.assertEqual(rows[18],3)
        self.assertFalse(replay.METADATA_IMPORT_PARITY_CLAIMED)
        self.assertEqual(replay.COMPARISON_SCOPE,'owned-catalog-query-logical-reference-model')
        self.assertEqual(f.load_saved()[1],before)
        # Own logical contract only, not a fabricated native expected result.
        self.assertEqual(rows[0],'01')
        self.assertEqual(rows[15:17],['action-error','action-error'])
        self.assertEqual(rows[22],'10/10')
        self.assertTrue(rows[23])

    def test_behavior_binding_rejects_changed_type_or_validation(self):
        setup,assets=f.load_saved();raw=assets['generated/Catalog.xml']
        for old,new in ((b'<v8:Digits>12</v8:Digits>',b'<v8:Digits>13</v8:Digits>'),
                        (b'<CheckUnique>true</CheckUnique>',b'<CheckUnique>false</CheckUnique>'),
                        (b'<FillChecking>DontCheck</FillChecking>',b'<FillChecking>ShowError</FillChecking>')):
            changed=raw.replace(old,new);self.assertNotEqual(changed,raw)
            with self.assertRaises(ValueError):replay.require_behavior_profile(setup,changed)


if __name__=='__main__':unittest.main()
