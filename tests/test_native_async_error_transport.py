"""Exact generated error/marker routines with a bounded JSON serializer double.

The documented automatic WriteJSON mapping accepts Undefined as JSON null and
rejects unlisted types, including BSL Null. This double models only the subset
used by these routines, not a native JSON implementation or API-alias inventory.
The VM executes unchanged source slices; strings are escaped only by Python's
strict JSON serializer. Neither these tests nor a Python model establish that
this correction repairs the native case-6 syntax failure. A native rerun remains
necessary. See docs/native-client-async-measurement.md for primary references.
"""
from decimal import Decimal
import json
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.error_info import BSLErrorInfo
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray, BSLObject, HostFunction, NULL
import test_native_async_protocol as protocol
from test_native_async_fixture import without_error_payload_sentinels

suite = protocol.suite
NONCE = 'a' * 32
PATH = '/offline-controlled/completed.json'  # Never opened on disk.
FIELDS = ('description', 'code', 'additional', 'category', 'cause', 'module', 'line', 'source')
ADVERSARIAL = ('"quoted"', r'back\slash', 'CR\rLF\nTAB\t',
               ''.join(chr(code) for code in range(32)), 'Кириллица 😀',
               '\\n is not a newline', '"\\\r\n\t\x00\x01\x1f')


def json_subset(value):
    """No generic str(), fallback encoder, Null normalization, or hand escaping."""
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is Decimal:
        if not value.is_finite() or value != value.to_integral_value():
            raise TypeError('Outside this fixture integer-only serializer subset')
        return int(value)
    if type(value) is BSLArray:
        return [json_subset(item) for item in value]
    if type(value) is BSLStructure:
        return {item.key: json_subset(item.value) for item in value}
    # BSL Null is not in the documented automatic-serialization type list.
    # This model deliberately rejects it; no native exception text is inferred.
    raise TypeError('Unsupported controlled JSON input type')


