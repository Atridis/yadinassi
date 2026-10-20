"""Native list streams plus defensive inverse models, never generated .out files."""
from decimal import Decimal as D
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.native_observations import extract_payload, inverse_stream, read_observation
from yadinassi import Interpreter, serialization
from yadinassi.serialization import value_from_string_internal as read
from yadinassi.serialization import value_to_string_internal as write
from yadinassi.type_values import type_of
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.value_lists import BSLValueList
from yadinassi.values import BSLArray, BSLType, NULL, equal

ROOT = Path(__file__).resolve().parents[1]


def sample():
    values = BSLValueList()
    values.add(D(10), 'first', True)
    values.add(D(20), 'second')
    return values


class ValueListCodecBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = (ROOT / 'integrational_tests/output/collections.out').read_text(encoding='utf-8-sig')

    def native(self, name):
        return read_observation(extract_payload(self.output, 'table.list.codec.' + name))

    def test_all_runtime_types_have_complete_codec_policy(self):
        self.assertEqual(serialization._CODECS, set(BSLType))
        self.assertEqual(set(serialization._TYPE_IDS), set(BSLType))

    def test_four_genuine_native_streams_and_fresh_identity(self):
        populated = BSLValueList()
        populated.add('Я😀', 'first', True)
        array = BSLArray()
        array.items = [D(10), NULL, None]
        populated.add(array, 'second')
        live = sample()
        history = sample()
        history.delete(D(0))
        history.insert(D(0), D(30), 'third', True)
        cases = [('empty', BSLValueList()), ('populated', populated),
                 ('item', live.items[0]), ('history', history)]
        for name, original in cases:
            with self.subTest(name=name):
                native = self.native(name)
                payload = native.get('Write')
                self.assertEqual(write(original), payload)
                self.assertEqual(write(type_of(original)), native.get('TypeWrite'))
                self.assertIs(read(native.get('TypeWrite')), type_of(original))
                self.assertIs(native.get('TypeRead').get('Equal'), True)
                self.assertIs(native.get('TypeRead').get('Stable'), True)
                restored = read(payload)
                self.assertIsNot(restored, original)
                self.assertEqual(str(type_of(restored)), native.get('ReadType'))
                self.assertEqual(write(restored), inverse_stream(native))
                self.assertIs(equal(original, restored), native.get('Equal'))
                view = native.get('ReadView')
                if name == 'item':
                    self.assertEqual(view.get('Fields').items,
                                     [restored.value, restored.presentation, restored.check])
                    self.assertIs(view.get('Saved'), False)
                    with self.assertRaisesRegex(ValueError, 'пока не поддерживается'):
                        restored.get_id()
                else:
                    self.assertEqual(restored.count(), view.get('Count'))
                    for item, fields in zip(restored.items, view.get('Items').items):
                        self.assertEqual(write(item.value), write(fields.items[0]))
                        self.assertEqual([item.presentation, item.check], fields.items[1:])
                        self.assertIs(restored.find_by_id(item.get_id()), item)
                    self.assertEqual(restored._next_id, original._next_id)
                if name == 'history':
                    for field in ('IDs', 'ReadIDs'):
                        self.assertEqual([item.get('ID') for item in native.get(field)], [D(2), D(1)])
                        self.assertTrue(all(item.get('Found') for item in native.get(field)))
                    self.assertEqual([i.get_id() for i in restored], [D(2), D(1)])
                    self.assertEqual(restored.add().get_id(), D(3))
        self.assertIsNot(read(write(populated)).items[1].value, array)

    def test_detached_item_and_history_empty_models_preserve_stream_ids(self):
        values = sample()
        item = values.items[0]
        values.clear()
        decoded = read(write(values))
        self.assertEqual(decoded.add().get_id(), D(2))
        self.assertEqual(read(write(item))._id, -1)
        self.assertEqual(write(read(write(item))), write(item))
        del values
        self.assertEqual(read(write(item))._id, -1)

    def test_nested_snapshots_are_independent_and_cycles_are_rejected(self):
        values = sample()
        graph = BSLArray()
        graph.items = [values, values, values.items[0]]
        restored = read(write(graph))
        self.assertIsNot(restored.items[0], restored.items[1])
        self.assertIsNot(restored.items[0].items[0], restored.items[2])
        restored.items[0].items[0].value = D(99)
        self.assertEqual(restored.items[1].items[0].value, D(10))
        for mode in ('list', 'item', 'array'):
            values = sample()
            item = values.items[0]
            item.value = values if mode == 'list' else item
            if mode == 'array':
                nested = BSLArray()
                nested.items = [values]
                item.value = nested
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'циклические'):
                write(values)
        self.assertEqual(write('ok'), '{"S","ok"}')

    def test_malformed_default_list_records_are_rejected(self):
        stream = self.native('populated').get('Write')
        replacements = [
            ('{6,', '{7,'), (serialization._LIST_ENTRY_ID, 'unknown'),
            (',0,0,\n{2', ',1,0,\n{2'), ('{2,\n', '{1,\n'),
            ('{"Pattern"}', '{"Pattern",{"N"}}'), ('{"Pattern"},0,1', '{"Pattern"},1,1'),
            ('{"Pattern"},0,1', '{"Pattern"},0,0'), ('{"Pattern"},0,1', '{"Pattern"},0,-2'),
            ('},1,0,""}', '},0,0,""}'), ('},1,0,""}', '},-1,0,""}'),
            ('},1,0,""}', '},01,0,""}'), ('},1,0,""}', '},1.5,0,""}'),
            ('{4,0,', '{4,1,'), ('{0},"",-1', '{0},"picture",-1'),
            ('"first",1,', '"first",2,'), ('"first",1,', '0,1,'),
            ('},0,0,""}', '},0,1,""}'), ('},0,0,""}', '},0,0,"unknown"}'),
        ]
        for old, new in replacements:
            self.assertIn(old, stream)
            with self.subTest(new=new), self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                read(stream.replace(old, new, 1))
        for kind in (BSLType.VALUE_LIST, BSLType.VALUE_LIST_ITEM):
            identifier = serialization._TYPE_IDS[kind]
            for body in ('', ',0', ',{}', ',{0}'):
                with self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                    read('{"#",' + identifier + body + '}')

    def test_standalone_item_malformed_fields_and_maximum_history_id(self):
        stream = self.native('item').get('Write')
        for old, new in [('"first",1,', '"first","1",'),
                         ('},0,0,""}', '},-2,0,""}'),
                         ('},0,0,""}', '},"0",0,""}'),
                         ('},0,0,""}', '},0,0}'),
                         ('{4,0,', '{5,0,'),
                         ('{0},"",-1,-1', '{0},"",0,-1')]:
            with self.subTest(new=new), self.assertRaisesRegex(ValueError, 'Ошибка формата потока'):
                read(stream.replace(old, new, 1))
        # A bounded defensive ID model, not a claimed native maximum.
        values = sample()
        values._next_id = 2 ** 32
        last = read(write(values))
        self.assertEqual(last._next_id, 2 ** 32)
        with self.assertRaisesRegex(ValueError, 'предел идентификаторов'):
            last.add()
        from yadinassi.type_qualifiers import BSLNumberQualifiers
        # Host-corrupted descriptors must not silently lose hidden qualifiers.
        object.__setattr__(values.value_type, "number_qualifiers", BSLNumberQualifiers(D(1)))
        with self.assertRaisesRegex(ValueError, 'квалификаторы отсутствующего типа'):
            write(values)

    def test_large_writer_accepted_lists_have_sufficient_parser_token_budget(self):
        # Native shapes repeated for defensive resource testing, not new native
        # size-limit claims. Default picture metadata exceeds eight tokens/node.
        values = BSLValueList()
        for index in range(4000):
            values.add(D(index), 'x')
        stream = write(values)
        self.assertEqual(len(stream), 397898)
        restored = read(stream)
        self.assertEqual(write(restored), stream)
        self.assertEqual(restored.add().get_id(), D(4000))
        # Nested snapshots must share the semantic budget, without an ad hoc
        # top-level size cap that hides the same asymmetry inside another type.
        nested = BSLValueList()
        for index in range(1000):
            child = BSLValueList()
            child.add(D(index), 'x')
            nested.add(child)
        stream = write(nested)
        self.assertEqual(write(read(stream)), stream)
        with patch('yadinassi.serialization._MAX_NODES', 2):
            # Grammar-level limits still apply before semantic validation to
            # hostile streams containing many otherwise meaningless tokens.
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read('{' + ','.join('0' for _ in range(64)) + '}')

    def test_resource_budgets_for_nodes_depth_text_and_identifiers(self):
        values = sample()
        stream = write(values)
        with patch('yadinassi.serialization._MAX_NODES', 3):
            for operation, value in ((write, values), (read, stream)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                    operation(value)
        with patch('yadinassi.serialization._MAX_DEPTH', 1):
            for operation, value in ((write, values), (read, stream)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                    operation(value)
        with patch('yadinassi.serialization._MAX_TEXT', 20):
            for operation, value in ((write, values), (read, stream)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                    operation(value)
        for replacement in ('4294967296', '9' * 100):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                read(stream.replace('{"Pattern"},0,1', '{"Pattern"},0,' + replacement))
        with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
            read(stream.replace('{2,\n', '{10001,\n', 1))

    def test_host_corruption_and_typed_constraint_never_silently_dropped(self):
        for change in ('duplicate', 'foreign', 'id', 'next', 'index', 'check', 'presentation', 'typed'):
            values = sample()
            if change == 'duplicate':
                values.items.append(values.items[0])
            elif change == 'foreign':
                values.items[0] = sample().items[0]
            elif change == 'id':
                values.items[0]._id = -1
            elif change == 'next':
                values._next_id = 1
            elif change == 'index':
                values._by_id[3] = values.items[0]
            elif change == 'check':
                values.items[0].check = D(1)
            elif change == 'presentation':
                values.items[0].presentation = None
            else:
                values.value_type = BSLTypeDescription('Number')
            with self.subTest(change=change), self.assertRaises(ValueError):
                write(values)

    def test_bsl_errors_are_catchable_and_do_not_mutate_assignment(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute('values = New ValueList; item = values.Add(); item.Value = values; saved = "unchanged"; '
                   'Try saved = ValueToStringInternal(values); Except Message("caught"); EndTry;')
        self.assertEqual(vm.execute('saved'), 'unchanged')
        self.assertEqual(output, ['caught'])

    def test_cli_transport_ignores_non_utf8_process_defaults(self):
        # Model the Windows parent pipe codec on Linux too. Also supply a
        # non-UTF8 inherited stdio setting; the CLI configures its own UTF-8.
        with patch('subprocess._text_encoding', return_value='cp1252'), \
                patch.dict(os.environ, {'PYTHONIOENCODING': 'cp1252'}):
            self.test_cli_roundtrip_all_text_transports()

    def test_cli_roundtrip_all_text_transports(self):
        code = ('values = New СписокЗначений; item = values.Add(1, "item"); '
                'copy = ValueFromStringInternal(ValueToStringInternal(values)); '
                'Message(TypeOf(copy) = Type("ValueList")); '
                'Message(copy.Get(0).GetID()); Message(copy.Get(0).Value);')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'Список.bsl'
            path.write_text(code, encoding='utf-8-sig')
            for args, stdin in ((("-c", code), None), ((str(path),), None),
                                (("-",), code), ((), code + '\n/exit\n')):
                with self.subTest(args=args):
                    result = subprocess.run([sys.executable, '-m', 'yadinassi', *args],
                                            input=stdin, encoding='utf-8', capture_output=True,
                                            env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                                            cwd=ROOT, timeout=30)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (0, 'Да\n0\n1\n', ''))


if __name__ == '__main__':
    unittest.main()
