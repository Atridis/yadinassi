"""Native-backed scalar observations and explicit unmeasured-scope guards.

These unit assertions transcribe observed values, not fabricated native golden
streams. Constructors/copy qualifiers additionally follow the official object
reference. Ambiguous union conversions remain guarded; fixed String defaults
have dedicated native-backed tests.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
from itertools import permutations
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.dates import BSLDate, MAX_TICKS, date, shift_date
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import (
    BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
    BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers,
    BSLStringQualifiers,
)
from yadinassi.values import BSLArray, BSLFixedArray, BSLType, HostFunction, NULL


D = Decimal
TD = BSLTypeDescription
NQ = BSLNumberQualifiers
SQ = BSLStringQualifiers
DQ = BSLDateQualifiers
BQ = BSLBinaryDataQualifiers


def array(*items):
    result = BSLArray()
    result.items = list(items)
    return result


class DescriptionConstructionTests(unittest.TestCase):
    def test_empty_undefined_strings_and_bilingual_names(self):
        for args in ((), (None,), ('',), ('Undefined',), ('Неопределено',)):
            with self.subTest(args=args):
                description = TD(*args)
                self.assertEqual(description.types, ())
                self.assertEqual(str(description), '')
                self.assertEqual(description, TD())
        self.assertEqual(TD(' Число , Строка '), TD('String,Number'))
        self.assertEqual(TD('nUmBeR,сТрОкА'), TD('Number,String'))
        self.assertEqual(str(TD('Null')), 'Null')

    def test_order_dedup_and_array_isolation(self):
        names = ('Boolean', 'String', 'Date', 'Number')
        ordered = (BSLType.BOOLEAN, BSLType.STRING, BSLType.DATE, BSLType.NUMBER)
        for order in permutations(names):
            with self.subTest(order=order):
                self.assertEqual(TD(','.join(order)).types, ordered)
        source = array(BSLType.STRING, BSLType.NUMBER, BSLType.STRING)
        description = TD(source)
        source.items.clear()
        self.assertEqual(description.types, (BSLType.STRING, BSLType.NUMBER))
        first, second = description.get_types(), description.get_types()
        self.assertIs(type(first), BSLArray)
        self.assertIsNot(first, second)
        first.items.clear()
        first.add(BSLType.DATE)
        self.assertEqual(second.items, [BSLType.STRING, BSLType.NUMBER])
        self.assertEqual(description.get_types().items, second.items)

    def test_documented_copy_add_remove_and_qualifier_preservation(self):
        source = TD('String,Number', NQ(D(5), D(2)))
        clone = TD(source)
        changed = TD(source, 'Date', 'String')
        self.assertEqual(clone, source)
        self.assertIsNot(clone, source)
        self.assertEqual(changed.types, (BSLType.DATE, BSLType.NUMBER))
        self.assertEqual(str(changed), 'Дата, Число')
        self.assertEqual(changed.number_qualifiers.digits, D(5))
        override = TD(source, None, None, NQ(D(3), D(1)))
        self.assertEqual(override.number_qualifiers.digits, D(3))
        self.assertEqual(override.number_qualifiers.fraction_digits, D(1))
        self.assertEqual(source.number_qualifiers.digits, D(5))
        self.assertNotEqual(override, source)

    def test_structural_equality_is_independent_of_qualifier_object_identity(self):
        left = TD('Number', NQ(D(5), D(2)))
        right = TD('Number', NQ(D(5), D(2)))
        self.assertIsNot(left.number_qualifiers, right.number_qualifiers)
        self.assertEqual(left, right)
        self.assertEqual(hash(left), hash(right))
        self.assertNotEqual(left, TD('Number', NQ(D(6), D(2))))
        self.assertNotEqual(left, TD('Number', NQ(D(5), D(1))))
        self.assertNotEqual(left, TD('Number', NQ(D(5), D(2), BSLAllowedSign.NONNEGATIVE)))
        self.assertNotEqual(left, 'Число')
        self.assertNotEqual(left, None)

    def test_supplement_scalar_properties_and_ignored_binary_qualifier(self):
        for description in (TD(), TD('Number,String,Date,Boolean')):
            self.assertEqual(description.number_qualifiers.digits, D(0))
            self.assertEqual(description.number_qualifiers.fraction_digits, D(0))
            self.assertIs(description.number_qualifiers.allowed_sign, BSLAllowedSign.ANY)
            self.assertEqual(description.string_qualifiers.length, D(0))
            self.assertIs(description.string_qualifiers.allowed_length, BSLAllowedLength.VARIABLE)
            self.assertIs(description.date_qualifiers.date_fractions, BSLDateFractions.DATE_TIME)
            self.assertEqual(description.binary_data_qualifiers.length, D(0))
            self.assertIs(description.binary_data_qualifiers.allowed_length, BSLAllowedLength.VARIABLE)
        supplied = BQ(D(8), BSLAllowedLength.FIXED)
        description = TD('Number,String,Date', NQ(D(5), D(2), BSLAllowedSign.NONNEGATIVE),
                         SQ(D(4), BSLAllowedLength.FIXED), DQ(BSLDateFractions.TIME), supplied)
        self.assertEqual(description.number_qualifiers.digits, D(5))
        self.assertEqual(description.number_qualifiers.fraction_digits, D(2))
        self.assertIs(description.number_qualifiers.allowed_sign, BSLAllowedSign.NONNEGATIVE)
        self.assertEqual(description.string_qualifiers.length, D(4))
        self.assertIs(description.string_qualifiers.allowed_length, BSLAllowedLength.FIXED)
        self.assertIs(description.date_qualifiers.date_fractions, BSLDateFractions.TIME)
        self.assertEqual(description.binary_data_qualifiers.length, D(0))
        self.assertIs(description.binary_data_qualifiers.allowed_length, BSLAllowedLength.VARIABLE)
        self.assertEqual(supplied.length, D(8))
        self.assertIs(supplied.allowed_length, BSLAllowedLength.FIXED)
        self.assertEqual(TD(description), description)

    def test_members_are_bilingual_case_insensitive_and_read_only(self):
        description = TD('Number,String,Date', NQ(D(5), D(2)), SQ(D(4)),
                         DQ(BSLDateFractions.TIME), BQ(D(8)))
        for english, russian, expected in (
                ('NumberQualifiers', 'КвалификаторыЧисла', description.number_qualifiers),
                ('StringQualifiers', 'КвалификаторыСтроки', description.string_qualifiers),
                ('DateQualifiers', 'КвалификаторыДаты', description.date_qualifiers),
                ('BinaryDataQualifiers', 'КвалификаторыДвоичныхДанных', description.binary_data_qualifiers)):
            for name in (english, russian, english.upper(), russian.upper()):
                self.assertIs(description.get_member(name), expected)
                with self.assertRaises(ValueError):
                    description.set_member(name, None)
        for name in ('Types', 'Типы', 'ContainsType', 'СодержитТип',
                     'AdjustValue', 'ПривестиЗначение'):
            self.assertIs(type(description.get_member(name)), HostFunction)
        for name in ('types', 'number_qualifiers', '__dict__', '__class__', 'items'):
            if name == 'types':
                continue  # Deliberately exposed as the BSL Types method.
            with self.assertRaises(ValueError):
                description.get_member(name)
        with self.assertRaises(FrozenInstanceError):
            description.types = ()
        with self.assertRaises(FrozenInstanceError):
            description.number_qualifiers = NQ()

    def test_contains_type_uses_exact_type_argument(self):
        description = TD('String,Number')
        self.assertIs(description.contains_type(BSLType.STRING), True)
        self.assertIs(description.contains_type(BSLType.DATE), False)
        self.assertIs(description.contains_type(BSLType.ARRAY), False)
        for value in ('String', D(0), None, False, NULL, []):
            with self.subTest(value=value), self.assertRaises(TypeError):
                description.contains_type(value)
        with self.assertRaises(TypeError):
            description.contains_type()

    def test_invalid_and_out_of_scope_constructors_are_atomic(self):
        bad_sources = ('Unknown', 'BinaryData', 'Array', 'Null,Number',
                       'Number,,String', [], {}, D(1), True, NULL,
                       BSLType.STRING, array('String'), array(BSLType.ARRAY),
                       BSLFixedArray(array(BSLType.STRING)))
        for source in bad_sources:
            with self.subTest(source=source), self.assertRaises((TypeError, ValueError)):
                TD(source)
        for args in (('Number', SQ()), ('String', None, NQ()),
                     ('Date', None, None, BQ()), ('String', None, None, None, SQ()),
                     ('Number', None, None, None, None, None),
                     (TD('String'), 'Number', 'Number'),
                     (TD('String'), None, None, None, None, None, None, None)):
            with self.subTest(args=args), self.assertRaises((TypeError, ValueError)):
                TD(*args)
        source = TD('String,Number')
        before = source.types
        with self.assertRaises(ValueError):
            TD(source, 'NoSuchType')
        self.assertEqual(source.types, before)

    def test_nondefault_qualifiers_for_absent_scalar_types_are_explicitly_unsupported(self):
        sources = [('String', NQ(D(5), D(2))),
                   ('String', NQ(D(0), D(0), BSLAllowedSign.NONNEGATIVE)),
                   ('Number', None, SQ(D(4))),
                   ('Number', None, None, DQ(BSLDateFractions.DATE)),
                   (TD('Number', NQ(D(5), D(2))), None, 'Number'),
                   (TD('String', None, SQ(D(4))), None, 'String'),
                   (TD('Date', None, None, DQ(BSLDateFractions.TIME)), None, 'Date')]
        for args in sources:
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, 'при отсутствии'):
                TD(*args)
        self.assertEqual(TD('Boolean', NQ(), SQ(), DQ()), TD('Boolean'))
        # An explicit reset removes the unmeasured orphaned qualifier state.
        source = TD('String', None, SQ(D(4)))
        self.assertEqual(TD(source, None, 'String', None, SQ()), TD())
        self.assertEqual(source.string_qualifiers.length, D(4))

    def test_untrusted_host_objects_cannot_invoke_equality_hash_or_conversion_hooks(self):
        class HostileMeta(type):
            def __eq__(cls, other):
                raise AssertionError('host metaclass equality invoked')

            def __hash__(cls):
                raise AssertionError('host metaclass hashing invoked')

        class Hostile(metaclass=HostileMeta):
            def __eq__(self, other):
                raise AssertionError('host equality invoked')

            def __hash__(self):
                raise AssertionError('host hashing invoked')

            def __str__(self):
                raise AssertionError('host string conversion invoked')

        value = Hostile()
        for constructor_args in ((value,), (array(value),), ('Number', value),
                                 ('String', None, value), (TD(), value)):
            with self.assertRaises((ValueError, TypeError)):
                TD(*constructor_args)
        with self.assertRaises(TypeError):
            TD('Number').contains_type(value)
        for names in ('', 'Number', 'String', 'Date', 'Boolean', 'Null'):
            with self.assertRaises(ValueError):
                TD(names).adjust_value(value)

    def test_constructor_resource_budgets_are_explicit(self):
        for source in (' ' * 4097, array(*([BSLType.STRING] * 4097))):
            with self.assertRaisesRegex(ValueError, 'ресурсов Yadinassi'):
                TD(source)


class DescriptionAdjustmentTests(unittest.TestCase):
    def test_native_scalar_conversion_observations(self):
        cases = [('Number', '12.5', D('12.5')), ('Number', 'abc', D(0)),
                 ('Number', True, D(1)), ('Number', None, D(0)),
                 ('String', D('12.5'), '12,5'), ('String', False, 'Нет'),
                 ('String', None, ''), ('Date', '20240229123456', date('20240229123456')),
                 ('Date', D(1), BSLDate(0)), ('Boolean', 'True', True),
                 ('Boolean', D(0), False), ('Boolean', D(2), True),
                 ('Boolean', None, False), ('', D(12), D(12)),
                 ('Null', D(12), NULL), ('Undefined,Number', '12', D(12))]
        for name, value, expected in cases:
            with self.subTest(name=name, value=value):
                result = TD(name).adjust_value(value)
                self.assertIs(type(result), type(expected))
                self.assertEqual(result, expected)

    def test_native_union_matching_values_and_conversion_order(self):
        cases = [('Number,String', '12', '12'), ('String,Number', D(12), D(12)),
                 ('Number,Date', '20240229', date('20240229')),
                 ('Date,Number', '20240229', date('20240229')),
                 ('Number,String', True, 'Да'), ('String,Number', True, 'Да')]
        for names, value, expected in cases:
            with self.subTest(names=names, value=value):
                self.assertEqual(TD(names).adjust_value(value), expected)
        all_types = TD('Number,String,Boolean,Date')
        for value in (D('12.345'), '12', False, date('20240229')):
            self.assertEqual(all_types.adjust_value(value), value)

    def test_native_qualified_number_rounding_and_saturation(self):
        description = TD('Number', NQ(D(5), D(2)))
        for source, expected in (('1.234', '1.23'), ('1.235', '1.24'),
                                 ('1.245', '1.25'), ('-1.245', '-1.25'),
                                 ('-1.235', '-1.24'), ('999.99', '999.99'),
                                 ('1000', '999.99'), ('999.995', '999.99'),
                                 ('-1000', '-999.99')):
            with self.subTest(source=source):
                self.assertEqual(description.adjust_value(D(source)), D(expected))
        nonnegative = TD('Number', NQ(D(5), D(2), BSLAllowedSign.NONNEGATIVE))
        self.assertEqual(nonnegative.adjust_value(D('-1.235')), D(0))
        # Explicit implementation checks around the measured rounding rule.
        for source, expected in (('0.005', '0.01'), ('-0.005', '-0.01'),
                                 ('0.0049', '0'), ('-0.0049', '0')):
            self.assertEqual(description.adjust_value(D(source)), D(expected))
        self.assertEqual(TD('Number').adjust_value(D('123456789012345678901234567890123456789')),
                         D('123456789012345678901234567890123456789'))

    def test_qualified_decimal_operations_do_not_use_the_host_context(self):
        description = TD('Number', NQ(D(39), D(2)))
        source = D('1234567890123456789012345678901234567.895')
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.traps[InvalidOperation] = True
            context.clear_flags()
            self.assertEqual(description.adjust_value(source), D('1234567890123456789012345678901234567.90'))
            self.assertEqual(description.adjust_value(D('1e999999999')), D('9999999999999999999999999999999999999.99'))
            self.assertEqual(description.adjust_value(D('1e-999999999')), D(0))
            self.assertEqual(description.adjust_value('abc'), D(0))
            self.assertFalse(any(context.flags.values()))

    def test_native_string_limits_preserve_utf16_units_and_spaces(self):
        cases = [(SQ(D(4)), 'ab', 'ab'),
                 (SQ(D(4), BSLAllowedLength.FIXED), 'ab', 'ab  '),
                 (SQ(D(4), BSLAllowedLength.FIXED), 'abcdef', 'abcd'),
                 (SQ(D(2)), 'Я😀Z', 'Я\ud83d'),
                 (SQ(D(3)), 'Я😀Z', 'Я😀'),
                 (SQ(D(3)), 'a  b', 'a  ')]
        for qualifier, value, expected in cases:
            with self.subTest(qualifier=qualifier, value=value):
                self.assertEqual(TD('String', None, qualifier).adjust_value(value), expected)
        fixed = TD('String', None, SQ(D(4), BSLAllowedLength.FIXED))
        self.assertEqual(fixed.adjust_value('Я😀'), 'Я😀 ')
        self.assertEqual(fixed.adjust_value('\ud83d'), '\ud83d   ')

    def test_native_date_fraction_adjustments_keep_only_confirmed_ticks(self):
        original = date('20240229123456')
        source = shift_date(original, D('0.1234'))
        expected = ((BSLDateFractions.DATE, date('20240229')),
                    (BSLDateFractions.TIME, date('00010101123456')),
                    (BSLDateFractions.DATE_TIME, source))
        for fraction, target in expected:
            with self.subTest(fraction=fraction):
                result = TD('Date', None, None, DQ(fraction)).adjust_value(source)
                self.assertEqual(result, target)
        self.assertEqual(source.ticks, original.ticks + 1234)
        for boundary in (BSLDate(0, True), BSLDate(MAX_TICKS, True)):
            for names in ('', 'Date', 'String'):
                with self.assertRaises(ValueError):
                    TD(names).adjust_value(boundary)

    def test_matching_union_values_still_apply_qualifiers(self):
        description = TD('String,Number,Date', NQ(D(5), D(2)), SQ(D(2)), DQ(BSLDateFractions.DATE))
        self.assertEqual(description.adjust_value(D('1.235')), D('1.24'))
        self.assertEqual(description.adjust_value('abcd'), 'ab')
        self.assertEqual(description.adjust_value(date('20240229123456')), date('20240229'))

    def test_native_supplement_defaults_are_distinct_from_conversion(self):
        cases = [('Number', D(0)), ('String', ''), ('Date', BSLDate(0)),
                 ('Boolean', False), ('Number,String', None), ('String,Number', None),
                 ('Number,Date', None), ('Undefined,Number', D(0)),
                 ('Null', NULL), ('', None)]
        for names, expected in cases:
            with self.subTest(names=names):
                description = TD(names)
                actual = description.adjust_value()
                self.assertIs(type(actual), type(expected))
                self.assertEqual(actual, expected)
                self.assertEqual(description.get_member('ПривестиЗначение')(), expected)
        self.assertEqual(TD('Number', NQ(D(5), D(2))).adjust_value(), D(0))
        self.assertEqual(TD('Date', None, None, DQ(BSLDateFractions.TIME)).adjust_value(), BSLDate(0))
        self.assertEqual(TD('String', None, SQ(D(4))).adjust_value(), '')

    def test_unmeasured_ambiguous_coercions_remain_explicit(self):
        for names, value in (('Number,Date', True), ('String,Number', None),
                             ('Date,Boolean', '20240229'), ('Boolean', 'unknown'),
                             ('Date', None), ('Number', NULL)):
            with self.subTest(names=names, value=value), self.assertRaisesRegex(ValueError, 'пока не поддерживается'):
                TD(names).adjust_value(value)
        for value in (array(), [], {}, object(), 1, 1.0):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                TD('').adjust_value(value)

    def test_resource_and_nonfinite_guards_do_not_become_default_values(self):
        for value in ('1' * 4097, D('1' * 4097), D('NaN'), D('Infinity')):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                TD('Number').adjust_value(value)
        with self.assertRaisesRegex(ValueError, 'ресурсов Yadinassi'):
            TD('String', None, SQ(D(1))).adjust_value('a' * 1_000_001)


class DescriptionRuntimeTests(unittest.TestCase):
    def test_bilingual_runtime_methods_and_immutable_properties(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute('''
            d = New TypeDescription("String,Number");
            e = Новый ОписаниеТипов("Число,Строка");
            Message(d = e);
            Message(d.ContainsType(Type("String")));
            Message(d.СодержитТип(Тип("Дата")));
            Message(d.AdjustValue(True));
            Message(e.ПривестиЗначение(12));
            a = d.Types(); a.Clear(); a.Add(Type("Date"));
            Message(d.Типы().Count());
            Message(d.StringQualifiers.Length = d.КвалификаторыСтроки.Длина);
        ''')
        self.assertEqual(output, ['Да', 'Да', 'Нет', 'Да', '12', '2', 'Да'])
        for statement in ('d.StringQualifiers = New StringQualifiers(2)',
                          'd.NumberQualifiers.Digits = 2',
                          'd.ContainsType("String")', 'd.Types(1)',
                          'd.AdjustValue(1, 2)', 'd.__dict__'):
            with self.subTest(statement=statement), self.assertRaises(BSLError):
                vm.execute(statement)
        self.assertEqual(vm.execute('d.Types().Count()'), D(2))
        self.assertEqual(vm.execute('d.StringQualifiers.Length'), D(0))

    def test_supplement_defaults_through_bilingual_runtime_calls(self):
        vm = Interpreter()
        for names, expected in [('Number', D(0)), ('String', ''), ('Date', BSLDate(0)),
                                ('Boolean', False), ('Number,String', None),
                                ('Date,Number', None), ('Undefined,Number', D(0)),
                                ('Null', NULL), ('', None)]:
            vm.execute(f'd = New TypeDescription("{names}");')
            self.assertEqual(vm.execute('d.AdjustValue()'), expected)
            self.assertEqual(vm.execute('d.ПривестиЗначение()'), expected)

    def test_constructor_positional_holes_only_select_optional_qualifiers(self):
        vm = Interpreter()
        vm.execute('''
            s = New TypeDescription("String", , New StringQualifiers(4, AllowedLength.Fixed));
            d = Новый ОписаниеТипов("Дата", , , Новый КвалификаторыДаты(ЧастиДаты.Дата));
            n = New TypeDescription("Number", New NumberQualifiers(5, 2));
            copy = New TypeDescription(n, , , New NumberQualifiers(3, 1));
        ''')
        self.assertEqual(vm.execute('s.AdjustValue("ab")'), 'ab  ')
        self.assertEqual(vm.execute('d.AdjustValue(Date("20240229123456"))'), date('20240229'))
        self.assertEqual(vm.execute('copy.AdjustValue(99.95)'), D('99.9'))
        self.assertEqual(vm.execute('n.NumberQualifiers.Digits'), D(5))
        self.assertEqual(vm.execute('copy.NumberQualifiers.Digits'), D(3))
        for expression in ('New NumberQualifiers(5, )',
                           'New StringQualifiers(4, )', 'New Array(,)',
                           's.AdjustValue(,)', 's.ContainsType(,)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute(expression)

    def test_argument_evaluation_once_and_dynamic_constructor_parameters(self):
        vm = Interpreter()
        vm.execute('''
            Var calls;
            Function SourceTypes()
                calls = calls + 1;
                Return "Number";
            EndFunction
            Function NumberSettings()
                calls = calls + 1;
                Return New NumberQualifiers(5, 2);
            EndFunction
            calls = 0;
            d = New TypeDescription(SourceTypes(), NumberSettings());
        ''')
        self.assertEqual(vm.execute('calls'), D(2))
        self.assertEqual(vm.execute('d.AdjustValue(1.245)'), D('1.25'))
        vm.execute('''
            args = New Array;
            args.Add("String"); args.Add(Undefined);
            args.Add(New StringQualifiers(3));
            dynamic = New("TypeDescription", args);
        ''')
        self.assertEqual(vm.execute('dynamic.AdjustValue("abcdef")'), 'abc')


if __name__ == '__main__':
    unittest.main()
