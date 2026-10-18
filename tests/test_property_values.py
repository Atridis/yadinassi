"""Documented intersection copy; optional selection lists are not implemented."""
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
                     'target, New Array()', 'New FixedStructure(target), source',
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

    def test_arity_and_unsupported_optional_arguments(self):
        for args in ('', 'target', 'target, source, "Имя"',
                     'target, source, Undefined', 'target, source, , "Имя"',
                     'target, source, Undefined, "Имя"'):
            with self.assertRaises(BSLError):
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
                        'FillPropertyValues(Arg("a", target), Arg("b", source));')
        self.assertEqual(self.vm.execute('order'), 'ab')
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
        for target, source in ((Hostile(), BSLStructure()), (BSLStructure(), Hostile())):
            with self.assertRaises(TypeError):
                fill_property_values(target, source)

    def test_user_routine_can_shadow_one_alias(self):
        self.vm.execute('Function FillPropertyValues() Return 7; EndFunction; '
                        'value = FillPropertyValues(); ЗаполнитьЗначенияСвойств(target, source);')
        self.assertEqual(self.vm.execute('value'), Decimal(7))
        self.assertEqual(self.vm.execute('target.Имя'), 'Я😀')
