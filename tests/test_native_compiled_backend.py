"""Offline backend-selection evidence only; not a fresh native 1C run."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_1c_smoke import smoke
from scripts import native_async_comparison as async_adapter

ROOT=Path(__file__).resolve().parents[1]
full=smoke.FULL

class NativeCompiledBackendTests(unittest.TestCase):
    def test_isolated_child_explicit_strict_and_default_output_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);source=path/'case.bsl';stats=path/'stats.json'
            source.write_text('Function F() Return 42; EndFunction Message(F());',encoding='utf-8')
            command=[sys.executable,'-I','-B','-c',full.EXECUTE_SCRIPT,str(ROOT),str(source),full.LINUX_TARGET]
            old=subprocess.run(command,capture_output=True,timeout=30)
            new=subprocess.run([*command,'compiled-strict',str(stats)],capture_output=True,timeout=30)
            self.assertEqual((old.returncode,new.returncode),(0,0),(old.stderr,new.stderr))
            self.assertEqual(old.stdout,new.stdout)
            self.assertEqual(new.stderr,b'')
            observed=json.loads(stats.read_text(encoding='utf-8'))
            self.assertIn(observed['lowering_variant'],('inline','node-scaffold'))
            evidence=full.execution_evidence([observed])
            self.assertEqual(evidence['execution_backend'],'compiled-strict')
            for key in ('interpreter_fallbacks','old_backend_executions','strict_rejections'):
                bad=copy.deepcopy(evidence);bad['cases'][0][key]=1
                with self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)
            for bad in ({}, {'execution_backend':'interpreter'}, {'schema':2}):
                with self.assertRaises(full.FullError):full.validate_execution_evidence(bad,1)

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

    def test_direct_legacy_visitor_entry_is_detected_in_strict_child(self):
        script=full.EXECUTE_SCRIPT.replace('interpreter.execute(source_text, str(source))',
            "interpreter.execute(source_text, str(source))\nfrom yadinassi.syntax.parser import parse\ninterpreter.visit_Literal(parse('1;')[0].expression)")
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);source=path/'case.bsl';stats=path/'stats.json'
            source.write_text('Message(42);',encoding='utf-8')
            process=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT),str(source),
                full.LINUX_TARGET,'compiled-strict',str(stats)],capture_output=True,timeout=30)
            self.assertEqual(process.returncode,0,process.stderr)
            observed=json.loads(stats.read_text(encoding='utf-8'))
            self.assertGreater(observed['old_backend_executions'],0)
            with self.assertRaises(full.FullError):full.execution_evidence([observed])

    def test_context_owned_early_return_visitors_invalidate_strict_child_evidence(self):
        injection = "from types import SimpleNamespace\nfrom yadinassi.source_constant_managers import _ValueInterpreter\nfrom yadinassi.form_runtime import _FormInterpreter\nfrom yadinassi.syntax.parser import parse\nvalue_vm=object.__new__(_ValueInterpreter)\nvalue_vm.manager=SimpleNamespace(value_read=lambda vm: 7)\nif value_vm.visit_Name(parse('Value;')[0].expression)!=7: raise AssertionError('Value result')\nform=SimpleNamespace(_check=lambda: None)\nform_vm=object.__new__(_FormInterpreter)\nfrom yadinassi import Interpreter\nInterpreter.__init__(form_vm, execution_backend='compiled-strict')\nform_vm._form_session=SimpleNamespace(form=form)\nif form_vm.visit_Name(parse('ThisObject;')[0].expression) is not form: raise AssertionError('ThisObject identity')\n"
        script=full.EXECUTE_SCRIPT.replace('interpreter.execute(source_text, str(source))',
            'interpreter.execute(source_text, str(source))\n' + injection)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);source=path/'case.bsl';stats=path/'stats.json'
            source.write_text('Message(42);',encoding='utf-8')
            process=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT),str(source),
                full.LINUX_TARGET,'compiled-strict',str(stats)],capture_output=True,timeout=30)
            self.assertEqual(process.returncode,0,process.stderr)
            observed=json.loads(stats.read_text(encoding='utf-8'))
            self.assertEqual(observed['old_backend_executions'],2)
            self.assertGreater(sum(observed[k] for k in ('emitted_executions','helper_executions','inline_blocks','inline_fragments')),0)
            with self.assertRaises(full.FullError):full.execution_evidence([observed])

    def test_async_context_observer_detects_early_return_and_restores_visitors(self):
        from unittest.mock import patch
        from yadinassi.source_constant_managers import _ValueInterpreter
        from yadinassi.form_runtime import _FormInterpreter
        original_visitors=(_ValueInterpreter.visit_Name,_FormInterpreter.visit_Name)
        original_install=async_adapter.Capture.install
        def install(capture,vm):
            exec("from types import SimpleNamespace\nfrom yadinassi.source_constant_managers import _ValueInterpreter\nfrom yadinassi.form_runtime import _FormInterpreter\nfrom yadinassi.syntax.parser import parse\nvalue_vm=object.__new__(_ValueInterpreter)\nvalue_vm.manager=SimpleNamespace(value_read=lambda vm: 7)\nif value_vm.visit_Name(parse('Value;')[0].expression)!=7: raise AssertionError('Value result')\nform=SimpleNamespace(_check=lambda: None)\nform_vm=object.__new__(_FormInterpreter)\nfrom yadinassi import Interpreter\nInterpreter.__init__(form_vm, execution_backend='compiled-strict')\nform_vm._form_session=SimpleNamespace(form=form)\nif form_vm.visit_Name(parse('ThisObject;')[0].expression) is not form: raise AssertionError('ThisObject identity')\n", {})
            original_install(capture,vm)
        _,sources=async_adapter.read_pinned_sources((ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_bytes())
        evidence=[]
        with patch.object(async_adapter.Capture,'install',install):
            async_adapter.execute_actual(sources,execution_backend='compiled-strict',execution_evidence=evidence)
        self.assertEqual((_ValueInterpreter.visit_Name,_FormInterpreter.visit_Name),original_visitors)
        self.assertEqual(len(evidence),8)
        self.assertTrue(all(row['old_backend_executions']==2 for row in evidence))
        with self.assertRaises(full.FullError):full.execution_evidence(evidence)

    def test_async_actual_strict_matches_old_with_aggregate_evidence(self):
        _,sources=async_adapter.read_pinned_sources((ROOT/'scripts/native_1c_bootstrap/full_suite.py').read_bytes())
        before=async_adapter.execute_actual(sources)
        evidence=[]
        after=async_adapter.execute_actual(sources,execution_backend='compiled-strict',execution_evidence=evidence)
        self.assertEqual(after,before)
        self.assertEqual(len(evidence),8)
        full.validate_execution_evidence(full.execution_evidence(evidence),8)

    def test_async_isolated_child_transmits_backend_and_finite_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path=Path(directory)/'execution.json'
            process=subprocess.run([sys.executable,'-I','-B','-c',full.ASYNC_EXECUTE_SCRIPT,
                str(ROOT),'compiled-strict',str(evidence_path)],capture_output=True,timeout=30)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(process.stderr,b'')
            actual=json.loads(process.stdout)
            async_adapter.validate_actual(actual)
            evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
            full.validate_execution_evidence(full.execution_evidence(evidence),8)

    def test_schema_three_requires_explicit_validated_execution_witness(self):
        from unittest.mock import patch
        from test_native_1c_full_host import ComparisonTests
        case=ComparisonTests('test_fresh_real_source_path_complete_bytes_and_no_normalization')
        try:
            case.setUp()
            stats={key:0 for key in ('emitted_executions','helper_executions','rejected_units',
                'unsupported_executions','interpreter_fallbacks','old_backend_executions','strict_rejections','inline_blocks','inline_fragments')}
            stats.update(emitted_executions=1,lowering_variant='node-scaffold',fast_inline_enabled=False,node_coverage='observed')
            def runner(args,cwd,**limits):
                self.assertEqual(args[-2],'compiled-strict')
                Path(args[-1]).write_text(json.dumps(stats),encoding='utf-8')
                return 0,case.payload,b''
            with patch.object(full,'validate_tree_load_observations'), patch.object(full,'validate_tree_move_observations'), patch.object(full,'validate_tree_total_observations'):
                result=full.compare_outputs(case.root,case.capture,case.stage3,case.inputs,
                    runner=runner,execution_backend='compiled-strict')
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
