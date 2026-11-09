"""Local compressed snapshots; only degree-zero scalar has native evidence."""
from dataclasses import FrozenInstanceError
from decimal import Decimal as D
import unittest
from unittest.mock import patch
import zlib

from yadinassi import Interpreter, BSLError
from yadinassi.data_compression import BSLDeflation, compression_degree
from yadinassi.file_io import BSLBinaryData
from yadinassi.structures import BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_storage import BSLValueStorage, Snapshot, SnapshotError
from yadinassi.values import BSLArray, BSLType


def array(*values):
    result = BSLArray(); result.items = list(values); return result


def malformed(root):
    return BSLValueStorage._from_snapshot(Snapshot(root))


class ValueStorageCompressionTests(unittest.TestCase):
    def test_official_aliases_and_identity(self):
        vm = Interpreter()
        try:
            vm.execute('A=New Deflation; B=Новый СжатиеДанных(9); '
                       'X=TypeOf(A); Y=Тип("СжатиеДанных");')
            self.assertIs(vm.variables['x'], BSLType.DEFLATION)
            self.assertIs(vm.variables['y'], BSLType.DEFLATION)
            self.assertIs(type_by_name('Deflation'), BSLType.DEFLATION)
            self.assertIs(type_of(BSLDeflation()), BSLType.DEFLATION)
            with self.assertRaises(BSLError): vm.execute('New DataCompression;')
        finally: vm.close()

    def test_integer_levels_and_default(self):
        self.assertEqual(compression_degree(BSLDeflation()), -1)
        self.assertEqual(compression_degree(None), 0)
        for level in range(-1, 10):
            with self.subTest(level=level):
                settings = BSLDeflation(D(level))
                self.assertEqual(compression_degree(settings), level)
                self.assertEqual(BSLValueStorage('text', settings).get(), 'text')

    def test_invalid_settings_and_levels(self):
        for value in (True, False, 1, '9', D('-2'), D('10'), D('0.5'),
                      D('NaN'), D('Infinity'), D('1e100000')):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                BSLDeflation(value)
        for settings in ('bad', D(1), True, object()):
            with self.assertRaises(TypeError): BSLValueStorage('x', settings)

    def test_settings_are_immutable_and_have_no_invented_properties(self):
        value = BSLDeflation()
        with self.assertRaises(FrozenInstanceError): value._degree = 9
        for name in ('Level', 'CompressionDegree', 'СтепеньСжатия', '_degree'):
            with self.subTest(name=name), self.assertRaises(ValueError): value.get_member(name)
        with self.assertRaises(ValueError): str(value)
        with self.assertRaises(ValueError): str(BSLType.DEFLATION)

    def test_settings_themselves_remain_nonportable(self):
        from yadinassi.serialization import value_to_string_internal
        for value in (BSLDeflation(), BSLType.DEFLATION):
            with self.assertRaises(ValueError): value_to_string_internal(value)
            with self.assertRaises(SnapshotError): BSLValueStorage(value)

    def test_omitted_compression_and_degree_zero_do_not_compress(self):
        with patch('yadinassi.value_storage.compress_payload', side_effect=AssertionError('no zlib')):
            for settings in (None, BSLDeflation(D(0))):
                self.assertEqual(BSLValueStorage('text', settings).get(), 'text')
                self.assertEqual(BSLValueStorage(BSLBinaryData.from_bytes(b'bytes'), settings).get()._data, b'bytes')

    def test_repetitive_text_is_actually_compressed(self):
        text = 'Привет 😀' * 1000
        holder = BSLValueStorage(text, BSLDeflation(D(9)))
        root = holder._snapshot._root
        self.assertEqual(root[0], 'string_zlib')
        self.assertLess(len(root[1]), len(text.encode('utf-8')) // 10)
        self.assertEqual(holder.get(), text)

    def test_binary_and_empty_payloads_roundtrip_all_levels(self):
        for data in (b'', bytes(range(256)) * 8, b'a' * 4096):
            for level in range(-1, 10):
                with self.subTest(length=len(data), level=level):
                    holder = BSLValueStorage(BSLBinaryData.from_bytes(data), BSLDeflation(D(level)))
                    a, b = holder.get(), holder.get()
                    self.assertEqual(a._data, data); self.assertEqual(b._data, data)
                    self.assertIsNot(a, b)

    def test_unicode_surrogates_nul_and_empty_text(self):
        for text in ('', '\x00', '\ud800', '\udfff', 'Я😀\ud800\x00'):
            with self.subTest(text=ascii(text)):
                self.assertEqual(BSLValueStorage(text, BSLDeflation()).get(), text)

    def test_nested_collections_and_storages_stay_independent(self):
        child = array('a' * 100)
        source = array(child, child, BSLValueStorage(array('inner'), BSLDeflation()))
        holder = BSLValueStorage(source, BSLDeflation())
        child.items[0] = 'changed'
        first, second = holder.get(), holder.get()
        self.assertEqual(first.items[0].items, ['a' * 100])
        self.assertIsNot(first.items[0], first.items[1])
        first.items[0].items.append('new')
        self.assertEqual(second.items[0].items, ['a' * 100])
        self.assertEqual(first.items[2].get().items, ['inner'])

    def test_logical_text_budget_is_enforced_before_compression(self):
        with patch('yadinassi.value_storage.MAX_TEXT_UNITS', 4):
            with self.assertRaises(SnapshotError): BSLValueStorage('😀😀x', BSLDeflation())
            self.assertEqual(BSLValueStorage('😀😀', BSLDeflation()).get(), '😀😀')

    def test_aggregate_text_budget_is_enforced_again_on_get(self):
        holder = BSLValueStorage(array('abc', 'def'), BSLDeflation())
        with patch('yadinassi.value_storage.MAX_TEXT_UNITS', 5):
            with self.assertRaises(SnapshotError): holder.get()

    def test_binary_capture_and_restore_budgets_are_unchanged(self):
        source = array(BSLBinaryData.from_bytes(b'ab'), BSLBinaryData.from_bytes(b'cd'))
        holder = BSLValueStorage(source, BSLDeflation())
        with patch('yadinassi.value_storage.MAX_BINARY_BYTES', 3):
            with self.assertRaises(SnapshotError): BSLValueStorage(source, BSLDeflation())
            with self.assertRaises(SnapshotError): holder.get()

    def test_compressed_byte_budget_applies_to_capture_and_restore(self):
        holder = BSLValueStorage('abc', BSLDeflation())
        with patch('yadinassi.value_storage.MAX_COMPRESSED_BYTES', 1):
            with self.assertRaises(SnapshotError): BSLValueStorage('abc', BSLDeflation())
            with self.assertRaises(SnapshotError): holder.get()

    def test_compression_does_not_erase_node_depth_or_cycle_limits(self):
        root = array(array('value'))
        holder = BSLValueStorage(root, BSLDeflation())
        with patch('yadinassi.value_storage.MAX_DEPTH', 1):
            with self.assertRaises(SnapshotError): BSLValueStorage(root, BSLDeflation())
            with self.assertRaises(SnapshotError): holder.get()
        with patch('yadinassi.value_storage.MAX_NODES', 2):
            with self.assertRaises(SnapshotError): holder.get()
        root.items.append(root)
        with self.assertRaises(SnapshotError): BSLValueStorage(root, BSLDeflation())

    def test_corrupt_truncated_and_concatenated_payloads_fail(self):
        packed = zlib.compress(b'abc')
        for data in (b'bad', packed[:-1], packed + b'trailing', packed + packed):
            for tag in ('string_zlib', 'binary_zlib'):
                with self.subTest(tag=tag, data=data), self.assertRaises(SnapshotError):
                    malformed((tag, data, 3)).get()

    def test_length_framing_and_type_checks_fail_closed(self):
        packed = zlib.compress(b'abc')
        for size in (-1, 0, 2, 4, True, D(3), 10**100):
            with self.subTest(size=size), self.assertRaises(SnapshotError):
                malformed(('binary_zlib', packed, size)).get()
        for data in (bytearray(packed), None, 'bad'):
            with self.assertRaises(SnapshotError): malformed(('binary_zlib', data, 3)).get()

    def test_deflate_bomb_is_bounded_by_declared_and_logical_lengths(self):
        packed = zlib.compress(b'a' * 100000)
        with self.assertRaises(SnapshotError): malformed(('binary_zlib', packed, 3)).get()
        with patch('yadinassi.value_storage.MAX_BINARY_BYTES', 100):
            with self.assertRaises(SnapshotError): malformed(('binary_zlib', packed, 100000)).get()

    def test_invalid_text_encoding_fails_without_publishing(self):
        with self.assertRaises(SnapshotError): malformed(('string_zlib', zlib.compress(b'\xff'), 1)).get()

    def test_missing_or_hostile_settings_never_call_subclass_hooks(self):
        calls = []
        class Hostile(BSLDeflation):
            @property
            def _degree(self): calls.append('property'); return 9
        with self.assertRaises(TypeError): BSLValueStorage('x', object.__new__(Hostile))
        with self.assertRaises(ValueError): BSLValueStorage('x', object.__new__(BSLDeflation))
        settings = BSLDeflation(); object.__setattr__(settings, '_degree', True)
        with self.assertRaises(ValueError): BSLValueStorage('x', settings)
        self.assertEqual(calls, [])

    def test_bilingual_and_dynamic_bsl_workflows(self):
        vm = Interpreter()
        try:
            vm.execute('D=Новый СжатиеДанных(9); V=Новый Структура("Text", "Привет"); '
                       'S=Новый ХранилищеЗначения(V,D); V.Text="changed"; R=S.Получить(); '
                       'P=New Array; P.Add(V); P.Add(D); S2=New(Type("ValueStorage"),P); R2=S2.Get();')
            self.assertEqual(vm.execute('R.Text'), 'Привет')
            self.assertEqual(vm.execute('R2.Text'), 'changed')
        finally: vm.close()

    def test_optional_slot_and_required_value_guard(self):
        vm = Interpreter()
        try:
            vm.execute('S=New ValueStorage("x",); V=S.Get();')
            self.assertEqual(vm.variables['v'], 'x')
            for source in ('New ValueStorage(,);', 'New ValueStorage();',
                           'New ValueStorage(1, New Deflation, 2);', 'New Deflation(1,2);'):
                with self.subTest(source=source), self.assertRaises(BSLError): vm.execute(source)
        finally: vm.close()

    def test_bsl_catches_corruption_without_damaging_other_storage(self):
        vm = Interpreter()
        try:
            vm.variables['broken'] = malformed(('string_zlib', b'bad', 2))
            vm.execute('Good=New ValueStorage("keep",New Deflation); '
                       'Caught=False; Try X=Broken.Get(); Except Caught=True; EndTry; Y=Good.Get();')
            self.assertIs(vm.variables['caught'], True); self.assertEqual(vm.variables['y'], 'keep')
        finally: vm.close()
