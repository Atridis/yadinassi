"""Host wire tests, not native managed-form or cross-context transfer evidence."""
from decimal import Decimal, localcontext
import json
import unittest

from yadinassi.dates import BSLDate, MAX_TICKS
from yadinassi.values import NULL
from yadinassi.ui.protocol import (CatalogRef, MAX_LINE_BYTES, PROTOCOL, UIError,
    decode_line, decode_value, encode_line, encode_value, validate_request)

CATALOG = '00000000-0000-0000-0000-000000000001'
RECORD = '00000000-0000-0000-0000-000000000002'


class UIValueTests(unittest.TestCase):
    def test_exact_scalar_roundtrip(self):
        values = (None, NULL, '', 'Кириллица\n😀', True, False,
                  Decimal('12345678901234567890.0001'), Decimal('-0.00'),
                  Decimal('1E+4096'), Decimal('1E-4096'), BSLDate(0),
                  BSLDate(12345), BSLDate(MAX_TICKS), CatalogRef(CATALOG, RECORD),
                  CatalogRef(CATALOG, '00000000-0000-0000-0000-000000000000'))
        with localcontext() as context:
            context.prec = 2
            for value in values:
                with self.subTest(value=value):
                    wire = encode_value(value)
                    restored = decode_value(decode_line(encode_line(wire)))
                    self.assertIs(type(restored), type(value))
                    self.assertEqual(restored, value)
                    self.assertEqual(encode_value(restored), wire)

    def test_undefined_null_are_not_conflated(self):
        self.assertNotEqual(encode_value(None), encode_value(NULL))
        self.assertIsNone(decode_value({'type': 'Undefined'}))
        self.assertIs(decode_value({'type': 'Null'}), NULL)

    def test_no_host_objects_containers_or_coercion(self):
        class Text(str): pass
        for value in (1, 1.5, [], {}, object(), Text('x'), bytes(16),
                      Decimal('NaN'), Decimal('Infinity'), Decimal('1E+4097'),
                      Decimal('1' * 129), Decimal('1' * 2048), BSLDate(0, boundary=True)):
            with self.subTest(type=type(value)), self.assertRaises(UIError):
                encode_value(value)

    def test_reject_forged_typed_values(self):
        values = (None, [], {}, {'type': []}, {'type': 'Boolean', 'value': 1},
                  {'type': 'Number', 'value': 1}, {'type': 'Number', 'value': 'NaN'},
                  {'type': 'Number', 'value': '01'}, {'type': 'Number', 'value': '+1'},
                  {'type': 'Number', 'value': '1e2'}, {'type': 'Number', 'value': '1E+99999'},
                  {'type': 'Undefined', 'value': None}, {'type': 'Date', 'ticks': 0},
                  {'type': 'Date', 'ticks': '-1'}, {'type': 'Date', 'ticks': '01'},
                  {'type': 'Date', 'ticks': str(MAX_TICKS + 1)},
                  {'type': 'PythonObject', 'value': 'x'},
                  {'type': 'CatalogRef', 'catalog': CATALOG, 'record': RECORD, 'path': '/tmp'},
                  {'type': 'CatalogRef', 'catalog': 'Products', 'record': RECORD})
        for value in values:
            with self.subTest(value=value), self.assertRaises(UIError): decode_value(value)

    def test_uuid_canonical_scope_and_text_budgets(self):
        for catalog, record in ((RECORD.upper().replace('2', 'A'), RECORD),
                                ('0' * 36, RECORD),
                                ('00000000-0000-0000-0000-000000000000', RECORD),
                                (CATALOG, '{' + RECORD + '}')):
            with self.assertRaises(UIError): CatalogRef(catalog, record)
        for value in ('x' * 8193, '😀' * 2049, '\ud800'):
            with self.assertRaises(UIError): encode_value(value)


class UIProtocolTests(unittest.TestCase):
    def request(self):
        return {'jsonrpc': '2.0', 'id': 1, 'method': 'ui.hello', 'params': {'protocol': PROTOCOL}}

    def test_ndjson_roundtrip(self):
        message = self.request()
        wire = encode_line(message)
        self.assertEqual(wire.count(b'\n'), 1)
        self.assertEqual(validate_request(decode_line(wire)), message)

    def test_duplicate_keys_nonjson_numbers_encoding_and_frames(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                    b'{"x":1.0}', b'{"x":1e1}', b'{"x":123456789012}',
                    b'{}\n{}\n', b'{\n"x":1}', b'{}\r\n', b'\xff',
                    b'\xef\xbb\xbf{}', b'{', b'{"x":"\\ud800"}'):
            with self.subTest(raw=raw), self.assertRaises(UIError): decode_line(raw)

    def test_limits_are_enforced_before_recursive_parse_or_dispatch(self):
        for raw in (b' ' * (MAX_LINE_BYTES + 1), b'[' * 10000,
                    ('[0,' + '0,' * 9000 + '0]').encode(),
                    json.dumps({'x': 'a' * 8193}).encode()):
            with self.assertRaises(UIError): decode_line(raw)
        data = {}; data['cycle'] = data
        with self.assertRaises(UIError): encode_line(data)
        with self.assertRaises(UIError): encode_line({'x': 1.5})
        with self.assertRaises(UIError): encode_line({1: 'x'})
        with self.assertRaises(UIError): encode_line(['a' * 8000] * 18)

    def test_encoded_depth_is_decodable(self):
        for depth in range(20):
            value = 'x'
            for _ in range(depth): value = [value]
            try: raw = encode_line(value)
            except UIError: continue
            self.assertEqual(decode_line(raw), value)

    def test_closed_request_envelope(self):
        invalid = [[], {}, {'jsonrpc': '2.0', 'method': 'ui.hello', 'params': {}},
                   {**self.request(), 'id': True}, {**self.request(), 'id': 0},
                   {**self.request(), 'id': '1'}, {**self.request(), 'extra': 1},
                   {**self.request(), 'method': 'callProcedure'},
                   {**self.request(), 'params': {'protocol': PROTOCOL, 'code': 'Message(1)'}}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(UIError): validate_request(value)

    def test_finite_navigation_events_no_bsl_handler_fields(self):
        params = {'formId': 'catalog-browser', 'baseRevision': 0,
                  'event': 'selectCatalog', 'catalog': CATALOG}
        message = {**self.request(), 'method': 'ui.event', 'params': params}
        self.assertEqual(validate_request(message), message)
        for changed in ({**params, 'procedure': 'Save'}, {**params, 'event': 'Write'},
                        {**params, 'baseRevision': False}, {**params, 'formId': '../other'},
                        {**params, 'catalog': '/some/database'}):
            with self.assertRaises(UIError): validate_request({**message, 'params': changed})


if __name__ == '__main__': unittest.main()
