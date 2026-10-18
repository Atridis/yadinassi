"""PR47 native references plus explicitly local regression boundaries."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.values import BSLObject


class ReferenceArgumentTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)
        self.vm.execute('''
            Procedure SetValue(x) x = 99; EndProcedure
            Procedure ReadValue(x) Message(x); EndProcedure
            Procedure SetThenRaise(x) SetValue(x); Raise "stop"; EndProcedure
            Function ValCopy(Val x) x = 99; Return x; EndFunction
            a = New Array; a.Add(10); a.Add(20);
            s = New Structure("Value", 10);
            m = New Map; m.Insert("key", 10);
            fa = New FixedArray(a); fs = New FixedStructure(s); fm = New FixedMap(m);
        ''')

    def test_live_reads_in_both_directions_for_each_mutable_slot(self):
        self.vm.execute('''
            Procedure Live(slot, Val owner, Val key)
                slot = 11; Message(owner[key]); owner[key] = 12; Message(slot);
            EndProcedure
        ''')
        for slot, owner, key in [('a[0]', 'a', '0'), ('s.Value', 's', '"Value"'),
                                 ('s["Value"]', 's', '"Value"'), ('m["key"]', 'm', '"key"')]:
            with self.subTest(slot=slot):
                self.output.clear()
                self.vm.execute(f'Live({slot}, {owner}, {key});')
                self.assertEqual(self.output, ['11', '12'])
                self.assertEqual(self.vm.execute(slot), Decimal(12))

    def test_repeated_slot_and_case_insensitive_property_aliases(self):
        self.vm.execute('''
            Procedure Aliases(first, second)
                first = 11; Message(second); second = 12; Message(first);
            EndProcedure
            Aliases(a[0], a[0]); Aliases(s.Value, s["vAlUe"]);
            Aliases(m["key"], (m["key"]));
        ''')
        self.assertEqual(self.output, ['11', '12'] * 3)

    def test_nested_receiver_and_index_expressions_once_left_to_right(self):
        self.vm.execute('''
            Var trace; trace = "";
            Function Owner(Val value) trace = trace + "R"; Return value; EndFunction
            Function Index() trace = trace + "I"; Return 0; EndFunction
            SetValue(Owner(a)[Index()]); Message(trace);
            trace = ""; SetValue(Owner(s).Value); Message(trace);
        ''')
        self.assertEqual(self.output, ['RI', 'R'])
        self.assertEqual(self.vm.execute('a[0]'), Decimal(99))
        self.assertEqual(self.vm.execute('s.Value'), Decimal(99))

    def test_nested_slots_and_parentheses(self):
        self.vm.execute('''
            a[0] = s; s.Value = m;
            SetValue((((a[0].Value["key"]))));
        ''')
        self.assertEqual(self.vm.execute('m["key"]'), Decimal(99))

    def test_grouping_preserves_variable_alias_but_not_computed_expression(self):
        self.vm.execute('x = 10; SetValue((((x)))); SetValue((x + 1));')
        self.assertEqual(self.vm.execute('x'), Decimal(99))

    def test_forwarding_and_exception_keep_prior_writes(self):
        for slot in ('a[0]', 's.Value', 's["Value"]', 'm["key"]'):
            with self.subTest(slot=slot):
                self.vm.execute(f'Try SetThenRaise({slot}); Except caught = True; EndTry;')
                self.assertEqual(self.vm.execute(slot), Decimal(99))
                self.assertIsNone(self.vm.locals)
        self.vm.execute('SetValue(a[1]);')
        self.assertEqual(self.vm.execute('a[1]'), Decimal(99))

    def test_fixed_slots_enter_and_read_before_assignment_error(self):
        self.vm.execute('''
            Var entered; entered = 0;
            Procedure ReadThenWrite(slot)
                entered = entered + 1; Message(slot); slot = 99;
                entered = entered + 100;
            EndProcedure
        ''')
        for slot in ('fa[0]', 'fs.Value', 'fs["Value"]', 'fm["key"]'):
            with self.subTest(slot=slot), self.assertRaises(BSLError):
                self.vm.execute(f'ReadThenWrite({slot});')
            self.assertEqual(self.vm.execute(slot), Decimal(10))
            self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execute('entered'), Decimal(4))
        self.assertEqual(self.output, ['10'] * 4)

    def test_fixed_slot_forwarded_to_read_only_routine(self):
        self.vm.execute('Procedure Forward(x) ReadValue(x); EndProcedure '
                        'Forward(fa[0]); Forward(fs.Value); Forward(fm["key"]);')
        self.assertEqual(self.output, ['10', '10', '10'])

    def test_val_isolates_all_slot_assignments_including_fixed(self):
        for slot in ('a[0]', 's.Value', 'm["key"]', 'fa[0]', 'fs.Value', 'fm["key"]'):
            with self.subTest(slot=slot):
                self.assertEqual(self.vm.execute(f'ValCopy({slot})'), Decimal(99))
                self.assertEqual(self.vm.execute(slot), Decimal(10))

    def test_invalid_slots_fail_before_body_or_later_arguments(self):
        self.vm.execute('''
            Var effects; effects = 0;
            Function Effect() effects = effects + 1; Return 0; EndFunction
            Procedure Enter(slot, ignored) effects = effects + 10; EndProcedure
        ''')
        for slot in ('a[-1]', 'a[2]', 'a[0.5]', 'a["0"]', 's.Absent',
                     's["Absent"]', 's[0]', 'fs.Absent', 'fa[2]', 'fm["absent"]'):
            with self.subTest(slot=slot), self.assertRaises(BSLError):
                self.vm.execute(f'Enter({slot}, Effect());')
            self.assertEqual(self.vm.execute('effects'), Decimal(0))
            self.assertIsNone(self.vm.locals)

    def test_mutable_map_missing_slot_can_be_read_then_created(self):
        self.vm.execute('ReadValue(m["missing"]); SetValue(m["missing"]);')
        self.assertEqual(self.output, [''])
        self.assertEqual(self.vm.execute('m["missing"]'), Decimal(99))
        self.assertEqual(self.vm.execute('m.Count()'), Decimal(2))

    def test_map_key_types_and_identity_are_preserved(self):
        self.vm.execute('''
            m[True] = 1; m[1] = 2; m[a] = 3;
            SetValue(m[True]); SetValue(m[a]);
        ''')
        self.assertEqual(self.vm.execute('m[True]'), Decimal(99))
        self.assertEqual(self.vm.execute('m[1]'), Decimal(2))
        self.assertEqual(self.vm.execute('m[a]'), Decimal(99))

    def test_property_output_assigns_existing_slot_and_missing_value(self):
        for slot in ('a[0]', '(a[0])', 's.Value', 's["Value"]', 'm["new"]'):
            with self.subTest(slot=slot):
                self.vm.execute('source = New Structure("Found", 42);')
                self.assertTrue(self.vm.execute(f'source.Property("Found", {slot})'))
                self.assertEqual(self.vm.execute(slot), Decimal(42))
                self.assertFalse(self.vm.execute(f'source.Property("Missing", {slot})'))
                self.assertIsNone(self.vm.execute(slot))

    def test_property_output_into_fixed_target_fails_without_changing_target(self):
        for slot in ('fa[0]', 'fs.Value', 'fm["key"]'):
            with self.subTest(slot=slot), self.assertRaises(BSLError):
                self.vm.execute(f's.Property("Value", {slot});')
            self.assertEqual(self.vm.execute(slot), Decimal(10))

    def test_reference_type_serialization_dereferences_live_value(self):
        self.vm.execute('''
            Procedure Roundtrip(slot)
                Message(TypeOf(slot));
                slot = ValueFromStringInternal(ValueToStringInternal(slot)) + 1;
                Message(ValueToStringInternal(slot));
            EndProcedure
            Roundtrip(a[0]);
        ''')
        self.assertEqual(self.output, ['Число', '{"N",11}'])

    def test_eval_and_execute_keep_live_slot_and_forwarding(self):
        self.vm.execute('''
            Procedure Dynamic(slot)
                Execute("SetValue(slot);"); Message(Eval("slot"));
                Execute("Execute(""slot = slot + 1;"");");
                Eval("ValCopy(slot)");
            EndProcedure
            Dynamic(s.Value); Message(s.Value);
            Execute("SetValue(a[0]);"); Message(a[0]);
        ''')
        self.assertEqual(self.output, ['99', '100', '99'])

    def test_conditional_and_function_results_remain_temporary_values(self):
        self.vm.execute('''
            SetValue(?(True, a[0], 0)); SetValue((a[0] + 0));
        ''')
        self.assertEqual(self.vm.execute('a[0]'), Decimal(10))

    def test_loops_assign_through_slot_reference(self):
        self.vm.execute('''
            Procedure CountTo(slot) For slot = 1 To 2 Do EndDo; EndProcedure
            CountTo(a[0]);
        ''')
        self.assertEqual(self.vm.execute('a[0]'), Decimal(3))

    def test_wrong_arity_does_not_evaluate_receiver(self):
        self.vm.execute('''
            Var calls; calls = 0;
            Function Owner() calls = calls + 1; Return New Array(1); EndFunction
        ''')
        with self.assertRaises(BSLError):
            self.vm.execute('SetValue(Owner()[0], 2);')
        self.assertEqual(self.vm.execute('calls'), Decimal(0))

    def test_non_collection_index_rejected_without_index_effects(self):
        self.vm.execute('''
            Var calls; calls = 0;
            Function Index() calls = calls + 1; Return 0; EndFunction
        ''')
        with self.assertRaises(BSLError):
            self.vm.execute('SetValue(7[Index()]);')
        self.assertEqual(self.vm.execute('calls'), Decimal(0))

    def test_host_properties_are_explicitly_outside_current_reference_support(self):
        class Host(BSLObject):
            def get_member(self, name):
                raise AssertionError('host getter should not be consulted')
        self.vm.variables['host'] = Host()
        with self.assertRaisesRegex(BSLError, 'только для структуры'):
            self.vm.execute('SetValue(host.value);')

    def test_imported_forwarding_eval_execute_and_exception(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            (root / 'inner.bsl').write_text('''
                Procedure Change(slot) Export
                    Execute("slot = Eval(""slot + 1"");");
                    Raise "native-style-stop";
                EndProcedure
            ''', encoding='utf-8-sig')
            (root / 'outer.bsl').write_text('''// #import inner.bsl
                Procedure Forward(slot) Export inner.Change(slot); EndProcedure
            ''', encoding='utf-8-sig')
            self.vm.execute('// #import outer.bsl\nTry outer.Forward((s.Value)); '
                            'Except caught = True; EndTry;', str(root / 'main.bsl'))
            self.assertEqual(self.vm.execute('s.Value'), Decimal(11))
            self.assertTrue(self.vm.execute('caught'))
            self.assertIsNone(self.vm.locals)

    def test_local_binding_keeps_original_owner_when_caller_variable_is_rebound(self):
        # Explicit local behavior only: receiver replacement was not native-probed.
        self.vm.execute('''
            Procedure Rebind(slot, owner)
                owner = New Array(1); slot = 99;
            EndProcedure
            original = a; Rebind(a[0], a);
        ''')
        self.assertEqual(self.vm.execute('original[0]'), Decimal(99))
        self.assertIsNone(self.vm.execute('a[0]'))

    def test_local_slot_revalidates_bounds_after_structural_mutation(self):
        # Deliberately no promise of native slot lifetime after deletion/clear.
        self.vm.execute('Procedure ClearThenWrite(slot, Val owner) '
                        'owner.Clear(); slot = 99; EndProcedure')
        with self.assertRaises(BSLError):
            self.vm.execute('ClearThenWrite(a[0], a);')
        self.assertEqual(self.vm.execute('a.Count()'), Decimal(0))
        self.assertIsNone(self.vm.locals)


if __name__ == '__main__':
    unittest.main()
