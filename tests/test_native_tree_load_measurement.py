"""Input observer tests only: synthetic actions are NOT native LoadColumn answers."""
from contextlib import ExitStack
from decimal import Decimal as D
import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRowCollection, BSLValueTreeColumnCollection
from yadinassi.values import BSLArray, BSLFixedArray, HostFunction, NULL
from yadinassi.structures import BSLStructure
from scripts import native_historical_replay as replay
from yadinassi.type_descriptions import BSLTypeDescription

ROOT = Path(__file__).resolve().parents[1]
START = '// Begin bounded ValueTree LoadColumn helpers (measurement only; no native answers).\n'
END = '// End bounded ValueTree LoadColumn helpers.\n\n'
CALL_START = '// Begin bounded ValueTree LoadColumn observations (measurement only; no native answers).\n'
CALL_END = '// End bounded ValueTree LoadColumn observations.\n'
BASE_SHA = '5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4'


def source():
    data = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes()
    data = data.replace(b'\r\n', b'\n') if os.name == 'nt' else data
    # These remain explicit historical action-helper tests, not the current
    # fail-only Rows diagnostic route. The inverse is exact/source-bound.
    return replay.without_tree_rows_diagnostic(data.decode('utf-8-sig')).encode('utf-8-sig')


def fragments():
    text = source().decode('utf-8-sig')
    helper = START + text.split(START, 1)[1].split(END, 1)[0] + END
    calls = CALL_START + text.split(CALL_START, 1)[1].split(CALL_END, 1)[0] + CALL_END
    return helper, calls


def array(values):
    a = BSLArray(); a.items = list(values); return a


class LoadObserverTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute('Procedure Показать(Label, Value) Message(Label + ": [" + Value + "]"); EndProcedure;' + fragments()[0])

    def probe(self, case):
        return self.vm.execute(f'TreeLoadProbe({case})')

    def witness(self, callback, *, returns_value=True):
        stack = ExitStack()
        for cls in (BSLValueTree, BSLValueTreeRowCollection, BSLValueTreeColumnCollection):
            original = cls.get_method
            def method(receiver, name, original=original):
                if name.casefold() in ('loadcolumn', 'загрузитьколонку'):
                    return HostFunction(name, lambda *args: callback(receiver, name, args), returns_value=returns_value)
                return original(receiver, name)
            stack.enter_context(mock.patch.object(cls, 'get_method', method))
        return stack

    def snapshot_setup(self, case=1):
        self.vm.execute(f'S = TreeLoadFresh({case}); Source = TreeLoadPair(6,7); Original = Source; Refs = New Array;')
        return self.vm.variables['s']

    def snapshot(self):
        return self.vm.execute('TreeLoadSnapshot(S, Source, Original, Refs)')

    def test_real_host_calibration_and_all45_baselines_with_missing_method(self):
        self.assertEqual(self.vm.execute('TreeLoadCalibrate()'), '-')
        # Preserve the original action-error observation test after runtime implementation.
        # Only this synthetic test suppresses dispatch; native parity is separate.
        original = BSLValueTreeRowCollection.get_method
        def missing(receiver, name):
            if name.casefold() in ('loadcolumn', 'загрузитьколонку'):
                raise ValueError('Synthetic missing method')
            return original(receiver, name)
        with mock.patch.object(BSLValueTreeRowCollection, 'get_method', missing):
            results = [self.probe(i) for i in range(1,46)]
        self.assertTrue(all(r[2] == '1' and '?' not in r and '!' not in r for r in results))
        self.assertEqual([len(r) for r in results], [125 if 37 <= i <= 40 else 65 for i in range(1,46)])
        self.assertEqual(sum(len(f'TL{i:02d}: [{r}]') for i,r in enumerate(results,1)),3525)
        self.assertTrue(all(r.isascii() for r in results))

    def test_all45_argument_routes_and_no_implicit_expression_calls(self):
        seen=[]
        with self.witness(lambda receiver,name,args: seen.append((receiver,name,args))):
            self.vm.execute(fragments()[1])
        self.assertEqual(len(seen),45)
        self.assertEqual(len(self.output),45)
        self.assertEqual(seen[0][1],'ЗагрузитьКолонку'); self.assertEqual(seen[1][1],'lOaDcOlUmN')
        self.assertEqual(seen[1][2][1],'iD')
        self.assertEqual(seen[2][0].parent.get_member('Id'),D(1))
        self.assertEqual(seen[3][0].parent.get_member('Id'),D(6))
        self.assertEqual([r[2][1] for r in seen[10:16]],list(map(D,['0','1','0.5','1.5','1.9','-0.5'])))
        self.assertIs(seen[16][2][1].table,seen[16][0].tree)
        self.assertIsNot(seen[20][2][1].table,seen[20][0].tree)
        self.assertEqual([r[2][1] for r in seen[21:25]], [D(-1),D(4),None,True])
        self.assertEqual([r[2][0] for r in seen[25:29]], ['bad',D(7),None,NULL])
        self.assertIs(type(seen[29][2][0]),BSLStructure)
        self.assertEqual(seen[30][2],())
        self.assertEqual(seen[31][2][1:],('Id',True))
        self.assertIs(type(seen[32][0]),BSLValueTree)
        self.assertEqual(len(seen[44][2]),1)
        self.assertEqual([len(r[2][0].items) for r in seen[6:10]],[0,1,3,2])
        self.assertIs(type(seen[9][2][0]),BSLFixedArray)
        self.assertEqual([r[2][0].items for r in seen[40:44]],[[D(7),'bad'],['bad',D(7)],[D(7),None],[D(6),D(7),'bad']])
        self.assertFalse(any('?' in r or '!' in r for r in self.output))
        self.assertEqual(self.output[33][4:10],': [1X0')

    def test_statement_procedure_succeeds_but_expression_rejects_before_call(self):
        seen=[]
        with self.witness(lambda *args:seen.append(args),returns_value=False):
            statement=self.probe(1); expression=self.probe(34)
        self.assertEqual(statement[2],'0'); self.assertEqual(expression[2],'1')
        self.assertEqual(expression[4:6],'--'); self.assertEqual(len(seen),1)
        self.assertNotIn('!',expression)

    def test_action_exception_preserves_partial_tree_and_source_mutations(self):
        def act(receiver,name,args):
            receiver.tree.rows.items[0].set_member('Mark','from-result')
            args[0].items[0]=D(5)
            raise ValueError('PRIVATE-ACTION-TEXT')
        with self.witness(act): result=self.probe(1)
        self.assertEqual(result[2],'1'); self.assertIn('1_b_c_g_',result)
        self.assertTrue(result.endswith('A125_7_..')); self.assertNotIn('PRIVATE',result)
        self.assertNotIn('!',result)

    def test_two_way_aliases_and_independent_equal_structures_are_distinguished(self):
        def shared(receiver,name,args):receiver.items[0].set_member('Key',args[0].items[0])
        def copied(receiver,name,args):receiver.items[0].set_member('Key',BSLStructure('Mark','base'))
        for case,mark in [(37,'Q0'),(38,'R0')]:
            with self.witness(shared): result=self.probe(case)
            first,last=result[6:].split('|')
            self.assertEqual(result[2:4],'01'); self.assertEqual(first.count('P0'),2)
            self.assertEqual(last.count(mark),2); self.assertNotIn('!',result)
            with self.witness(copied): result=self.probe(case)
            first,last=result[6:].split('|')
            self.assertIn('P1',first); self.assertIn('P0',first)
            if case==37:self.assertIn('P1',last);self.assertIn('Q0',last)
            else:self.assertIn('R1',last);self.assertIn('P0',last)

    def test_source_membership_changes_do_not_replace_snapshot_with_a_summary(self):
        def values(receiver,name,args):
            receiver.items[0].set_member('Key',args[0].items[0]); receiver.items[1].set_member('Key',args[0].items[1])
        with self.witness(values): deleted=self.probe(39); replaced=self.probe(40)
        for result,tail in [(deleted,'A117_....'),(replaced,'A125_7_..')]:
            first,last=result[6:].split('|')
            self.assertEqual(first[:50],last[:50]); self.assertTrue(last.endswith(tail))
            self.assertEqual(result[2:4],'01'); self.assertNotIn('!',result)

    def test_mutation_error_and_skipped_mutation_remain_distinct(self):
        with self.witness(lambda *args:None): result=self.probe(38)
        self.assertEqual(result[2:4],'02'); self.assertNotIn('!',result)
        with self.witness(lambda *args:(_ for _ in ()).throw(ValueError('private'))): result=self.probe(38)
        self.assertEqual(result[2:4],'13'); self.assertNotIn('!',result)

    def test_setup_and_calibration_errors_are_distinct_and_bounded(self):
        original=BSLValueTreeRowCollection.add; calls=[]
        def setup_failure(receiver):
            calls.append(receiver)
            if len(calls)>2:raise ValueError('PRIVATE')
            return original(receiver)
        with mock.patch.object(BSLValueTreeRowCollection,'add',setup_failure):
            result=self.probe(1)
        self.assertTrue(result.startswith('1?S0--!'));self.assertEqual(len(result),65)
        with mock.patch.object(BSLStructure,'__eq__',lambda *args:True,create=True):
            result=self.probe(1)
        self.assertTrue(result.startswith('1?C03-!'));self.assertEqual(len(result),65)
        self.assertNotIn('PRIVATE',result)

    def test_every_calibration_stage_is_finite_rejected_and_precedes_actions(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('diagnostic_contract', ROOT / 'scripts/native_1c_tree_load_contract.py')
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        helper, _ = fragments()
        for code in '0123456789ABCDEFGHIJKLMNOPQR':
            with self.subTest(stage=code):
                marker = ('    Stage = "0";\n    Попытка\n' if code == '0'
                          else f'        Stage = "{code}";\n')
                self.assertEqual(helper.count(marker), 1)
                changed = helper.replace(marker, marker + '        ВызватьИсключение "PRIVATE-SYNTHETIC";\n')
                vm = Interpreter()
                vm.execute(changed)
                with self.witness(lambda *args: self.fail('LoadColumn must not run after calibration failure')):
                    results = [vm.execute(f'TreeLoadProbe({case})') for case in range(1, 46)]
                self.assertEqual(results, ['1?C0' + code + '-!' + '.' * 58] * 45)
                units = sum(len(f'TL{i:02d}: [{value}]'.encode('utf-16-le')) // 2
                            for i, value in enumerate(results, 1))
                self.assertEqual(units, 3285)
                self.assertLessEqual(units, 3525)
                self.assertLess(3525, 3800)
                for case, result in enumerate(results, 1):
                    with self.assertRaises(contract.ObservationError):
                        contract.validate_payload(result.encode('ascii'), case)

    def test_unknown_cells_strings_shapes_and_result_types_fail_closed(self):
        self.vm.execute('Refs=New Array;')
        invalid=('8','-1','0.5','"BASE"','"é"','"unknown"','New Array',
                 'New Structure("mark","base")','New Structure("Mark,Extra","base",1)',
                 'New Structure("Other","base")','New Structure("Mark",1)')
        for text in invalid:
            with self.subTest(text=text),self.assertRaises(BSLError):self.vm.execute('TreeLoadCell('+text+',Refs)')
        with self.witness(lambda *args:BSLArray()): result=self.probe(34)
        self.assertEqual(result[2],'0');self.assertEqual(result[6:],'!' + '.'*58)

    def test_scalar_codebook_is_typed_and_exact(self):
        self.vm.execute('Refs=New Array;')
        for expression,expected in [('Undefined','U_'),('Null','L_'),('True','T_'),('False','F_'),('1','1_'),('"1"','j_'),('""','a_'),('"base"','e_')]:
            self.assertEqual(self.vm.execute('TreeLoadCell('+expression+',Refs)'),expected)

    def test_registry_is_stable_and_rejects_sixty_first_structure(self):
        refs=array([]); self.vm.variables['refs']=refs
        for i in range(60):
            self.vm.variables['value']=BSLStructure('Mark','base')
            code=self.vm.execute('TreeLoadCell(Value,Refs)')
            self.assertEqual(code,'P'+'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwx'[i])
            self.assertEqual(self.vm.execute('TreeLoadCell(Value,Refs)'),code)
        self.vm.variables['value']=refs.items[0];refs.items[0].set_member('Mark','from-source')
        self.assertEqual(self.vm.execute('TreeLoadCell(Value,Refs)'),'Q0')
        self.vm.variables['value']=BSLStructure('Mark','base')
        with self.assertRaises(BSLError):self.vm.execute('TreeLoadCell(Value,Refs)')
        self.assertEqual(len(refs.items),60)

    def test_each_schema_or_topology_drift_is_an_observer_failure(self):
        mutations=[
            lambda s:s.get_member('Tree').columns.add('Extra'),
            lambda s:s.get_member('Tree').columns.items.reverse(),
            lambda s:setattr(s.get_member('Tree').columns.items[0],'name','ID'),
            lambda s:setattr(s.get_member('Tree').columns.items[0],'title','other'),
            lambda s:setattr(s.get_member('Tree').columns.items[0],'width',D(1)),
            lambda s:setattr(s.get_member('Tree').columns.items[0],'value_type',BSLTypeDescription('Number')),
            lambda s:s.get_member('Tree').rows.items.reverse(),
            lambda s:s.get_member('Tree').rows.add(),
            lambda s:s.get_member('Nodes').items[5].rows.add(),
            lambda s:s.get_member('Foreign').rows.add(),
            lambda s:s.get_member('Foreign').columns.add('Extra'),
            lambda s:setattr(s.get_member('Foreign').columns.items[0],'title','other'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                s=self.snapshot_setup(); mutate(s)
                with self.assertRaises(BSLError):self.snapshot()

    def test_replaced_collection_objects_cannot_hide_behind_equal_elements(self):
        def replace_rows(tree, parent=None):
            original = tree.rows if parent is None else parent.rows
            replacement=BSLValueTreeRowCollection(tree,parent)
            replacement.items=list(original.items)
            if parent is None:tree.rows=replacement
            else:parent.rows=replacement
        def replace_columns(tree):
            replacement=BSLValueTreeColumnCollection(tree)
            replacement.items=list(tree.columns.items)
            tree.columns=replacement
        for change in (
            lambda s:replace_rows(s.get_member('Tree')),
            lambda s:replace_rows(s.get_member('Tree'),s.get_member('Nodes').items[0]),
            lambda s:replace_rows(s.get_member('Tree'),s.get_member('Nodes').items[5]),
            lambda s:replace_rows(s.get_member('Foreign')),
            lambda s:replace_columns(s.get_member('Tree')),
            lambda s:replace_columns(s.get_member('Foreign')),
        ):
            with self.subTest(change=change):
                s=self.snapshot_setup();change(s)
                with self.assertRaises(BSLError):self.snapshot()

    def test_typed_qualifier_change_fails_without_trusting_descriptor_identity(self):
        s=self.snapshot_setup(41)
        descriptor=s.get_member('Tree').columns.items[1].value_type
        object.__setattr__(descriptor.number_qualifiers,'digits',D(5))
        with self.assertRaises(BSLError):self.snapshot()

    def test_genuine_empty_modes_do_not_clear_or_read_deleted_rows(self):
        with mock.patch.object(BSLValueTreeRowCollection,'clear',side_effect=AssertionError('must not clear')):
            for case,prefix in [(5,'EE'),(6,'NN'),(19,'EE')]:
                result=self.probe(case)
                self.assertEqual(result[6:8],prefix);self.assertEqual(result[8:56],'.'*48)
                self.assertNotIn('!',result)

    def test_invalid_scalar_source_postvalue_is_observed(self):
        def action(receiver,name,args):args[0].set_member('Mark','from-source')
        with self.witness(action): result=self.probe(30)
        self.assertTrue(result.endswith('R01Q0....')); self.assertNotIn('!',result)
        for value,tail in [('bad','S01h_....'),(D(7),'N017_....'),(None,'U01U_....'),(NULL,'L01L_....')]:
            self.snapshot_setup();self.vm.variables['source']=value;self.vm.variables['original']=value
            self.assertTrue(self.snapshot().endswith(tail))

    def test_all_cell_slots_and_source_positions_fit_without_truncation(self):
        s=self.snapshot_setup();refs=self.vm.variables['refs']
        for row in s.get_member('Nodes').items:
            for column in ('Id','Key','Group','Mark'):row.set_member(column,BSLStructure('Mark','base'))
        self.vm.variables['source']=array([BSLStructure('Mark','base') for _ in range(3)])
        first=self.snapshot();self.assertEqual(len(first),59);self.assertEqual(len(refs.items),27)
        for row in s.get_member('Nodes').items:
            for column in ('Id','Key','Group','Mark'):row.set_member(column,BSLStructure('Mark','from-result'))
        self.vm.variables['source']=array([BSLStructure('Mark','from-source') for _ in range(3)])
        second=self.snapshot();self.assertEqual(len(second),59);self.assertEqual(len(refs.items),54)
        self.assertTrue(first.endswith('A23POPPPQ'));self.assertNotEqual(first,second)


class LoadObserverSourceTests(unittest.TestCase):
    def test_exact_appended_blocks_restore_all976_inputs(self):
        raw=source();text=raw.decode('utf-8-sig');helper,calls=fragments()
        self.assertEqual(text.count(START),1);self.assertEqual(text.count(CALL_START),1)
        self.assertTrue(text.endswith(calls))
        restored=text.replace(helper,'',1)[:-len(calls)].encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(restored).hexdigest(),BASE_SHA)
        parse(helper+calls)
        self.assertEqual(calls.splitlines()[1:-1],[f'Показать("TL{i:02d}", TreeLoadProbe({i}));' for i in range(1,46)])
        self.assertEqual(helper.count('Вычислить('),1)
        self.assertNotIn('UnloadColumn(',helper);self.assertNotIn('TreeUnload',helper)
        for forbidden in ('ОписаниеОшибки','ЗначениеВСтрокуВнутр','Записать','Прочитать','Пока '):self.assertNotIn(forbidden,helper)


if __name__=='__main__':unittest.main()
