"""Offline transport, finite category and fixture checks; never runs 1C."""
from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/native_1c_bootstrap'))
from catalog_deletion_diagnostic_behavior import fixture, route
from catalog_deletion_rights_behavior import route as rights_route
from native_1c_bootstrap.inject_modules import ROLE_FILES
from test_catalog_object_fixture import baseline
import catalog_deletion_diagnostic_suite as suite

spec = importlib.util.spec_from_file_location('catalog_diagnostic_host', ROOT / 'scripts/native_1c_catalog_deletion_diagnostic_profile.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
NONCE = 'c' * 32


def values():
    result = [False] * route.COUNT
    result[0] = True     # existing success, no exception category
    result[14] = True    # new exception, unmatched category
    return result


def wire(rows, nonce=NONCE):
    prefix = 'CDM|'+nonce+'|'
    return (prefix+'entered\n'+''.join(prefix+str(i)+'|B|'+('1' if v else '0')+'\n'
            for i,v in enumerate(rows,1))+prefix+'completed\n').encode('ascii')


def identity(raw, **kwargs): return json.loads(raw)


def envelope():
    hashes = {name: host.FULL.digest((ROOT/name).read_bytes()) for name in host.staged_files()}
    raw = route.canonical(values())
    stage = suite.empty_report(NONCE)
    module = host.FULL.digest(host.FULL.generated_module(route.program(fixture.load_saved()[0],NONCE)))
    stage.update(status='ok', failure_kind='none', failure_phase='final', input_sha256=hashes,
                 source_sha256=host.SOURCE_SHA256, module_sha256=module, module_verified_sha256=module,
                 output_sha256=host.FULL.digest(raw), output_size=len(raw), record_count=20)
    for flag in host.FLAGS: stage[flag] = True
    stage['process_diagnostics'].update(stage='after_exit', reason='none')
    payload = {'schema':host.SCHEMA, 'profile':host.PROFILE, 'nonce':NONCE,
               'report':{'status':'ok', 'native_tests_completed':True, 'stage3':stage},
               'outputs':[{'name':'catalog-object.out', 'size':len(raw),
                           'sha256':host.FULL.digest(raw), 'data_b64':base64.b64encode(raw).decode()}]}
    return payload, hashes, raw


class DiagnosticPacketTests(unittest.TestCase):
    def setUp(self):
        # Test-only reader adapts static fixtures for Windows stat differences;
        # no claim that it proves Linux production descriptor safety.
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_synthetic_file)
            patcher.start(); self.addCleanup(patcher.stop)

    def test_source_hash_and_distinct_identity(self):
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(),route.SOURCE_SHA256)
        self.assertNotEqual(route.SOURCE_SHA256, rights_route.SOURCE_SHA256)
        self.assertNotEqual(route.PROFILE, rights_route.PROFILE)
        self.assertEqual(host.ARTIFACT,'catalog-deletion-diagnostic')

    def test_source_tamper_refused(self):
        with mock.patch.object(Path,'read_bytes',return_value=b'changed'):
            with self.assertRaises(ValueError): route.source()

    def test_source_has_no_raw_message_or_external_actions(self):
        source = route.source().decode('utf-8')
        self.assertNotIn('Message(',source)
        self.assertNotIn('Сообщить(',source)
        self.assertIn('CDMClass(ErrorDescription())',source)
        self.assertIn('Lower(Left(ErrorText, 2048))',source)
        self.assertEqual(source.count('CDMEmit('),20)

    def test_program_pins_setup_and_nonce(self):
        setup,_ = fixture.load_saved()
        program = route.program(setup,NONCE)
        declarations, body = route.source().split(b'\nM = Catalogs.', 1)
        self.assertIn(declarations, program)
        self.assertIn(b'M = Catalogs.' + body, program)
        self.assertLess(program.index(b'Function CDMClass('), program.index(('CDM|'+NONCE+'|entered').encode()))
        self.assertLess(program.index(('CDM|'+NONCE+'|entered').encode()), program.index(b'M = Catalogs.'))
        self.assertIn(('CDM|'+NONCE+'|entered').encode(),program)
        self.assertLessEqual(len(program),route.MAX_OUTPUT)
        for nonce in ('','g'*32,'a'*31):
            with self.assertRaises(ValueError): route.program(setup,nonce)

    def test_classifier_patterns_priority_and_prefix_bound(self):
        from yadinassi import Interpreter
        source = route.source().decode('utf-8').split('\nM = Catalogs.', 1)[0]
        cases = ['недостаточно прав', 'lock conflict', 'method not found',
                 'nothing relevant', 'access denied and lock conflict', 'x'*2048+'access denied']
        statements = ''.join('Message(CDMClass("'+value+'"));' for value in cases)
        output = []
        Interpreter(output=output.append).execute(source + '\n' + statements + 'Message(CDMClass(1));')
        self.assertEqual(output, ['1', '2', '3', '4', '1', '4', '4'])

    def test_program_rejects_foreign_setup(self):
        with self.assertRaises(ValueError): route.program(object(),NONCE)

    def test_transport_exact_boolean_roundtrip(self):
        self.assertEqual(route.parse_wire(wire(values()),NONCE),values())
        self.assertEqual(json.loads(route.canonical(values())),values())

    def test_categories_are_one_hot_and_success_not_other(self):
        v=values(); self.assertTrue(v[0]); self.assertFalse(any(v[1:5])); self.assertTrue(v[14]); self.assertFalse(v[10])
        self.assertTrue(route.canonical(v))
        for mutate in ((0,False),(1,True),(14,False),(11,True)):
            bad=values();bad[mutate[0]]=mutate[1]
            with self.assertRaises(ValueError): route.canonical(bad)

    def test_every_single_category_admitted(self):
        for first in range(5):
            for second in range(10,15):
                v=[False]*20;v[first]=True;v[second]=True
                self.assertEqual(route.parse_wire(wire(v),NONCE),v)

    def test_wrong_nonce_and_wrong_count_refused(self):
        with self.assertRaises(ValueError): route.parse_wire(wire(values()),'d'*32)
        for n in (19,21):
            with self.assertRaises(ValueError): route.parse_wire(wire([False]*n),NONCE)

    def test_malformed_wire_refused(self):
        raw=wire(values())
        for item in (raw.replace(b'|2|B|0',b'|1|B|0'),raw.replace(b'|2|B|0',b'|2|S|x'),
                     raw.replace(b'\n',b'\r\n'),raw[:-1]):
            with self.assertRaises(ValueError): route.parse_wire(item,NONCE)

    def test_nonboolean_refused(self):
        v=values();v[-1]=0
        with self.assertRaises(ValueError): route.canonical(v)

    def test_exact_rights_and_redump(self):
        setup,prepared=fixture.prepare(baseline())
        self.assertEqual(route.CATALOG_RIGHTS,('Read','Insert','Update','Delete'))
        self.assertTrue(fixture.verify_redump(prepared,dict(prepared)))
        changed=dict(prepared);marker=b'<right><name>Delete</name><value>true</value></right>'
        self.assertEqual(changed[ROLE_FILES[1]].count(marker),1)
        changed[ROLE_FILES[1]]=changed[ROLE_FILES[1]].replace(marker,b'')
        with self.assertRaises(ValueError):fixture.verify_redump(prepared,changed)

    def test_offline_staging_binds_diagnostic_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged=Path(tmp).resolve()/'stage'
            hashes=host.stage_inputs(ROOT,staged,host.SMOKE)
            self.assertEqual(hashes[host.SOURCE],route.SOURCE_SHA256)
            self.assertIn('scripts/catalog_deletion_rights_behavior/fixture.py',hashes)
            self.assertEqual((staged/'bootstrap/catalog_object_suite.py').read_bytes(),
                             (ROOT/'scripts/native_1c_bootstrap/catalog_deletion_diagnostic_suite.py').read_bytes())
            host.validate_inputs(staged,hashes,host.SMOKE)

    def test_staged_source_tamper_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged=Path(tmp).resolve()/'stage';hashes=host.stage_inputs(ROOT,staged,host.SMOKE)
            (staged/'bootstrap/catalog_deletion_diagnostic_behavior/observe.bsl').write_bytes(b'changed')
            with self.assertRaises(host.CatalogObjectError):host.validate_inputs(staged,hashes,host.SMOKE)

    def test_envelope_binds_profile_source_and_redump(self):
        payload,hashes,raw=envelope()
        self.assertEqual(host.validate_envelope(json.dumps(payload).encode(),NONCE,hashes,identity)[1],raw)
        for key,value in (('source_sha256','f'*64),('record_count',32),('config_verified',False)):
            bad=copy.deepcopy(payload);bad['report']['stage3'][key]=value
            with self.assertRaises(host.CatalogObjectError):host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity)
        bad=copy.deepcopy(payload);bad['profile']=rights_route.PROFILE
        with self.assertRaises(host.CatalogObjectError):host.validate_envelope(json.dumps(bad).encode(),NONCE,hashes,identity)

    def test_envelope_failure_does_not_return_partial_data(self):
        payload,hashes,_=envelope();payload['outputs']=[]
        payload['report'].update(status='stage3_failed',native_tests_completed=False)
        payload['report']['stage3'].update(status='failed',failure_kind='module_mismatch',failure_phase='enterprise',completed=False)
        with self.assertRaises(host.CatalogObjectError) as caught:
            host.validate_envelope(json.dumps(payload).encode(),NONCE,hashes,identity)
        self.assertEqual(caught.exception.native_failure['failure_phase'],'enterprise')


if __name__=='__main__': unittest.main()
