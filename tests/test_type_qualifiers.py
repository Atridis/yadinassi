"""Native scalar qualifier observations and explicitly local safety boundaries.

The constructor cases come from the owner's values.bsl types.* checkpoint.
Unsupported-edge/resource tests describe Yadinassi policy, not native outcomes.
Codec and type-registry behavior are exercised separately from this module.
"""

from dataclasses import FrozenInstanceError
from decimal import (Clamped, Decimal, Inexact, Overflow, ROUND_UP, Rounded,
                     Underflow, localcontext)
import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.type_qualifiers import (
    ALLOWED_LENGTHS, ALLOWED_SIGNS, DATE_FRACTIONS,
    BSLAllowedLength, BSLAllowedLengths, BSLAllowedSign, BSLAllowedSigns,
    BSLBinaryDataQualifiers, BSLDateFractions, BSLDateFractionsNamespace,
    BSLDateQualifiers, BSLNumberQualifiers, BSLStringQualifiers,
)
from yadinassi.values import NULL, equal, to_string


ENUM_CASES = (
    (ALLOWED_SIGNS, 'Any', 'Любой', BSLAllowedSign.ANY, 'Любой'),
    (ALLOWED_SIGNS, 'Nonnegative', 'Неотрицательный', BSLAllowedSign.NONNEGATIVE,
     'Неотрицательный'),
    (ALLOWED_LENGTHS, 'Fixed', 'Фиксированная', BSLAllowedLength.FIXED,
     'Фиксированная'),
    (ALLOWED_LENGTHS, 'Variable', 'Переменная', BSLAllowedLength.VARIABLE,
     'Переменная'),
    (DATE_FRACTIONS, 'Date', 'Дата', BSLDateFractions.DATE, 'Дата'),
    (DATE_FRACTIONS, 'Time', 'Время', BSLDateFractions.TIME, 'Время'),
    (DATE_FRACTIONS, 'DateTime', 'ДатаВремя', BSLDateFractions.DATE_TIME,
     'Дата и время'),
)


class QualifierEnumTests(unittest.TestCase):
    def test_namespace_members_are_bilingual_and_case_insensitive(self):
        for namespace, english, russian, member, _ in ENUM_CASES:
            for spelling in (english, russian, english.upper(), russian.lower(),
                             english.swapcase(), russian.swapcase()):
                with self.subTest(spelling=spelling):
                    self.assertIs(namespace.get_member(spelling), member)

    def test_opaque_members_have_native_ordinals_and_presentations(self):
        for family, ordinals in ((BSLAllowedSign, [0, 1]),
                                 (BSLAllowedLength, [0, 1]),
                                 (BSLDateFractions, [1, 2, 3])):
            self.assertEqual([item.value for item in family], ordinals)
        self.assertIs(BSLDateFractions.DATETIME, BSLDateFractions.DATE_TIME)
        for namespace, _, _, member, presentation in ENUM_CASES:
            self.assertEqual(to_string(member), presentation)
            self.assertTrue(equal(member, member))
            for other in (member.value, Decimal(member.value), False, True,
                          None, NULL, presentation, namespace):
                with self.subTest(member=member, other=other):
                    self.assertFalse(equal(member, other))
                    self.assertFalse(equal(other, member))
        self.assertFalse(equal(BSLAllowedSign.ANY, BSLAllowedLength.FIXED))
        self.assertFalse(equal(BSLAllowedSign.NONNEGATIVE, BSLDateFractions.DATE))

    def test_namespace_classes_and_presentations_are_distinct(self):
        for namespace, cls, presentation in (
                (ALLOWED_SIGNS, BSLAllowedSigns, 'ПеречислениеДопустимыйЗнак'),
                (ALLOWED_LENGTHS, BSLAllowedLengths, 'ПеречислениеДопустимаяДлина'),
                (DATE_FRACTIONS, BSLDateFractionsNamespace, 'ПеречислениеЧастиДаты')):
            self.assertIs(type(namespace), cls)
            self.assertEqual(to_string(namespace), presentation)

    def test_namespaces_do_not_guess_unmeasured_iteration_or_reflect_host(self):
        for namespace in (ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS):
            with self.assertRaises(TypeError):
                iter(namespace)
            for name in ('__class__', '__dict__', 'get_member', 'set_member',
                         'name', 'value', 'Count', 'Get', 'items', 'Missing'):
                with self.subTest(namespace=namespace, name=name):
                    with self.assertRaises(ValueError):
                        namespace.get_member(name)
            with self.assertRaises(FrozenInstanceError):
                namespace.extra = 1

    def test_every_namespace_property_is_read_only(self):
        for namespace, english, russian, member, _ in ENUM_CASES:
            for name in (english, russian, 'Missing'):
                with self.assertRaisesRegex(ValueError, 'недоступно для записи'):
                    namespace.set_member(name, None)
            self.assertIs(namespace.get_member(english), member)