def encode(value):
    return json.dumps(json_subset(value), ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def bsl_array(values):
    result = BSLArray()
    result.items[:] = [bsl_array(item) if type(item) is list
                       else Decimal(item) if type(item) is int else item for item in values]
    return result


class ControlledUTF8(BSLObject):
    def __init__(self, text, encoding, bom):
        assert type(text) is str and encoding == 'UTF-8' and bom is False
        self.size = len(text.encode('utf-8'))

    def get_member(self, name):
        if name != 'Size':
            raise ValueError('Unexpected source spelling')
        return HostFunction(name, lambda: Decimal(self.size))


class ControlledWriter(BSLObject):
    def __init__(self):
        self.opened = self.closed = False
        self.raw = None
        self.value = None

    def open_file(self, path, encoding, bom):
        assert path == PATH and encoding == 'UTF-8' and bom is False
        assert not self.opened
        self.opened = True

    def write(self, value):
        assert self.opened and not self.closed and self.raw is None
        self.value = value
        self.raw = encode(value)

    def close(self):
        assert self.opened and self.raw is not None
        self.closed = True

    def get_member(self, name):
        method = {'ОткрытьФайл': self.open_file, 'Закрыть': self.close}.get(name)
        if method is None:
            raise ValueError('Unexpected source spelling')
        return HostFunction(name, method, returns_value=False)


UNAVAILABLE_GETTERS = ('Description', 'Code', 'AdditionalInformation',
                       'IsErrorOfCategory', 'Cause', 'ModuleName', 'LineNumber', 'InitialString')


def harness(case_id=6, *, previous=False):
    module = suite.async_client_module(case_id).decode('utf-8-sig')
    if previous:
        # Negative control only: exact inverse to the reviewed previous template.
        module = without_error_payload_sentinels(module)
    vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
    writer = ControlledWriter()
    vm.register_type('ЗаписьJSON', lambda: writer)
    vm.register_function('ЗаписатьJSON', lambda actual, value: actual.write(value), returns_value=False)
    vm.register_function('GetBinaryDataFromString', ControlledUTF8)
    # Source-driven exact slices. No reimplementation of the BSL branches.
    for start, end in (
        ('&НаКлиенте\nФункция АсинхНомерСлучая()', '&НаКлиенте\nФункция АсинхКонтекстПробы()'),
        ('&НаКлиенте\nФункция АсинхПара(', '&AtClient\nProcedure AsyncExpectToken('),
        ('&НаКлиенте\nПроцедура АсинхЗаписатьЗавершение(', '&НаКлиенте\nАсинх Процедура АсинхКореньПробы()'),
    ):
        vm.execute(module[module.index(start):module.index(end)], source='offline-exact-generated-routines')
    vm.execute('Var АсинхЗапрос, АсинхКонтекст, АсинхТрасса, АсинхЗначения, АсинхОшибки; '
               'Var АсинхЗавершено, АсинхНесовместимо, АсинхСбой; '
               'АсинхКонтекст = "client"; АсинхЗавершено = False; '
               'АсинхНесовместимо = False; АсинхСбой = False; '
               'АсинхОшибки = New Array;')
    vm.variables['асинхзапрос'] = BSLStructure('nonce,completed', NONCE, PATH)
    trace, values, errors = protocol.observation(case_id)
    vm.variables['асинхтрасса'] = bsl_array(trace)
    vm.variables['асинхзначения'] = bsl_array(values)
    return vm, writer, values, errors


def capture(vm, error, slot=1, phase=1, *, unavailable=()):
    vm.variables['savederror'] = error
    get_member = BSLErrorInfo.get_member

    def controlled_member(actual, name):
        if actual is error and name in unavailable:
            raise ValueError('Controlled unavailable property')
        return get_member(actual, name)

    # Fault injection on the existing exact type, not invented native members,
    # type identities, source rewrites, or changes to the production runtime.
    with mock.patch.object(BSLErrorInfo, 'get_member', controlled_member):
        vm.execute(f'АсинхСохранитьОшибку({slot}, {phase}, SavedError);')


def complete(vm):
    vm.execute('Caught = False; Try АсинхЗаписатьЗавершение(1, 0); '
               'Except Caught = True; EndTry;')


class GeneratedErrorTransportTests(unittest.TestCase):
    def test_strict_serializer_subset_never_coerces_null_or_unknown_types(self):
        self.assertEqual(encode(None), b'null')
        self.assertEqual(encode(bsl_array([None, True, 7, '"\\\n'])), b'[null,true,7,"\\"\\\\\\n"]')
        for value in (NULL, object(), b'null', 1.5, Decimal('NaN'), Decimal('1.5')):
            with self.subTest(value=type(value).__name__), self.assertRaises(TypeError):
                encode(value)
        for value in (bsl_array([NULL]), BSLStructure('sentinel', NULL)):
            with self.assertRaises(TypeError):
                encode(value)

    def test_actual_field_routine_serializes_undefined_and_rejections_as_json_null(self):
        samples = ((None, 0, [1, None], False), (None, 1, [1, None], False),
                   (None, 2, [1, None], False), (None, 3, [0, None], True),
                   ('x' * 513, 0, [0, None], True), ('я' * 257, 3, [0, None], True),
                   (Decimal(-1), 1, [0, None], True), (Decimal('1.5'), 0, [0, None], True),
                   (NULL, 0, [0, None], True))
        for value, mode, expected, incompatible in samples:
            with self.subTest(value=type(value).__name__, mode=mode):
                vm, _, _, _ = harness()
                vm.variables['inputvalue'] = value
                vm.execute(f'Pair = АсинхПоле(InputValue, {mode});')
                self.assertEqual(json.loads(encode(vm.execute('Pair'))), expected)
                self.assertEqual(vm.execute('АсинхНесовместимо'), incompatible)

    def test_all_eight_unavailable_defaults_remain_tag_zero(self):
        for case_id in range(8):
            vm, _, _, _ = harness(case_id)
            capture(vm, BSLErrorInfo('private controlled error'), slot=0, phase=0,
                    unavailable=UNAVAILABLE_GETTERS)
            descriptor = json.loads(encode(vm.execute('АсинхОшибки[0]')))
            self.assertEqual({field: descriptor[field] for field in FIELDS},
                             {field: [0, None] for field in FIELDS})
            self.assertFalse(vm.execute('АсинхНесовместимо'))
            suite._async_private_error(descriptor)

    def test_tag_zero_and_tag_one_preserve_distinct_public_fingerprints(self):
        projected = []
        for unavailable, expected_tag in (((), 1), (('Cause',), 0)):
            vm, _, _, _ = harness()
            capture(vm, BSLErrorInfo('error'), unavailable=unavailable)
            descriptor = json.loads(encode(vm.execute('АсинхОшибки[0]')))
            self.assertEqual(descriptor['cause'], [expected_tag, None])
            projected.append(suite._async_private_error(descriptor))
        self.assertNotEqual(projected[0][5:], projected[1][5:])

    def test_actual_descriptor_and_completed_marker_roundtrip_adversarial_strings(self):
        for case_id in range(8):
            for text in ADVERSARIAL:
                with self.subTest(case=case_id, text=repr(text)):
                    vm, writer, values, errors = harness(case_id)
                    error = BSLErrorInfo(text, code=text, additional_information=text,
                                         module_name=text, line_number=17, initial_string=text)
                    for slot, pair in enumerate(values):
                        if pair[0] == 7:
                            capture(vm, error, slot, errors[pair[1]][0])
                    complete(vm)
                    self.assertFalse(vm.execute('Caught'))
                    self.assertTrue(writer.opened and writer.closed)
                    marker = suite.strict_json(writer.raw, max_depth=5)
                    self.assertEqual(marker, json.loads(writer.raw))
                    for descriptor in marker['errors']:
                        for field in ('description', 'code', 'additional', 'module', 'source'):
                            self.assertEqual(descriptor[field], [2, text])
                        self.assertEqual(descriptor['cause'], [1, None])
                    # Unchanged production acceptance: no patched validator or schema.
                    suite.validate_async_marker(marker, NONCE, case_id, 'completed')
                    self.assertFalse(vm.execute('АсинхНесовместимо'))
                    self.assertLessEqual(len(writer.raw), suite.ASYNC_MAX_MARKER)

    def test_actual_completion_accepts_unavailable_and_undefined_fields_without_merging_tags(self):
        for unavailable in ((), UNAVAILABLE_GETTERS):
            vm, writer, values, errors = harness()
            error = BSLErrorInfo(None, code=None, additional_information=None,
                                 module_name='module', line_number=17, initial_string='source')
            for slot, pair in enumerate(values):
                if pair[0] == 7:
                    capture(vm, error, slot, errors[pair[1]][0], unavailable=unavailable)
            complete(vm)
            self.assertFalse(vm.execute('Caught'))
            self.assertTrue(writer.opened and writer.closed)
            marker = suite.strict_json(writer.raw, max_depth=5)
            for descriptor in marker['errors']:
                for field in ('description', 'code', 'additional', 'cause'):
                    self.assertEqual(descriptor[field], [0 if unavailable else 1, None])
                if unavailable:
                    self.assertEqual([descriptor[field] for field in FIELDS], [[0, None]] * 8)
            suite.validate_async_marker(marker, NONCE, 6, 'completed')

    def test_previous_null_sentinel_is_rejected_by_the_same_strict_double(self):
        for unavailable in ((), UNAVAILABLE_GETTERS):
            vm, writer, _, _ = harness(previous=True)
            capture(vm, BSLErrorInfo('error'), unavailable=unavailable)
            with self.assertRaises(TypeError):
                encode(vm.execute('АсинхОшибки[0]'))
            complete(vm)
            self.assertTrue(vm.execute('Caught'))
            self.assertTrue(writer.opened)
            self.assertFalse(writer.closed)
            self.assertIsNone(writer.raw)

    def test_semantic_null_and_undefined_value_tags_are_not_transport_sentinels(self):
        vm, _, _, _ = harness(3)
        vm.execute('АсинхСохранить(0, Null); АсинхСохранить(1, Undefined);')
        self.assertEqual(json.loads(encode(vm.execute('АсинхЗначения')))[:2], [[2, 0], [1, 0]])


if __name__ == '__main__':
    unittest.main()
