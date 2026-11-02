"""Production codecs/CLI envelope and complete marker budgets for observation mode.

Pure synthetic tests. No 1C process, fixed-path infobase, or native parity claim.
Structural majorants remain bounds, not falsely labeled valid native evidence.
"""
from __future__ import annotations
import contextlib
import copy
import io
import itertools
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_native_infobase_budget as ib
import test_native_async_budget as ab
from test_native_1c_full_host import SyntheticFilesystemCase
from test_native_preprocessor_measurement import TOKEN, marker
import test_native_1c_full_stage as stage_fixture

full,suite,smoke=ib.full,ib.suite,ib.smoke
ROOT=Path(__file__).resolve().parents[1]
BOUNDS={}


def bind(stage,inputs,modules,*,observed=True):
    stage['schema']=5
    stage['preprocessor_status']='observed' if observed else ('not_started' if stage['status']=='not_started' else 'failed')
    inputs[full.CLIENT_SOURCE]=full.PREPROCESSOR_SOURCE_SHA256
    modules['client_probe']=full.PREPROCESSOR_MODULE_SHA256
    for name in ('client_probe','client_watchdog'):
        if name in stage:
            record=stage[name]
            for key in full.CLIENT_HASHES:
                if record.get(key) is not None:
                    record[key]=full.PREPROCESSOR_SOURCE_SHA256 if key=='source_sha256' else full.PREPROCESSOR_MODULE_SHA256
    if observed:
        stage['client_probe']['infobase_context']=full.INFOBASE_CONTEXT_EXPECTED_TOKEN
        stage['client_probe']['preprocessor_profile']=TOKEN
    else:
        full.discard_infobase_capture(stage)
    return stage


def source_provenance():
    # Exercise the real source inventory/aggregate hashing. Installed dependency
    # availability is irrelevant to this byte budget, so supply pinned versions.
    # Current union: 111 = reviewed DOM runtime 106 plus five InformationRegister modules.
    # This exact source expectation is not the unchanged 512-file protocol cap.
    # Independent provenance checks bind the source additions and reject byte drift.
    with mock.patch.object(full.importlib.metadata,'version',side_effect=lambda name:full.DEPENDENCIES[name]):
        result=full.interpreter_provenance(ROOT)
    if result['source_file_count'] != 111:
        raise AssertionError(('Unexpected runtime inventory',result['source_file_count']))
    return result


def report_for(stage,*,accepted=False,majorant=False):
    value=ib.report_for(stage,accepted=accepted)
    value['interpreter']=source_provenance()
    if majorant:
        # 99.99.999 and 512 cover the larger accepted widths too. Actual inventory
        # remains explicitly exercised above, with all runtime source hashes.
        value['interpreter']['python_version']='99.99.999'
        value['interpreter']['source_file_count']=512
    return value


def summary(value,*,selected=None,async_mode=False,error=False,artifact_error=False):
    options=(dict(side_effect=smoke.SmokeError('x'*64,validated_report=copy.deepcopy(value),cleanup_error='x'*64))
             if error else dict(return_value=copy.deepcopy(value)))
    with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
        path=Path(directory).resolve()/'summary.json'
        arguments=['--execute-approved-image','--full-suite','--client-probe',
            '--client-preprocessor-measurement','--native-target',full.LINUX_TARGET,
            '--comparison-mode',full.MAP_MODE,'--export-native-outputs','--output',str(path)]
        if async_mode: arguments.append('--client-async-measurement')
        elif selected is not None:
            arguments.extend(flag for flag,present in zip(ib.CLI_FLAGS,selected) if present)
        with mock.patch.object(smoke,'run_smoke',**options),mock.patch.object(full,'verify_output_artifact',
                side_effect=full.FullError('native_artifact_evidence_invalid') if artifact_error else None):
            code=smoke.main(arguments)
        raw=path.read_text(encoding='utf-8').encode()
        public=json.loads(raw)
        if 'probe' not in public: raise AssertionError(('Lost production report',public))
        if public['purpose']!='client-preprocessor-observation-v1' or public['preprocessor_parity_claimed'] is not False:
            raise AssertionError('Observation must never become suffix parity')
        return raw,code


