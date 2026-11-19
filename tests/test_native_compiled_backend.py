"""Current direct child security plus historical evidence validators; no native run."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_1c_smoke import smoke

ROOT=Path(__file__).resolve().parents[1]
full=smoke.FULL

class NativeCompiledBackendTests(unittest.TestCase):

    def test_direct_child_default_and_explicit_route_execute_real_routines(self):
        bodies = ('Function F() Return 42; EndFunction Message(F());',
                  'Function F() s=0;For i=1 To 2 Do s=s+21;EndDo;Return s;EndFunction Message(F());')
        # Read actual backend state after execution; output equality is not the
        # witness of backend selection.
        script = full.EXECUTE_SCRIPT + "\nprint(interpreter.execution_backend, file=sys.stderr)\n"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.bsl'
            for body in bodies:
                source.write_text(body, encoding='utf-8')
                for arguments in ([], ['python-direct']):
                    with self.subTest(body=body, arguments=arguments):
                        result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                            str(ROOT), str(source), full.LINUX_TARGET, *arguments],
                            capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, b'42\n')
                        self.assertEqual(result.stderr, b'python-direct\n')

    def test_direct_child_backend_drift_fails_before_and_after_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.bsl'
            source.write_text('Message(42);', encoding='utf-8')
            for boundary in ('before', 'after'):
                marker = ('interpreter = Interpreter(output=emit, **options)' if boundary == 'before'
                          else 'interpreter.execute(source_text, str(source))')
                script = full.EXECUTE_SCRIPT.replace(marker, marker + "\ninterpreter._execution_backend = 'interpreter'")
                self.assertNotEqual(script, full.EXECUTE_SCRIPT)
                with self.subTest(boundary=boundary):
                    result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                        str(ROOT), str(source), full.LINUX_TARGET, 'python-direct'],
                        capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b'execution backend mismatch', result.stderr)
                    self.assertEqual(result.stdout, b'' if boundary == 'before' else b'42\n')

    def test_child_rejects_invalid_backend_protocol_before_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.bsl'; stats = Path(directory) / 'execution.json'
            source.write_text('Message(42);', encoding='utf-8')
            command = [sys.executable, '-I', '-B', '-c', full.EXECUTE_SCRIPT, str(ROOT), str(source), full.LINUX_TARGET]
            for args in (['interpreter'], ['hybrid'], ['garbage'], ['compiled-strict'], ['python-direct', str(stats)], ['compiled-strict', str(stats), 'extra']):
                with self.subTest(args=args):
                    result = subprocess.run(command + args, capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, b'')
                    self.assertFalse(stats.exists())

    def test_unobserved_stats_cannot_be_called_compiled(self):
        stats={key:0 for key in ('emitted_executions','helper_executions','rejected_units',
            'unsupported_executions','interpreter_fallbacks','old_backend_executions','strict_rejections','inline_blocks','inline_fragments')}
        stats['lowering_variant']='node-scaffold'
        stats['fast_inline_enabled']=False
        stats['node_coverage']='observed'
        with self.assertRaises(full.FullError):full.execution_evidence([stats])

    def test_inline_entry_counts_do_not_claim_node_coverage(self):
        stats={key:0 for key in ('emitted_executions','helper_executions','rejected_units',
            'unsupported_executions','interpreter_fallbacks','old_backend_executions','strict_rejections','inline_blocks','inline_fragments')}
        stats.update(inline_blocks=1,node_coverage='unobserved',lowering_variant='inline',fast_inline_enabled=True)
        evidence=full.execution_evidence([stats])
        self.assertEqual(evidence['cases'][0]['node_coverage'],'unobserved')
        self.assertEqual(evidence['cases'][0]['emitted_executions'],0)

    def test_translated_evidence_has_explicit_version_and_rejects_tampering(self):
        stats={key:0 for key in ('emitted_executions','helper_executions','rejected_units',
            'unsupported_executions','interpreter_fallbacks','old_backend_executions','strict_rejections',
            'inline_blocks','inline_fragments','python_translated_blocks','python_translated_nodes','plain_adapter_blocks','block_executions','metadata_block_executions')}
        stats.update(python_translated_blocks=1,node_coverage='unobserved',lowering_variant='python-translation',fast_inline_enabled=True)
        evidence=full.execution_evidence([stats])
        self.assertEqual(evidence['schema'],'compiled-native-execution-v2')
        for key,value in [('python_translated_blocks',True),('python_translated_nodes',-1),
                          ('python_translated_nodes',10**12+1),('plain_adapter_blocks',1),('unexpected',0)]:
            bad=copy.deepcopy(evidence);bad['cases'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
        for key in ('emitted_executions','helper_executions','inline_blocks','inline_fragments','block_executions','metadata_block_executions'):
            bad=copy.deepcopy(evidence);bad['cases'][0][key]=1
            with self.subTest(mixed_route=key),self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
        for key in ('python_translated_blocks','python_translated_nodes','plain_adapter_blocks','block_executions','metadata_block_executions'):
            bad=copy.deepcopy(evidence);del bad['cases'][0][key]
            with self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
        bad=copy.deepcopy(evidence);bad['schema']='compiled-native-execution-v1'
        with self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
        for variant in ('inline','node-scaffold'):
            bad=copy.deepcopy(evidence);bad['cases'][0]['lowering_variant']=variant
            with self.subTest(false_label=variant),self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
            bad['cases'][0]['emitted_executions']=1
            with self.subTest(mixed_label=variant),self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
        stats['python_translated_blocks']=0
        with self.assertRaises(full.FullError):full.execution_evidence([stats])

    def test_sync_only_evidence_v3_and_malformed_counts(self):
        stats={key:0 for key in ('emitted_executions','helper_executions','rejected_units',
            'unsupported_executions','interpreter_fallbacks','old_backend_executions','strict_rejections',
            'inline_blocks','inline_fragments','python_translated_blocks','python_translated_nodes',
            'plain_adapter_blocks','block_executions','metadata_block_executions','python_sync_routine_calls')}
        stats.update(python_sync_routine_calls=1,node_coverage='unobserved',
                     lowering_variant='python-translation',fast_inline_enabled=True)
        evidence=full.execution_evidence([stats])
        self.assertEqual(evidence['schema'],'compiled-native-execution-v3')
        self.assertEqual(evidence['cases'][0]['python_translated_nodes'],0)
        for value in (True,False,-1,10**12+1,1.0,'1',None,0):
            bad=copy.deepcopy(evidence);bad['cases'][0]['python_sync_routine_calls']=value
            with self.subTest(value=value),self.assertRaises(full.FullError):
                full.validate_execution_evidence(bad,1)
        for key,value in (('plain_adapter_blocks',1),('inline_blocks',1),
                          ('interpreter_fallbacks',1),('old_backend_executions',1),
                          ('lowering_variant','inline'),('python_sync_admission_nodes',10),
                          ('node_coverage','observed')):
            bad=copy.deepcopy(evidence);bad['cases'][0][key]=value
            with self.subTest(key=key),self.assertRaises(full.FullError):
                full.validate_execution_evidence(bad,1)
        bad=copy.deepcopy(evidence);del bad['cases'][0]['python_sync_routine_calls']
        with self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
        for version in ('compiled-native-execution-v1','compiled-native-execution-v2'):
            bad=copy.deepcopy(evidence);bad['schema']=version
            with self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)

    def test_schema_three_requires_explicit_validated_execution_witness(self):
        from unittest.mock import patch
        from test_native_1c_full_host import ComparisonTests
        case=ComparisonTests('test_fresh_real_source_path_complete_bytes_and_no_normalization')
        try:
            case.setUp()
            stats={key:0 for key in ('emitted_executions','helper_executions','rejected_units',
                'unsupported_executions','interpreter_fallbacks','old_backend_executions','strict_rejections','inline_blocks','inline_fragments')}
            stats.update(emitted_executions=1,lowering_variant='node-scaffold',fast_inline_enabled=False,node_coverage='observed')
            # Synthetic historical report: validate its contract, never execute
            # a deleted engine or claim these counters were freshly observed.
            def runner(args,cwd,**limits):
                self.assertEqual(args[-1], 'python-direct')
                return 0,case.payload,b''
            with patch.object(full,'validate_tree_load_observations'), patch.object(full,'validate_tree_move_observations'), patch.object(full,'validate_tree_total_observations'):
                result=full.compare_outputs(case.root,case.capture,case.stage3,case.inputs,
                    runner=runner,execution_backend='python-direct')
            result.pop('execution_backend')
            result['schema'] = 3
            result['execution'] = full.execution_evidence([dict(stats) for _ in full.SCENARIOS])
            full.validate_comparison(result, case.stage3, full.WINDOWS_TARGET, full.BYTE_EXACT,
                                     expected_execution_backend='compiled-strict')
            with self.assertRaises(full.FullError):
                full.validate_comparison(result, case.stage3, full.WINDOWS_TARGET, full.BYTE_EXACT,
                                         expected_execution_backend='interpreter')
            downgraded = {k: v for k, v in result.items() if k != 'execution'}
            downgraded['schema'] = 2
            with self.assertRaises(full.FullError):
                full.validate_comparison(downgraded, case.stage3, full.WINDOWS_TARGET, full.BYTE_EXACT,
                                         expected_execution_backend='compiled-strict')
            for schema in (3.0, '3', True, None):
                for expected in (None, 'compiled-strict', 'interpreter'):
                    with self.subTest(schema=schema, expected=expected):
                        malformed = copy.deepcopy(result)
                        malformed['schema'] = schema
                        with self.assertRaises(full.FullError):
                            full.validate_comparison(malformed, case.stage3, full.WINDOWS_TARGET, full.BYTE_EXACT,
                                                     expected_execution_backend=expected)
            self.assertEqual(result['schema'],3)
            self.assertEqual(result['acceptance_status'],'accepted')
            self.assertEqual(len(result['execution']['cases']),len(full.SCENARIOS))
            full.validate_comparison(result,case.stage3,full.WINDOWS_TARGET,full.BYTE_EXACT)
            for backend in ('interpreter','hybrid',None):
                bad=copy.deepcopy(result);bad['execution']['execution_backend']=backend
                with self.assertRaises(full.FullError):
                    full.validate_comparison(bad,case.stage3,full.WINDOWS_TARGET,full.BYTE_EXACT)
            bad=copy.deepcopy(result);del bad['execution']
            with self.assertRaises(full.FullError):
                full.validate_comparison(bad,case.stage3,full.WINDOWS_TARGET,full.BYTE_EXACT)
        finally:
            case.doCleanups()

    def test_source_only_inverse_is_exact_and_rejects_mutation(self):
        from test_native_async_fixture import without_compiled_backend_harness
        import hashlib
        source=(ROOT/'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        contract=json.loads((ROOT/'tests/native_compiled_source_inverse.json').read_text(encoding='utf-8'))
        restored=without_compiled_backend_harness(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),contract['base_sha256'])
        changed=source+'# changed\n'
        self.assertEqual(without_compiled_backend_harness(changed),changed)

    def test_invalid_backend_rejected_before_native_work(self):
        with self.assertRaises(smoke.SmokeError):
            smoke.run_smoke(Path('/not-used'),execution_backend='compiled-strict')
        with self.assertRaises(smoke.SmokeError):
            smoke.run_smoke(Path('/not-used'),full_suite=True,execution_backend='garbage')

    def test_three_harness_inverses_are_exact_and_reject_unknown_changes(self):
        from test_native_async_fixture import historical_source_bytes
        import hashlib
        inventory=json.loads((ROOT/'tests/native_compiled_source_inverse.json').read_text(encoding='utf-8'))
        contracts={'scripts/native_1c_full_host.py':inventory,**inventory['additional_sources']}
        for path,contract in contracts.items():
            with self.subTest(path=path):
                raw=(ROOT/path).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),contract['candidate_sha256'])
                restored=historical_source_bytes(path,raw,contract['base_sha256'])
                self.assertEqual(hashlib.sha256(restored).hexdigest(),contract['base_sha256'])
                self.assertEqual(historical_source_bytes(path,restored,contract['base_sha256']),restored)
                self.assertEqual(historical_source_bytes(path,raw,contract['candidate_sha256']),raw)
                self.assertEqual(historical_source_bytes(path,raw,'0'*64),raw)
                with self.assertRaisesRegex(AssertionError,'outer identity'):
                    historical_source_bytes(path,raw+b'\n# changed',contract['base_sha256'])

if __name__=='__main__':unittest.main()
