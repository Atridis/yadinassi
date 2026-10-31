import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/native_1c_db_oracle'))
from catalog_read_packet import probe
from catalog_read_packet import scalar_wire as wire
from yadinassi.syntax.parser import parse

class Tests(unittest.TestCase):
    def test_generation_parse_and_repeat(self):
        a,b=probe.fresh_setup(),probe.fresh_setup()
        self.assertTrue(set(a.names+a.metadata_ids+a.record_ids).isdisjoint(b.names+b.metadata_ids+b.record_ids))
        for block in probe.cases(a):
            source=probe.render(a,block);parse(source)
            self.assertNotIn('@@',source)
            self.assertNotIn('NativeOracleItems',source)
            self.assertEqual(len(probe.cases(a)[block]),24)
    def test_controls_use_documented_reference_metadata_not_manager_method(self):
        from catalog_read_packet import batch
        from catalog_read_fixture import load, BLOCKS
        for repeat in (1, 2):
            b, _, files = load(repeat)
            cases = probe.cases(b.setup)
            for block in ('identity', 'types', 'errors'):
                self.assertIn('.EmptyRef().Metadata().Name', cases[block][0][1])
            self.assertIn('.EmptyRef().Metadata().Name', cases['identity'][1][1])
            # Unsupported manager method remains an observation, not a control.
            self.assertEqual(dict(cases['identity'])['manager.metadata'],
                f'Catalogs.{b.setup.names[0]}.Metadata() = Metadata.Catalogs.{b.setup.names[0]}')
            for block in ('cursor', 'fields', 'lookup', 'row4'):
                self.assertIn('.EmptyRef().Metadata().Name', batch.render_block(b, block)[1][0][1])
            for state in batch.STATES:
                text = files['setup-' + state + '.bsl'].decode()
                self.assertNotIn('Manager.Metadata()', text)
                self.assertEqual(text.count('Manager.EmptyRef().Metadata().Name'), 2)
            self.assertIn('.EmptyRef().Metadata().Name', probe.render_fresh(b.setup))

    def test_observer_runs_without_unsupported_success(self):
        from yadinassi import Interpreter
        s=probe.fresh_setup()
        for block in probe.cases(s):
            output=[]
            Interpreter(output.append).execute(probe.render(s,block))
            raw=('\n'.join(output)+'\n').encode('ascii')
            records=wire.validate_output(raw)
            self.assertEqual(len(records),24)
            with self.assertRaises(ValueError):probe.require_available(raw,s,block)
    def test_catalog_fragments(self):
        import xml.etree.ElementTree as ET
        s=probe.fresh_setup(); files,identities=probe.catalog_artifacts(s)
        self.assertEqual(len(files),2)
        ids=[]
        for i,name in enumerate(s.names):
            raw=files[f'Catalogs/{name}.xml'];root=ET.fromstring(raw)
            self.assertNotIn(b'@@',raw)
            self.assertNotIn(b'NativeOracleItems',raw)
            catalog=root.find('{http://v8.1c.ru/8.3/MDClasses}Catalog')
            self.assertEqual(catalog.attrib['uuid'],s.metadata_ids[i])
            self.assertEqual(len(catalog.find('{http://v8.1c.ru/8.3/MDClasses}ChildObjects')),0)
            ids.extend(identities[name].values())
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(set(ids).isdisjoint(s.record_ids))
    def test_wire_max(self):
        raw=wire.C1+wire.C2+b''.join(f'CR-{i:02}: [ok|S64:{"0000"*64}]\n'.encode() for i in range(1,25))
        self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertLess(len(raw),8192)
        self.assertEqual(len(wire.validate_output(raw)),24)
    def test_closed_wire(self):
        raw=wire.C1+wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,25))
        for bad in (raw+b'\n',raw.replace(b'CR-02',b'CR-01'),raw.replace(b'\n',b'\r\n'),raw[:-1],raw.replace(b'action-error',b'ok|N65'),raw.replace(b'action-error',b'ok|S1:d83d0000'),raw.replace(b'action-error',b'ok|S1:FFFF')):
            with self.assertRaises(ValueError):wire.validate_output(bad)
        for block in ('identity','types','errors'):
            with self.assertRaises(ValueError):probe.require_available(raw,probe.fresh_setup(),block)
    def test_positive_control(self):
        s=probe.fresh_setup()
        for block in probe.cases(s):
            values=([*s.names,s.record_ids[0],s.record_ids[0]] if block=='identity' else [s.names[0],s.record_ids[0]])
            lines=[]
            for i in range(24):
                scalar='B1' if i>=len(values) else 'S'+str(len(values[i]))+':'+''.join(f'{ord(c):04x}' for c in values[i])
                lines.append(f'CR-{i+1:02}: [ok|{scalar}]\n'.encode())
            raw=wire.C1+wire.C2+b''.join(lines)
            self.assertEqual(len(probe.require_available(raw,s,block)),24)
            with self.assertRaises(ValueError):probe.require_available(raw,probe.fresh_setup(),block)
    def test_identity_roles_and_name_injection(self):
        s=probe.fresh_setup()
        for invalid in (probe.Setup(('C12345678','x";'),s.metadata_ids,s.record_ids),probe.Setup(s.names,s.metadata_ids,(s.metadata_ids[0],s.record_ids[1])),probe.Setup(s.names,s.metadata_ids,('00000000-0000-0000-0000-000000000000',s.record_ids[1]))):
            with self.assertRaises(ValueError):probe.cases(invalid)

if __name__=='__main__':unittest.main()
