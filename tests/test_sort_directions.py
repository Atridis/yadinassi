"""Owner-confirmed SortDirection behavior and explicit safe-subset guards.

Native evidence is read from collections.out, never fabricated or rewritten.
Unobserved namespace types/codecs and reflective host behavior stay unsupported.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal, ROUND_DOWN, Rounded, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.native_observations import extract_payload, inverse_stream, read_observation
from yadinassi import Interpreter, serialization
from yadinassi.errors import BSLRuntimeError
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.numeric.round_modes import BSLRoundMode
from yadinassi.search_directions import BSLSearchDirection
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.sort_directions import BSLSortDirection, BSLSortDirections, SORT_DIRECTIONS
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLObject, BSLType, equal, to_string


ASC, DESC = BSLSortDirection.ASC, BSLSortDirection.DESC
DIRECTION_ID = '8acd280e-c29c-4543-8be7-7f78cad52c06'
ROOT = Path(__file__).resolve().parents[1]


def array(*values):
    result = BSLArray()
    result.items = list(values)
    return result


class SortDirectionValueTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_exactly_two_opaque_identities_not_numeric_flags_or_other_enums(self):
        self.assertEqual(list(BSLSortDirection), [ASC, DESC])
        self.assertFalse(equal(ASC, DESC))
        for direction in BSLSortDirection:
            self.assertTrue(equal(direction, direction))
            for other in (None, False, True, Decimal(0), Decimal(1), 0, 1,
                          str(direction), SORT_DIRECTIONS, BSLType.SORT_DIRECTION,
                          BSLSearchDirection.FROM_BEGIN, BSLSearchDirection.FROM_END,
                          BSLRoundMode.ROUND15_AS10, BSLRoundMode.ROUND15_AS20):
                with self.subTest(direction=direction.name, other=other):
                    self.assertFalse(equal(direction, other))
                    self.assertFalse(equal(other, direction))

    def test_bilingual_case_insensitive_globals_and_members(self):
        for namespace in ('SortDirection', 'НаправлениеСортировки'):
            for spelling in (namespace, namespace.lower(), namespace.upper()):
                self.assertIs(self.vm.execute(spelling), SORT_DIRECTIONS)
                for member, expected in (('Asc', ASC), ('Возр', ASC),
                                         ('Desc', DESC), ('Убыв', DESC)):
                    for name in (member, member.lower(), member.upper(), member.swapcase()):
                        with self.subTest(namespace=spelling, member=name):
                            self.assertIs(SORT_DIRECTIONS.get_member(name), expected)
                            self.assertIs(self.vm.execute(spelling + '.' + name), expected)

    def test_presentations_and_value_type_identity(self):
        for value, text in ((ASC, 'По возрастанию'), (DESC, 'По убыванию')):
            self.assertEqual(to_string(value), text)
            self.assertIs(type_of(value), BSLType.SORT_DIRECTION)
        self.assertEqual(str(BSLType.SORT_DIRECTION), 'НаправлениеСортировки')
        self.assertEqual(str(SORT_DIRECTIONS), 'ПеречислениеНаправлениеСортировки')
        for name in ('SortDirection', 'НаправлениеСортировки'):
            for spelling in (name, name.lower(), name.upper()):
                self.assertIs(type_by_name(spelling), BSLType.SORT_DIRECTION)
                self.assertIs(self.vm.execute('Type("' + spelling + '")'), BSLType.SORT_DIRECTION)
        self.assertIs(type_of(BSLType.SORT_DIRECTION), BSLType.TYPE)

    def test_unobserved_namespace_type_and_codec_are_explicitly_unsupported(self):
        # The owner's namespace probe observes String(), not TypeOf() or a GUID.
        for name in ('EnumSortDirection', 'ПеречислениеНаправлениеСортировки',
                     'SortDirections', 'SortDirection ', ' SortDirection'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                type_by_name(name)
        with self.assertRaisesRegex(TypeError, 'пока не поддерживается'):
            type_of(SORT_DIRECTIONS)
        for value in (SORT_DIRECTIONS, array(ASC, SORT_DIRECTIONS, DESC)):
            with self.assertRaisesRegex(TypeError, 'поддерживаемым типам'):
                write(value)
        for expression in ('TypeOf(SortDirection)', 'ValueToStringInternal(SortDirection)'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)

    def test_namespace_is_read_only_and_has_no_host_reflection(self):
        for name in ('Unknown', 'Ascending', 'Descending', '__class__', '__dict__',
                     '__iter__', 'get_member', 'get_method', 'set_member',
                     'name', 'value', 'items', 'Count', 'Get'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    SORT_DIRECTIONS.get_member(name)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('SortDirection.' + name)
        for name in ('Asc', 'Убыв', 'Unknown'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'недоступно для записи'):
                    SORT_DIRECTIONS.set_member(name, None)
                with self.assertRaises(FrozenInstanceError):
                    setattr(SORT_DIRECTIONS, name, None)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('SortDirection.' + name + ' = 1;')
        self.assertIs(self.vm.execute('SortDirection.Asc'), ASC)

    def test_values_and_namespace_do_not_gain_accidental_operators_or_constructors(self):
        self.vm.execute('direction = SortDirection.Asc;')
        for expression in (
                'direction.Name', 'direction.Value', 'direction.__class__',
                'direction[0]', 'direction()', 'direction.Get()',
                'direction < direction', 'direction <= direction',
                'direction > direction', 'direction >= direction',
                'direction + 1', '1 + direction', '-direction', 'Not direction',
                'Boolean(direction)', 'Number(direction)', 'SortDirection[0]',
                'SortDirection()', 'SortDirection.Asc()', 'SortDirection.Get()',
                'SortDirection.Count()', 'SortDirection + 1',
                'SortDirection < SortDirection', 'Boolean(SortDirection)',
                'Number(SortDirection)', 'New SortDirection', 'New НаправлениеСортировки',
                'New (Type("SortDirection"))'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        for code in ('For Each value In direction Do EndDo;',
                     'If direction Then Message(1); EndIf;',
                     'If SortDirection Then Message(1); EndIf;'):
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)

    def test_collection_lookup_keeps_enum_and_number_identities_distinct(self):
        self.vm.execute('''
            values = New Array;
            values.Add(SortDirection.Asc); values.Add(НаправлениеСортировки.Убыв);
            Message(values.Find(НаправлениеСортировки.Возр));
            Message(values.Find(SortDirection.Desc));
            Message(values.Find(0) = Undefined);
            record = New Structure("Direction", (New FixedArray(values))[0]);
            map = New Map;
            map[SortDirection.Asc] = "asc"; map[SortDirection.Desc] = "desc";
            map[0] = "zero"; map[1] = "one"; map[False] = "false"; map[True] = "true";
            map[SearchDirection.FromBegin] = "search";
            map[RoundMode.Round15as10] = "round";
            map.Insert(НаправлениеСортировки.Возр, "updated");
            Message(map.Count()); Message(map[record.Direction]);
            Message(map[SortDirection.Desc]); Message(map[0]); Message(map[1]);
            Message(map[False]); Message(map[True]);
            Message(map[SearchDirection.FromBegin]); Message(map[RoundMode.Round15as10]);
            map.Delete(НаправлениеСортировки.Убыв);
            Message(map.Get(SortDirection.Desc) = Undefined);
        ''')
        self.assertEqual(self.output, ['0', '1', 'Да', '8', 'updated', 'desc',
                                      'zero', 'one', 'false', 'true', 'search', 'round', 'Да'])


class SortDirectionIterationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_native_order_and_independent_iterators(self):
        first, second = iter(SORT_DIRECTIONS), iter(SORT_DIRECTIONS)
        self.assertIsNot(first, second)
        self.assertIs(next(first), ASC)
        self.assertEqual(list(second), [ASC, DESC])
        self.assertEqual(list(first), [DESC])
        self.assertEqual(list(SORT_DIRECTIONS), [ASC, DESC])

    def test_aliases_and_loop_expression_evaluated_once(self):
        calls = []

        def directions():
            calls.append(True)
            return SORT_DIRECTIONS

        self.vm.register_function('Directions', directions)
        for name in ('НаправлениеСортировки', 'SORTDIRECTION', 'sortdirection',
                     'alias', 'Directions()'):
            self.vm.execute(f'''
                alias = SortDirection; found = New Array;
                Для Каждого item Из {name} Цикл found.Add(item); КонецЦикла;
            ''')
            self.assertEqual(self.vm.variables['found'].items, [ASC, DESC])
        self.assertEqual(calls, [True])

    def test_nested_loops_break_continue_return_and_error_recovery(self):
        self.vm.execute('''
            Function FirstDirection()
                For Each localDirection In SortDirection Do Return localDirection; EndDo;
            EndFunction
            total = 0;
            For Each outer In SortDirection Do
                For Each inner In НаправлениеСортировки Do total = total + 1; EndDo;
            EndDo;
            Message(total);
            For Each direction In SortDirection Do
                If direction = SortDirection.Asc Then Continue; EndIf;
                Message(direction); Break;
            EndDo;
            Message(FirstDirection() = SortDirection.Asc);
            For Each direction In SortDirection Do direction = 123; EndDo;
            For Each direction In SortDirection Do Message(direction); EndDo;
        ''')
        self.assertEqual(self.output, ['4', 'По убыванию', 'Да', 'По возрастанию', 'По убыванию'])
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('For Each item In SortDirection Do result = 1 / 0; EndDo;')
        self.vm.execute('For Each item In SortDirection Do Message(item); EndDo;')
        self.assertEqual(self.output[-2:], ['По возрастанию', 'По убыванию'])

    def test_host_subclasses_and_hostile_metaclasses_are_not_iterated(self):
        calls = []

        class HostNamespace(BSLSortDirections):
            def __iter__(self):
                calls.append('namespace')
                return iter([ASC])

        class PretendNamespace(type):
            def __eq__(cls, other):
                return True

        class HostObject(BSLObject, metaclass=PretendNamespace):
            def __iter__(self):
                calls.append('host')
                return iter([ASC])

        for value in (ASC, DESC, HostNamespace(), HostObject(), [], (), {}, iter([ASC])):
            self.vm.variables['source'] = value
            with self.subTest(kind=type(value).__name__), self.assertRaisesRegex(
                    BSLRuntimeError, 'Для Каждого ожидает'):
                self.vm.execute('For Each item In source Do EndDo;')
        self.assertEqual(calls, [])


class SortDirectionCodecTests(unittest.TestCase):
    def test_exact_value_and_type_payloads_restore_canonical_identities(self):
        for value, index in ((ASC, '0'), (DESC, '1')):
            payload = '{"#",' + DIRECTION_ID + ',' + index + '}'
            self.assertEqual(write(value), payload)
            self.assertIs(read(payload), value)
            self.assertIs(type_of(read(payload)), BSLType.SORT_DIRECTION)
        type_payload = '{"T",' + DIRECTION_ID + '}'
        self.assertEqual(write(BSLType.SORT_DIRECTION), type_payload)
        self.assertIs(read(type_payload), BSLType.SORT_DIRECTION)

    def test_indices_reject_unobserved_values_and_coercions(self):
        for body in ('', '2', '-1', '-0', '+0', '+1', '00', '01',
                     '0.0', '1.0', '1e0', 'NaN', 'Infinity', 'true',
                     '٠', '１', '"0"', '"1"', '{}', '{0}',
                     '{"N",0}', '{"B",1}', '0,1', '1' * 10000):
            with self.subTest(body=body[:40]), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read('{"#",' + DIRECTION_ID + ',' + body + '}')

    def test_only_observed_record_shapes_ids_and_tags_are_supported(self):
        for payload in ('{"#","' + DIRECTION_ID + '",0}',
                        '{"#",' + DIRECTION_ID.upper() + ',0}',
                        '{"T",' + DIRECTION_ID.upper() + '}',
                        '{"T",' + DIRECTION_ID + ',0}',
                        '{"t",' + DIRECTION_ID + '}',
                        '{"T",' + DIRECTION_ID + ',{}}',
                        '{"#",' + DIRECTION_ID + ',{"U"}}',
                        '{"#",' + DIRECTION_ID + '}',
                        '{"#",00000000-0000-0000-0000-000000000000,0}'):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(payload)

    def test_all_truncations_are_catchable_and_reader_recovers(self):
        for value in (ASC, DESC, BSLType.SORT_DIRECTION):
            payload = write(value)
            for end in range(len(payload)):
                with self.subTest(value=str(value), end=end), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(payload[:end])
            self.assertIs(read(payload), value)

    def test_values_and_type_survive_supported_containers(self):
        contents = array(ASC, DESC, BSLType.SORT_DIRECTION)
        record = BSLStructure('Asc,Desc,Kind', *contents.items)
        mapping = BSLMap()
        for key, value in ((ASC, 'asc'), (DESC, 'desc'), (Decimal(0), 'zero'),
                           (Decimal(1), 'one'), (False, 'false'), (True, 'true'),
                           (BSLSearchDirection.FROM_BEGIN, 'search')):
            mapping.insert(key, value)
        for original in (contents, BSLFixedArray(contents), record, BSLFixedStructure(record),
                         mapping, BSLFixedMap(mapping), BSLKeyAndValue(ASC, DESC)):
            with self.subTest(kind=type_of(original)):
                restored = read(write(original))
                self.assertIs(type_of(restored), type_of(original))
                if type(original) in (BSLMap, BSLFixedMap):
                    # Map stream order is not canonical or stable on readback.
                    self.assertEqual(len(restored._items), 7)
                    for key, value in mapping._items.values():
                        self.assertEqual(restored.get(key), value)
                elif type(original) in (BSLStructure, BSLFixedStructure):
                    for name, expected in zip(('Asc', 'Desc', 'Kind'), contents.items):
                        self.assertIs(restored.get_member(name), expected)
                elif type(original) is BSLKeyAndValue:
                    self.assertIs(restored.key, ASC)
                    self.assertIs(restored.value, DESC)
                else:
                    for left, right in zip(original.items, restored.items):
                        self.assertIs(left, right)

    def test_host_namespace_hooks_do_not_run_for_types_or_codec(self):
        class HostNamespace(BSLSortDirections):
            def __str__(self):
                raise AssertionError('Host presentation must not run')

        value = HostNamespace()
        with self.assertRaises(TypeError):
            type_of(value)
        with self.assertRaises(TypeError):
            write(value)

    def test_decimal_context_unchanged_on_success_and_rejection(self):
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.flags[Rounded] = True
            for signal in context.traps:
                context.traps[signal] = True
            before = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            for value in (ASC, DESC, BSLType.SORT_DIRECTION, array(ASC, Decimal('1.234'), DESC)):
                read(write(value))
            with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read('{"#",' + DIRECTION_ID + ',1.0}')
            self.assertEqual((context.prec, context.rounding, dict(context.flags), dict(context.traps)), before)

    def test_resource_limits_cover_enum_and_type_nodes(self):
        for value in (ASC, DESC, BSLType.SORT_DIRECTION):
            payload = write(value)
            with patch.object(serialization, '_MAX_TEXT', len(payload)):
                self.assertEqual(write(value), payload)
                self.assertIs(read(payload), value)
            with patch.object(serialization, '_MAX_TEXT', len(payload) - 1):
                for operation, argument in ((write, value), (read, payload)):
                    with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                        operation(argument)
        allowed, rejected = array(ASC, DESC), array(ASC, DESC, BSLType.SORT_DIRECTION)
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_NODES', 3):
            self.assertEqual(write(allowed), allowed_payload)
            self.assertEqual(read(allowed_payload).items, [ASC, DESC])
            for operation, argument in ((write, rejected), (read, rejected_payload)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)
        allowed, rejected = array(array(ASC)), array(array(array(DESC)))
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_DEPTH', 2):
            self.assertEqual(write(allowed), allowed_payload)
            read(allowed_payload)
            for operation, argument in ((write, rejected), (read, rejected_payload)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)


class SortDirectionNativeEvidenceTests(unittest.TestCase):
    """Compare the exact committed owner probe functions to genuine records."""

    @classmethod
    def setUpClass(cls):
        cls.output = (ROOT / 'tests/fixtures/native_windows/collections.out').read_text(
            encoding='utf-8-sig')
        cls.helpers = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(
            encoding='utf-8-sig').split('#Область МассивыИСтруктуры', 1)[0]

    def native(self, name):
        return read_observation(extract_payload(self.output, 'table.list.sort.enum.' + name))

    def test_entire_native_identity_and_iteration_record(self):
        vm = Interpreter()
        vm.execute(self.helpers)
        self.assertEqual(write(vm.execute('ТипНаправленияСортировкиПробы()')),
                         write(self.native('identity')))

    def test_entire_native_value_and_type_codec_records(self):
        vm = Interpreter()
        vm.execute(self.helpers)
        for name, value, source in (
                ('asc', ASC, 'КодекНаправленияСортировкиПробы(SortDirection.Asc, Истина)'),
                ('desc', DESC, 'КодекНаправленияСортировкиПробы(SortDirection.Desc)')):
            snapshot = self.native(name + '-codec')
            self.assertEqual(write(vm.execute(source)), write(snapshot))
            self.assertEqual(write(value), snapshot.get('Write'))
            self.assertIs(read(snapshot.get('Write')), value)
            self.assertEqual(write(read(snapshot.get('Write'))), inverse_stream(snapshot))

    def test_entire_native_constructor_readonly_missing_member_and_index_boundaries(self):
        vm = Interpreter()
        vm.execute(self.helpers)
        result = vm.execute('''
            СерияСортировкиСписка("empty", "Ответ = Новый SortDirection;|SortDirection.Asc = SortDirection.Desc;|Ответ = SortDirection.Unknown;|Ответ = SortDirection[0];")
        ''')
        self.assertEqual(write(result), write(self.native('boundaries')))


if __name__ == '__main__':
    unittest.main()
