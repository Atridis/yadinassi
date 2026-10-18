"""Owner-confirmed search enums and bounded codec checks, not new goldens."""

from dataclasses import FrozenInstanceError
from decimal import Decimal, ROUND_DOWN, Rounded, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.round_modes import BSLRoundMode, ROUND_MODES
from yadinassi.search_directions import (
    BSLSearchDirection, BSLSearchDirections, SEARCH_DIRECTIONS,
)
from yadinassi import serialization
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read, value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.values import BSLArray, BSLFixedArray, BSLObject, BSLType, equal, to_string


DIRECTION_ID = 'bee8fa9f-59d0-4e71-9f6e-599d83cb1960'
NAMESPACE_ID = 'ca8683c7-a41c-4c82-b912-6afb606e8b01'
BEGIN = BSLSearchDirection.FROM_BEGIN
END = BSLSearchDirection.FROM_END
ROOT = Path(__file__).resolve().parents[1]


def array(*items):
    result = BSLArray()
    for item in items:
        result.add(item)
    return result


class SearchDirectionValueTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.variables['directions'] = SEARCH_DIRECTIONS

    def test_foreach_rejects_hostile_metaclass_without_iterating(self):
        calls = []

        class PretendNamespace(type):
            def __eq__(cls, other):
                return True

        class HostObject(BSLObject, metaclass=PretendNamespace):
            def __iter__(self):
                calls.append('iterated')
                return iter([BEGIN])

        self.vm.variables['host'] = HostObject()
        with self.assertRaisesRegex(BSLRuntimeError, 'ожидает массив'):
            self.vm.execute('For Each Item In host Do EndDo;')
        self.assertEqual(calls, [])

    def test_exactly_two_opaque_identities_never_equal_numeric_flags(self):
        self.assertEqual(list(BSLSearchDirection), [BEGIN, END])
        self.assertFalse(equal(BEGIN, END))
        for direction in BSLSearchDirection:
            self.assertTrue(equal(direction, direction))
            for other in [None, False, True, Decimal(0), Decimal(1), 0, 1,
                          to_string(direction), SEARCH_DIRECTIONS,
                          BSLType.SEARCH_DIRECTION, BSLRoundMode.ROUND15_AS10,
                          BSLRoundMode.ROUND15_AS20]:
                with self.subTest(direction=direction.name, other=other):
                    self.assertFalse(equal(direction, other))
                    self.assertFalse(equal(other, direction))

    def test_bilingual_case_insensitive_members(self):
        for name, expected in [('СНачала', BEGIN), ('FromBegin', BEGIN),
                               ('СКонца', END), ('FromEnd', END)]:
            for spelling in [name, name.lower(), name.upper(), name.swapcase()]:
                with self.subTest(name=spelling):
                    self.assertIs(SEARCH_DIRECTIONS.get_member(spelling), expected)
                    self.assertIs(self.vm.execute('directions.' + spelling), expected)

    def test_observed_presentations_and_type_identities(self):
        for value, presentation in [(BEGIN, 'С начала'), (END, 'С конца')]:
            self.assertEqual(to_string(value), presentation)
            self.assertIs(type_of(value), BSLType.SEARCH_DIRECTION)
            self.assertEqual(to_string(type_of(value)), 'НаправлениеПоиска')
        self.assertEqual(to_string(SEARCH_DIRECTIONS), 'ПеречислениеНаправлениеПоиска')
        self.assertIs(type_of(SEARCH_DIRECTIONS), BSLType.SEARCH_DIRECTIONS)
        self.assertIs(type_of(type_of(SEARCH_DIRECTIONS)), BSLType.TYPE)
        self.assertIsNot(BSLType.SEARCH_DIRECTION, BSLType.SEARCH_DIRECTIONS)

    def test_type_names_resolve_values_but_neither_namespace_name(self):
        for name in ['SearchDirection', 'НаправлениеПоиска']:
            for spelling in [name, name.upper(), name.lower()]:
                with self.subTest(name=spelling):
                    self.assertIs(type_by_name(spelling), BSLType.SEARCH_DIRECTION)
                    self.assertIs(self.vm.execute('Type("' + spelling + '")'),
                                  BSLType.SEARCH_DIRECTION)
        for name in ['EnumSearchDirection', 'ПеречислениеНаправлениеПоиска',
                     'SearchDirections', 'SearchDirection ', ' SearchDirection']:
            for spelling in [name, name.upper(), name.lower()]:
                with self.subTest(name=spelling):
                    with self.assertRaisesRegex(ValueError, 'Тип не поддерживается'):
                        type_by_name(spelling)
                    with self.assertRaises(BSLRuntimeError):
                        self.vm.execute('Type("' + spelling + '")')

    def test_namespace_has_no_reflective_members_or_mutable_api(self):
        for name in ['__class__', '__dict__', '__iter__', 'get_member',
                     'get_method', 'set_member', 'name', 'value', 'FROM_BEGIN',
                     'items', 'FromBeginning', 'Count', 'Get']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    SEARCH_DIRECTIONS.get_member(name)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('directions.' + name)
        for name in ['FromBegin', 'СКонца', 'unknown']:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'недоступно для записи'):
                    SEARCH_DIRECTIONS.set_member(name, None)
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('directions.' + name + ' = 1;')
                with self.assertRaises(FrozenInstanceError):
                    setattr(SEARCH_DIRECTIONS, name, None)
        self.assertIs(SEARCH_DIRECTIONS.get_member('FromBegin'), BEGIN)

    def test_values_have_no_accidental_operators_methods_or_constructors(self):
        self.vm.execute('direction = directions.FromBegin;')
        for expression in [
                'direction.Name', 'direction.Value', 'direction.__class__',
                'direction[0]', 'direction()', 'direction.Get()',
                'direction < direction', 'direction <= direction',
                'direction > direction', 'direction >= direction',
                'direction + 1', '1 + direction', '-direction', 'Not direction',
                'Boolean(direction)', 'Number(direction)',
                'directions[0]', 'directions()', 'directions.FromBegin()',
                'directions.Get()', 'directions.Count()', 'directions + 1',
                'directions < directions', 'Boolean(directions)', 'Number(directions)',
                'New SearchDirection', 'New НаправлениеПоиска',
                'New (Type("SearchDirection"))', 'New (TypeOf(directions))']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        for code in ['For Each value In direction Do EndDo;',
                     'If direction Then Message(1); EndIf;',
                     'If directions Then Message(1); EndIf;']:
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)

    def test_storable_findable_and_distinct_from_round_modes_and_numbers(self):
        self.vm.execute('''
            values = New Array;
            values.Add(directions.FromBegin); values.Add(directions.СКонца);
            Message(values.Find(directions.СНачала));
            Message(values.Find(directions.FromEnd));
            Message(values.Find(0) = Undefined);
            fixed = New FixedArray(values);
            record = New Structure("Direction", fixed[0]);
            Message(record.Direction = directions.FromBegin);
            map = New Map;
            map[directions.FromBegin] = "begin"; map[directions.FromEnd] = "end";
            map[0] = "zero"; map[1] = "one";
            map[False] = "false"; map[True] = "true";
            map[RoundMode.Round15as10] = "round";
            map.Insert(directions.СНачала, "updated");
            Message(map.Count()); Message(map[record.Direction]);
            Message(map[directions.СКонца]); Message(map[0]); Message(map[1]);
            Message(map[False]); Message(map[True]); Message(map[RoundMode.Round15as10]);
            map.Delete(directions.СКонца);
            Message(map.Get(directions.FromEnd) = Undefined);
        ''')
        self.assertEqual(self.output, ['0', '1', 'Да', 'Да', '7', 'updated',
                                      'end', 'zero', 'one', 'false', 'true', 'round', 'Да'])

    def test_host_namespace_subclasses_are_not_typed_or_serialized(self):
        class HostNamespace(BSLSearchDirections):
            def __str__(self):
                raise AssertionError('Host presentation must not run')

        value = HostNamespace()
        with self.assertRaises(TypeError):
            type_of(value)
        with self.assertRaises(TypeError):
            write(value)


class SearchDirectionIterationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_native_order_and_independent_iterators(self):
        first, second = iter(SEARCH_DIRECTIONS), iter(SEARCH_DIRECTIONS)
        self.assertIsNot(first, second)
        self.assertIs(next(first), BEGIN)
        self.assertEqual(list(second), [BEGIN, END])
        self.assertEqual(list(first), [END])
        self.assertEqual(list(SEARCH_DIRECTIONS), [BEGIN, END])

    def test_global_aliases_and_loop_expression_evaluated_once(self):
        calls = []

        def directions():
            calls.append(True)
            return SEARCH_DIRECTIONS

        self.vm.register_function('Directions', directions)
        for name in ['НаправлениеПоиска', 'SEARCHDIRECTION', 'searchdirection',
                     'alias', 'Directions()']:
            with self.subTest(name=name):
                self.vm.execute(f'''
                    alias = SearchDirection; found = New Array;
                    Для Каждого item Из {name} Цикл found.Add(item); КонецЦикла;
                ''')
                self.assertEqual(self.vm.variables['found'].items, [BEGIN, END])
        self.assertEqual(calls, [True])

    def test_nested_break_continue_return_and_repeated_iteration(self):
        self.vm.execute('''
            Function FirstDirection()
                For Each localDirection In SearchDirection Do Return localDirection; EndDo;
            EndFunction
            total = 0;
            For Each outer In SearchDirection Do
                For Each inner In НаправлениеПоиска Do total = total + 1; EndDo;
            EndDo;
            Message(total);
            For Each direction In SearchDirection Do
                If direction = SearchDirection.FromBegin Then Continue; EndIf;
                Message(direction); Break;
            EndDo;
            Message(FirstDirection());
            For Each direction In SearchDirection Do direction = 123; EndDo;
            Message(direction);
            For Each direction In SearchDirection Do Message(direction); EndDo;
        ''')
        self.assertEqual(self.output, ['4', 'С конца', 'С начала', '123', 'С начала', 'С конца'])
        self.assertNotIn('localdirection', self.vm.variables)

    def test_body_error_does_not_poison_namespace(self):
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('For Each item In SearchDirection Do result = 1 / 0; EndDo;')
        self.vm.execute('For Each item In SearchDirection Do Message(item); EndDo;')
        self.assertEqual(self.output, ['С начала', 'С конца'])

    def test_host_iterables_subclasses_and_individual_values_remain_rejected(self):
        class HostIterable(BSLObject):
            def __iter__(self):
                raise AssertionError('Host iterable must not run')

        class HostNamespace(BSLSearchDirections):
            def __iter__(self):
                raise AssertionError('Host namespace iterator must not run')

        for value in [BEGIN, END, HostIterable(), HostNamespace(), [], (), {}, iter([BEGIN])]:
            self.vm.variables['source'] = value
            with self.subTest(kind=type(value).__name__), self.assertRaisesRegex(
                    BSLRuntimeError, 'Для Каждого ожидает'):
                self.vm.execute('For Each item In source Do EndDo;')


