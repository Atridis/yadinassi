"""Whole-family JSON workflows; native calibration is a separate evidence gate."""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import os
import json
import random
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.json_processing import (
    BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings, BSLJSONLineBreak,
    BSLJSONValueType as T, read_json, write_json,
)
from yadinassi.values import BSLArray, BSLFixedArray, NULL
from yadinassi.structures import BSLStructure, BSLFixedStructure
from yadinassi.maps import BSLMap, BSLFixedMap


class JSONFamilyTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(lambda _: None)

    def read(self, text, mapping=False):
        r = BSLJSONReader(); r.set_string(text)
        return read_json(r, mapping)

    def write(self, value):
        w = BSLJSONWriter(); w.set_string(BSLJSONWriterSettings(BSLJSONLineBreak.NONE))
        write_json(w, value)
        return w.close()

    def test_bilingual_end_to_end(self):
        for reader, writer, read, write, setstring, close in (
            ('JSONReader', 'JSONWriter', 'ReadJSON', 'WriteJSON', 'SetString', 'Close'),
            ('ЧтениеJSON', 'ЗаписьJSON', 'ПрочитатьJSON', 'ЗаписатьJSON', 'УстановитьСтроку', 'Закрыть'),
        ):
            self.vm.execute(f'r=New {reader};r.{setstring}("{{""name"":""Привет"",""values"":[1.25,true,null]}}");'
                            f'x={read}(r);w=New {writer};w.{setstring}(New JSONWriterSettings(JSONLineBreak.None));'
                            f'{write}(w,x);s=w.{close}();')
            self.assertEqual(self.vm.execute('s'), '{"name":"Привет","values":[1.25,true,null]}')
            self.assertIs(self.vm.execute('x.values[2]'), None)
            self.assertEqual(self.vm.execute(f'(TypeOf(r)=Type("{reader}"))'), True)
            self.assertEqual(self.vm.execute(f'(TypeOf(w)=Type("{writer}"))'), True)

    def test_constructor_dispatch_does_not_call_host_equality(self):
        class Extension:
            def __eq__(self, other): raise AssertionError('unexpected constructor equality')
            def __call__(self): return D(42)
        self.vm.register_type('Extension', Extension())
        self.assertEqual(self.vm.execute('New Extension'), D(42))

    def test_null_enum_member_is_not_the_null_literal(self):
        for namespace in ('JSONValueType', 'ТипЗначенияJSON'):
            self.assertIs(self.vm.execute(namespace + '.Null'), T.NULL)
        self.assertIs(self.vm.execute('Null'), NULL)
        self.assertFalse(self.vm.execute('Null=1;'))
        self.assertIs(self.vm.execute('Null'), NULL)
        self.assertIs(self.vm.execute('TypeOf(JSONValueType.Null)'), self.vm.execute('Type("JSONValueType")'))

    def test_exact_decimal_null_boolean_unicode(self):
        values = self.read('[12345678901234567890.123456789,-2e-20,true,false,null,"\\uD83D\\uDE00"]')
        self.assertEqual(values.items, [D('12345678901234567890.123456789'), D('-2e-20'), True, False, None, '😀'])
        self.assertEqual(self.read(self.write(values)).items, values.items)
        self.assertEqual(self.write('\u2028\u2029'), '"\\u2028\\u2029"')

    def test_structure_map_and_fixed_collections(self):
        with self.assertRaises(ValueError): self.read('{"bad-key":1}')
        mapping = self.read('{"bad-key":1,"":2}', True)
        self.assertEqual(self.write(mapping), '{"bad-key":1,"":2}')
        for value in (BSLFixedMap(mapping), BSLFixedStructure(BSLStructure('a', D(1))),
                      BSLFixedArray(self.read('[1,2]'))):
            self.assertEqual(self.write(self.read(self.write(value), True)), self.write(value))
        mapping.insert(D(3), 'invalid')
        with self.assertRaises(TypeError): self.write(mapping)

    def test_nested_document_roundtrips(self):
        rng = random.Random(20261031)
        def value(depth):
            if depth == 0:
                return rng.choice([None, True, False, 12345678901234567890, -125, 'quote"\\\n', 'Привет😀'])
            kind = rng.randrange(3)
            if kind == 0: return [value(depth - 1) for _ in range(rng.randrange(5))]
            if kind == 1: return {f'key-{i}': value(depth - 1) for i in range(rng.randrange(5))}
            return value(0)
        for _ in range(100):
            expected = value(5)
            encoded = self.write(self.read(json.dumps(expected, ensure_ascii=False), True))
            self.assertEqual(json.loads(encoded), expected)

    def test_tokens_and_skip(self):
        r = BSLJSONReader(); r.set_string('[{"a":[1,2]},true,null]')
        self.assertIs(r.get_member('CurrentValueType'), T.NONE)
        with self.assertRaises(ValueError): r.get_member('CurrentValue')
        self.assertTrue(r.read()); self.assertIs(r.get_member('CurrentValueType'), T.START_ARRAY)
        with self.assertRaises(ValueError): r.get_member('CurrentValue')
        self.assertTrue(r.read()); self.assertIs(r._current[0], T.START_OBJECT)
        self.assertTrue(r.skip()); self.assertEqual(r._current, (T.BOOLEAN, True))
        self.assertTrue(r.read()); self.assertEqual(r._current, (T.NULL, None))
        self.assertTrue(r.read()); self.assertIs(r._current[0], T.END_ARRAY)
        self.assertFalse(r.read()); self.assertFalse(r.read())
        r.close()
        with self.assertRaises(ValueError): r.read()

    def test_read_subtree_and_continue(self):
        r = BSLJSONReader(); r.set_string('[{"a":1},2]'); r.read()
        self.assertEqual(self.write(read_json(r)), '{"a":1}')
        self.assertIs(r._current[0], T.END_OBJECT)
        self.assertEqual(read_json(r), D(2))
        r.read(); self.assertIs(r._current[0], T.END_ARRAY)

    def test_native_cursor_and_replacement(self):
        r = BSLJSONReader(); r.set_string('[1,2]'); r.read(); r.read()
        self.assertEqual(read_json(r), D(2))
        self.assertIsNone(read_json(r))
        r.close(); r.set_string('[1]'); r.read(); r.set_string('{"b":2}')
        self.assertEqual(read_json(r), D(1))
        r.close(); r.set_string('{"b":2}')
        self.assertEqual(self.write(read_json(r)), '{"b":2}')
        self.assertEqual(self.write(self.read('[1,]')), '[1]')
        self.assertEqual(self.write(self.read('["comma,]",[],]')), '["comma,]",[]]')
        for text in ('[,]', '[1,,]', '[,1,]', '{"a":1,}'):
            with self.subTest(text=text), self.assertRaises(ValueError): self.read(text)

    def test_manual_writer_mixed_with_global(self):
        w = BSLJSONWriter(); w.set_string(BSLJSONWriterSettings(BSLJSONLineBreak.NONE))
        w.write_start_object(); w.write_property_name('a'); w.write_start_array()
        w.write_value('quote"\\\n'); write_json(w, BSLStructure('b', D(3)))
        w.write_end_array(); w.write_end_object()
        self.assertEqual(w.close(), '{"a":["quote\\"\\\\\\n",{"b":3}]}')
        with self.assertRaises(ValueError): w.write_value(D(1))

    def test_files_with_bom_and_encodings(self):
        with tempfile.TemporaryDirectory(prefix='yadinassi-json-') as tmp:
            for encoding, bom, prefix in [('UTF-8', False, b'"'), ('UTF-8', True, b'\xef\xbb\xbf'),
                                           ('UTF-16', True, b'\xff\xfe'), ('UTF-16', False, b'"\x00'), ('windows-1251', False, b'"')]:
                path = Path(tmp) / 'data.json'
                w = BSLJSONWriter(); w.open_file(str(path), encoding, bom); w.write_value('Привет')
                self.assertEqual(w.close(), '')
                self.assertTrue(path.read_bytes().startswith(prefix))
                r = BSLJSONReader(); r.open_file(str(path), encoding)
                self.assertEqual(read_json(r), 'Привет')
                r.close(); path.unlink()

    def test_file_lifecycle_errors_and_regular_file_guard(self):
        with tempfile.TemporaryDirectory(prefix='yadinassi-json-life-') as tmp:
            path = Path(tmp) / 'data.json'; path.write_bytes(b'previous')
            w = BSLJSONWriter()
            with self.assertRaises(ValueError): w.open_file(str(path), 'unsupported')
            self.assertEqual(path.read_bytes(), b'previous')
            w.open_file(str(path)); self.assertEqual(path.read_bytes(), b'')
            old = w._file; w.set_string(); self.assertTrue(old.closed)
            w.open_file(str(path), 'windows-1251'); stream = w._file; w.write_value('😀')
            with self.assertRaises(UnicodeError): w.close()
            self.assertTrue(stream.closed)
            if hasattr(os, 'mkfifo'):
                fifo = Path(tmp) / 'pipe'; os.mkfifo(fifo)
                with self.assertRaises(ValueError): BSLJSONReader().open_file(str(fifo))
                with self.assertRaises((ValueError, OSError)): w.open_file(str(fifo))

    def test_bsl_file_workflow_optional_slots(self):
        with tempfile.TemporaryDirectory(prefix='yadinassi-json-bsl-') as tmp:
            path = str(Path(tmp) / 'данные.json').replace('"', '""')
            self.vm.execute('p=New JSONWriterSettings(, "  ");'
                            'w=New JSONWriter;w.OpenFile("' + path + '",,True,New JSONWriterSettings(JSONLineBreak.None));'
                            'WriteJSON(w,New Structure("name", "Привет"));s=w.Close();'
                            'r=New JSONReader;r.OpenFile("' + path + '",);x=ReadJSON(r);r.Close();')
            self.assertEqual(self.vm.execute('s'), '')
            self.assertEqual(self.vm.execute('x.name'), 'Привет')
            self.assertTrue(Path(tmp, 'данные.json').read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_explicit_internal_codec_refusal(self):
        for expression in ('New JSONReader', 'New JSONWriter', 'New JSONWriterSettings',
                           'JSONValueType.Number', 'JSONLineBreak.Auto', 'Type("JSONReader")'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute('ValueToStringInternal(' + expression + ')')

    def test_invalid_documents_and_types(self):
        for text in ('', '{', '[1,,]', '{"a":}', 'NaN', 'Infinity', '1 2', '"bad\nline"'):
            with self.subTest(text=text), self.assertRaises(ValueError): self.read(text)
        for value in (NULL, object(), D('NaN'), D('Infinity')):
            with self.subTest(value=type(value)), self.assertRaises((TypeError, ValueError)): self.write(value)
        for code in ('New JSONReader(1)', 'ReadJSON(1)', 'WriteJSON(1,2)', 'r=New JSONReader;r.SetString(1)',
                     'r=New JSONReader;r.CurrentValue=1', 'JSONValueType.Number=1',
                     's=New JSONWriterSettings(JSONLineBreak.None);s.NewLines=JSONLineBreak.Auto'):
            with self.subTest(code=code), self.assertRaises(BSLError): self.vm.execute(code)

    def test_bad_writer_sequences_and_reuse(self):
        w = BSLJSONWriter()
        with self.assertRaises(ValueError): w.write_value(D(1))
        w.set_string(); w.write_start_object()
        with self.assertRaises(ValueError): w.write_value(D(1))
        with self.assertRaises(ValueError): w.write_end_array()
        w.write_property_name('a')
        with self.assertRaises(ValueError): w.close()
        w.write_value(D(1)); w.write_end_object()
        self.assertEqual(self.write(self.read(w.close())), '{"a":1}')
        w.set_string(); w.write_value(True); self.assertEqual(w.close(), 'true')

    def test_cycles_resource_bounds_and_no_host_hooks(self):
        a = BSLArray(); a.add(a)
        with self.assertRaises(ValueError): self.write(a)
        class Hostile:
            def __str__(self): raise AssertionError('host hook')
        with self.assertRaises(TypeError): self.write(Hostile())
        with patch('yadinassi.json_processing.MAX_TEXT', 100):
            a = BSLArray(); a.add('x' * 80); a.add('x' * 80)
            with self.assertRaises(ValueError): self.write(a)
            with self.assertRaises(ValueError): BSLJSONReader().set_string(' ' * 101)
        with self.assertRaises(ValueError): self.write(D('1E1000000'))
        with self.assertRaises(ValueError): self.read('[' * 130 + '0' + ']' * 130)

    def test_procedure_semantics_and_private_surface(self):
        self.vm.execute('w=New JSONWriter;w.SetString();')
        for code in ('x=w.WriteStartObject()', 'x=WriteJSON(w,1)', 'x=w._parts', 'x=w.__class__'):
            with self.subTest(code=code), self.assertRaises(BSLError): self.vm.execute(code)
        self.vm.execute('WriteJSON(w,1);')
        self.assertEqual(self.vm.execute('w.Close()'), '1')

    def test_layout_and_settings_types(self):
        w = BSLJSONWriter(); w.set_string(BSLJSONWriterSettings(BSLJSONLineBreak.WINDOWS, '  '))
        write_json(w, self.read('{"a":[1,2]}'))
        self.assertEqual(w.close(), '{\r\n  "a": [\r\n    1,\r\n    2\r\n  ]\r\n}')
        for name in ('JSONValueType', 'JSONLineBreak', 'JSONWriterSettings'):
            self.assertIsNotNone(self.vm.execute(f'Type("{name}")'))


if __name__ == '__main__': unittest.main()
