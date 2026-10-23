"""Finite client Async protocol tests. Synthetic evidence is never native parity."""
from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest

import test_native_client_collections_host as fixtures

suite = fixtures.suite
full = fixtures.full
H = 'a' * 64
MODULES = [str(i) * 64 for i in range(8)]
NONCE = 'a' * 32


def private_error(phase):
    return dict(schema=1,phase=phase,description=[2,'ASYNC-REJECT'],code=[2,'ASYNC-CODE'],
                additional=[2,'ASYNC-DETAIL'],category=[3,1],cause=[1,None],
                module=[2,'fixed-module'],line=[3,17],source=[2,'fixed-source'])


def observation(case, *, scalar_errors=(True,True,True), nested=True, reject_call=False,
                await_errors=(True,True), reverse=False):
    values = [[4,-999999] for _ in range((4,3,5,3,4,7,3,3)[case])]
    errors=[]
    def error(slot,phase):
        values[slot]=[7,len(errors)]
        errors.append([phase,2,2,2,1,0,H])
    if case == 3:
        for slot,caught in enumerate(scalar_errors):
            if caught: error(slot,slot+3)
    if case == 4:
        if nested: values[1]=[6,0]
        else: values[2]=[0,0]
    if case == 6:
        if reject_call:
            error(0,0);values[1]=values[2]=[0,0]
        else:
            for slot,caught in enumerate(await_errors,1):
                if caught: error(slot,slot)
    if case == 7: error(2,6)
    # Independently specified legal schedules. Only case1 varies caller-vs-callee.
    middle = {
        0:[10,11,12,13,14,15,16,17,18],
        1:[10,11,12,25,26,13,14,15,16,17],
        2:[10,11,12,25,26,13,14,15,16,17,18,27,28,19,20,21,22,23,24],
        3:[10,12 if scalar_errors[0] else 11,13,15 if scalar_errors[1] else 14,16,18 if scalar_errors[2] else 17],
        4:[10,11,12,13,14,15,16,17 if nested else 18,19],
        5:[10,11,12,13,14,15,16],
        6:([10,11,12,14] if reject_call else [10,11,12,13,15,17 if await_errors[0] else 16,18,20 if await_errors[1] else 19]),
        7:[10,11,12,13,14,15,16,17,18],
    }[case]
    if reverse and case == 1:
        middle=[10,11,12,25,26,15,16,13,14,17]
    if reverse and case == 2:
        middle=[10,11,12,25,26,15,16,17,18,27,28,21,19,20,13,14,22,23,24]
    return [0,1,*middle,2,3,4],values,errors


def record(**options):
    return dict(version=2,status='ok',failure_kind='none',template_sha256=H,continuity_sha256=H,failure_diagnostics=None,
                marker_validation_failure=None,
                process_diagnostics=fixtures.process_diagnostics(),
                cases=[[i,1,0,MODULES[i],63,*observation(i,**options)] for i in range(8)])


