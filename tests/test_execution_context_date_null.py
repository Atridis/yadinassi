"""Captured eight Date/Null facts plus explicitly local transfer safety guards.

Native run 40078699477 on 8.3.27.1508 Linux reported dn.v1:22222277 for
the exact core below. Measurement acceptance is not full native parity.
Bounds, excluded Date representations, NoContext and async composition tests
are local policy/regressions, not additional native observations.
"""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import os
from pathlib import Path
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND, date
from yadinassi.maps import BSLMap
from yadinassi.structures import BSLStructure
from yadinassi.type_values import type_of
from yadinassi.values import BSLArray, BSLType, NULL


CORE = (Path(__file__).resolve().parents[1] /
        'integrational_tests/directive_probes/date_null_core.bsl')
CORE_SHA256 = '1b6c51fba57161907d26d78b3c96d317ff1f4b65098d6bf5a0815ed5fb575a70'
DATE_A = date(*(Decimal(n) for n in (2024, 1, 2, 3, 4, 5)))
DATE_B = date(*(Decimal(n) for n in (2031, 6, 7, 8, 9, 10)))


def array(*items):
    result = BSLArray()
    result.items = list(items)
    return result


def nested(value, edges):
    for _ in range(edges):
        value = array(value)
    return value


class ExecutionContextDateNullTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.vm = Interpreter(self.messages.append)

    def tearDown(self):
        self.vm.close()

    def assert_restored(self):
        self.assertEqual(self.vm.execution_context, 'client')
        self.assertEqual(self.vm._context_stack, ['client'])
        self.assertEqual(self.vm._module_context_stack, [True])
        self.assertIsNone(self.vm.locals)

    def assert_date(self, value, expected):
        self.assertIs(type(value), BSLDate)
        self.assertEqual(value.ticks, expected.ticks)
        self.assertFalse(value.boundary)

    def test_exact_eight_operation_native_capture_replay(self):
        source = CORE.read_bytes()
        # A Windows checkout may use CRLF; compare the same LF Linux witness
        # fixture, without changing any production source or capture gate.
        if os.name == 'nt':
            source = source.replace(b'\r\n', b'\n')
        self.assertEqual(sha256(source).hexdigest(), CORE_SHA256)
        self.vm.execute(source.decode('utf-8'))
        observed = self.vm.execute('DNCollect()')
        self.assertEqual(observed.items, [Decimal(2)] * 6 + [Decimal(7)] * 2)
        self.vm.variables['observed'] = observed
        self.assertEqual(self.vm.execute('DNEncode(observed)'), 'dn.v1:22222277')
        self.assertEqual(self.messages, [])
        self.assert_restored()

    def test_direct_result_copyback_and_val_rebinding_preserve_exact_types(self):
        self.vm.execute('''
&AtServer
Function Echo(Val Value) Return Value; EndFunction
&AtServer
Procedure Replace(Value, Val Control, Val Replacement)
    Value=Replacement; Control=Replacement;
EndProcedure
x=Date(2024,1,2,3,4,5); control=x;
r=Echo(x); Replace(x,control,Null);
''')
        self.assert_date(self.vm.variables['r'], DATE_A)
        self.assertIs(self.vm.variables['x'], NULL)
        self.assert_date(self.vm.variables['control'], DATE_A)
        self.vm.execute('control=Null; Replace(x,control,Date(2031,6,7,8,9,10));')
        self.assert_date(self.vm.variables['x'], DATE_B)
        self.assertIs(self.vm.variables['control'], NULL)
        self.assertIs(self.vm.execute('Echo(Null)'), NULL)
        self.assertIsNone(self.vm.execute('Echo(Undefined)'))
        self.assertIs(type_of(NULL), BSLType.NULL)
        self.assertIs(type_of(None), BSLType.UNDEFINED)
        self.assert_restored()

    def test_whole_second_dates_are_not_restricted_to_sample_years(self):
        values = [None, '', True, Decimal('1.5'), NULL, DATE_A, DATE_B]
        for parts in ((1, 1, 2), (1900, 1, 1), (9999, 12, 30)):
            values.append(date(*(Decimal(n) for n in parts)))
        copied = self.vm._copy_context_packet(values)
        for original, result in zip(values, copied):
            self.assertIs(result, original)

    def test_val_graph_and_nonval_result_are_detached_per_occurrence(self):
        self.vm.execute('''
&AtServer
Function Swap(Val Graph)
    Graph.Leaves[0]=Null; Graph.Leaves[1]=Date(2031,6,7,8,9,10);
    Return Graph;
EndFunction
&AtServer
Function Change(Graph) Graph=Swap(Graph); Return Graph; EndFunction
leaves=New Array; leaves.Add(Date(2024,1,2,3,4,5)); leaves.Add(Null);
x=New Structure("Leaves",leaves); old=x; valresult=Swap(x); result=Change(x);
''')
        old = self.vm.variables['old']
        self.assert_date(old.get('Leaves').items[0], DATE_A)
        self.assertIs(old.get('Leaves').items[1], NULL)
        outputs = [self.vm.variables[name] for name in ('valresult', 'x', 'result')]
        for output in outputs:
            self.assertIsNot(output, old)
            self.assertIsNot(output.get('Leaves'), old.get('Leaves'))
            self.assertIs(output.get('Leaves').items[0], NULL)
            self.assert_date(output.get('Leaves').items[1], DATE_B)
        self.assertEqual(len({id(value) for value in outputs}), 3)
        self.assertEqual(len({id(value.get('Leaves')) for value in outputs}), 3)
        outputs[0].get('Leaves').items[0] = Decimal(9)
        self.assertIs(outputs[1].get('Leaves').items[0], NULL)
        self.assert_restored()

    def test_shared_children_and_packet_roots_remain_independent(self):
        child = array(DATE_A, NULL)
        root = BSLStructure('Left,Right', child, child)
        first, second = self.vm._copy_context_packet([root, root])
        branches = [first.get('Left'), first.get('Right'),
                    second.get('Left'), second.get('Right')]
        self.assertIsNot(first, second)
        self.assertEqual(len({id(value) for value in branches + [child]}), 5)
        branches[0].items[0] = NULL
        for branch in branches[1:] + [child]:
            self.assert_date(branch.items[0], DATE_A)
        self.assertEqual(list(first._items), ['left', 'right'])
        self.assertEqual([item[0] for item in first._items.values()], ['Left', 'Right'])

    def test_excluded_date_representations_reject_before_activation(self):
        self.vm.execute('''
&AtServer
Procedure Change(Value) Message("body"); Value=Null; EndProcedure
#If AtServer Then
Message("initializer");
#EndIf
''')
        invalid = [BSLDate(DATE_A.ticks + 1), BSLDate(DATE_A.ticks + TICKS_PER_SECOND // 2),
                   BSLDate(0), BSLDate(MAX_TICKS),
                   BSLDate(0, True), BSLDate(MAX_TICKS, True)]
        for value in invalid:
            for original in (value, BSLStructure('Leaves', array(DATE_A, NULL, value))):
                with self.subTest(value=value.ticks, boundary=value.boundary,
                                  nested=type(original) is BSLStructure):
                    self.vm.variables['x'] = original
                    with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
                        self.vm.execute('Change(x);')
                    self.assertIs(self.vm.variables['x'], original)
                    self.assertEqual(self.messages, [])
                    self.assert_restored()

    def test_exact_types_reject_subclasses_descriptors_and_host_objects(self):
        class DateTrap(BSLDate):
            def __str__(self):
                raise AssertionError('host conversion')

        class ArrayTrap(BSLArray):
            def __iter__(self):
                raise AssertionError('host iteration')

        class StructureTrap(BSLStructure):
            def get(self, name):
                raise AssertionError('host access')

        for value in (DateTrap(DATE_A.ticks), ArrayTrap(), StructureTrap(),
                      BSLType.NULL, BSLMap(), object(), datetime(2024, 1, 2), 1, 1.0):
            with self.subTest(kind=type(value).__name__):
                for packet in ([value], [BSLStructure('Leaf', value)]):
                    with self.assertRaises(TypeError):
                        self.vm._copy_context_packet(packet)

    def test_node_and_depth_limits_count_new_leaves_before_acceptance(self):
        for leaf in (DATE_A, NULL):
            self.assertEqual(len(self.vm._copy_context_packet([leaf] * 10000)), 10000)
            with self.assertRaisesRegex(ValueError, 'предел'):
                self.vm._copy_context_packet([leaf] * 10001)
            root = array(*([leaf] * 9999))
            self.assertEqual(len(self.vm._copy_context_packet([root])[0].items), 9999)
            with self.assertRaisesRegex(ValueError, 'предел'):
                self.vm._copy_context_packet([None, root])
            self.vm._copy_context_packet([nested(leaf, 64)])
            with self.assertRaisesRegex(ValueError, 'предел'):
                self.vm._copy_context_packet([nested(leaf, 65)])

    def test_shared_expansion_cycles_and_recovery_remain_bounded(self):
        shared = array(DATE_A, NULL)
        for _ in range(13):
            shared = array(shared, shared)
        with self.assertRaisesRegex(ValueError, 'предел'):
            self.vm._copy_context_packet([shared])
        cycle = array(DATE_A, NULL)
        root = BSLStructure('Leaves', cycle)
        cycle.items.append(root)
        with self.assertRaisesRegex(ValueError, 'циклических'):
            self.vm._copy_context_packet([root])
        for bad in (cycle, BSLDate(DATE_A.ticks + 1)):
            with self.assertRaises(ValueError):
                self.vm._copy_context_packet([array(DATE_A, NULL, bad)])
            good = self.vm._copy_context_packet([array(DATE_A, NULL)])[0]
            self.assert_date(good.items[0], DATE_A)
            self.assertIs(good.items[1], NULL)

    def test_named_inputs_are_late_and_expression_values_early(self):
        self.vm.execute('''
&AtServer
Function Capture(Val Named, Ref, Val Early, Val Token)
    Return New Structure("Named,Ref,Early",Named,Ref,Early);
EndFunction
Function Identity(Val Value) Return Value; EndFunction
Function Effect(Value, Calls) Calls=Calls+1; Value=Null; Return 0; EndFunction
x=Date(2024,1,2,3,4,5); calls=0;
result=Capture(x,x,Identity(x),Effect(x,calls));
''')
        result = self.vm.variables['result']
        self.assertIs(result.get('Named'), NULL)
        self.assertIs(result.get('Ref'), NULL)
        self.assert_date(result.get('Early'), DATE_A)
        self.assertIs(self.vm.variables['x'], NULL)
        self.assertEqual(self.vm.variables['calls'], Decimal(1))
        self.assert_restored()

    def test_all_outputs_validate_before_any_caller_write(self):
        cycle = array(NULL)
        cycle.items.append(cycle)
        invalid = [BSLMap(), BSLDate(DATE_A.ticks + 1), cycle,
                   nested(NULL, 65), array(*([NULL] * 9999))]
        self.vm.execute('''
&AtServer
Procedure Change(A,B) A=Null; B=Invalid(); EndProcedure
''')
        for value in invalid:
            self.vm.register_function('Invalid', lambda value=value: value)
            for actuals in ('x,y', 'x,x'):
                with self.subTest(kind=type(value).__name__, actuals=actuals):
                    self.vm.variables.update(x=DATE_A, y=DATE_B)
                    with self.assertRaises(BSLError):
                        self.vm.execute(f'Change({actuals});')
                    self.assertIs(self.vm.variables['x'], DATE_A)
                    self.assertIs(self.vm.variables['y'], DATE_B)
                    self.assert_restored()

    def test_invalid_result_blocks_output_even_when_discarded(self):
        self.vm.execute('''
&AtServer
Function Change(Value) Value=Null; Return New Map; EndFunction
x=Date(2024,1,2,3,4,5); result="old";
''')
        original = self.vm.variables['x']
        for call in ('Change(x);', 'result=Change(x);'):
            with self.assertRaises(BSLError):
                self.vm.execute(call)
            self.assertIs(self.vm.variables['x'], original)
            self.assertEqual(self.vm.variables['result'], 'old')
            self.assert_restored()

    def test_val_rebinding_is_not_part_of_outgoing_packet(self):
        self.vm.execute('''
&AtServer
Function Change(Value, Val Control)
    Value=Null; Control=Date(2024,1,2,3,4,5)+0.0001; Return True;
EndFunction
x=Date(2024,1,2,3,4,5); control=x; result=Change(x,control);
''')
        self.assertIs(self.vm.variables['x'], NULL)
        self.assert_date(self.vm.variables['control'], DATE_A)
        self.assertIs(self.vm.variables['result'], True)
        self.assert_restored()

    def test_duplicate_actuals_publish_in_formal_order(self):
        self.vm.execute('''
&AtServer
Procedure Change(A,B) B=Date(2031,6,7,8,9,10); A=Null; EndProcedure
&AtServer
Procedure UnchangedLast(A,B) A=Null; EndProcedure
x=Date(2024,1,2,3,4,5); Change(x,x);
''')
        self.assert_date(self.vm.variables['x'], DATE_B)
        self.vm.execute('UnchangedLast(x,x);')
        self.assert_date(self.vm.variables['x'], DATE_B)
        self.assert_restored()

    def test_nonval_actual_restriction_precedes_earlier_effects(self):
        self.vm.execute('''
&AtServer
Procedure Change(Val First, Value) Value=Null; EndProcedure
Function Effect() Message("effect"); Return 0; EndFunction
x=New Structure("Leaf",Date(2024,1,2,3,4,5));
''')
        for actual in ('x.Leaf', 'Date(2024,1,2,3,4,5)'):
            with self.assertRaisesRegex(BSLError, 'без Знач'):
                self.vm.execute(f'Change(Effect(),{actual});')
            self.assertEqual(self.messages, [])
            self.assert_date(self.vm.variables['x'].get('Leaf'), DATE_A)
            self.assert_restored()

    def test_escaping_error_preserves_actual_effects_but_never_copies_out(self):
        self.vm.execute('''
&AtServer
Procedure Fail(Value, Graph, Val Token)
    Value=Date(2031,6,7,8,9,10); Graph.Leaf=Value; Raise "escape";
EndProcedure
&AtServer
Procedure Recover(Value)
    Try Raise "caught"; Except Value=Date(2031,6,7,8,9,10); EndTry;
EndProcedure
Function Effect(Value) Value=Null; Return 0; EndFunction
x=Date(2024,1,2,3,4,5); graph=New Structure("Leaf",x); old=graph;
Try Fail(x,graph,Effect(x)); Except EndTry;
''')
        self.assertIs(self.vm.variables['x'], NULL)
        self.assertIs(self.vm.variables['graph'], self.vm.variables['old'])
        self.assert_date(self.vm.variables['graph'].get('Leaf'), DATE_A)
        self.assert_restored()
        self.vm.execute('Recover(x);')
        self.assert_date(self.vm.variables['x'], DATE_B)
        self.assert_restored()

    def test_initializer_failure_keeps_outputs_and_restores_activation(self):
        failures = [True, False]
        self.vm.register_function('ShouldFail', lambda: failures.pop(0))
        self.vm.execute('''
&AtServer
Procedure Change(Value) Value=Null; EndProcedure
#If AtServer Then
If ShouldFail() Then Raise "initializer"; EndIf;
#EndIf
x=Date(2024,1,2,3,4,5);
''')
        original = self.vm.variables['x']
        with self.assertRaisesRegex(BSLError, 'initializer'):
            self.vm.execute('Change(x);')
        self.assertIs(self.vm.variables['x'], original)
        self.assert_restored()
        self.vm.execute('Change(x);')
        self.assertIs(self.vm.variables['x'], NULL)
        self.assert_restored()

    def test_nocontext_shared_copier_and_nested_server_calls_local_regression(self):
        self.vm.execute('''
&AtServerNoContext
Procedure Inner(Value) Value.Leaf=Null; EndProcedure
&AtServerNoContext
Function Change(Value, Val DateValue)
    Inner(Value); Value.When=DateValue; Return Value;
EndFunction
x=New Structure("Leaf,When",Date(2024,1,2,3,4,5),Null); old=x;
result=Change(x,Date(2031,6,7,8,9,10));
''')
        self.assertIs(self.vm.variables['x'].get('Leaf'), NULL)
        self.assert_date(self.vm.variables['x'].get('When'), DATE_B)
        self.assert_date(self.vm.variables['old'].get('Leaf'), DATE_A)
        self.assertIs(self.vm.variables['old'].get('When'), NULL)
        self.assertIsNot(self.vm.variables['result'], self.vm.variables['x'])
        self.assert_restored()

    def test_async_suspension_keeps_late_named_early_expression_values(self):
        self.vm.execute('''
Var x,calls;
&AtServer
Function Capture(Val Named, Value, Val Early, Val Token)
    Value=Date(2031,6,7,8,9,10);
    Return New Structure("Named,Early",Named,Early);
EndFunction
Function Identity(Val Value) Return Value; EndFunction
Async Function Effect() calls=calls+1; token=Await 0; x=Null; Return 0; EndFunction
Async Function Main() Return Capture(x,x,Identity(x),Await Effect()); EndFunction
x=Date(2024,1,2,3,4,5); calls=0; p=Main();
''')
        result = self.vm.variables['p'].result
        self.assertIs(result.get('Named'), NULL)
        self.assert_date(result.get('Early'), DATE_A)
        self.assert_date(self.vm.variables['x'], DATE_B)
        self.assertEqual(self.vm.variables['calls'], Decimal(1))
        self.assert_restored()

    def test_async_outgoing_failure_keeps_roots_and_cleans_nested_diagnostics(self):
        self.vm.execute('''
Var x,y;
&AtServer
Procedure Change(A,B,Val Token) A=Null; B=Date(2024,1,2,3,4,5)+0.0001; EndProcedure
Async Function Main()
    Try Raise "caller"; Except
        before=ErrorInfo().Description;
        Try Change(x,y,Await 0); Except caught=ErrorInfo().Description; EndTry;
        token=Await 0;
        Return New Structure("Before,Caught,After",before,caught,ErrorInfo().Description);
    EndTry;
EndFunction
x=Date(2024,1,2,3,4,5); y=Null; p=Main();
''')
        result = self.vm.variables['p'].result
        self.assertEqual(result.get('Before'), 'caller')
        self.assertIn('Межконтекстная передача', result.get('Caught'))
        # Existing nested-handler semantics clear, rather than restore, outer
        # diagnostics. Date/Null transfer must not change that separate contract.
        self.assertEqual(result.get('After'), '')
        self.assert_date(self.vm.variables['x'], DATE_A)
        self.assertIs(self.vm.variables['y'], NULL)
        self.assert_restored()


if __name__ == '__main__':
    unittest.main()
