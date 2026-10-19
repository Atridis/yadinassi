"""Null: owner's native observations and explicit defensive subset checks.

Only NativeNullEvidenceTests claims native parity. Other tests exercise local
safety and integration boundaries, not undocumented native acceptance rules.
"""

from copy import copy, deepcopy
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
import re
import unittest

from scripts.smoke_test import null_checkpoint_output, null_checkpoint_source
from yadinassi import BSLError, Interpreter, ast
from yadinassi.lexer import Lexer
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.parser import parse
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_checks import value_is_filled
from yadinassi.values import (
    BSLArray, BSLFixedArray, BSLNull, BSLType, NULL, boolean, equal, number, to_string,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
NATIVE = ROOT / 'integrational_tests/output/values.out'
TYPE_RECORD = '{"T",af40a278-63bc-478e-91a8-19e0d16b10b5}'


class NativeNullEvidenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.native = null_checkpoint_output(NATIVE.read_text(encoding='utf-8-sig'))
        cls.source = null_checkpoint_source(SOURCE.read_text(encoding='utf-8-sig'))
        cls.records = dict(re.findall(
            r'^null\.([a-z0-9.-]+): \[(.*?)\](?=\nnull\.|\n?\Z)',
            cls.native, re.MULTILINE | re.DOTALL))
        cls.expressions = {
            node.expression.arguments[0].value: node.expression.arguments[1].value
            for node in parse(cls.source)
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьNull'}

    def test_unchanged_native_checkpoint_matches_in_full(self):
        output = []
        Interpreter(output.append).execute(self.source, str(SOURCE))
        self.assertEqual('\n'.join(output) + '\n', self.native)
        self.assertEqual(len(self.native.splitlines()), 98)
        self.assertEqual(len(self.expressions), 40)
        self.assertEqual(set(self.records), set(self.expressions) | {'checkpoint.complete'})
        self.assertEqual(self.records['checkpoint.complete'], 'ok')

    def test_every_observation_individually(self):
        vm = Interpreter(lambda message: None)
        vm.execute(self.source)
        for label, expression in self.expressions.items():
            with self.subTest(label=label, expression=expression):
                expected = self.records[label]
                if expected == 'error':
                    with self.assertRaises(BSLError):
                        vm.execute('(' + expression + ')')
                else:
                    self.assertEqual(write(vm.execute('(' + expression + ')')), expected)

    def test_genuine_records_have_inverse_codec(self):
        for label, payload in self.records.items():
            if payload in ('error', 'ok'):
                continue
            with self.subTest(label=label):
                restored = read(payload)
                if label == 'collection.map-roundtrip':
                    # Mutable-map stream order reverses on each serialization;
                    # test recovered keys rather than inventing a stable order.
                    mapping = restored.get_member('Restored')
                    self.assertEqual(mapping.get(NULL), 'second')
                    self.assertEqual(mapping.get(None), 'undefined')
                    self.assertEqual(len(mapping._items), 2)
                else:
                    self.assertEqual(write(restored), payload)
        self.assertIs(read(self.records['literal.upper']), NULL)
        self.assertIs(read(self.records['type.name']), BSLType.NULL)
        self.assertEqual(self.records['type.name'], TYPE_RECORD)


class NullIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(lambda message: None)

    def test_literal_singleton_and_case_handling(self):
        for spelling in ('Null', 'NULL', 'null', 'nUlL'):
            self.assertIs(self.vm.execute(spelling), NULL)
            self.assertEqual(Lexer(spelling).tokens()[0].kind, 'NULL')
        self.assertIs(BSLNull('Null'), NULL)
        self.assertIs(copy(NULL), NULL)
        self.assertIs(deepcopy(NULL), NULL)
        self.assertIsNot(NULL, None)
        self.assertIsNot(NULL, BSLType.NULL)
        self.assertIsNot(NULL, False)
        for identifier in ('Nullish', 'Null_1', 'Нулл'):
            self.assertEqual(Lexer(identifier).tokens()[0].kind, 'IDENT')
        self.assertIs(self.vm.execute('Null = 1'), False)
        self.assertIs(self.vm.execute('Null'), NULL)
        for code in ('Var Null;', 'Function F(Null) Return 1; EndFunction'):
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_type_identity_bilingual_builtins_and_opaque_members(self):
        for call in ('TypeOf(Null)', 'ТипЗнч(Null)', 'тИпЗнЧ(nUlL)',
                     'Type("NULL")', 'Тип("Null")', 'tYpE("nUlL")'):
            self.assertIs(self.vm.execute(call), BSLType.NULL)
        self.assertIs(type_of(NULL), BSLType.NULL)
        self.assertIs(type_of(BSLType.NULL), BSLType.TYPE)
        for name in ('Нулл', ' NULL ', ''):
            with self.assertRaises(ValueError):
                type_by_name(name)
        for expression in ('Null.value', 'Null.name', 'Null.__class__',
                           'Type("Null").value', 'Null[0]', 'Null()', 'New Null'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_default_parameters_and_dynamic_evaluation(self):
        self.vm.execute('''
            Function DefaultNull(value = Null) Return value; EndFunction
            Функция ПоУмолчанию(Знач Значение = nUlL) Возврат Значение; КонецФункции
        ''')
        for expression in ('DefaultNull()', 'ПоУмолчанию()',
                           'Eval("Null")', 'Вычислить("nUlL")'):
            self.assertIs(self.vm.execute(expression), NULL)
        self.assertIsNone(self.vm.execute('DefaultNull(Undefined)'))
        self.vm.execute('saved = Undefined; Execute("saved = Null");')
        self.assertIs(self.vm.execute('saved'), NULL)

    def test_scalar_conversions_and_context_independence(self):
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = context.traps[Rounded] = True
            self.assertEqual(to_string(NULL), '')
            self.assertIs(value_is_filled(NULL), False)
            self.assertEqual(write(NULL), '{"L"}')
            self.assertIs(read('{"L"}'), NULL)
            self.assertEqual(write(BSLType.NULL), TYPE_RECORD)
            self.assertIs(read(TYPE_RECORD), BSLType.NULL)
            for function in (boolean, number):
                with self.assertRaises((ValueError, TypeError)):
                    function(NULL)
        for name in ('String', 'Строка'):
            self.assertEqual(self.vm.execute(f'{name}(Null)'), '')
        # Existing local string-conversion path, not an additional native probe.
        self.assertEqual(self.vm.execute('"prefix" + Null'), 'prefix')
        for name in ('ValueIsFilled', 'ЗначениеЗаполнено'):
            self.assertIs(self.vm.execute(f'{name}(Null)'), False)

    def test_equality_and_lookup_keep_undefined_distinct(self):
        self.assertTrue(equal(NULL, read('{"L"}')))
        for value in (None, False, True, Decimal(0), '', BSLType.NULL, object()):
            self.assertFalse(equal(NULL, value))
            self.assertFalse(equal(value, NULL))
        self.vm.execute('a = New Array; a.Add(Undefined); a.Add(Null); a.Add(Type("Null"));')
        for constructor in ('a', 'New FixedArray(a)'):
            self.vm.execute('b = ' + constructor)
            self.assertEqual(self.vm.execute('b.Find(Null)'), Decimal(1))
            self.assertEqual(self.vm.execute('b.Find(Undefined)'), Decimal(0))
            self.assertEqual(self.vm.execute('b.Find(Type("Null"))'), Decimal(2))

    def test_short_circuit_does_not_evaluate_right_side(self):
        calls = []
        self.vm.register_function('GetNull', lambda: calls.append('called') or NULL)
        for expression, result in (('False And GetNull()', False), ('True Or GetNull()', True),
                                   ('Ложь И GetNull()', False), ('Истина Или GetNull()', True)):
            self.assertIs(self.vm.execute(expression), result)
        self.assertEqual(calls, [])
        for expression in ('True And GetNull()', 'False Or GetNull()'):
            with self.assertRaises(BSLError):
                self.vm.execute(expression)
        self.assertEqual(calls, ['called', 'called'])

    def test_null_conditions_fail_before_body_runs(self):
        for code in ('If Null Then touched = True; EndIf;',
                     'While Null Do touched = True; EndDo;',
                     'Если Null Тогда touched = True; КонецЕсли;'):
            self.vm.execute('touched = False')
            with self.assertRaises(BSLError):
                self.vm.execute(code)
            self.assertIs(self.vm.execute('touched'), False)

    def test_error_location_assignment_atomicity_and_recovery(self):
        expressions = ('Number(Null)', 'Boolean(Null)', 'Not Null', 'Null < 0',
                       'Null + 1', '1 / Null', '?(Null, 1, 2)',
                       'Null + "suffix"', '+Null', 'Null % 1', '1 % Null',
                       'Null <= Null', 'Null >= Null',
                       'ValueFromStringInternal("{""L"",0}")')
        for expression in expressions:
            with self.subTest(expression=expression):
                self.vm.execute('saved = "old"')
                with self.assertRaises(BSLError) as caught:
                    self.vm.execute('\nsaved = ' + expression, 'null-test.bsl')
                self.assertEqual(caught.exception.source, 'null-test.bsl')
                self.assertEqual(caught.exception.line, 2)
                self.assertGreater(caught.exception.column, 0)
                self.assertEqual(self.vm.execute('saved'), 'old')
                self.assertIs(self.vm.execute('caught = False; Try ' + expression +
                                             '; Except caught = True; EndTry; caught'), True)
                self.assertIs(self.vm.execute('Null'), NULL)

    def test_typed_map_keys_replacement_and_inverse(self):
        mapping = BSLMap()
        for key, value in ((None, 'undefined'), (NULL, 'first'), (False, 'false'),
                           (Decimal(0), 'zero'), ('', 'empty'), (BSLType.NULL, 'type')):
            mapping.insert(key, value)
        mapping.insert(read('{"L"}'), 'second')
        self.assertEqual(len(mapping._items), 6)
        for value in (mapping, BSLFixedMap(mapping), read(write(mapping)),
                      read(write(BSLFixedMap(mapping)))):
            self.assertEqual(value.get(NULL), 'second')
            self.assertEqual(value.get(None), 'undefined')
            self.assertEqual(value.get(BSLType.NULL), 'type')
            self.assertEqual(len(value._items), 6)
        mapping.delete(NULL)
        self.assertIsNone(mapping.get(NULL))
        self.assertEqual(mapping.get(None), 'undefined')

    def test_null_survives_supported_collection_boundaries(self):
        array = BSLArray()
        array.add(NULL)
        array.add(None)
        structure = BSLStructure('Value,Other', NULL, None)
        samples = (array, BSLFixedArray(array), structure, BSLFixedStructure(structure),
                   BSLKeyAndValue(NULL, NULL))
        for value in samples:
            with self.subTest(kind=type_of(value)):
                restored = read(write(value))
                self.assertIs(type_of(restored), type_of(value))
                self.assertEqual(write(restored), write(value))
        self.assertIs(read(write(array)).items[0], NULL)
        self.assertIsNone(read(write(array)).items[1])
        self.assertIs(read(write(structure)).get_member('Value'), NULL)
        self.assertIs(read(write(BSLKeyAndValue(NULL, NULL))).key, NULL)

    def test_malformed_null_records_are_rejected(self):
        # Deliberately stricter local decoder boundary; no native claims here.
        for payload in ('{"L",0}', '{"L",""}', '{"L",{"U"}}', '{"l"}',
                        '{L}', '{"Null"}', '{"L"',
                        '{"T","af40a278-63bc-478e-91a8-19e0d16b10b5"}',
                        '{"#",af40a278-63bc-478e-91a8-19e0d16b10b5,0}',
                        '{"T",af40a278-63bc-478e-91a8-19e0d16b10b5,0}'):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(payload)
        # Keep existing first-record semantics, established for the codec.
        self.assertIs(read('{"L"} trailing text'), NULL)

    def test_host_objects_cannot_impersonate_null_or_invoke_hooks(self):
        class HostileMeta(type):
            def __eq__(self, other):
                raise AssertionError('metaclass equality')
            def __hash__(self):
                raise AssertionError('metaclass hashing')
        class Hostile(metaclass=HostileMeta):
            def __eq__(self, other):
                raise AssertionError('equality')
            def __hash__(self):
                raise AssertionError('hashing')
            def __bool__(self):
                raise AssertionError('truth')
            def __str__(self):
                raise AssertionError('presentation')
        host = Hostile()
        for function in (type_of, value_is_filled, write, read, boolean, number):
            with self.subTest(function=function.__name__), self.assertRaises((TypeError, ValueError)):
                function(host)
        self.assertFalse(equal(NULL, host))
        self.assertFalse(equal(host, NULL))
        mapping = BSLMap()
        mapping.insert(host, 'host')
        mapping.insert(NULL, 'null')
        self.assertEqual(mapping.get(host), 'host')
        self.assertEqual(mapping.get(NULL), 'null')
        self.assertEqual(len(mapping._items), 2)