class AsyncProtocolTests(unittest.TestCase):
    def accept(self,value):
        snapshot=copy.deepcopy(value)
        self.assertEqual(suite.validate_async_report(value,H,MODULES),value)
        self.assertEqual(full.validate_client_async(value,H,MODULES),value)
        self.assertEqual(value,snapshot)

    def reject(self,value):
        with self.assertRaises(suite.FullError): suite.validate_async_report(value,H,MODULES)
        with self.assertRaises(ValueError): full.validate_client_async(value,H,MODULES)

    def test_report_version_two_is_explicit_and_old_reports_fail_closed(self):
        self.assertEqual(record()['version'], 2)
        self.assertEqual(suite.empty_async_report()['version'], 2)
        self.assertIsNone(record()['marker_validation_failure'])
        self.assertIsNone(suite.empty_async_report()['marker_validation_failure'])
        for version in (None, True, False, 0, 1, 3, 2.0, '2'):
            data = record()
            data['version'] = version
            self.reject(data)
        data = record()
        del data['marker_validation_failure']
        self.reject(data)
        # Only the public async report is version 2. Private marker and
        # private descriptor schemas remain byte-compatible schema 1.
        marker = dict(schema=1, nonce=NONCE, case=0, phase='entered', witness='client')
        self.assertEqual(suite.validate_async_marker(marker, NONCE, 0, 'entered'), marker)
        self.assertEqual(full.validate_async_marker_raw(json.dumps(marker).encode(), NONCE, 0, 'entered'), marker)
        self.assertEqual(private_error(6)['schema'], 1)
        for schema in (True, 0, 2):
            invalid = dict(marker, schema=schema)
            with self.assertRaises(suite.FullError):
                suite.validate_async_marker(invalid, NONCE, 0, 'entered')
            with self.assertRaises(ValueError):
                full.validate_async_marker_raw(json.dumps(invalid).encode(), NONCE, 0, 'entered')

    def test_marker_validation_hint_types_bounds_and_failure_applicability(self):
        base = record()
        base.update(status='failed', failure_kind='invalid_result', continuity_sha256=None,
                    failure_diagnostics=[4, 3, 2, 0], marker_validation_failure=[1, 38, 3, 28])
        base['cases'][7] = [7, 2, 4, MODULES[7], 0, [], [], []]
        self.accept(base)
        for malformed in ({}, (), '', True, 0, [], [1, 38, 3], [1, 38, 3, 28, 0]):
            data = copy.deepcopy(base)
            data['marker_validation_failure'] = malformed
            self.reject(data)
        for index, maximum in enumerate((1, 42, 3, 31)):
            for item in (True, False, None, 'PRIVATE', 0.0, -1, maximum + 1, [], {}):
                data = copy.deepcopy(base)
                data['marker_validation_failure'][index] = item
                self.reject(data)
        for failure in (None, [3, 3, 2, 0], [4, 2, 2, 0], [4, 3, 3, 0], [4, 3, 1, 0]):
            data = copy.deepcopy(base)
            data['failure_diagnostics'] = failure
            self.reject(data)
        for status, kind in (('ok', 'none'), ('not_started', 'prerequisites_failed'),
                             ('inconclusive', 'unsupported_observation'), ('failed', 'timeout')):
            data = copy.deepcopy(base)
            data.update(status=status, failure_kind=kind)
            self.reject(data)
        for cases in (record()['cases'], [], None):
            data = copy.deepcopy(base)
            data['cases'] = cases
            self.reject(data)
        data = copy.deepcopy(base)
        data['cases'][6] = [6, 2, 4, MODULES[6], 0, [], [], []]
        self.reject(data)
        data = record()
        data['marker_validation_failure'] = [1, 38, 3, 28]
        self.reject(data)

    def test_every_conditional_inventory_and_error_phase_path(self):
        for scalar,nested,call,awaited in itertools.product(itertools.product((False,True),repeat=3),(False,True),(False,True),itertools.product((False,True),repeat=2)):
            self.accept(record(scalar_errors=scalar,nested=nested,reject_call=call,await_errors=awaited))

    def test_settled_await_orders_and_sibling_interleavings_are_not_predetermined(self):
        self.accept(record(reverse=False));self.accept(record(reverse=True))
        self.assertLess(observation(1)[0].index(13),observation(1)[0].index(15))
        self.assertGreater(observation(1,reverse=True)[0].index(13),observation(1,reverse=True)[0].index(15))

    def test_all_failure_positions_reasons_and_verified_hash_states(self):
        for index,reason,verified in itertools.product(range(8),range(1,15),(False,True)):
            if reason==14 and not verified: continue
            data=record();state=3 if reason==14 else 2
            data.update(status='inconclusive' if state==3 else 'failed',failure_kind=suite.ASYNC_FAILURES[reason],continuity_sha256=None)
            data['cases'][index:]=[[index,state,reason,MODULES[index] if verified else None,0,[],[],[]]]+[[i,0,1,None,0,[],[],[]] for i in range(index+1,8)]
            if index==0 and not verified:data['template_sha256']=None
            self.accept(data)
        self.accept(suite.empty_async_report())

    def test_rows_must_be_exact_eight_fields_and_ordered(self):
        base=record()
        for case in range(8):
            for changed in (base['cases'][case][:-1],base['cases'][case]+[0],{},None):
                data=copy.deepcopy(base);data['cases'][case]=changed;self.reject(data)
        for index in range(8):
            data=record();data['cases'][index][0]=(index+1)%8;self.reject(data)
        for key in ('extra','raw_errors','private_diagnostics'):
            data=record();data[key]='PRIVATE';self.reject(data)

    def test_every_event_is_required_exactly_once(self):
        for case in range(8):
            base=record();trace=base['cases'][case][5]
            for index in range(len(trace)):
                data=copy.deepcopy(base);data['cases'][case][5].pop(index);self.reject(data)
                data=copy.deepcopy(base);data['cases'][case][5].insert(index,trace[index]);self.reject(data)
            for token in (True,False,1.0,-1,29,100,'PRIVATE',None):
                data=copy.deepcopy(base);data['cases'][case][5][2]=token;self.reject(data)

    def test_each_causal_edge_and_root_join_boundary_is_enforced(self):
        for case in range(8):
            for left,right in suite.ASYNC_EDGES[case]:
                data=record();trace=data['cases'][case][5]
                if left not in trace or right not in trace:continue
                a,b=trace.index(left),trace.index(right);trace[a],trace[b]=trace[b],trace[a]
                self.reject(data)
        data=record();trace=data['cases'][2][5];trace.remove(24);trace.insert(-1,24);self.reject(data)

    def test_scalar_value_types_bounds_and_no_public_strings(self):
        for case in range(8):
            for slot in range(len(record()['cases'][case][6])):
                for value in ([4,True],[True,0],[4,1.0],[4,-1000000],[4,1000000],[5,8],[6,1],[3,2],[0,1],[8,0],['4',0],[4,'PRIVATE'],{},None,[] ):
                    data=record();data['cases'][case][6][slot]=value;self.reject(data)
        for value in ([1,0],[2,0],[3,0],[3,1],[4,-999999],[4,999999],[5,0],[5,7],[6,0]):
            data=record();data['cases'][0][6][0]=value;self.accept(data)

    def test_error_reference_bijection_phase_bounds_and_no_arbitrary_text(self):
        for edit in (
            lambda d:d['cases'][3][6][1].__setitem__(1,0),
            lambda d:d['cases'][3][7][0].__setitem__(0,4),
            lambda d:d['cases'][3][7].append([3,2,2,2,1,0,H]),
            lambda d:d['cases'][6][7][0].__setitem__(6,'PRIVATE'),
            lambda d:d['cases'][7][6].__setitem__(2,[4,1]),
            lambda d:d['cases'][0][6].__setitem__(0,[7,0]),
        ):
            data=record();edit(data);self.reject(data)
        for index in range(6):
            for value in (True,1.0,-1,7,'PRIVATE',None):
                data=record();data['cases'][3][7][0][index]=value;self.reject(data)

    def test_failure_proof_trace_and_unreached_hash_are_never_salvaged(self):
        data=record();data.update(status='failed',failure_kind='process_failed',continuity_sha256=None)
        data['cases'][7]=[7,2,11,MODULES[7],0,[],[],[]];self.accept(data)
        for index,value in ((4,63),(5,[0]),(6,[[1,0]]),(7,[[6,2,2,2,1,0,H]])):
            changed=copy.deepcopy(data);changed['cases'][7][index]=value;self.reject(changed)
        changed=copy.deepcopy(data);changed['cases'][2]=[2,0,1,None,0,[],[],[]];self.reject(changed)
        changed=record();changed['cases'][0][4]=True;self.reject(changed)

    def test_wire_only_compresses_diagnostics_and_public_rows_stay_compact(self):
        data=record();wire=suite.encode_async_wire(data)
        self.assertEqual(full.decode_async_wire(wire),data)
        self.assertEqual(suite.decode_async_wire(wire),data)
        self.assertEqual(full.encode_async_wire(data),wire)
        self.assertTrue(all(type(row) is list and len(row)==8 for row in wire['cases']))
        self.assertNotIn('roundtrip_sha256',json.dumps(data))
        self.assertNotIn('witness_verified',json.dumps(data))
        named=suite.async_named_cases(data)
        self.assertTrue(named[0]['proof']['roundtrip_module_equal'])
        self.assertEqual(named[0]['roundtrip_sha256'],MODULES[0])
        self.assertEqual(len(data['cases'][0]),8)

    def test_diagnostics_strict_count_sum_enum_types(self):
        for key,value in (('stage',[]),('reason',{}),('unexpected_count',True),('zombie_count',1),('stage','PRIVATE')):
            data=record();data['process_diagnostics'][key]=value;self.reject(data)
        data=record();data['process_diagnostics']['classes']['native']=1;self.reject(data)

    def test_private_descriptor_hash_commits_exact_bounded_fields(self):
        desc=private_error(6)
        first=suite._async_private_error(desc)
        self.assertEqual(first,full.validate_async_private_descriptor(desc))
        self.assertEqual(first[:6],[6,2,2,2,1,0])
        other=copy.deepcopy(desc);other['source']=[2,'a different source']
        second=suite._async_private_error(other)
        self.assertEqual(first[:6],second[:6]);self.assertNotEqual(first[6],second[6])
        unavailable=copy.deepcopy(desc);unavailable['description']=[0,None];unavailable['category']=[0,None];unavailable['cause']=[0,None]
        self.assertEqual(suite._async_private_error(unavailable)[:6],[6,4,2,2,3,3])
        for value in ([2,'x'*513],[2,'я'*257],[3,True],[4,1],[5,0],[2,'\ud800'],[2,{}]):
            bad=copy.deepcopy(desc);bad['description']=value
            with self.assertRaises(suite.FullError):suite._async_private_error(bad)
            with self.assertRaises((ValueError,UnicodeError)):full.validate_async_private_descriptor(bad)
        big=copy.deepcopy(desc)
        for key in ('description','code','additional','module','source'):big[key]=[2,'\x00'*512]
        with self.assertRaises(suite.FullError):suite._async_private_error(big)
        with self.assertRaises(ValueError):full.validate_async_private_descriptor(big)

    def test_duplicate_trailing_partial_bom_deep_and_wrong_bound_markers_fail(self):
        marker=dict(schema=1,nonce=NONCE,case=0,phase='entered',witness='client')
        good=json.dumps(marker).encode()
        malformed=[good[:-1],good+b'{}',b'\xef\xbb\xbf'+good,good.replace(b'"schema": 1',b'"schema": 1,"schema": 1'),b'['*20+b'0'+b']'*20]
        for key,value in (('case',True),('schema',True),('case',1),('nonce','b'*32),('witness','server'),('extra','PRIVATE')):
            bad=dict(marker);bad[key]=value;malformed.append(json.dumps(bad).encode())
        for raw in malformed:
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'marker.json';path.write_bytes(raw)
                with self.assertRaises(suite.FullError):suite.client_async_marker(path,NONCE,0,'entered')
            with self.assertRaises(ValueError):full.validate_async_marker_raw(raw,NONCE,0,'entered')
        self.assertEqual(full.validate_async_marker_raw(good,NONCE,0,'entered'),marker)

    def test_private_marker_projection_contains_no_descriptor_text(self):
        trace,values,errors=observation(7)
        marker=dict(schema=1,nonce=NONCE,case=7,phase='completed',witness='client',status=1,failure=0,trace=trace,values=values,errors=[private_error(6)])
        first=suite.validate_async_marker(marker,NONCE,7,'completed')
        second=full.validate_async_marker_raw(json.dumps(marker).encode(),NONCE,7,'completed')
        self.assertEqual(first,second)
        self.assertNotIn('fixed-source',json.dumps(first));self.assertNotIn('ASYNC-REJECT',json.dumps(first))


if __name__ == '__main__': unittest.main()
