"""Official XML-only fixture admission; no native database data or sessions."""
from pathlib import Path
import sys,unittest,hashlib,subprocess,os,tempfile,re,shutil
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from catalog_object_behavior import fixture as f
from native_1c_bootstrap.inject_modules import role_documents,ROLE_NAME,ROLE_FILES


def baseline():
    config=('<?xml version="1.0" encoding="UTF-8"?>\n<MetaDataObject xmlns="'+f.MD+'" version="2.20"><Configuration uuid="10000000-0000-4000-8000-000000000001"><Properties><Name>OwnedApplication</Name><DefaultRunMode>ManagedApplication</DefaultRunMode><DefaultRoles/></Properties><ChildObjects><Language>English</Language><Role>'+ROLE_NAME+'</Role></ChildObjects></Configuration></MetaDataObject>').encode()
    files={'Configuration.xml':config,'Ext/SessionModule.bsl':b'// owned bootstrap\n','ConfigDumpInfo.xml':b'<ExportInfo/>'}
    files.update(role_documents({'namespace':f.MD,'format_version':'2.20','configuration_name':'OwnedApplication','configuration_uuid':'10000000-0000-4000-8000-000000000001'}))
    return files

class CatalogObjectFixtureTests(unittest.TestCase):
    def test_saved_hashes_render_and_exact_baseline_preservation(self):
        s,assets=f.load_saved();files=baseline();copy=dict(files);actual_s,expected=f.prepare(files)
        self.assertEqual(s,actual_s);self.assertEqual(files,copy)
        self.assertEqual(set(expected)-set(files),{'Catalogs/'+s.name+'.xml'})
        self.assertEqual(expected['Catalogs/'+s.name+'.xml'],assets['generated/Catalog.xml'])
        for name in set(files)-{'Configuration.xml',ROLE_FILES[1]}:self.assertEqual(expected[name],files[name])
        self.assertEqual(expected['Configuration.xml'].replace(('<Catalog>'+s.name+'</Catalog>').encode(),b''),files['Configuration.xml'])
        self.assertTrue(f.verify_redump(expected,dict(expected)))
    def test_exact_added_permissions_and_original_rights_preserved(self):
        files=baseline();s,expected=f.prepare(files);root,_=f._xml(expected[ROLE_FILES[1]]);rn='{'+f.RIGHTS+'}'
        objects=root.findall(rn+'object');self.assertEqual(len(objects),2)
        self.assertEqual(objects[1].find(rn+'name').text,'Catalog.'+s.name)
        self.assertEqual([n.find(rn+'name').text for n in objects[1].findall(rn+'right')],['Read','Insert','Update'])
        for old,new in ((b'Insert',b'Delete'),(b'<value>true</value>',b'<value>false</value>')):
            changed=dict(expected);changed[ROLE_FILES[1]]=changed[ROLE_FILES[1]].replace(old,new)
            with self.assertRaises(ValueError):f.verify_redump(expected,changed)
    def test_nonempty_or_foreign_baseline_refused_before_addition(self):
        for old,new in ((b'<Role>',b'<Catalog>X</Catalog><Role>'),(b'<DefaultRoles/>',b'<DefaultRoles>All</DefaultRoles>')):
            files=baseline();files['Configuration.xml']=files['Configuration.xml'].replace(old,new)
            with self.assertRaises(ValueError):f.prepare(files)
        files=baseline();files[ROLE_FILES[1]]=files[ROLE_FILES[1]].replace(b'<name>Administration</name>',b'<name>FullAccess</name>')
        with self.assertRaises(ValueError):f.prepare(files)
    def test_inventory_modules_identity_and_used_qnames_must_match(self):
        _,expected=f.prepare(baseline())
        for mode in ('extra','module','identity','qname'):
            changed=dict(expected)
            if mode=='extra':changed['Ext/Foreign.bsl']=b'// extra'
            elif mode=='module':changed['Ext/SessionModule.bsl']+=b'Message("changed");'
            else:
                name=next(p for p in changed if p.startswith('Catalogs/'))
                changed[name]=changed[name].replace(b'xmlns:xs="http://www.w3.org/2001/XMLSchema"',b'xmlns:xs="urn:foreign"') if mode=='qname' else changed[name].replace(b'<Name>OwnedCatalog',b'<Name>ForeignCatalog')
            with self.subTest(mode=mode),self.assertRaises(ValueError):f.verify_redump(expected,changed)
    def test_prefix_alias_and_bookkeeping_do_not_change_semantics(self):
        _,expected=f.prepare(baseline());actual=dict(expected)
        name=next(p for p in actual if p.startswith('Catalogs/'))
        actual[name]=actual[name].replace(b'xmlns:xs=',b'xmlns:scalar=').replace(b'xsi:type="xs:',b'xsi:type="scalar:')
        actual['ConfigDumpInfo.xml']=b'<ExportInfo version="new"/>'
        self.assertTrue(f.verify_redump(expected,actual))
    def test_baseline_rights_type_namespace_cannot_be_rebound(self):
        files=baseline();raw=files[ROLE_FILES[1]]
        raw=re.sub(rb'(</?)([A-Za-z][A-Za-z0-9]*)',rb'\1r:\2',raw)
        raw=raw.replace(('xmlns="'+f.RIGHTS+'"').encode(),('xmlns:r="'+f.RIGHTS+'" xmlns="urn:foreign"').encode())
        files[ROLE_FILES[1]]=raw
        with self.assertRaises(ValueError):f.prepare(files)

    def test_path_entity_and_asset_mutations_refused(self):
        for path,raw in (('../x.xml',b'<x/>'),('More.xml',b'<!DOCTYPE x><x/>')):
            files=baseline();files[path]=raw
            with self.assertRaises(ValueError):f.prepare(files)
        with patch.dict(f.ASSET_HASHES,{'packet.py':'0'*64}),self.assertRaises(ValueError):f.load_saved()
    def test_cold_staged_import_has_only_actual_bootstrap_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copytree(ROOT/'scripts/catalog_object_behavior',root/'catalog_object_behavior',ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copyfile(ROOT/'scripts/native_1c_bootstrap/inject_modules.py',root/'inject_modules.py')
            code='import sys;sys.path.insert(0,'+repr(str(root))+');from catalog_object_behavior.fixture import load_saved;load_saved()'
            proc=subprocess.run([sys.executable,'-I','-c',code],cwd=tmp,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)

    def test_cold_import_with_only_tests_path(self):
        env=dict(os.environ);env['PYTHONPATH']=str(ROOT/'tests')
        proc=subprocess.run([sys.executable,'-c','import test_catalog_object_fixture'],cwd=tempfile.gettempdir(),env=env,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)

if __name__=='__main__':unittest.main()