class QualifierConstructorTests(unittest.TestCase):
    def test_native_defaults(self):
        number = BSLNumberQualifiers()
        self.assertEqual(number.digits, Decimal(0))
        self.assertEqual(number.fraction_digits, Decimal(0))
        self.assertIs(number.allowed_sign, BSLAllowedSign.ANY)
        for cls in (BSLStringQualifiers, BSLBinaryDataQualifiers):
            value = cls()
            self.assertEqual(value.length, Decimal(0))
            self.assertIs(value.allowed_length, BSLAllowedLength.VARIABLE)
        self.assertIs(BSLDateQualifiers().date_fractions, BSLDateFractions.DATE_TIME)

    def test_native_number_constructor_normalization(self):
        for args, digits, fractions in (
                ((Decimal(-1),), 0, 0),
                ((Decimal('5.9'), Decimal('2.9')), 5, 2),
                ((Decimal(2), Decimal(3)), 2, 2),
                ((Decimal(0), Decimal(2)), 0, 0),
                ((Decimal(38), Decimal(10)), 38, 10),
                ((Decimal(39),), 39, 0),
                (('5', '2'), 5, 2)):
            with self.subTest(args=args):
                value = BSLNumberQualifiers(*args)
                self.assertEqual(value.digits, Decimal(digits))
                self.assertEqual(value.fraction_digits, Decimal(fractions))
                self.assertIs(type(value.digits), Decimal)
                self.assertIs(type(value.fraction_digits), Decimal)
                self.assertIs(value.allowed_sign, BSLAllowedSign.ANY)

    def test_native_configured_number_sign_is_preserved(self):
        value = BSLNumberQualifiers(Decimal(5), Decimal(2), BSLAllowedSign.NONNEGATIVE)
        self.assertEqual((value.digits, value.fraction_digits), (Decimal(5), Decimal(2)))
        self.assertIs(value.allowed_sign, BSLAllowedSign.NONNEGATIVE)

    def test_native_length_constructor_normalization(self):
        for cls in (BSLStringQualifiers, BSLBinaryDataQualifiers):
            for arg, expected in ((Decimal(-1), 0), (Decimal('3.9'), 3), ('3', 3)):
                with self.subTest(cls=cls.__name__, arg=arg):
                    value = cls(arg)
                    self.assertEqual(value.length, Decimal(expected))
                    self.assertIs(type(value.length), Decimal)
                    self.assertIs(value.allowed_length, BSLAllowedLength.VARIABLE)

    def test_native_zero_fixed_normalizes_to_variable(self):
        for cls in (BSLStringQualifiers, BSLBinaryDataQualifiers):
            value = cls(Decimal(0), BSLAllowedLength.FIXED)
            self.assertEqual(value.length, Decimal(0))
            self.assertIs(value.allowed_length, BSLAllowedLength.VARIABLE)
            configured = cls(Decimal(4), BSLAllowedLength.FIXED)
            self.assertEqual(configured.length, Decimal(4))
            self.assertIs(configured.allowed_length, BSLAllowedLength.FIXED)

    def test_native_configured_dates(self):
        for member in BSLDateFractions:
            self.assertIs(BSLDateQualifiers(member).date_fractions, member)

    def test_native_rejected_explicit_undefined_and_numeric_enum_slots(self):
        for factory, args in (
                (BSLNumberQualifiers, (None,)),
                (BSLNumberQualifiers, (Decimal(5), Decimal(2), Decimal(0))),
                (BSLStringQualifiers, (Decimal(3), Decimal(0))),
                (BSLBinaryDataQualifiers, (Decimal(3), Decimal(0))),
                (BSLDateQualifiers, (Decimal(0),))):
            with self.subTest(factory=factory.__name__, args=args), self.assertRaises(TypeError):
                factory(*args)

    def test_native_presentations(self):
        for value, presentation in (
                (BSLNumberQualifiers(5, 2), 'КвалификаторыЧисла'),
                (BSLStringQualifiers(4), 'КвалификаторыСтроки'),
                (BSLBinaryDataQualifiers(4), 'КвалификаторыДвоичныхДанных'),
                (BSLDateQualifiers(), 'КвалификаторыДаты')):
            self.assertEqual(to_string(value), presentation)

    def test_valid_numeric_conversion_ignores_ambient_decimal_context(self):
        args = (Decimal('39.9'), Decimal('10.9'))
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_UP
            context.Emax = 1
            context.Emin = -1
            for signal in (Inexact, Rounded, Overflow, Underflow, Clamped):
                context.traps[signal] = True
            context.clear_flags()
            number = BSLNumberQualifiers(*args)
            text_number = BSLNumberQualifiers('39.9', '10.9')
            string = BSLStringQualifiers('100.9', BSLAllowedLength.FIXED)
            self.assertEqual((number.digits, number.fraction_digits),
                             (Decimal(39), Decimal(10)))
            self.assertEqual((text_number.digits, text_number.fraction_digits),
                             (Decimal(39), Decimal(10)))
            self.assertEqual(string.length, Decimal(100))
            self.assertFalse(any(context.flags.values()))