class SearchDirectionCodecTests(unittest.TestCase):
    def test_exact_native_payloads_restore_canonical_identities(self):
        for value, index in [(BEGIN, '0'), (END, '1')]:
            payload = '{"#",' + DIRECTION_ID + ',' + index + '}'
            self.assertEqual(write(value), payload)
            self.assertIs(read(payload), value)
            self.assertIs(type_of(read(payload)), BSLType.SEARCH_DIRECTION)

    def test_both_type_records_roundtrip_despite_namespace_name_lookup_failure(self):
        for value, identifier in [(BSLType.SEARCH_DIRECTION, DIRECTION_ID),
                                  (BSLType.SEARCH_DIRECTIONS, NAMESPACE_ID)]:
            payload = '{"T",' + identifier + '}'
            self.assertEqual(write(value), payload)
            self.assertIs(read(payload), value)
            self.assertIs(type_of(read(payload)), BSLType.TYPE)

    def test_namespace_payload_restores_undefined(self):
        payload = '{"#",' + NAMESPACE_ID + '}'
        self.assertEqual(write(SEARCH_DIRECTIONS), payload)
        self.assertIsNone(read(payload))
        self.assertIs(type_of(read(payload)), BSLType.UNDEFINED)
        self.assertEqual(write(read(payload)), '{"U"}')
        self.assertFalse(equal(read(payload), SEARCH_DIRECTIONS))

    def test_enum_indices_reject_unobserved_values_and_coercions(self):
        for body in ['', '2', '-1', '-0', '+0', '+1', '00', '01',
                     '0.0', '1.0', '1e0', 'NaN', 'Infinity', 'true',
                     '٠', '１', '"0"', '"1"', '{}', '{0}',
                     '{"N",0}', '{"B",1}', '0,1', '1' * 10000]:
            payload = '{"#",' + DIRECTION_ID + ',' + body + '}'
            with self.subTest(body=body[:40]), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(payload)

    def test_exact_record_shapes_ids_and_tags_are_required(self):
        for identifier in [DIRECTION_ID, NAMESPACE_ID]:
            for payload in ['{"#","' + identifier + '"}',
                            '{"#","' + identifier + '",0}',
                            '{"#",' + identifier.upper() + ',0}',
                            '{"T",' + identifier.upper() + '}',
                            '{"T",' + identifier + ',0}',
                            '{"t",' + identifier + '}',
                            '{"T",' + identifier + ',{}}',
                            '{"#",' + identifier + ',{"U"}}']:
                with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(payload)
        for payload in ['{"#",' + DIRECTION_ID + '}',
                        '{"#",' + NAMESPACE_ID + ',0}',
                        '{"#",' + NAMESPACE_ID + ',{}}',
                        '{"#",' + NAMESPACE_ID.upper() + '}',
                        '{"#",00000000-0000-0000-0000-000000000000,0}']:
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read(payload)

    def test_all_record_truncations_are_catchable_and_do_not_poison_reader(self):
        for value in [BEGIN, END, SEARCH_DIRECTIONS, BSLType.SEARCH_DIRECTION,
                      BSLType.SEARCH_DIRECTIONS]:
            payload = write(value)
            for end in range(len(payload)):
                with self.subTest(value=str(value), end=end), self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                    read(payload[:end])
            restored = read(payload)
            self.assertIs(restored, None if value is SEARCH_DIRECTIONS else value)

    def test_enum_values_and_types_survive_all_supported_containers(self):
        contents = array(BEGIN, END, BSLType.SEARCH_DIRECTION, BSLType.SEARCH_DIRECTIONS)
        record = BSLStructure('Begin,End,Kind,NamespaceKind', *contents.items)
        mapping = BSLMap()
        for key, value in [(BEGIN, 'begin'), (END, 'end'),
                           (Decimal(0), 'zero'), (Decimal(1), 'one'),
                           (False, 'false'), (True, 'true'),
                           (BSLRoundMode.ROUND15_AS10, 'round')]:
            mapping.insert(key, value)
        for original in [contents, BSLFixedArray(contents), record, BSLFixedStructure(record),
                         mapping, BSLFixedMap(mapping), BSLKeyAndValue(BEGIN, END)]:
            with self.subTest(kind=type_of(original)):
                restored = read(write(original))
                self.assertIs(type_of(restored), type_of(original))
                if type(original) in (BSLMap, BSLFixedMap):
                    self.assertEqual(len(restored._items), 7)
                    for key, value in mapping._items.values():
                        self.assertEqual(restored.get(key), value)
                elif type(original) in (BSLStructure, BSLFixedStructure):
                    for name, expected in zip(('Begin', 'End', 'Kind', 'NamespaceKind'), contents.items):
                        self.assertIs(restored.get_member(name), expected)
                elif type(original) is BSLKeyAndValue:
                    self.assertIs(restored.key, BEGIN)
                    self.assertIs(restored.value, END)
                else:
                    for left, right in zip(original.items, restored.items):
                        self.assertIs(left, right)

    def test_namespace_readback_transform_preserves_adjacent_values(self):
        contents = array(SEARCH_DIRECTIONS, BEGIN, END, BSLType.SEARCH_DIRECTIONS, ROUND_MODES)
        for original in [contents, BSLFixedArray(contents)]:
            restored = read(write(original))
            self.assertIs(type_of(restored), type_of(original))
            self.assertEqual(list(restored.items), [None, BEGIN, END, BSLType.SEARCH_DIRECTIONS, None])

    def test_decimal_context_is_unchanged_on_success_and_rejection(self):
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_DOWN
            context.flags[Rounded] = True
            for signal in context.traps:
                context.traps[signal] = True
            before = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            for value in [BEGIN, END, SEARCH_DIRECTIONS, BSLType.SEARCH_DIRECTION,
                          BSLType.SEARCH_DIRECTIONS, array(BEGIN, Decimal('1.234'), END)]:
                read(write(value))
            with self.assertRaisesRegex(ValueError, FORMAT_ERROR):
                read('{"#",' + DIRECTION_ID + ',1.0}')
            after = context.prec, context.rounding, dict(context.flags), dict(context.traps)
            self.assertEqual(after, before)

    def test_resource_limits_cover_enum_and_namespace_nodes(self):
        # Small patched budgets check exact boundaries without large allocations.
        for value in [BEGIN, SEARCH_DIRECTIONS, BSLType.SEARCH_DIRECTIONS]:
            payload = write(value)
            with patch.object(serialization, '_MAX_TEXT', len(payload)):
                self.assertEqual(write(value), payload)
                read(payload)
            with patch.object(serialization, '_MAX_TEXT', len(payload) - 1):
                for operation, argument in [(write, value), (read, payload)]:
                    with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                        operation(argument)
        allowed = array(BEGIN, SEARCH_DIRECTIONS)
        rejected = array(BEGIN, SEARCH_DIRECTIONS, END)
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_NODES', 3):
            self.assertEqual(write(allowed), allowed_payload)
            self.assertEqual(read(allowed_payload).items, [BEGIN, None])
            for operation, argument in [(write, rejected), (read, rejected_payload)]:
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)
        allowed, rejected = array(array(BEGIN)), array(array(array(END)))
        allowed_payload, rejected_payload = write(allowed), write(rejected)
        with patch.object(serialization, '_MAX_DEPTH', 2):
            self.assertEqual(write(allowed), allowed_payload)
            read(allowed_payload)
            for operation, argument in [(write, rejected), (read, rejected_payload)]:
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    operation(argument)


