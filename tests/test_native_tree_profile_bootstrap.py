"""Synthetic profile/adapter checks; not native semantics evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/native_1c_bootstrap'))
sys.path.insert(0,str(ROOT/'scripts'))
import full_suite as full
import tree_suite as tree
from scripts import native_1c_tree_fill_contract as contract
from yadinassi import Interpreter
NONCE='0123456789abcdef0123456789abcdef'


def payload():
    lines=['TF-C: [-]']
    for case in range(1,33):
        before=contract.baseline(case)
        shared=before if case!=31 else before[:50]+'R01Q0....'
        lines.append(f'TF-{case}: [E{before}{before}{shared}]')
    lines.append('TF-A: [1S1123S1123SR123SU124SU124MU123MU123MU123MU123MU123MU123MU123AU123AU123SU423SU423]')
    return ('\n'.join(lines)+'\n').encode('ascii')


class TreeProfileTests(unittest.TestCase):
    def test_closed_inventory_separate_wire_and_source(self):
        self.assertEqual(full.SCENARIOS,('collections','dates','functions','numbers','strings','values'))
        self.assertEqual([k for k in tree.INPUT_FILES if k.startswith('integrational_tests/measurements/')],[tree.SOURCE])
        self.assertFalse(any(k.startswith('integrational_tests/tests/') for k in tree.INPUT_FILES))
        self.assertNotEqual(full.WIRE_SCHEMA,tree.WIRE_SCHEMA)
        self.assertEqual(tree.empty_report(NONCE)['cases'][0]['name'],'tree_fill_values')
        for nonce in ('','0'*31,'X'*32,1):
            with self.assertRaises(full.FullError): tree.empty_report(nonce)

    def test_adapter_preserves_original_observations(self):
        source=(ROOT/tree.SOURCE).read_text(encoding='utf-8').encode('utf-8')
        template=(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8')
        module=tree.client_module(source,template)
        self.assertIn(b'"tree-v1"',module)
        writer='ПараметрыJSON = Новый ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина);'.encode()
        self.assertEqual(module.count(writer),1)
        self.assertEqual(module.count('Запись.ОткрытьФайл(Путь, , , ПараметрыJSON);'.encode()),1)
        self.assertNotIn('Запись.ОткрытьФайл(Путь);'.encode(),module)
        runtime=Interpreter()
        runtime.execute(module.decode('utf-8-sig'))
        runtime.execute('Result = ВычислитьПробу();')
        values=runtime.variables['result'].items
        raw=('\n'.join(values)+'\n').encode('ascii')
        self.assertEqual(len(contract.validate_output(raw)),32)
        self.assertEqual(raw,payload())
        for bad in (source+b'\n',source.replace(b'\n',b'\r\n'),source.replace(b'32',b'31',1)):
            with self.assertRaises(full.FullError): tree.client_module(bad,template)
        with self.assertRaises(full.FullError): tree.client_module(source,template+b'\n')

    def test_client_ascii_budget_and_exact_count(self):
        module=tree.client_module((ROOT/tree.SOURCE).read_text(encoding='utf-8').encode('utf-8'),(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode('utf-8'))
        runtime=Interpreter();runtime.execute(module.decode('utf-8-sig'))
        for value in ('é','😀','\x00','a\nb','\r', chr(34), chr(92), '/', '<', '>', '&', chr(39), '{', '|'):
            runtime.execute('TreeLaneMessages = Новый Массив; TreeLaneCharacters = 0;')
            runtime.variables['bad']=value
            with self.assertRaises(Exception): runtime.execute('TreeLaneCapture(bad);')
        runtime.execute('TreeLaneMessages = Новый Массив; TreeLaneCharacters = 0;')
        runtime.variables['alphabet']='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz -.:[]_'
        runtime.execute('TreeLaneCapture(alphabet);')
        runtime.execute('TreeLaneMessages = Новый Массив; TreeLaneCharacters = 0;')
        runtime.variables['maximal']='x'*(tree.MAX_OUTPUT-tree.COUNT)
        runtime.execute('TreeLaneCapture(maximal);')
        with self.assertRaises(Exception): runtime.execute('TreeLaneCapture("x");')
        runtime.execute('TreeLaneMessages = Новый Массив; TreeLaneCharacters = 0;')
        for _ in range(tree.COUNT): runtime.execute('TreeLaneCapture("");')
        with self.assertRaises(Exception): runtime.execute('TreeLaneCapture("");')

    def test_markers_reject_cross_profile_missing_and_changed_values(self):
        good={'schema':tree.PROFILE,'nonce':NONCE,'phase':'completed','witness':'client',
              'values':payload().decode().splitlines()}
        # Byte reader patched only for portable unit fixture, not native security.
        def read(path,limit,**kw):
            raw=path.read_bytes()
            if len(raw)>limit: raise full.FullError('output_limit')
            return raw
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(full,'secure_bytes',read):
            path=Path(tmp)/'marker.json'
            path.write_text(json.dumps(good)); self.assertEqual(tree.client_marker(path,NONCE,'completed'),good)
            for field,value in [('schema',1),('nonce','1'*32),('phase','entered'),('witness','server'),('values',good['values'][:-1])]:
                bad={**good,field:value}; path.write_text(json.dumps(bad))
                with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed')
            bad=copy.deepcopy(good);bad['values'][1]+='x';path.write_text(json.dumps(bad))
            with self.assertRaises(full.FullError): tree.client_marker(path,NONCE,'completed')

    def test_direct_stage_route_rejects_mixed_profiles_before_side_effects(self):
        import run_stage
        cases=[{'tree_suite':1}, {'tree_suite':True}, {'tree_suite':True,'full_nonce':'invalid'}]
        for name in ('client_probe','watchdog_check','client_dates','client_values','client_collections',
                     'client_numbers','client_async','preprocessor_measurement'):
            cases.append({'tree_suite':True,'full_nonce':NONCE,name:True})
            cases.append({'tree_suite':True,'full_nonce':NONCE,name:1})
        with mock.patch.object(run_stage.uuid,'uuid4',side_effect=AssertionError('bootstrap started')) as start:
            for options in cases:
                with self.subTest(options=options),self.assertRaises(run_stage.StageError):
                    run_stage.run(**options)
            start.assert_not_called()

    def test_server_lane_binds_source_bytes_and_restores_launcher(self):
        def portable(path,limit,**kw):
            raw=path.read_bytes()
            if len(raw)>limit: raise full.FullError('output_limit')
            return raw
        for failure in (None,'module','output','source','client'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                inputs=Path(tmp)/'inputs'; inputs.mkdir()
                for name,target in tree.INPUT_FILES.items():
                    dst=inputs/target;dst.parent.mkdir(parents=True,exist_ok=True)
                    # Portable textual fixture, not the native filesystem reader.
                    dst.write_bytes((ROOT/name).read_text(encoding='utf-8').encode())
                def run_case(platform,source,epf,directory,output):
                    module=directory/'src/TestModule/Ext/ObjectModule.bsl'
                    module.parent.mkdir(parents=True)
                    raw=full.generated_module(source.read_bytes())
                    module.write_bytes(raw+(b'x' if failure=='module' else b''))
                    (directory/'TestModule.build-result.txt').write_text('0')
                    (directory/'TestModule.epf').write_bytes(b'fake test artifact')
                    data=payload()+(b'x' if failure=='output' else b'')
                    (directory/'result.json').write_text(json.dumps({'messages':data.decode().splitlines(),'error':''}))
                    output.write_bytes(data)
                    if failure=='source':
                        (inputs/'bootstrap/tree_suite.py').write_bytes(b'changed')
                original=(lambda *a:None,lambda *a:None,lambda *a:None)
                launcher=types.SimpleNamespace(read_result=original[0],run_process=original[1],build_epf=original[2],run_case=run_case)
                platform=types.SimpleNamespace(timeout=120,user='NativeSmoke',password=None)
                client={**full.empty_dates_report(),'status':'failed' if failure=='client' else 'ok',
                        'failure_kind':'output_mismatch' if failure=='client' else 'none'}
                with mock.patch.object(full,'secure_bytes',portable), \
                     mock.patch.object(full,'require_epf'),mock.patch.object(full,'require_zero_result'), \
                     mock.patch.object(full,'run_client_probe',return_value=client):
                    result=tree.run_suite(launcher,platform,Path(tmp)/'launcher.epf',Path(tmp)/'result',inputs,NONCE)
                self.assertEqual((launcher.read_result,launcher.run_process,launcher.build_epf),original)
                self.assertEqual(result['status'],'ok' if failure is None else 'failed')
                if failure is None: self.assertEqual(result['cases'][0]['message_count'],34)

    def test_finite_diagnostics_do_not_include_raw_payloads(self):
        cases=[(payload().replace(b'TF-C: [-]',b'TF-C: [G]'), 'calibration',0,'G'),
               (payload().replace(payload().splitlines()[2],b'TF-2: [Q]'), 'probe_q',2,None),
               (payload().replace(payload().splitlines()[1],b'TF-1: [B]'), 'probe_b',1,None),
               (payload()+b'\n','record_count',None,None),
               (b'x'*8193,'output_limit',None,None),
               (b'private\x00','encoding',None,None)]
        for raw,category,case,calibration in cases:
            diagnostic=tree.observation_diagnostic(raw,'server')
            self.assertEqual(diagnostic,{'site':'server','category':category,'case':case,'calibration':calibration})
            tree.validate_diagnostic(diagnostic)
            with self.assertRaises(tree.ObservationFailure) as caught: tree.validate_observations(raw)
            self.assertEqual(caught.exception.diagnostic,diagnostic)
            self.assertNotIn('private',str(caught.exception))
        good={'site':'server','category':'probe_q','case':2,'calibration':None}
        for key,value in [('category','arbitrary'),('category',[]),('case',33),('case',-1),('case',True),
                          ('case',None),('calibration','private'),('calibration','G'),('site','arbitrary')]:
            with self.subTest(key=key,value=value),self.assertRaises(full.FullError):
                tree.validate_diagnostic({**good,key:value})

    def test_physical_source_cap(self):
        raw=(ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_bytes()
        self.assertLessEqual(len(raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')),294912)

class HistoricalProfileInverseTests(unittest.TestCase):
    def test_exact_inverse_and_fixture_newlines(self):
        import hashlib
        from test_native_async_fixture import without_tree_profile_measurement as inverse
        source=(ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_text(encoding='utf-8')
        restored=inverse(source)
        self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(),
                         '0cf75e36ca12243cc95db40ec20d83e0779e3771519de2cb066e4f67cb6c501d')
        self.assertEqual(inverse(restored),restored)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'historical.py'
            path.write_bytes(source.replace('\n','\r\n').encode('utf-8'))
            self.assertEqual(inverse(path.read_text(encoding='utf-8')),restored)
        with self.assertRaises(AssertionError):
            inverse(source.replace('\n','\r\n'))

    def test_outer_and_inner_tampering_rejected(self):
        import test_native_async_fixture as fixture
        source=(ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_text(encoding='utf-8')
        for bad in (source+'\n',source.replace('tree_output: Path','tree_output: str',1),
                    source.replace('import ', '# changed\nimport ',1)):
            with self.subTest(kind=bad[-30:]),self.assertRaises(AssertionError):
                fixture.without_tree_profile_measurement(bad)
        inventory=json.loads((ROOT/'tests/tree_profile_source_inverse.json').read_text(encoding='utf-8'))
        path='scripts/native_1c_bootstrap/full_suite.py'
        for mutation in ('candidate_sha256','base_sha256','old','new'):
            changed=copy.deepcopy(inventory)
            if mutation in ('old','new'):
                changed[path]['edits'][0][mutation]+='tamper'
            else:
                changed[path][mutation]='0'*64
            with self.subTest(mutation=mutation),mock.patch.object(fixture.json,'loads',return_value=changed):
                with self.assertRaises(AssertionError):
                    fixture.without_tree_profile_measurement(source)


if __name__=='__main__': unittest.main()


class APIControlDiagnosticParityTests(unittest.TestCase):
    def test_api_controls_category_matches_host_and_producer(self):
        from scripts import native_1c_tree_profile as host
        good = {'site': 'server', 'category': 'api_controls', 'case': None, 'calibration': None}
        for site in ('server', 'client'):
            tree.validate_diagnostic({**good, 'site': site})
            host.validate_diagnostic({**good, 'site': site})
        invalid = [{**good, 'case': value} for value in (0, 1, 32, True)]
        invalid += [{**good, 'calibration': 'G'}, {**good, 'description': 'private diagnostic'}]
        for diagnostic in invalid:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaises(full.FullError): tree.validate_diagnostic(diagnostic)
                with self.assertRaises(host.TreeError): host.validate_diagnostic(diagnostic)

    def test_malformed_api_aggregate_has_no_case_or_private_text(self):
        from scripts import native_1c_tree_profile as host
        original = payload().splitlines(keepends=True)
        for line in (b'TF-A: [private]\n', b'TF-X: [1]\n', b'TF-A: [1' + b'SU129' * 16 + b']\n'):
            raw = b''.join(original[:-1]) + line
            for site in ('server', 'client'):
                expected = {'site': site, 'category': 'api_controls', 'case': None, 'calibration': None}
                self.assertEqual(tree.observation_diagnostic(raw, site), expected)
                tree.validate_diagnostic(expected)
                host.validate_diagnostic(expected)
                with self.assertRaises(tree.ObservationFailure) as caught:
                    tree.validate_observations(raw, site)
                self.assertEqual(caught.exception.diagnostic, expected)
                self.assertNotIn('private', str(caught.exception))
                self.assertEqual(set(caught.exception.diagnostic), {'site', 'category', 'case', 'calibration'})