class QualifierBoundaryTests(unittest.TestCase):
    def test_unsupported_negative_cases_are_explicitly_labeled(self):
        for factory, args in (
                (BSLNumberQualifiers, (Decimal('-1.9'),)),
                (BSLNumberQualifiers, (Decimal(5), Decimal(-1))),
                (BSLNumberQualifiers, (Decimal(5), Decimal('-0.9'))),
                (BSLStringQualifiers, (Decimal('-1.9'),)),
                (BSLBinaryDataQualifiers, (Decimal('-1.9'),))):
            with self.subTest(factory=factory.__name__, args=args):
                with self.assertRaisesRegex(ValueError, 'пока не поддерживается'):
                    factory(*args)

    def test_unmeasured_implicit_coercions_and_host_hooks_are_not_invented(self):
        class HostObject:
            def __str__(self):
                raise AssertionError('No host hook should run')

            def __int__(self):
                raise AssertionError('No host hook should run')

        class StringSubclass(str):
            def strip(self):
                raise AssertionError('No host hook should run')

        class DecimalSubclass(Decimal):
            pass

        for cls in (BSLNumberQualifiers, BSLStringQualifiers, BSLBinaryDataQualifiers):
            for value in (None, NULL, False, True, 3.9, [], {}, HostObject(),
                          StringSubclass('3'), DecimalSubclass('3')):
                with self.subTest(cls=cls.__name__, value_type=type(value).__name__):
                    with self.assertRaises(TypeError):
                        cls(value)

    def test_wrong_enum_family_and_plain_values_do_not_coerce(self):
        for bad in (0, Decimal(0), None, NULL, False, 'Any', BSLAllowedLength.FIXED,
                    BSLDateFractions.DATE, ALLOWED_SIGNS):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                BSLNumberQualifiers(5, 2, bad)
        for cls in (BSLStringQualifiers, BSLBinaryDataQualifiers):
            for bad in (0, Decimal(0), None, NULL, False, 'Fixed', BSLAllowedSign.ANY,
                        BSLDateFractions.DATE, ALLOWED_LENGTHS):
                with self.subTest(cls=cls.__name__, bad=bad), self.assertRaises(TypeError):
                    cls(3, bad)
        for bad in (1, Decimal(1), None, NULL, True, 'Date', BSLAllowedSign.ANY,
                    BSLAllowedLength.FIXED, DATE_FRACTIONS):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                BSLDateQualifiers(bad)

    def test_host_metaclass_equality_is_never_called_during_type_validation(self):
        class HostMeta(type):
            def __eq__(cls, other):
                raise AssertionError('Host metaclass equality must not run')

            def __hash__(cls):
                raise AssertionError('Host metaclass hashing must not run')

        class HostObject(metaclass=HostMeta):
            pass

        class HostString(str, metaclass=HostMeta):
            pass

        class HostDecimal(Decimal, metaclass=HostMeta):
            pass

        for value in (HostObject(), HostString('3'), HostDecimal('3')):
            for factory in (BSLNumberQualifiers, BSLStringQualifiers,
                            BSLBinaryDataQualifiers, BSLDateQualifiers):
                with self.subTest(factory=factory.__name__), self.assertRaises(TypeError):
                    factory(value)
            with self.assertRaises(TypeError):
                BSLNumberQualifiers(5, value)
            with self.assertRaises(TypeError):
                BSLNumberQualifiers(5, 2, value)
            for factory in (BSLStringQualifiers, BSLBinaryDataQualifiers):
                with self.assertRaises(TypeError):
                    factory(3, value)

    def test_nonfinite_and_invalid_number_inputs_fail_cleanly(self):
        for cls in (BSLNumberQualifiers, BSLStringQualifiers, BSLBinaryDataQualifiers):
            for value in ('NaN', 'sNaN', 'Infinity', '-Infinity', 'not a number', '',
                          Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity')):
                with self.subTest(cls=cls.__name__, value=value):
                    with self.assertRaises(ValueError):
                        cls(value)

    def test_local_count_budgets_are_not_a_native_38_digit_cap(self):
        self.assertEqual(BSLNumberQualifiers(4096).digits, Decimal(4096))
        self.assertEqual(BSLStringQualifiers(1_000_000).length, Decimal(1_000_000))
        self.assertEqual(BSLBinaryDataQualifiers(1_000_000).length, Decimal(1_000_000))
        for factory, args in (
                (BSLNumberQualifiers, (4097,)),
                (BSLNumberQualifiers, (5, 4097)),
                (BSLStringQualifiers, (1_000_001,)),
                (BSLBinaryDataQualifiers, (1_000_001,))):
            with self.subTest(factory=factory.__name__, args=args):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    factory(*args)

    def test_huge_numeric_exponents_and_coefficients_are_bounded_before_expansion(self):
        for cls in (BSLNumberQualifiers, BSLStringQualifiers, BSLBinaryDataQualifiers):
            for value in (Decimal('1e999999999'), '1e999999999', '9' * 4097,
                          Decimal('9' * 4097), 1 << 20000):
                with self.subTest(cls=cls.__name__, value_type=type(value).__name__):
                    with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                        cls(value)
            self.assertEqual(cls(Decimal('1e-999999999')).get_member(
                'Digits' if cls is BSLNumberQualifiers else 'Length'), Decimal(0))

    def test_extra_constructor_arguments_are_rejected(self):
        for factory, args in ((BSLNumberQualifiers, (1, 0, BSLAllowedSign.ANY, 0)),
                              (BSLStringQualifiers, (1, BSLAllowedLength.FIXED, 0)),
                              (BSLBinaryDataQualifiers, (1, BSLAllowedLength.FIXED, 0)),
                              (BSLDateQualifiers, (BSLDateFractions.DATE, 0))):
            with self.subTest(factory=factory.__name__), self.assertRaises(TypeError):
                factory(*args)


class QualifierObjectBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda text: None)
        for russian, factory, english in (
                ('КвалификаторыЧисла', BSLNumberQualifiers, 'NumberQualifiers'),
                ('КвалификаторыСтроки', BSLStringQualifiers, 'StringQualifiers'),
                ('КвалификаторыДвоичныхДанных', BSLBinaryDataQualifiers, 'BinaryDataQualifiers'),
                ('КвалификаторыДаты', BSLDateQualifiers, 'DateQualifiers')):
            self.vm.register_type(russian, factory, english)
        self.vm.variables.update({'signs': ALLOWED_SIGNS, 'lengths': ALLOWED_LENGTHS,
                                  'fractions': DATE_FRACTIONS})

    def test_every_property_is_bilingual_and_case_insensitive(self):
        cases = (
            (BSLNumberQualifiers(5, 2, BSLAllowedSign.NONNEGATIVE),
             [('Digits', 'Разрядность', Decimal(5)),
              ('FractionDigits', 'РазрядностьДробнойЧасти', Decimal(2)),
              ('AllowedSign', 'ДопустимыйЗнак', BSLAllowedSign.NONNEGATIVE)]),
            (BSLStringQualifiers(4, BSLAllowedLength.FIXED),
             [('Length', 'Длина', Decimal(4)),
              ('AllowedLength', 'ДопустимаяДлина', BSLAllowedLength.FIXED)]),
            (BSLBinaryDataQualifiers(4, BSLAllowedLength.FIXED),
             [('Length', 'Длина', Decimal(4)),
              ('AllowedLength', 'ДопустимаяДлина', BSLAllowedLength.FIXED)]),
            (BSLDateQualifiers(BSLDateFractions.TIME),
             [('DateFractions', 'ЧастиДаты', BSLDateFractions.TIME)]),
        )
        for value, properties in cases:
            self.vm.variables['q'] = value
            for english, russian, expected in properties:
                for name in (english, russian, english.upper(), russian.swapcase()):
                    with self.subTest(value=value, name=name):
                        self.assertEqual(value.get_member(name), expected)
                        self.assertEqual(self.vm.execute('q.' + name), expected)
                        with self.assertRaisesRegex(ValueError, 'недоступно для записи'):
                            value.set_member(name, None)
                        with self.assertRaises(BSLRuntimeError):
                            self.vm.execute('q.' + name + ' = Undefined;')
                        self.assertEqual(value.get_member(name), expected)

    def test_qualifiers_are_host_immutable_and_do_not_expose_python_internals(self):
        for value, attribute in ((BSLNumberQualifiers(5, 2), 'digits'),
                                 (BSLStringQualifiers(4), 'length'),
                                 (BSLBinaryDataQualifiers(4), 'allowed_length'),
                                 (BSLDateQualifiers(), 'date_fractions')):
            with self.assertRaises(FrozenInstanceError):
                setattr(value, attribute, None)
            self.vm.variables['q'] = value
            for name in ('__class__', '__dict__', 'get_member', 'set_member',
                         'fraction_digits', 'allowed_length', 'date_fractions',
                         'Count', 'Get', 'Missing'):
                with self.subTest(value=value, name=name):
                    with self.assertRaises(ValueError):
                        value.get_member(name)
                    with self.assertRaises(BSLRuntimeError):
                        self.vm.execute('q.' + name)

    def test_bilingual_constructor_factories_work_without_integration_registration(self):
        self.vm.execute('''
            n = New NumberQualifiers(5.9, 2.9, signs.Nonnegative);
            s = Новый КвалификаторыСтроки(4, lengths.Фиксированная);
            b = New BinaryDataQualifiers(0, lengths.Fixed);
            d = Новый КвалификаторыДаты(fractions.Время);
        ''')
        self.assertEqual(self.vm.execute('n.Разрядность'), Decimal(5))
        self.assertEqual(self.vm.execute('n.FractionDigits'), Decimal(2))
        self.assertIs(self.vm.execute('n.AllowedSign'), BSLAllowedSign.NONNEGATIVE)
        self.assertIs(self.vm.execute('s.ДопустимаяДлина'), BSLAllowedLength.FIXED)
        self.assertIs(self.vm.execute('b.AllowedLength'), BSLAllowedLength.VARIABLE)
        self.assertIs(self.vm.execute('d.DateFractions'), BSLDateFractions.TIME)

    def test_no_accidental_methods_operators_indexing_or_namespace_iteration(self):
        self.vm.variables['q'] = BSLNumberQualifiers(5, 2)
        self.vm.variables['member'] = BSLAllowedSign.ANY
        for expression in ('q.Digits()', 'q[0]', 'q.Get()', 'q + 1', '-q',
                           'Boolean(q)', 'Number(q)', 'member.Value',
                           'member.Name', 'member[0]', 'member + 1',
                           'signs.Any()', 'signs.Count()', 'signs[0]'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        for variable in ('q', 'signs', 'lengths', 'fractions', 'member'):
            with self.subTest(variable=variable), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f'For Each item In {variable} Do EndDo;')


if __name__ == '__main__':
    unittest.main()
