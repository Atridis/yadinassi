"""Static New member syntax, independently of constructed runtime values.

The owner's native values fixture rejects types-extra.syntax.array-direct,
array-parentheses and description-parentheses, while array-receiver succeeds.
The original TypeDescription probes also reject direct methods/properties.
Functional New(...) has no corresponding native observation in that fixture.
"""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse, parse_expression, parse_fragment
from yadinassi.type_qualifiers import BSLDateFractions
from yadinassi.values import BSLArray


# Every built-in constructor, with a valid instance and useful member read.
CONSTRUCTORS = (
    ('Array', 'Массив', '()', 'Count()', Decimal(0)),
    ('Structure', 'Структура', '()', 'Count()', Decimal(0)),
    ('Map', 'Соответствие', '()', 'Count()', Decimal(0)),
    ('FixedArray', 'ФиксированныйМассив', '(New Array)', 'Count()', Decimal(0)),
    ('FixedStructure', 'ФиксированнаяСтруктура', '(New Structure)', 'Count()', Decimal(0)),
    ('FixedMap', 'ФиксированноеСоответствие', '(New Map)', 'Count()', Decimal(0)),
    ('NumberQualifiers', 'КвалификаторыЧисла', '(5, 2)', 'Digits', Decimal(5)),
    ('StringQualifiers', 'КвалификаторыСтроки', '(3)', 'Length', Decimal(3)),
    ('DateQualifiers', 'КвалификаторыДаты', '(DateFractions.Date)',
     'DateFractions', BSLDateFractions.DATE),
    ('BinaryDataQualifiers', 'КвалификаторыДвоичныхДанных', '(8)', 'Length', Decimal(8)),
    ('TypeDescription', 'ОписаниеТипов', '("String")', 'ContainsType(Type("String"))', True),
)


def quote(text):
    return '"' + text.replace('"', '""') + '"'


