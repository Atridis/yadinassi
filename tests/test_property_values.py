"""Native-backed intersection, fixed targets, and bounded selection lists."""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.structures import BSLStructure, BSLFixedStructure, fill_property_values


class PropertyValuesTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('target = New Structure("Имя,Количество,Оставить", "старое", 0, 9); '
                        'source = New Structure("иМя,Количество,Лишнее", "Я😀", 3, 42);')

    def test_aliases_case_and_intersection(self):
        for name in ('ЗаполнитьЗначенияСвойств', 'FillPropertyValues',
                     'зАпОлНиТьЗнАчЕнИяСвОйСтВ', 'fIlLpRoPeRtYvAlUeS'):
            self.setUp()
            self.vm.execute(f'{name}(target, source);')
            self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
            self.assertEqual(self.vm.execute('target.Количество'), Decimal(3))
            self.assertEqual(self.vm.execute('target.Оставить'), Decimal(9))
            self.assertEqual(self.vm.execute('target.Count()'), Decimal(3))
            self.assertFalse(self.vm.execute('target.Property("Лишнее")'))
            self.assertEqual([p.key for p in self.vm.variables['target']],
                             ['Имя', 'Количество', 'Оставить'])
            self.assertEqual(self.vm.execute('source.Лишнее'), Decimal(42))

    def test_fixed_source_and_undefined_copy(self):
        self.vm.execute('source.Имя = Undefined; fixed = New FixedStructure(source); '
                        'FillPropertyValues(target, fixed);')
        self.assertIsNone(self.vm.execute('target.Имя'))
        self.assertEqual(self.vm.execute('target.Количество'), Decimal(3))
        self.assertEqual(self.vm.execute('fixed.Count()'), Decimal(3))

    def test_empty_disjoint_and_self_copy(self):
        self.vm.execute('FillPropertyValues(target, New Structure()); '
                        'FillPropertyValues(New Structure(), source); '
                        'FillPropertyValues(target, New Structure("Other", 1)); '
                        'FillPropertyValues(target, target);')
        self.assertEqual(self.vm.execute('target.Имя'), 'старое')
        self.assertEqual(self.vm.execute('target.Count()'), Decimal(3))

    def test_shallow_copy_preserves_references_and_aliases(self):
        self.vm.execute('items = New Array(); items.Add("Я"); '
                        'source = New Structure("a,b", items, items); '
                        'target = New Structure("a,b"); alias = target; '
                        'FillPropertyValues(target, source); target.a.Add(7);')
        self.assertTrue(self.vm.execute('(target.a = source.a)'))
        self.assertTrue(self.vm.execute('(target.a = target.b)'))
        self.assertTrue(self.vm.execute('(alias = target)'))
        self.assertEqual(self.vm.execute('source.a.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('alias.b[1]'), Decimal(7))

    def test_cycles_remain_references(self):
        self.vm.execute('source = New Structure("self"); source.self = source; '
                        'target = New Structure("self"); FillPropertyValues(target, source);')
        self.assertTrue(self.vm.execute('(target.self = source)'))
        self.assertFalse(self.vm.execute('(target.self = target)'))

    def test_existing_iteration_is_not_composition_change(self):
        self.vm.execute('count = 0; For Each pair In target Do '
                        'FillPropertyValues(target, source); count = count + 1; EndDo;')
        self.assertEqual(self.vm.execute('count'), Decimal(3))

    def test_validation_before_mutation_and_recovery(self):
        for args in ('target, 1', 'target, Undefined', 'target, New Map()',
                     'target, New Array()',
                     '1, source', 'Undefined, source', 'New Map(), source'):
            self.setUp()
            before = self.vm.execute('ValueToStringInternal(target)')
            with self.assertRaises(BSLError):
                self.vm.execute('FillPropertyValues(' + args + ');')
            self.assertEqual(self.vm.execute('ValueToStringInternal(target)'), before)
            self.vm.execute('Try FillPropertyValues(' + args + '); Except caught = True; EndTry; '
                            'FillPropertyValues(target, source);')
            self.assertTrue(self.vm.execute('caught'))
            self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')

    def test_fixed_target_is_accepted_without_mutation(self):
        self.vm.execute('fixed = New FixedStructure(target); alias = fixed; '
                        'FillPropertyValues(fixed, source); '
                        'FillPropertyValues(fixed, New FixedStructure(source));')
        self.assertEqual(self.vm.execute('fixed.Имя'), 'старое')
        self.assertEqual(self.vm.execute('fixed.Количество'), Decimal(0))
        self.assertTrue(self.vm.execute('(fixed = alias)'))
        self.assertEqual(self.vm.execute('fixed.Count()'), Decimal(3))

    def test_explicit_undefined_and_omitted_optional_arguments(self):
        for suffix in (', Undefined', ', Undefined, Undefined', ', , Undefined'):
            self.setUp()
            self.vm.execute('FillPropertyValues(target, source' + suffix + ');')
            self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
            self.assertEqual(self.vm.execute('target.Количество'), Decimal(3))

    def test_selected_copy_preserves_other_properties(self):
        for source in ('source', 'New FixedStructure(source)'):
            self.setUp()
            self.vm.execute(f'FillPropertyValues(target, {source}, "иМя");')
            self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
            self.assertEqual(self.vm.execute('target.Количество'), Decimal(0))
            self.assertEqual([p.key for p in self.vm.variables['target']],
                             ['Имя', 'Количество', 'Оставить'])

    def test_multiple_selected_properties_and_duplicates(self):
        self.vm.execute('FillPropertyValues(target, source, "Количество,Имя,иМя");')
        self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
        self.assertEqual(self.vm.execute('target.Количество'), Decimal(3))
        self.assertEqual(self.vm.execute('target.Оставить'), Decimal(9))

    def test_missing_selected_property_keeps_prior_assignments(self):
        for missing in ('НетТакогоСвойства', 'Лишнее', 'Оставить'):
            self.setUp()
            with self.assertRaises(BSLError):
                self.vm.execute(f'FillPropertyValues(target, source, "Имя,{missing},Количество");')
            self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
            self.assertEqual(self.vm.execute('target.Количество'), Decimal(0))
            self.assertEqual(self.vm.execute('target.Count()'), Decimal(3))
            self.assertEqual(self.vm.execute('source.Количество'), Decimal(3))

    def test_missing_first_selected_property_changes_nothing(self):
        with self.assertRaises(BSLError):
            self.vm.execute('FillPropertyValues(target, source, "НетТакогоСвойства,Имя");')
        self.assertEqual(self.vm.execute('target.Имя'), 'старое')

    def test_exclusion_with_omitted_or_undefined_selection(self):
        for selection in ('', 'Undefined'):
            self.setUp()
            self.vm.execute(f'FillPropertyValues(target, source, {selection}, "иМя");')
            self.assertEqual(self.vm.execute('target.Имя'), 'старое')
            self.assertEqual(self.vm.execute('target.Количество'), Decimal(3))
            self.assertEqual(self.vm.execute('target.Оставить'), Decimal(9))

    def test_multiple_exclusions(self):
        self.vm.execute('FillPropertyValues(target, source, Undefined, "Имя,Количество");')
        self.assertEqual(self.vm.execute('target.Имя'), 'старое')
        self.assertEqual(self.vm.execute('target.Количество'), Decimal(0))

    def test_selection_keeps_undefined_and_shallow_references(self):
        self.vm.execute('items = New Array(); source = New Structure("a,b", items, Undefined); '
                        'target = New Structure("a,b", 1, 2); '
                        'FillPropertyValues(target, source, "a,b"); target.a.Add(7);')
        self.assertTrue(self.vm.execute('(source.a = target.a)'))
        self.assertEqual(self.vm.execute('source.a[0]'), Decimal(7))
        self.assertIsNone(self.vm.execute('target.b'))

    def test_arity_and_invalid_list_types(self):
        for args in ('', 'target', 'target, source, 1', 'target, source, True',
                     'target, source, Undefined, New Array()',
                     'target, source, Undefined, Undefined, Undefined',
                     'target, source, ', 'target, source, , ',
                     ', source', 'target, , "Имя"'):
            with self.assertRaises(BSLError):
                self.vm.execute('FillPropertyValues(' + args + ');')
            self.assertEqual(self.vm.execute('target.Имя'), 'старое')

    def test_unverified_list_boundaries_fail_explicitly(self):
        for args in ('target, source, "Имя", "Количество"',
                     'New FixedStructure(target), source, "Имя"',
                     'target, source, ""', 'target, source, " Имя"',
                     'target, source, Undefined, "Лишнее"',
                     'target, source, Undefined, "Оставить"',
                     'target, source, Undefined, "НетТакогоСвойства"'):
            with self.assertRaisesRegex(BSLError, 'пока не поддержива'):
                self.vm.execute('FillPropertyValues(' + args + ');')
            self.assertEqual(self.vm.execute('target.Имя'), 'старое')

    def test_procedure_is_not_expression_and_arguments_not_evaluated(self):
        self.vm.execute('Var count; count = 0; Function Touch() count = count + 1; '
                        'Return New Structure(); EndFunction; saved = 7;')
        for text in ('saved = FillPropertyValues(Touch(), source);',
                     'Message(FillPropertyValues(target, source));',
                     'Eval("FillPropertyValues(target, source)");'):
            with self.assertRaisesRegex(BSLError, 'не возвращает значение'):
                self.vm.execute(text)
        self.assertEqual(self.vm.execute('count'), Decimal(0))
        self.assertEqual(self.vm.execute('saved'), Decimal(7))
        self.assertEqual(self.vm.execute('target.Имя'), 'старое')

    def test_arguments_once_left_to_right(self):
        self.vm.execute('Var order; order = ""; '
                        'Function Arg(Val tag, Val item) order = order + tag; Return item; EndFunction; '
                        'FillPropertyValues(Arg("a", target), Arg("b", source), '
                        'Arg("c", Undefined), Arg("d", "Количество"));')
        self.assertEqual(self.vm.execute('order'), 'abcd')
        self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')

    def test_existing_serialization_both_directions_and_aliases(self):
        self.vm.execute('items = New Array(); items.Add("Я😀"); '
                        'source = New Structure("a,b", items, items); target = New Structure("a,b"); '
                        'source = ValueFromStringInternal(ValueToStringInternal(source)); '
                        'FillPropertyValues(target, source); '
                        'copy = ValueFromStringInternal(ValueToStringInternal(target));')
        self.assertEqual(self.vm.execute('copy.a[0]'), 'Я😀')
        self.assertFalse(self.vm.execute('(copy.a = copy.b)'))
        self.assertEqual(self.vm.execute('ValueToStringInternal(copy)'),
                         self.vm.execute('ValueToStringInternal(target)'))
        self.vm.execute('fixed = New FixedStructure(source); '
                        'FillPropertyValues(target, ValueFromStringInternal(ValueToStringInternal(fixed)));')
        self.assertEqual(self.vm.execute('target.a[0]'), 'Я😀')

    def test_host_subclasses_do_not_invoke_hooks(self):
        class Hostile(BSLStructure):
            def __getattribute__(self, name):
                raise AssertionError('unexpected host hook')
        class HostileFixed(BSLFixedStructure):
            def __getattribute__(self, name):
                raise AssertionError('unexpected host hook')
        for hostile in (Hostile(), HostileFixed()):
            for target, source in ((hostile, BSLStructure()), (BSLStructure(), hostile)):
                with self.assertRaises(TypeError):
                    fill_property_values(target, source)

    def test_host_list_subclasses_do_not_invoke_hooks(self):
        class HostileString(str):
            def split(self, *args):
                raise AssertionError('unexpected host hook')
        target = BSLStructure('a', 1)
        source = BSLStructure('a', 2)
        for properties, exclude in ((HostileString('a'), None),
                                    (None, HostileString('a'))):
            with self.assertRaises(TypeError):
                fill_property_values(target, source, properties, exclude)
            self.assertEqual(target.get('a'), 1)

    def test_user_routine_can_shadow_one_alias(self):
        self.vm.execute('Function FillPropertyValues() Return 7; EndFunction; '
                        'value = FillPropertyValues(); ЗаполнитьЗначенияСвойств(target, source);')
        self.assertEqual(self.vm.execute('value'), Decimal(7))
        self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')


class OmissionDispatchRegressionTests(unittest.TestCase):
    def test_unrelated_method_receiver_not_evaluated_for_omitted_arguments(self):
        vm = Interpreter()
        vm.execute('Var count; count = 0; Function Get() count = count + 1; '
                   'Return New Array(); EndFunction;')
        with self.assertRaises(BSLError):
            vm.execute('Get().Add(, 1);')
        self.assertEqual(vm.execute('count'), Decimal(0))
