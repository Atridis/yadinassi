"""Offline authored packet checks; not native behavioral evidence."""
import hashlib
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from server_module_reuse_packet import packet, parse_records, PACKET_HASHES, SOURCE_SHA256, FORM_SHA256, MODULES_SHA256
from server_module_reuse_packet import route
from yadinassi.configuration_modules import compile_module

class PacketTests(unittest.TestCase):
    def test_inventory(self):
        self.assertEqual(len(packet()),13)
        self.assertEqual(set(packet()),set(PACKET_HASHES))
    def test_source_identity(self):
        for name,raw in packet().items():
            self.assertEqual(hashlib.sha256(raw).hexdigest(),PACKET_HASHES[name])
    def test_prepared(self):
        self.assertEqual(route.validate_prepared(route.sources()),route.module_digest())
    def test_changed_module_refused(self):
        values=route.sources(); values['CommonModules/ServerSession/Ext/Module.bsl']+=b'// drift'
        with self.assertRaises(ValueError):route.validate_prepared(values)
    def test_added_file_refused(self):
        values=route.sources();values['extra']=b'x'
        with self.assertRaises(ValueError):route.validate_prepared(values)
    def test_marker_binding(self):
        import json
        value=dict(schema=route.SCHEMA,nonce='a'*32,phase='entered',source_sha256=SOURCE_SHA256,form_sha256=FORM_SHA256,modules_sha256=MODULES_SHA256,records='')
        self.assertEqual(route.marker(json.dumps(value).encode(),'a'*32,'entered'),value)
        with self.assertRaises(ValueError):route.marker(json.dumps(value).encode(),'b'*32,'entered')
    def test_records_complete(self):
        self.assertEqual(parse_records(''.join(f'SR{i}=1|' for i in range(1,17)).encode()),('1',)*16)
    def test_records_error_retained(self):
        self.assertEqual(parse_records(''.join(f'SR{i}=error|' for i in range(1,17)).encode()),('error',)*16)
    def test_records_reorder_refused(self):
        with self.assertRaises(ValueError):parse_records(''.join(f'SR{i}=1|' for i in reversed(range(1,17))).encode())
    def test_raw_token_refused(self):
        with self.assertRaises(ValueError):parse_records(b'SR1=12345678-1234-1234-1234-123456789abc|',1)
    def test_source_drift_refused(self):
        with patch('server_module_reuse_packet.PACKET_HASHES',{'Launcher.xml':'0'*64}):
            with self.assertRaises(ValueError):packet()
    def test_module_authority(self):
        ns={'m':'http://v8.1c.ru/8.3/MDClasses'}
        for name in ('ServerSession','ServerRequest','CachedServerCall','ServerInspector'):
            path=f'CommonModules/{name}/Ext/Module.bsl'
            self.assertTrue(compile_module(packet()[path],path,'server',common=True))
            props=ET.fromstring(packet()[f'CommonModules/{name}.xml']).find('m:CommonModule/m:Properties',ns)
            for flag in ('Global','ClientManagedApplication','ExternalConnection','ClientOrdinaryApplication','Privileged'):
                self.assertEqual(props.find('m:'+flag,ns).text,'false')
            self.assertEqual(props.find('m:Server',ns).text,'true')
            self.assertEqual(props.find('m:ServerCall',ns).text,str(name in ('CachedServerCall','ServerInspector')).lower())
    def test_real_event_boundary(self):
        text=packet()['Launcher/Forms/Main/Ext/Form/Module.bsl'].decode()
        self.assertIn('AttachIdleHandler("SecondEvent", 1, True)',text)
        self.assertNotIn('SecondEvent();',text)
        self.assertIn('RequestToken = ServerInspector.RequestToken("lifetime")',text)
    def test_no_expected_answers(self):
        text=packet()['Launcher/Forms/Main/Ext/Form/Module.bsl'].decode()
        self.assertIn('Value = Observe(Number)',text)
        self.assertIn('Records = Records + "SR" + String(Number) + "=" + Value',text)
        self.assertNotIn('Expected',text)
    def test_server_exports_by_value(self):
        for name in ('CachedServerCall','ServerInspector'):
            text=packet()[f'CommonModules/{name}/Ext/Module.bsl'].decode()
            self.assertNotIn('New Array',text)
            for line in text.splitlines():
                if line.startswith('Function '):self.assertIn('(Val Key)',line)
    def test_refresh_side_is_distinct(self):
        text=packet()['CommonModules/ServerInspector/Ext/Module.bsl'].decode()
        self.assertIn('Procedure RefreshServer() Export\n RefreshReusableValues();',text)
        form=packet()['Launcher/Forms/Main/Ext/Form/Module.bsl'].decode()
        self.assertIn('ServerInspector.RefreshServer(); RefreshReusableValues();',form)
