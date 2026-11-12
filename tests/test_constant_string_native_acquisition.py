"""Offline contracts only, never executes Docker or 1C."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from constant_string_behavior import fixture,route
import native_1c_constant_string_profile as host
from test_session_parameter_native_acquisition import baseline

class ConstantStringWitnessTests(unittest.TestCase):
    def test_bound_source_and_syntax(self):
        from yadinassi.syntax.parser import parse
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(),route.SOURCE_SHA256)
        parse(route.program(None,'a'*32).decode())
    def test_get_precedes_set_and_no_default_assumed(self):
        source=route.source()
        self.assertLess(source.index(b'InitialValue = Constants.OwnedString.Get()'),source.index(b'Constants.OwnedString.Set(Marker)'))
        self.assertEqual(source.count(b'Constants.OwnedString.Set('),1)
        self.assertEqual(source.count(b'Constants.OwnedString.Get()'),2)
        self.assertIn(b'initial.get=error',source)
        self.assertNotIn(b'ErrorDescription()',source)
        self.assertEqual(source.count(b'.error=native-operation-failed'),3)
    def test_single_string64_declaration(self):
        _,assets=fixture.load_saved();root=ET.fromstring(assets['OwnedString.xml'])
        md='{'+fixture.original.MD+'}';v='{'+fixture.original.V8+'}'
        self.assertEqual(root[0].tag,md+'Constant');self.assertEqual(root.find('.//'+v+'Type').text,'xs:string')
        self.assertEqual(root.find('.//'+v+'Length').text,'64')
        self.assertEqual(root.find('.//'+v+'AllowedLength').text,'Variable')
        generated=root.findall('.//{http://v8.1c.ru/8.3/xcf/readable}GeneratedType')
        self.assertEqual([(n.attrib['name'],n.attrib['category']) for n in generated],
            [('ConstantManager.OwnedString','Manager'),('ConstantValueManager.OwnedString','ValueManager'),('ConstantValueKey.OwnedString','ValueKey')])
        ids=[child.text for n in generated for child in n]
        self.assertEqual(len(set(ids)),6)
        self.assertTrue(all(fixture.original._uuid(v) for v in ids))
    def test_minimal_install_preserves_bootstrap(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        self.assertEqual(set(after)-set(before),{'Constants/OwnedString.xml'})
        for name in before:
            if name not in ('Configuration.xml',fixture.original.ROLE_FILES[1]):self.assertEqual(before[name],after[name])
        rights=after[fixture.original.ROLE_FILES[1]]
        self.assertIn(b'Constant.OwnedString',rights);self.assertIn(b'<name>Read</name>',rights);self.assertIn(b'<name>Update</name>',rights)
    def test_wrong_bootstrap_and_type_drift_rejected(self):
        before=baseline()
        with self.assertRaises(ValueError):fixture.prepare(before,bootstrap_module=b'wrong')
        _,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl']);bad=dict(after)
        bad['Constants/OwnedString.xml']=bad['Constants/OwnedString.xml'].replace(b'xs:string',b'xs:boolean')
        with self.assertRaises(ValueError):fixture.verify_redump(after,bad)
    def test_single_nonce_bound_result(self):
        prefix='CST|'+'a'*32+'|';value='initial.get=ok\ninitial.length=0'
        wire=(prefix+'entered\n'+prefix+'1|'+json.dumps(value)+'\n'+prefix+'completed\n').encode()
        self.assertEqual(route.parse_wire(wire,'a'*32),[value])
        with self.assertRaises(ValueError):route.parse_wire(wire,'b'*32)
        with self.assertRaises(ValueError):route.parse_wire(wire+b'extra\n','a'*32)
    def test_staging_binds_exact_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            host.validate_inputs(dest,hashes,host.SMOKE)
            (dest/'bootstrap/constant_string_behavior/observe.bsl').write_bytes(b'changed')
            with self.assertRaises(ValueError):host.validate_inputs(dest,hashes,host.SMOKE)
    def test_native_runner_keeps_timeout_owner_and_check(self):
        raw=(ROOT/'scripts/native_1c_bootstrap/constant_string_suite.py').read_text()
        self.assertIn("platform.user!='NativeSmoke'",raw)
        self.assertIn('platform.timeout!=120',raw)
        self.assertIn("designer('check'",raw)
        self.assertIn('full.final_client_process_census(nonce)',raw)
