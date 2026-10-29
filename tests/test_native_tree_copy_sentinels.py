"""Closed fixed-guard/accessor diagnostics; no native semantic expectations."""
import unittest
from yadinassi import Interpreter
from scripts import native_1c_tree_copy_diagnostics as d
from scripts import native_1c_tree_copy_contract as contract
from test_native_tree_copy_measurement import HELPERS, maximum_output
import test_native_tree_profile_budget as budget


class CopySentinelTests(unittest.TestCase):
    def test_exact_registry_counts_and_existing_id_lookup_precede_capacity(self):
        for count,expected in ((61,'OK'),(62,'G01'),(63,'G02')):
            vm=Interpreter();vm.execute(HELPERS)
            vm.execute(f'Registry = Новый Массив; Для I=1 По {count} Цикл Registry.Add(Неопределено); КонецЦикла; T=Новый ДеревоЗначений; '
                'Попытка X=TCId(T,Registry); Result="OK"; Исключение Private=ОписаниеОшибки(); Result=TCFailureCode(Private); КонецПопытки;')
            self.assertEqual(vm.variables['result'],expected)
        vm=Interpreter();vm.execute(HELPERS)
        vm.execute('Registry=Новый Массив; T=Новый ДеревоЗначений; Registry.Add(T); Для I=2 По 62 Цикл Registry.Add(Неопределено); КонецЦикла; Result=TCId(T,Registry);')
        self.assertEqual(vm.variables['result'],'0')

    def test_all_known_codes_and_rethrows_are_finite(self):
        vm=Interpreter();vm.execute(HELPERS)
        for code in ('I',*d.DETAIL_REASONS):
            vm.variables['private']='private prefix copy-detail-'+code+' private suffix'
            vm.execute('Result=TCFailureCode(private);')
            self.assertEqual(vm.variables['result'],code)
        for text in ('arbitrary/private/path','copy-detail-G99','copy-detail-S99'):
            vm.variables['private']=text;vm.execute('Result=TCFailureCode(private);')
            self.assertEqual(vm.variables['result'],'')

    def test_all_snapshot_points_and_flatten_points_localize_unknown_errors(self):
        snapshot_start=HELPERS.index('Функция TCSnapshot('); snapshot_end=HELPERS.index('Функция TCArray()',snapshot_start)
        flatten_start=HELPERS.index('Процедура TCFlatten('); flatten_end=snapshot_start
        for kind,start,end,count in (('S',snapshot_start,snapshot_end,35),('F',flatten_start,flatten_end,3)):
            for i in range(1,count+1):
                point=f'{i:02}';block=HELPERS[start:end];marker=f'Point = "{point}";'
                self.assertIn(marker,block)
                block=block.replace(marker,marker+' ВызватьИсключение "PRIVATE-ACCESS-FAULT";',1)
                source=HELPERS[:start]+block+HELPERS[end:]
                # Point01 occurs before Try: inject its first executable checked operation instead.
                if point=='01':
                    source=HELPERS
                    needle='Если ТипЗнч(T) <> Тип("ДеревоЗначений")' if kind=='S' else 'Если Nodes.Count() >= 5'
                    source=source.replace(needle,'ВызватьИсключение "PRIVATE-ACCESS-FAULT"; '+needle,1)
                vm=Interpreter();vm.execute(source);vm.execute('Result=TCProbe(3);')
                self.assertEqual(vm.variables['result'],'XB'+kind+point,(kind,point,vm.variables['result']))
                self.assertNotIn('PRIVATE',vm.variables['result'])

    def test_every_detail_combination_and_malformed_combination_is_rejected_or_classified(self):
        lines=maximum_output().splitlines(keepends=True)
        for code,reason in d.DETAIL_REASONS.items():
            for step in d.CASE5_STEPS:
                changed=lines.copy();changed[5]=f'TC-5: [XM{step}{code}]\n'.encode();raw=b''.join(changed)
                value=d.observation_diagnostic(raw,'server',contract.validate_payload,contract.ObservationError)
                self.assertEqual(value['category'],'case5_step'+step+'_'+reason)
                budget.tree.validate_diagnostic(value,profile='tree-copy-v1');budget.host.validate_diagnostic(value,profile='tree-copy-v1')
                with self.assertRaises(contract.ObservationError):contract.validate_output(raw)
                with self.assertRaises(d.DiagnosticError):d.validate_diagnostic({**value,'case':4})
            changed=lines.copy();changed[3]=f'TC-3: [XB{code}]\n'.encode()
            self.assertEqual(d.observation_diagnostic(b''.join(changed),'server',contract.validate_payload,contract.ObservationError)['category'],'detail_b_'+reason)
        for payload in ('XM15G99','XM00G01','XM19G01','XM15G011','XM15G01PRIVATE'):
            changed=lines.copy();changed[5]=f'TC-5: [{payload}]\n'.encode()
            self.assertEqual(d.observation_diagnostic(b''.join(changed),'server',contract.validate_payload,contract.ObservationError)['category'],'payload_contract')
        self.assertEqual(len(d.DIAGNOSTIC_CATEGORIES),1218)
        self.assertEqual(len(set(d.DIAGNOSTIC_CATEGORIES)),1218)
        self.assertEqual(max(map(len,d.DIAGNOSTIC_CATEGORIES)),30)