class ConstructorMemberSyntaxTests(unittest.TestCase):
    def test_all_static_constructor_names_reject_member_methods_and_properties(self):
        for en, ru, arguments, member, _ in CONSTRUCTORS:
            for keyword, name in (('New', en), ('Новый', ru), ('nEw', en.swapcase())):
                for suffix in ('', '()', arguments):
                    for access in (member, 'MissingProperty', 'MissingMethod()'):
                        expression = f'{keyword} {name}{suffix}.{access}'
                        with self.subTest(expression=expression), self.assertRaises(BSLError):
                            parse_expression(expression)

    def test_nested_grouping_does_not_enable_constructor_member_access(self):
        for en, _, arguments, member, _ in CONSTRUCTORS:
            for depth in (1, 2, 4):
                expression = '(' * depth + f'New {en}{arguments}' + ')' * depth + '.' + member
                with self.subTest(expression=expression), self.assertRaises(BSLError):
                    parse_expression(expression)

    def test_rule_does_not_depend_on_registered_type_or_member(self):
        for expression in ('New UnregisteredType.Property',
                           '(New UnregisteredType()).Method()',
                           'New Array().Execute("x = 1")'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                parse_expression(expression)

    def test_error_points_at_member_separator(self):
        expression = '\n (New Array()).Count()'
        with self.assertRaises(BSLError) as caught:
            parse_expression(expression, 'constructor.bsl')
        self.assertEqual(caught.exception.source, 'constructor.bsl')
        self.assertEqual(caught.exception.line, 2)
        self.assertEqual(caught.exception.column, expression.splitlines()[1].index('.') + 1)
        self.assertNotIsInstance(caught.exception, BSLRuntimeError)

    def test_all_parser_entry_points_reject_static_member_access(self):
        for parser, source in (
            (parse_expression, '(New Array()).Count()'),
            (parse, 'x = New Array().Count();'),
            (parse_fragment, 'x = New Array().Count();'),
        ):
            with self.subTest(parser=parser.__name__), self.assertRaises(BSLError):
                parser(source)

    def test_module_syntax_error_precedes_all_effects_even_in_unreachable_code(self):
        vm = Interpreter()
        vm.execute('saved = 0;')
        for body in ('x = New Array().Count();',
                     'If False Then x = (New Array()).Count(); EndIf;',
                     'Try x = New Array().Count(); Except saved = 2; EndTry;',
                     'Function Uncalled() Return New Array().Count(); EndFunction'):
            with self.subTest(body=body), self.assertRaises(BSLError):
                vm.execute('saved = 1; ' + body)
            self.assertEqual(vm.execute('saved'), Decimal(0))

    def test_constructor_and_argument_are_not_evaluated_on_syntax_error(self):
        vm = Interpreter()
        calls = []
        vm.register_function('Argument', lambda: calls.append('argument'))
        vm.register_type('Probe', lambda argument: calls.append('constructor'))
        with self.assertRaises(BSLError):
            vm.execute('New Probe(Argument()).Missing')
        self.assertEqual(calls, [])

    def test_eval_rejects_direct_and_grouped_static_constructors(self):
        vm = Interpreter()
        for en, _, arguments, member, _ in CONSTRUCTORS:
            for wrapped in (f'New {en}{arguments}', f'(New {en}{arguments})'):
                expression = wrapped + '.' + member
                for evaluate in ('Eval', 'Вычислить'):
                    vm.execute('saved = 17; caught = False;')
                    vm.execute(f'Try saved = {evaluate}({quote(expression)}); '
                               'Except caught = True; EndTry;')
                    with self.subTest(expression=expression, evaluate=evaluate):
                        self.assertTrue(vm.execute('caught'))
                        self.assertEqual(vm.execute('saved'), Decimal(17))
        self.assertEqual(vm.execute('Eval("1 + 2")'), Decimal(3))

    def test_execute_rejects_before_fragment_side_effects(self):
        vm = Interpreter()
        vm.execute('saved = 0; caught = False;')
        fragment = 'saved = 1; x = (New Array()).Count();'
        vm.execute(f'Try Execute({quote(fragment)}); Except caught = True; EndTry;')
        self.assertTrue(vm.execute('caught'))
        self.assertEqual(vm.execute('saved'), Decimal(0))

    def test_all_constructed_values_support_members_through_receivers(self):
        vm = Interpreter()
        for en, ru, arguments, member, expected in CONSTRUCTORS:
            for keyword, name in (('New', en), ('Новый', ru)):
                vm.execute(f'value = {keyword} {name}{arguments};')
                for receiver in ('value', '(value)', '((value))'):
                    with self.subTest(name=name, receiver=receiver):
                        self.assertEqual(vm.execute(f'{receiver}.{member}'), expected)

    def test_factory_function_results_keep_member_access(self):
        vm = Interpreter()
        vm.execute('''
            Function Make() Return New Array; EndFunction
            Function Identity(value) Return value; EndFunction
            Function Description() Return New TypeDescription("String"); EndFunction
        ''')
        vm.register_function('HostFactory', BSLArray)
        for expression in ('Make().Count()', '(Make()).Count()',
                           'Identity(New Array).Count()', 'HostFactory().Count()',
                           'Eval("New Array").Count()',
                           'ValueFromStringInternal(ValueToStringInternal(New Array)).Count()'):
            with self.subTest(expression=expression):
                self.assertEqual(vm.execute(expression), Decimal(0))
        self.assertTrue(vm.execute('Description().ContainsType(Type("String"))'))
        self.assertEqual(vm.execute('Description().Types().Count()'), Decimal(1))
        self.assertEqual(vm.execute('Description().StringQualifiers.Length'), Decimal(0))

    def test_functional_new_behavior_is_unchanged_pending_native_evidence(self):
        # Preservation of the existing interpreter behavior, not a claim that
        # functional New member chaining has been verified on native 1C.
        vm = Interpreter()
        for expression in ('New("Array").Count()', '(New("Array")).Count()',
                           'New(Type("Array"), New Array).Count()'):
            with self.subTest(expression=expression):
                self.assertEqual(vm.execute(expression), Decimal(0))


if __name__ == '__main__':
    unittest.main()