class PreprocessorBudgetTests(SyntheticFilesystemCase):
    def setUp(self):
        super().setUp()
        if os.name == "nt":
            reader = mock.patch.object(suite, "secure_bytes", new=stage_fixture.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def roundtrip(self,stage,inputs,modules,**options):
        wire=ab.render_stage(stage);raw=json.loads(wire)
        self.assertEqual(full.decode_stage3_wire(raw),stage)
        self.assertEqual(suite.decode_stage_wire(raw),stage)
        self.assertEqual(full.validate_stage3(raw,ab.NONCE,inputs,modules,
            prerequisites=stage['status']!='not_started',preprocessor_measurement=True,**options),stage)
        with self.assertRaises(ValueError):
            full.validate_stage3(raw,ab.NONCE,inputs,modules,prerequisites=stage['status']!='not_started',**options)
        self.assertLessEqual(len(wire),8192)
        return wire

    def test_all32_success_subsets_actual_envelope_and_schema_downgrade_rejection(self):
        wire_bounds=[];summary_bounds=[];schemas=set()
        for selected in itertools.product((False,True),repeat=5):
            stage,inputs,modules=ib.parity_stage(selected);bind(stage,inputs,modules)
            options=dict(zip(ib.OPTION_NAMES,selected));wire=self.roundtrip(stage,inputs,modules,**options)
            schemas.add(json.loads(wire)['schema'])
            public,code=summary(report_for(stage,accepted=True),selected=selected)
            self.assertEqual(code,0);self.assertEqual(json.loads(public)['probe']['interpreter']['source_file_count'],111)
            for downgrade in ('schema','status','token','identity'):
                raw=json.loads(wire)
                if downgrade=='schema': raw['schema']-=4;raw.pop('preprocessor_status')
                elif downgrade=='status': raw['preprocessor_status']='failed'
                elif downgrade=='token': del raw['client_probe']['preprocessor_profile']
                else: inputs=dict(inputs);inputs[full.CLIENT_SOURCE]=full.INFOBASE_CONTEXT_SOURCE_SHA256
                with self.assertRaises(ValueError):
                    full.validate_stage3(raw,ab.NONCE,inputs,modules,prerequisites=True,
                        preprocessor_measurement=downgrade!='schema',**options)
            # Ten independent seven-digit output sizes and two extra native-size
            # repetitions in comparison are charged exactly as existing proof.
            digits=6+sum(selected[:4]);wire_bounds.append(len(wire)+digits)
            summary_bounds.append(len(public)+digits+12)
        self.assertEqual(schemas,{5,6,7})
        BOUNDS['parity_success_wire']=max(wire_bounds);BOUNDS['parity_success_summary']=max(summary_bounds)
        self.assertLessEqual(max(wire_bounds),8192);self.assertLessEqual(max(summary_bounds),32768)

    def test_all240_client_failure_frontiers_real_validation_and_summary(self):
        wires=[];summaries=[]
        for selected in itertools.product((False,True),repeat=5):
            stage,inputs,modules=ib.parity_stage(selected);bind(stage,inputs,modules)
            options=dict(zip(ib.OPTION_NAMES,selected));order=['client_probe']+[n for n in ib.RECORD_NAMES if n in stage]
            for index,diagnostic in itertools.product(range(len(order)),(False,True)):
                failed=ib.failed_frontier(stage,index,marker=diagnostic)
                failed['preprocessor_status']='failed'
                wire=self.roundtrip(failed,inputs,modules,**options)
                value=report_for(failed,majorant=True);value['stage2']['diagnostics']=ab.maximum_bootstrap_diagnostics()
                public,_=summary(value,selected=selected,error=True)
                self.assertNotIn('preprocessor_profile',json.loads(public)['probe']['stage3']['client_probe'])
                digits=6+sum(selected[:4]);wires.append(len(wire)+digits);summaries.append(len(public)+digits)
            if 'client_collections' in order:
                failed=ib.failed_frontier(stage,order.index('client_collections'),mismatch=True)
                failed['preprocessor_status']='failed';wire=self.roundtrip(failed,inputs,modules,**options)
                public,_=summary(report_for(failed,majorant=True),selected=selected,error=True)
                wires.append(len(wire)+6+sum(selected[:4]));summaries.append(len(public)+6+sum(selected[:4]))
        self.assertEqual(len(wires),240)
        BOUNDS['client_failure_wire']=max(wires);BOUNDS['client_failure_summary']=max(summaries)
        self.assertLessEqual(max(wires),8192);self.assertLessEqual(max(summaries),32768)

    def test_32_early_and192_server_frontiers_keep_full_report(self):
        wires=[];summaries=[]
        for selected in itertools.product((False,True),repeat=5):
            successful,inputs,modules=ib.parity_stage(selected);bind(successful,inputs,modules)
            options=dict(zip(ib.OPTION_NAMES,selected))
            stage=suite.empty_report(ab.NONCE,client_probe=True,preprocessor_measurement=True,**options)
            wire=self.roundtrip(stage,inputs,modules,**options)
            value=ab.majorant(early=True);value.pop('async_comparison');value['stage3']=stage
            value['interpreter']=source_provenance()
            public,_=summary(value,selected=selected,error=True);wires.append(len(wire));summaries.append(len(public))
            for index,name in enumerate(full.SCENARIOS):
                stage=suite.empty_report(ab.NONCE,client_probe=True,preprocessor_measurement=True,**options)
                stage.update(status='failed',preprocessor_status='failed',failure_kind=ab.longest(full.FAILURES-{'none','prerequisites_failed'}),
                             failed_case=name,input_sha256=copy.deepcopy(inputs))
                stage['cases'][:index+1]=copy.deepcopy(successful['cases'][:index+1])
                for case in stage['cases'][:index]:case['message_count']=32768
                stage['cases'][index].update(status='failed',output_sha256=None,output_size=None,message_count=None)
                wire=self.roundtrip(stage,inputs,modules,**options)
                value=ab.majorant();value.pop('async_comparison');value['stage3']=stage;value['interpreter']=source_provenance()
                public,_=summary(value,selected=selected,error=True)
                wires.append(len(wire)+6);summaries.append(len(public)+6)
        self.assertEqual(len(wires),224)
        BOUNDS['server_early_wire']=max(wires);BOUNDS['server_early_summary']=max(summaries)
        self.assertLessEqual(max(wires),8192);self.assertLessEqual(max(summaries),32768)

    def test_async_success_and18_structural_majorants_keep_caps(self):
        stage,inputs,modules=ab.stage();ib.bind_capture(stage,inputs,modules);bind(stage,inputs,modules)
        for record in ab.successful_records():
            stage['client_async']=record;self.roundtrip(stage,inputs,modules,client_async=True)
        wires=[];summaries=[]
        for early,case in itertools.product((False,True),(None,*range(8))):
            value=ab.majorant(early=early,marker_case=case)
            value['interpreter']=source_provenance();value['interpreter']['python_version']='99.99.999';value['interpreter']['source_file_count']=512
            stage=value['stage3'];stage['schema']=5;stage['preprocessor_status']='not_started'
            # Structural upper bounds are not validator-accepted evidence. Keep
            # actual failure serialization, then charge omitted fixed captures.
            wire=ab.render_stage(stage)
            self.assertEqual(full.decode_stage3_wire(json.loads(wire)),stage)
            public,_=summary(value,async_mode=True,error=True)
            wires.append(len(wire)+ib.WIRE_INCREMENT+62)
            summaries.append(len(public)+ib.SUMMARY_INCREMENT+72)
        BOUNDS['async_wire_upper']=max(wires);BOUNDS['async_summary_upper']=max(summaries)
        self.assertLessEqual(max(wires),8192);self.assertLessEqual(max(summaries),32768)

    def test_real_provenance_builder_retains_only_unchanged_six_outputs(self):
        bounds=[]
        for async_mode in (False, True):
            if async_mode:
                stage,inputs,modules=ab.stage();ib.bind_capture(stage,inputs,modules)
            else:
                stage,inputs,modules=ib.parity_stage((True,)*5)
            bind(stage,inputs,modules)
            value=report_for(stage,accepted=True)
            if async_mode:
                value['async_comparison']=ab.maximum_async_comparison()
            payloads={case['name']+'.out':b'x'*case['output_size'] for case in stage['cases']}
            from test_native_tree_total_contract import synthetic_output
            payloads['collections.out']=synthetic_output(stage['cases'][0]['output_size'])
            stage['cases'][0]['message_count']=1023
            for case in stage['cases']:
                case['output_sha256']=full.digest(payloads[case['name']+'.out'])
            value['stage3']=stage;value['comparison']=ab.accepted_comparison(stage)
            files=full.output_artifact_files(payloads,value,smoke.IMAGE)
            self.assertEqual(tuple(files),full.ARTIFACT_FILES)
            for name,raw in payloads.items(): self.assertEqual(files[name],raw)
            manifest=json.loads(files['provenance.json'])
            self.assertFalse(manifest['preprocessor_parity_claimed'])
            self.assertEqual(manifest['purpose'],'client-preprocessor-observation-v1')
            self.assertEqual(manifest['interpreter']['source_file_count'],111)
            self.assertNotIn(TOKEN,files['provenance.json'].decode())
            # The complete production builder also sees the longest supported
            # comparison partition, including Async error rows when requested.
            value['comparison']=ab.comparison(stage)
            larger=full.output_artifact_files(payloads,value,smoke.IMAGE)['provenance.json']
            bounds.extend((len(files['provenance.json'])+12,len(larger)+12))
        BOUNDS['provenance_upper']=max(bounds)
        self.assertLessEqual(max(bounds),32768)

    def test_complete_private_marker_native_compact_writer_and_provenance(self):
        source=(ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8-sig')
        self.assertIn('ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина)',source)
        markers=[]
        for phase in ('entered','completed'):
            for token in ('pp.v1:'+'000'*10,'pp.v1:'+'511'*10,TOKEN):
                value=marker(phase,token)
                # All strings in the complete marker are ASCII. Escape Unicode,
                # slash and optional BOM variants explicitly; no native-size claim.
                self.assertTrue(json.dumps(value,ensure_ascii=False).isascii())
                for separators in ((',',':'),(', ',': ')):
                    raw=json.dumps(value,ensure_ascii=True,separators=separators).encode()
                    markers.append(len(raw)+3)
                    with tempfile.TemporaryDirectory() as directory:
                        path=Path(directory).resolve()/'marker';path.write_bytes(b'\xef\xbb\xbf'+raw)
                        self.assertEqual(suite.preprocessor_client_marker(path,value['nonce'],phase,
                            source_hash=full.PREPROCESSOR_SOURCE_SHA256),value)
        BOUNDS['private_marker_upper']=max(markers);self.assertLessEqual(max(markers),2048)
        provenance=source_provenance();self.assertEqual(provenance['source_file_count'],111)
        BOUNDS['runtime_source_count']=provenance['source_file_count']
        self.assertEqual(full.ARTIFACT_FILES,ab.ARTIFACT_CLASSES)
        self.assertEqual((suite.MAX_STAGE_REPORT,full.MAX_STAGE_REPORT,smoke.MAX_OUTPUT),(8192,8192,32768))


if __name__=='__main__': unittest.main()