class SearchDirectionNativeEvidenceTests(unittest.TestCase):
    """Read committed owner observations without changing probe/golden files."""

    @classmethod
    def setUpClass(cls):
        lines = (ROOT / 'integrational_tests/output/strings.out').read_text(
            encoding='utf-8-sig').splitlines()
        cls.records = {}
        for line in lines:
            if line.startswith('search.enum.'):
                label, payload = line.split(': [', 1)
                if label in cls.records or not payload.endswith(']'):
                    raise AssertionError('Malformed or duplicated native enum observation: ' + label)
                cls.records[label] = payload[:-1]

    def test_native_value_namespace_type_and_readback_payloads(self):
        for name, value in [('begin', BEGIN), ('end', END), ('namespace', SEARCH_DIRECTIONS)]:
            prefix = 'search.enum.' + name
            self.assertEqual(write(value), self.records[prefix + '.payload'])
            self.assertEqual(write(type_of(value)), self.records[prefix + '.type'])
            self.assertEqual(write(to_string(value)), self.records[prefix + '.string'])
            restored = read(write(value))
            self.assertEqual(write(restored), self.records[prefix + '.readback'])
            self.assertEqual(write(type_of(restored)), self.records[prefix + '.readback-type'])

    def test_native_enum_boundary_and_collection_observations(self):
        vm = Interpreter()
        expressions = {
            'aliases': '(НаправлениеПоиска.СНачала = SearchDirection.FromBegin And '
                       'НаправлениеПоиска.СКонца = SearchDirection.FromEnd)',
            'type-ru': '(Type("НаправлениеПоиска") = TypeOf(SearchDirection.FromBegin))',
            'type-en': '(Type("SearchDirection") = TypeOf(SearchDirection.FromEnd))',
            'distinct': '(SearchDirection.FromBegin = SearchDirection.FromEnd)',
            'not-number': '(SearchDirection.FromBegin = 0)',
        }
        for label, expression in expressions.items():
            with self.subTest(label=label):
                self.assertEqual(write(vm.execute(expression)), self.records['search.enum.' + label])
        for label, source in [
                ('namespace-type-ru', 'Type("ПеречислениеНаправлениеПоиска")'),
                ('namespace-type-en', 'Type("EnumSearchDirection")'),
                ('readonly', 'SearchDirection.FromBegin = SearchDirection.FromEnd;'),
                ('constructor', 'New SearchDirection')]:
            with self.subTest(label=label):
                self.assertEqual(self.records['search.enum.' + label], 'error')
                with self.assertRaises(BSLRuntimeError):
                    vm.execute(source)
        self.assertEqual(write(''.join(write(value) + ';' for value in SEARCH_DIRECTIONS)),
                         self.records['search.enum.iteration'])
        restored = read(write(array(BEGIN, END)))
        self.assertEqual(write(restored.items == [BEGIN, END]), self.records['search.enum.array-readback'])
        mapping = BSLMap()
        mapping.insert(BEGIN, 'begin')
        mapping.insert(END, 'end')
        restored = read(write(mapping))
        self.assertEqual(write(len(restored._items) == 2 and restored.get(BEGIN) == 'begin'
                               and restored.get(END) == 'end'), self.records['search.enum.map-readback'])


if __name__ == '__main__':
    unittest.main()
