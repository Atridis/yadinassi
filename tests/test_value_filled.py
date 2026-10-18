"""EDT-documented filled values, plus explicitly local compatibility limits."""
from decimal import Decimal, localcontext, Inexact, Rounded
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.maps import BSLMap, BSLFixedMap
from yadinassi.structures import BSLStructure, BSLFixedStructure, BSLKeyAndValue
from yadinassi.values import BSLArray, BSLFixedArray, BSLType
from yadinassi.round_modes import BSLRoundMode, ROUND_MODES
from yadinassi.strings import _WHITESPACE
from yadinassi.value_checks import value_is_filled


class ValueFilledTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_documented_scalars(self):
        for value, expected in [(None, False), (False, True), (True, True),
                                (Decimal(0), False), (Decimal('-0.000'), False),
                                (Decimal('0.1'), True), (Decimal('-42'), True),
                                ('', False), ('   ', False), (' x ', True),
                                ('0', True), ('Нет', True)]:
            with self.subTest(value=value):
                self.assertIs(value_is_filled(value), expected)

    def test_bilingual_case_insensitive_names_and_boolean_type(self):
        for name in ('ЗначениеЗаполнено', 'ValueIsFilled', 'зНаЧеНиЕзАпОлНеНо', 'vAlUeIsFiLlEd'):
            self.assertIs(self.vm.execute(f'{name}(False)'), True)
            self.assertIs(self.vm.execute(f'{name}(Undefined)'), False)
            self.assertTrue(self.vm.execute(f'(TypeOf({name}(0)) = Type("Boolean"))'))

    def test_arrays_count_entries_not_filled_elements(self):
        array = BSLArray()
        self.assertIs(value_is_filled(array), False)
        self.assertIs(value_is_filled(BSLFixedArray(array)), False)
        array.add(None)
        fixed = BSLFixedArray(array)
        self.assertIs(value_is_filled(array), True)
        self.assertIs(value_is_filled(fixed), True)
        array.items.clear()
        self.assertIs(value_is_filled(array), False)
        self.assertIs(value_is_filled(fixed), True)
        array.add(array)
        self.assertIs(value_is_filled(array), True)

    def test_structure_and_map_count_not_values(self):
        for mutable, fixed in ((BSLStructure, BSLFixedStructure), (BSLMap, BSLFixedMap)):
            with self.subTest(collection=mutable):
                value = mutable()
                self.assertIs(value_is_filled(value), False)
                self.assertIs(value_is_filled(fixed(value)), False)
                value.insert('entry', None)
                snapshot = fixed(value)
                self.assertIs(value_is_filled(value), True)
                self.assertIs(value_is_filled(snapshot), True)
                value.clear()
                self.assertIs(value_is_filled(value), False)
                self.assertIs(value_is_filled(snapshot), True)
                value.insert('self', value)
                self.assertIs(value_is_filled(value), True)

    def test_existing_whitespace_contract_not_native_evidence(self):
        self.assertIs(value_is_filled(_WHITESPACE * 100), False)
        for char in _WHITESPACE:
            self.assertIs(value_is_filled(char), False)
        for text in ('\0', '\x1c', '\u200b', '\ufeff', '😀', '\ud83d', '\ude00'):
            self.assertIs(value_is_filled(text), True)
        self.assertIs(value_is_filled(' ' * 100000 + 'x'), True)

    def test_numeric_context_and_huge_exponents(self):
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = context.traps[Rounded] = True
            for text in ('1e1000000', '1e-1000000', '-1e1000000'):
                self.assertIs(value_is_filled(Decimal(text)), True)
            self.assertIs(value_is_filled(Decimal('-0e1000000')), False)
        for text in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
            with self.assertRaisesRegex(ValueError, 'конечное'):
                value_is_filled(Decimal(text))

    def test_serialization_uses_existing_boolean_format(self):
        for expression, serialized in [('ValueIsFilled(False)', '{"B",1}'),
                                       ('ЗначениеЗаполнено(0)', '{"B",0}')]:
            self.assertEqual(self.vm.execute(f'ValueToStringInternal({expression})'), serialized)
            self.assertIs(self.vm.execute(f'ValueFromStringInternal(ValueToStringInternal({expression}))'),
                          self.vm.execute(expression))

    def test_current_unsupported_types_do_not_guess_native_defaults(self):
        for value in (BSLType.NUMBER, BSLRoundMode.ROUND15_AS10, ROUND_MODES,
                      BSLKeyAndValue('x', None), object(), [], {}, 0):
            with self.assertRaisesRegex(TypeError, 'пока не поддерживается в Yadinassi'):
                value_is_filled(value)

    def test_extension_hooks_and_subclasses_are_not_invoked(self):
        class HostileMeta(type):
            def __eq__(self, other):
                raise AssertionError('metaclass equality')
            def __hash__(self):
                raise AssertionError('metaclass hashing')
        class Hostile(metaclass=HostileMeta):
            def __bool__(self):
                raise AssertionError('truth')
            def __len__(self):
                raise AssertionError('length')
            def __iter__(self):
                raise AssertionError('iteration')
        class ArraySubclass(BSLArray):
            def __getattribute__(self, name):
                raise AssertionError('attribute')
        for value in (Hostile(), ArraySubclass()):
            with self.assertRaises(TypeError):
                value_is_filled(value)

    def test_errors_preserve_assignment_and_recover(self):
        for expression in ('ValueIsFilled()', 'ЗначениеЗаполнено(1, 2)',
                           'ValueIsFilled(Type("Number"))',
                           'ValueIsFilled(RoundMode.Round15as10)', 'ValueIsFilled(RoundMode)'):
            with self.subTest(expression=expression):
                self.vm.execute('saved = "old"')
                with self.assertRaises(BSLError):
                    self.vm.execute('saved = ' + expression)
                self.assertEqual(self.vm.execute('saved'), 'old')
                self.assertTrue(self.vm.execute('caught = False; Try ' + expression +
                                                '; Except caught = True; EndTry; caught'))
                self.assertIs(self.vm.execute('ValueIsFilled(False)'), True)

    def test_runtime_mutation_and_fixed_snapshots(self):
        for constructor, fixed, add in [('Array', 'FixedArray', 'a.Add(Undefined)'),
                                       ('Structure', 'FixedStructure', 'a.Insert("x", Undefined)'),
                                       ('Map', 'FixedMap', 'a.Insert("x", Undefined)')]:
            self.vm.execute(f'a = New {constructor}; empty = ValueIsFilled(a); {add}; '
                            f'b = New {fixed}(a); filled = ValueIsFilled(a); a.Clear();')
            self.assertIs(self.vm.execute('empty'), False)
            self.assertIs(self.vm.execute('filled'), True)
            self.assertIs(self.vm.execute('ValueIsFilled(a)'), False)
            self.assertIs(self.vm.execute('ValueIsFilled(b)'), True)
