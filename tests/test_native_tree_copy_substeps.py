"""Finite observer faults; deliberately synthetic, never native Copy answers."""
import unittest
from pathlib import Path
from unittest import mock
from yadinassi import Interpreter
from yadinassi.value_trees import BSLValueTree
from scripts import native_1c_tree_copy_diagnostics as d
from scripts import native_1c_tree_copy_contract as contract
from test_native_tree_copy_measurement import SOURCE, HELPERS, emit, synthetic_method, maximum_output
import test_native_tree_profile_budget as budget


class CopySubstepDiagnostics(unittest.TestCase):
    def test_each_mutation_or_snapshot_checkpoint_reports_only_fixed_code(self):
        with mock.patch.object(BSLValueTree,'get_method',synthetic_method('deep')):
            for step in d.CASE5_STEPS:
                marker=f'Stage = "M{step}";'
                self.assertEqual(HELPERS.count(marker),1)
                source=HELPERS.replace(marker,marker+' ВызватьИсключение "PRIVATE-SOURCE-ERROR";',1)
                vm=Interpreter();vm.execute(source);vm.execute('Result = TCProbe(5);')
                self.assertEqual(vm.variables['result'],'XM'+step)
                self.assertNotIn('PRIVATE',vm.variables['result'])

    def test_both_identity_comparisons_rethrow_instead_of_false(self):
        for expression in ('Missing = (V = Неопределено);','Same = (V = Candidate);'):
            self.assertEqual(HELPERS.count(expression),1)
            source=HELPERS.replace(expression,'ВызватьИсключение "PRIVATE-IDENTITY-ERROR";',1)
            vm=Interpreter();vm.execute(source);vm.execute('Result = TCProbe(5);')
            self.assertEqual(vm.variables['result'],'XBI')
        self.assertEqual(HELPERS.count('PrivateIdentityDescription = ОписаниеОшибки();'),2)
        self.assertIn('Исключение\n        PrivateProbeDescription = ОписаниеОшибки();',HELPERS)

    def test_closed_step_identity_and_generic_identity_mapping(self):
        lines=maximum_output().splitlines(keepends=True)
        for step in d.CASE5_STEPS:
            for suffix in ('','I'):
                payload=('XM'+step+suffix).encode();changed=lines.copy();changed[5]=b'TC-5: ['+payload+b']\n'
                raw=b''.join(changed)
                value=d.observation_diagnostic(raw,'server',contract.validate_payload,contract.ObservationError)
                self.assertEqual(value['category'],'case5_step'+step+('_identity' if suffix else ''))
                budget.tree.validate_diagnostic(value,profile='tree-copy-v1')
                budget.host.validate_diagnostic(value,profile='tree-copy-v1')
                with self.assertRaises(contract.ObservationError):contract.validate_output(raw)
                with self.assertRaises(d.DiagnosticError):d.validate_diagnostic({**value,'case':4})
        for case in range(1,10):
            for stage in d.OBSERVER_STAGES:
                changed=lines.copy();changed[case]=f'TC-{case}: [X{stage}I]\n'.encode()
                value=d.observation_diagnostic(b''.join(changed),'client',contract.validate_payload,contract.ObservationError)
                self.assertEqual(value['category'],'identity_'+stage.lower())
                d.validate_diagnostic(value)
        for category in ('case5_step00','case5_step19','case5_step01_private','identity_private'):
            with self.assertRaises(d.DiagnosticError):d.validate_diagnostic(dict(site='server',case=5,category=category,calibration=None))
        for payload in (b'XM00',b'XM19',b'XM1',b'XM01II',b'XM01PRIVATE'):
            changed=lines.copy();changed[5]=b'TC-5: ['+payload+b']\n'
            value=d.observation_diagnostic(b''.join(changed),'server',contract.validate_payload,contract.ObservationError)
            self.assertEqual(value['category'],'payload_contract')

    def test_success_output_preserved_for_all_synthetic_copy_policies(self):
        # Remove ONLY observer instrumentation with exact inverse replacements.
        original=SOURCE
        first='''    Попытка Missing = (V = Неопределено);
    Исключение
        PrivateIdentityDescription = ОписаниеОшибки();
        ВызватьИсключение "copy-identity-compare";
    КонецПопытки;
    Если Missing Тогда Возврат "_"; КонецЕсли;'''
        original=original.replace(first,'    Если V = Неопределено Тогда Возврат "_"; КонецЕсли;',1)
        second='''        Candidate = Registry[I];
        Попытка Same = (V = Candidate);
        Исключение
            PrivateIdentityDescription = ОписаниеОшибки();
            ВызватьИсключение "copy-identity-compare";
        КонецПопытки;
        Если Same Тогда Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", I + 1, 1); КонецЕсли;'''
        original=original.replace(second,'        Если V = Registry[I] Тогда Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", I + 1, 1); КонецЕсли;',1)
        for step in d.CASE5_STEPS: original=original.replace(f'Stage = "M{step}"; ','')
        for mode in ('deep','shallow','outer'):
            with mock.patch.object(BSLValueTree,'get_method',synthetic_method(mode)):
                self.assertEqual(emit(),emit(original))
        self.assertEqual(len(maximum_output()),6746)
        self.assertEqual(max(map(len,d.DIAGNOSTIC_CATEGORIES)),30)

    def test_authenticated_failure_boundary_keeps_substep_but_never_payload(self):
        import copy,json
        from test_native_tree_copy_profile import success_envelope, SPEC, NONCE, PROFILE
        value,hashes,modules=success_envelope(__import__('test_native_tree_copy_measurement').capture(maximum_output()))
        value['outputs']=[]
        report=value['report'];report.update(status='stage3_failed',native_tests_completed=False)
        stage=report['stage3'];stage.update(status='failed',failure_kind='unsupported_observation',failed_case=SPEC.case)
        case=stage['cases'][0];case.update(status='failed',module_sha256=None,output_sha256=None,output_size=None,message_count=None)
        stage['client_tree']=budget.tree.full.empty_dates_report()
        stage['copy_access_probes']={'server':None,'client':None}
        for category in d.CASE5_CATEGORIES:
            stage['observation_diagnostic']=dict(site='server',case=5,category=category,calibration=None)
            with self.assertRaises(budget.host.TreeError) as caught:
                budget.host.validate_envelope(json.dumps(value).encode(),NONCE,hashes,modules,budget.smoke.validate_report,profile=PROFILE)
            self.assertEqual(str(caught.exception),'tree_observation_rejected')
            self.assertEqual(caught.exception.observation_diagnostic,stage['observation_diagnostic'])
        self.assertEqual(value['outputs'],[])
