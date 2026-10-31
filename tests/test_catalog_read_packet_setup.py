import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/native_1c_db_oracle'))
from catalog_read_packet import probe,setup_adapter as setup,scalar_wire as wire
from yadinassi.syntax.parser import parse
BASE=Path(probe.__file__).parent
CONFIG=b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Configuration><ChildObjects><Catalog>NativeOracleItems</Catalog></ChildObjects></Configuration></MetaDataObject>'
class SetupTests(unittest.TestCase):
    def test_saved_replay_and_source_extension(self):
        s=probe.fresh_setup();f,ids=probe.catalog_artifacts(s)
        rights=(BASE/'CRUDRights.xml').read_bytes().replace(b'@@CONFIGURATION_NAME@@',b'OwnedProbe')
        a=setup.extend_sources(s,f,ids,CONFIG,rights);b=setup.extend_sources(s,f,ids,CONFIG,rights)
        self.assertEqual(a,b);self.assertEqual(a['Configuration.xml'].count(b'<Catalog>'),3)
        self.assertEqual(a['Roles/NativeOracleCatalogCRUD/Ext/Rights.xml'].count(b'<name>Catalog.'),3)
        self.assertTrue(setup.verify_redump(s,f,ids,f))
        regenerated,_=probe.catalog_artifacts(s)
        with self.assertRaises(ValueError):setup.verify_redump(s,f,ids,regenerated)
        parse(setup.render_setup(s))
        source=setup.render_setup(s)
        self.assertLess(source.index('Функция CRCount'),source.index('Сообщить("CR-C1:'))
        extra=b'<object><name>Catalog.'+s.names[0].encode()+b'</name></object>'
        for invalid in (rights.replace(b'</Rights>',extra+b'</Rights>'),rights.replace(b'</object>',b'<unexpected/>'+b'</object>',1),rights.replace(b'<value>true</value>',b'<value>false</value>',1)):
            with self.assertRaises(ValueError):setup.add_rights(invalid,s)

    def test_invalid_sources(self):
        s=probe.fresh_setup();f,ids=probe.catalog_artifacts(s)
        for raw in (CONFIG.replace(b'NativeOracleItems',b'Other'),CONFIG.replace(b'<Catalog>',b'<Catalog>Other</Catalog><Catalog>',1),b'<!DOCTYPE a>'+CONFIG):
            with self.assertRaises(ValueError):setup.add_refs(raw,s)
        altered=dict(f);key=next(iter(f));altered[key]=f[key].replace(s.metadata_ids[0].encode(),s.record_ids[0].encode())
        with self.assertRaises(ValueError):setup.validate_saved(s,altered,ids)
        for raw in (f[key].replace(b'<CodeLength>2',b'<CodeLength>9'),f[key].replace(b'<ChildObjects/>',b''),b'<broken'):
            with self.assertRaises(ValueError):setup.validate_saved(s,{**f,key:raw},ids)

    def test_setup_evidence(self):
        s=probe.fresh_setup();values=['N0','N1','N1','N0','S36:'+''.join(f'{ord(c):04x}' for c in s.record_ids[0]),'B1']*2
        raw=wire.C1+wire.C2+b''.join(f'CR-{i:02}: [ok|{v}]\n'.encode() for i,v in enumerate(values,1))
        self.assertEqual(len(setup.require_setup_evidence(raw,s)),12)
        for bad in (raw.replace(b'ok|N0',b'ok|N1'),raw.replace(b'ok|B1',b'action-error'),raw.replace(b'ok|N1',b'ok|B1')):
            with self.assertRaises(ValueError):setup.require_setup_evidence(bad,s)
if __name__=='__main__':unittest.main()
