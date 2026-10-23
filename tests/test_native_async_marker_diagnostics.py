"""Failure-only finite validator hints. Synthetic tests are not native evidence."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_async_execution as execution
import test_native_async_protocol as protocol
from test_native_async_failure_diagnostics import install_windows_offline_reader

suite, host = protocol.suite, protocol.full
NONCE = protocol.NONCE


def marker(case=6, phase='completed'):
    value = dict(schema=1, nonce=NONCE, case=case, phase=phase, witness='client')
    if phase == 'completed':
        trace, values, errors = protocol.observation(case)
        value.update(status=1, failure=0, trace=trace, values=values,
                     errors=[protocol.private_error(error[0]) for error in errors])
    return value


def raw(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()


class AsyncMarkerClassifierTests(unittest.TestCase):
    def classify(self, value, expected, *, case=6, phase='completed'):
        data = value if type(value) is bytes else raw(value)
        with self.assertRaises(suite.FullError):
            suite.validate_async_marker(suite.strict_json(data,max_depth=5),NONCE,case,phase)
        with self.assertRaises((ValueError,UnicodeError)):
            host.validate_async_marker_raw(data,NONCE,case,phase)
        actual = suite.async_marker_validation_failure(data,NONCE,case,phase)
        self.assertEqual(actual,expected)
        self.assertNotIn('PRIVATE',json.dumps(actual))

    def test_valid_markers_are_never_failure_hints(self):
        for case in range(8):
            for phase in ('entered','completed'):
                value = marker(case,phase)
                suite.validate_async_marker(value,NONCE,case,phase)
                self.assertIsNone(suite.async_marker_validation_failure(raw(value),NONCE,case,phase))
        for status,kind in ((2,12),(3,14)):
            value = marker();value.update(status=status,failure=kind,trace=[],values=[],errors=[])
            self.assertIsNone(suite.async_marker_validation_failure(raw(value),NONCE,6,'completed'))

    def test_json_rejections_have_fixed_sites_not_payloads(self):
        good = raw(marker())
        for bad,site in ((b'\xff',1),(b'['*6+b'0'+b']'*6,2),
                         (good.replace(b'"schema":1',b'"schema":1,"schema":1',1),3),
                         (good.replace(b'"schema":1',b'"schema":10000000000',1),4),
                         (good.replace(b'"schema":1',b'"schema":1.0',1),5),
                         (good.replace(b'"schema":1',b'"schema":NaN',1),6),
                         (good[:-1],7),(good+b'PRIVATE',7)):
            with self.subTest(site=site): self.classify(bad,[1,site,3,31])

    def test_envelope_status_and_identity_are_separate(self):
        for edit,site in ((lambda v:v.update(extra='PRIVATE'),8),
                          (lambda v:v.update(schema=True),9),
                          (lambda v:v.update(status=True),10),
                          (lambda v:v.update(status=2,failure=12),11),
                          (lambda v:v.update(failure=12),12),
                          (lambda v:v.update(errors={}),13)):
            value=marker();edit(value);self.classify(value,[1,site,3,31])
        for key,value in (('nonce','b'*32),('case',0),('case',True),('phase','entered'),('witness','server')):
            bad=marker();bad[key]=value
            self.classify(bad,None)
        for key in ('nonce','case','phase','witness'):
            bad=marker();del bad[key]
            self.classify(bad,None)
        bad=marker(6,'entered');bad['schema']=False
        self.classify(bad,[0,9,3,31],phase='entered')

    def test_every_private_descriptor_rejection_site(self):
        changes = (
            (lambda d:d.clear(),14,31),
            (lambda d:d.update(schema=True),15,0),
            (lambda d:d.update(phase=7),16,1),
            (lambda d:d.update(description=[]),17,2),
            (lambda d:d.update(description=[6,0]),18,2),
            (lambda d:d.update(description=[0,0]),19,2),
            (lambda d:d.update(description=[2,0]),20,2),
            (lambda d:d.update(description=[2,'я'*257]),21,2),
            (lambda d:d.update(line=[3,True]),22,8),
            (lambda d:d.update(description=[4,1]),23,2),
            (lambda d:d.update(category=[5,0]),24,5),
            (lambda d:d.update(description=[2,'\ud800']),25,2),
            (lambda d:d.update({key:[2,'\x00'*512] for key in ('description','code','additional','module','source')}),26,31),
        )
        for change,site,field in changes:
            with self.subTest(site=site):
                value=marker();change(value['errors'][0]);self.classify(value,[1,site,0,field])

    def test_values_references_inventory_and_exact_causal_edge(self):
        changes = (
            (lambda v:v.update(trace=[]),27,3,31),
            (lambda v:v['trace'].__setitem__(2,True),28,3,31),
            (lambda v:v['trace'].insert(3,10),29,3,10),
            (lambda v:v['trace'].__setitem__(0,27),30,3,31),
            (lambda v:v['values'].__setitem__(0,[]),31,3,0),
            (lambda v:v['values'].__setitem__(0,[8,0]),32,3,0),
            (lambda v:v['values'].__setitem__(0,[4,True]),33,3,0),
            (lambda v:v['errors'][0].update(phase=0),34,0,1),
            (lambda v:v['values'][1].__setitem__(1,2),35,2,1),
            (lambda v:v['errors'].append(protocol.private_error(0)),36,3,31),
            (lambda v:v['values'].__setitem__(0,[0,0]),37,3,0),
            (lambda v:v['trace'].remove(11),38,3,11),
            (lambda v:v['trace'].insert(3,27),39,3,27),
            (lambda v:v['trace'].__setitem__(slice(3,5),[12,11]),40,3,1),
        )
        for change,site,ordinal,field in changes:
            with self.subTest(site=site):
                value=marker();change(value);self.classify(value,[1,site,ordinal,field])
        value=marker(7);value['values'][2]=[4,0];value['errors']=[]
        self.classify(value,[1,41,3,2],case=7)

    def test_supported_negative_mutations_always_agree_with_original_verdict(self):
        # Full tagged-field type/product coverage, including source fields and
        # unavailable getters. A hint may never convert rejection to success.
        fields=('description','code','additional','category','cause','module','line','source')
        payloads=(None,False,True,-1,0,1,2,999999,1000000,'','ASYNC-REJECT','PRIVATE',[],{})
        for field in fields:
            for tag in range(7):
                for payload in payloads:
                    value=marker();value['errors'][0][field]=[tag,payload];data=raw(value)
                    try:
                        suite.validate_async_marker(suite.strict_json(data,max_depth=5),NONCE,6,'completed')
                        accepted=True
                    except suite.FullError:
                        accepted=False
                    try:
                        host.validate_async_marker_raw(data,NONCE,6,'completed')
                        host_accepted=True
                    except (ValueError,UnicodeError):
                        host_accepted=False
                    self.assertEqual(accepted,host_accepted,(field,tag,payload))
                    hint=suite.async_marker_validation_failure(data,NONCE,6,'completed')
                    self.assertEqual(hint is None,accepted,(field,tag,payload,hint))

    def test_unknown_is_bounded_and_never_success(self):
        with mock.patch.object(suite,'validate_async_marker',side_effect=suite.FullError('invalid_result')):
            self.assertEqual(suite.async_marker_validation_failure(raw(marker()),NONCE,6,'completed'),[1,42,3,31])


class AsyncMarkerFailureProtocolTests(unittest.TestCase):
    def failed(self):
        value=protocol.record()
        value.update(status='failed',failure_kind='invalid_result',continuity_sha256=None,
                     failure_diagnostics=[4,3,2,3],marker_validation_failure=[1,19,0,2])
        value['cases'][6:]=[[6,2,4,protocol.MODULES[6],0,[],[],[]],[7,0,1,None,0,[],[],[]]]
        return value

    def reject(self,value,*,codecs=True):
        with self.assertRaises(suite.FullError): suite.validate_async_report(value,protocol.H,protocol.MODULES)
        with self.assertRaises(ValueError): host.validate_client_async(value,protocol.H,protocol.MODULES)
        if codecs:
            for codec in (suite.encode_async_wire,suite.decode_async_wire,host.encode_async_wire,host.decode_async_wire):
                with self.assertRaises((suite.FullError,ValueError)): codec(value)

    def test_exact_tuple_types_lengths_bounds_and_per_site_locators(self):
        good=self.failed()
        suite.validate_async_report(good,protocol.H,protocol.MODULES)
        host.validate_client_async(good,protocol.H,protocol.MODULES)
        for malformed in ({},(),'',True,0,[],[1,19,0],[1,19,0,2,0]):
            value=copy.deepcopy(good);value['marker_validation_failure']=malformed;self.reject(value)
        for index,maximum in enumerate((1,42,3,31)):
            for item in (True,False,None,'0',0.0,-1,maximum+1,[],{}):
                value=copy.deepcopy(good);value['marker_validation_failure'][index]=item;self.reject(value)
        for hint in ([1,0,3,31],[0,19,0,2],[1,19,3,2],[1,19,0,0],
                     [1,38,0,11],[1,38,3,31],[1,31,3,3],[1,40,3,20],[1,41,3,2]):
            value=copy.deepcopy(good);value['marker_validation_failure']=hint;self.reject(value)
        value=copy.deepcopy(good);del value['marker_validation_failure'];self.reject(value)

    def test_hint_applicability_never_salvages_failure_or_semantic_proof(self):
        changes=(lambda v:v.update(status='ok'),lambda v:v.update(status='not_started'),
                 lambda v:v.update(status='inconclusive'),lambda v:v.update(failure_kind='timeout'),
                 lambda v:v.update(failure_diagnostics=None),lambda v:v['failure_diagnostics'].__setitem__(0,3),
                 lambda v:v['failure_diagnostics'].__setitem__(1,2),lambda v:v['failure_diagnostics'].__setitem__(2,3),
                 lambda v:v['cases'][6].__setitem__(2,10))
        for change in changes:
            value=self.failed();change(value);self.reject(value)
        for index,item in ((4,63),(5,[0]),(6,[[1,0]]),(7,[[1,2,2,2,1,0,protocol.H]])):
            value=self.failed();value['cases'][6][index]=item;self.reject(value,codecs=False)
        value=self.failed();value['continuity_sha256']=protocol.H;self.reject(value,codecs=False)
        value=self.failed();suite.fail_async_process_checkpoint(value)
        self.assertIsNone(value['marker_validation_failure'])


class AsyncMarkerSnapshotTests(unittest.TestCase):
    def setUp(self):
        install_windows_offline_reader(self)
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.request=self.root/'request.json';self.request.write_bytes(b'{"schema":1}')
        self.request_snap=suite.async_file_snapshot(self.request,2048)
        self.entered=self.root/'entered.json';self.completed=self.root/'completed.json'
        self.entered.write_bytes(raw(marker(6,'entered')))
        value=marker();value['errors'][0]['description']=[0,0]
        self.completed.write_bytes(raw(value))
        self.previous={phase:suite.async_file_snapshot(path,suite.ASYNC_MAX_MARKER)
                       for phase,path in (('entered',self.entered),('completed',self.completed))}

    def capture(self,*,stage=4,stopped=True):
        return suite.observe_async_marker_validation_failure(stage,6,NONCE,stopped=stopped,
            marker_context=(self.entered,self.completed,self.request,self.request_snap,self.previous))

    def replace(self,path):
        other=path.with_suffix('.swap');other.write_bytes(path.read_bytes());other.replace(path)

    def test_exact_original_pins_are_required(self):
        self.assertEqual(self.capture(),[1,19,0,2])
        self.replace(self.completed);self.assertIsNone(self.capture())
        self.previous['completed']=suite.async_file_snapshot(self.completed,suite.ASYNC_MAX_MARKER)
        self.replace(self.request);self.assertIsNone(self.capture())

    def test_classification_rechecks_every_snapshot(self):
        original=suite.async_marker_validation_failure
        for target in (self.request,self.entered,self.completed):
            with self.subTest(target=target.name):
                def classify(*args,**kwargs):
                    self.replace(target)
                    return original(*args,**kwargs)
                with mock.patch.object(suite,'async_marker_validation_failure',side_effect=classify):
                    self.assertIsNone(self.capture())
                self.request_snap=suite.async_file_snapshot(self.request,2048)
                self.previous={phase:suite.async_file_snapshot(path,suite.ASYNC_MAX_MARKER)
                    for phase,path in (('entered',self.entered),('completed',self.completed))}
                # A replacement request is newer than the marker files. Refresh
                # all files in this synthetic setup for the next independent run.
                self.entered.write_bytes(raw(marker(6,'entered')))
                value=marker();value['errors'][0]['description']=[0,0]
                self.completed.write_bytes(raw(value))
                self.previous={phase:suite.async_file_snapshot(path,suite.ASYNC_MAX_MARKER)
                    for phase,path in (('entered',self.entered),('completed',self.completed))}

    def test_no_unstopped_or_wrong_stage_read(self):
        with mock.patch.object(suite,'async_diagnostic_snapshot',side_effect=AssertionError('unexpected read')):
            self.assertIsNone(self.capture(stopped=False))
            for stage in (0,1,2,3,5): self.assertIsNone(self.capture(stage=stage))

    def test_mismatched_binding_and_stale_timestamp_have_no_hint(self):
        for key,item in (('nonce','b'*32),('case',0),('phase','entered'),('witness','server')):
            bad=marker();bad[key]=item;self.completed.write_bytes(raw(bad))
            self.previous['completed']=suite.async_file_snapshot(self.completed,suite.ASYNC_MAX_MARKER)
            self.assertIsNone(self.capture())
        with mock.patch.object(suite,'async_diagnostic_after',return_value=False):
            self.assertIsNone(self.capture())


class AsyncMarkerExecutionTests(execution.AsyncExecutionTests):
    def test_failure_hint_is_captured_without_retaining_semantic_evidence(self):
        self.transform=lambda value:value['trace'].remove(11)
        result=self.run_async()
        self.assertEqual(result['marker_validation_failure'],[1,38,3,11])
        self.assertEqual(result['failure_diagnostics'],[4,3,2,3])
        self.assertEqual(result['failure_kind'],'invalid_result')
        self.assertEqual(result['cases'][0][4:],[0,[],[],[]])
        self.assertIsNone(result['continuity_sha256'])
        hashes=[suite.digest(suite.async_client_module(case)) for case in range(8)]
        suite.validate_async_report(result,suite.digest(suite.ASYNC_TEMPLATE.encode()),hashes)
        host.validate_client_async(result,suite.digest(suite.ASYNC_TEMPLATE.encode()),hashes)
        encoded=suite.encode_async_wire(result)
        self.assertEqual(host.decode_async_wire(encoded),result)
        suite.fail_async_process_checkpoint(result)
        self.assertIsNone(result['marker_validation_failure'])

    def test_binding_failures_never_gain_a_hint(self):
        for key,item in (('nonce','b'*32),('case',7),('witness','server'),('phase','entered')):
            self.transform=lambda value,key=key,item=item:value.update({key:item})
            result=self.run_async()
            self.assertIsNone(result['marker_validation_failure'])
            self.assertEqual(result['failure_kind'],'invalid_result')
            self.reset()

    def test_final_emitter_does_not_rebase_historical_hint(self):
        self.transform=lambda value:value['trace'].remove(11)
        result=self.run_async()
        report=suite.empty_report(NONCE,client_probe=True,client_async=True)
        report.update(status='failed',failure_kind='invalid_result',client_async=result)
        with mock.patch.object(suite,'observe_async_marker_validation_failure',side_effect=AssertionError('late rebase')):
            data=suite.build_envelope({'status':'stage3_failed','stage3':report},NONCE,self.root,quiet=True)
        emitted=json.loads(data)['report']['stage3']['client_async']
        self.assertEqual(emitted['marker_validation_failure'],[1,38,3,11])
        self.assertEqual(emitted['cases'][0][4:],[0,[],[],[]])


# Exact source text from measured head 7af481f4cbf33f9cf36bde4d719124e5c8d95b76.
# Adding diagnostics must not relax the original marker acceptance predicates.
ACCEPTANCE_PINS = {'scripts/native_1c_bootstrap/full_suite.py': {'strict_json': 'f00cc875f303195a17a9e5232da2064a5dee87503dff5a63771393ba3190327e',
                                               '_async_value': '9d7f0a8637fc67268bf56fce0bf629cd090618aa57585ab5f79288baecde3132',
                                               '_async_error': '12030331b2c48ec12c286b34a56c0eaf3a9fb84ec48d2e39a634902cb4bcb0da',
                                               'validate_async_observation': '7d899015e6d6ac2adbd7b128e41716a603cdb93f078053aec7ad29b229f85396',
                                               '_async_private_error': '62ad8a3c9c9ab629afa5df146470ceb6b085ec9b1449acc6090ce43a8e56b44f',
                                               'client_async_marker': '1dc67c6700e1ac1275b77383108f7c37befe17649a228667e392a3dc19dbf145',
                                               'validate_async_marker': 'f40bb81bd70062154a312046820fe87ca99303700e25124c444ecf6b6b1e59bd'},
 'scripts/native_1c_full_host.py': {'strict_json': 'f050811fc53fae4899021c3bb1133960ffc0d80f8def6e9bd10869675cc63b07',
                                    'validate_async_case_observation': '50aeb9fdbb3f41a81bc221bc331244524bf1b48b8fb374a46eaa5cab746687eb',
                                    'validate_async_private_descriptor': '0c2ddf95948decb7fad4b3645e30a9e876df1a5651e580be60b4596c57b1122f',
                                    'validate_async_marker_raw': '365557c2f14d0271432482246fc262caab2c6428a00e97152f24e4196fc54334'}}


class AsyncAcceptancePreservationTests(unittest.TestCase):
    def test_original_acceptance_functions_are_byte_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        for path,functions in ACCEPTANCE_PINS.items():
            source=(root/path).read_text(encoding='utf-8')
            nodes={node.name:node for node in ast.parse(source).body if isinstance(node,ast.FunctionDef)}
            for name,expected in functions.items():
                actual=hashlib.sha256(ast.get_source_segment(source,nodes[name]).encode()).hexdigest()
                self.assertEqual(actual,expected,(path,name))

    def test_classifier_input_bounds_fail_closed(self):
        for data,nonce,case,phase in ((b'x'*(suite.ASYNC_MAX_MARKER+1),NONCE,6,'completed'),
                ('not bytes',NONCE,6,'completed'),(b'{}','bad',6,'completed'),
                (b'{}',NONCE,True,'completed'),(b'{}',NONCE,6,'other')):
            self.assertIsNone(suite.async_marker_validation_failure(data,nonce,case,phase))


if __name__ == '__main__': unittest.main()
