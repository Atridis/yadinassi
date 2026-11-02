import hashlib
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import form_runtime_packet as packet
from yadinassi.form_runtime import FormSession


class FormPacketTests(unittest.TestCase):
    def test_local_source_replay_not_native_acquisition(self):
        output=[]
        session=FormSession(packet.source(),output=output.append,bindings={
            'OnCreateAtServer':'FormCreate','OnOpen':'FormOpen','BeforeClose':'FormBeforeClose'})
        result=session.open()
        raw=dict(result.attributes)['FLog'].encode('ascii')
        records=packet.require_available(packet.parse_records(raw))
        self.assertEqual(len(records),40)
        self.assertEqual(records[23:25],('server-create','server-create:client-open'))
        self.assertEqual(records[30],'direct-change:NameField')
        self.assertEqual(records[36],'cancel')
        self.assertEqual(records[38],'continue')
        self.assertEqual(session.state,'open')  # Direct BeforeClose is NOT a close.
        self.assertIn('automatic-command-dispatch',packet.UNMEASURED)
        self.assertEqual(packet.KINDS[30],'direct-handler')

    def test_source_and_actual_wiring_contract(self):
        source=packet.source()
        self.assertLessEqual(len(source.encode('utf-8')),8192)
        self.assertIn('&AtServer\nProcedure FormCreate',source)
        self.assertIn('&AtClient\nProcedure FormOpen',source)
        raw=(packet.ROOT/'form.xml').read_bytes()
        self.assertTrue(packet.validate_wiring(raw))
        with self.assertRaises(ValueError):packet.validate_wiring(raw.replace(b'OnCreateAtServer',b'OnOpen'))
        with self.assertRaises(ValueError):packet.validate_wiring(b'<!DOCTYPE Form>'+raw)

    def test_strict_count_order_and_failure(self):
        raw=''.join('MF'+str(i)+'=ok|' for i in range(1,41)).encode()
        self.assertEqual(len(packet.parse_records(raw)),40)
        for bad in (raw[:-1],raw+raw,raw.replace(b'MF2=',b'MF1='),raw.replace(b'=ok|',b'=private path|',1)):
            with self.assertRaises(ValueError):packet.parse_records(bad)
        records=packet.parse_records(raw.replace(b'MF27=ok|',b'MF27=!E|'))
        with self.assertRaises(ValueError):packet.require_available(records)
