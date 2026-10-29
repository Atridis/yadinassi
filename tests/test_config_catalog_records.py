"""Independent synthetic file layouts; not native compatibility evidence."""
from dataclasses import replace
from decimal import Decimal, localcontext
import unittest

import test_config_catalog_binding as fixture
from test_filedb_catalog import Source, P, u32

c = fixture.catalog
compiler = fixture.binding
records = __import__(fixture.PACKAGE + '.config_catalog_records', fromlist=['*'])
legacy = __import__(fixture.PACKAGE + '.filedb_records', fromlist=['*'])


def compiled(code=2, string=32, precision=9, scale=2):
    identity, attributes = fixture.identities(code, string, precision, scale)
    return compiler.compile_catalog_binding(identity, attributes, fixture.index(),
        profile=compiler.CatalogBindingProfile(compiler.PROFILE_IDENTIFIER), budget=c._Budget(c.CatalogLimits()))


def serialize(value):
    if type(value) is tuple:
        return '{' + ','.join(serialize(item) for item in value) + '}'
    if type(value) is str:
        return '"' + value.replace('"', '""') + '"'
    return str(value)


def text(value, capacity):
    raw = value.encode('utf-16-le')
    return (len(raw) // 2).to_bytes(2, 'little') + raw.ljust(capacity * 2, b'\xcc')


def current_row(amount=bytes.fromhex('1000000125'), mark=b'\0', payload=None):
    return (b'\0' + b'V' * 16 + b'R' * 16 + mark + b'P' * 16
            + text('K1', 2) + (text('alpha', 32) if payload is None else payload) + amount)


def changed_row(amount=bytes.fromhex('1000125000')):
    # Independently fixed 4/7/8,3 fixture, not derived from production placements.
    return b'\0' + b'V' * 16 + b'R' * 16 + b'\0' + b'P' * 16 + text('K007', 4) + text('Привет!', 7) + amount


def source(*, changed=False, raw=None, declarations=None, recordlock='0', format_item=0, data_header=8):
    shape = compiled(4, 7, 8, 3) if changed else compiled()
    stride = 81 if changed else 127
    row = changed_row() if changed else current_row()
    raw = b'\1' + b'\xab' * (stride - 1) + row if raw is None else raw
    value = Source(page_count=max(20, 11 + (len(raw) + P - 1) // P))
    value.catalog((2, 6, 10))
    for block, table, fields, files in ((2, 'CONFIG', (), (4, 5, 0)),
                                      (6, 'PARAMS', (), (6, 7, 0)),
                                      (10, shape.table_name, shape.declarations if declarations is None else declarations,
                                       (data_header, 9, 10))):
        desc = serialize((table, format_item if block == 10 else 0, ('Fields', *fields),
                          ('Indexes',), ('Recordlock', recordlock if block == 10 else '0'), ('Files', *files))).encode()
        value.chain(tuple(range(block, block + (len(desc) + 249) // 250)), desc)
    for page in (4, 5, 6, 7):
        value.page(page)[:24] = b'\x1c\xfd' + bytes(22)
    if data_header:
        head = value.page(data_header)
        head[:24] = b'\x1c\xfd' + bytes(14) + len(raw).to_bytes(8, 'little')
        for i in range((len(raw) + P - 1) // P):
            head[24 + i * 4:28 + i * 4] = u32(11 + i)
            value.page(11 + i)[:len(raw[i*P:(i+1)*P])] = raw[i*P:(i+1)*P]
    return value, shape


def prepared(value):
    reader = c.CatalogReader(value.read_at, value.size)
    catalog = reader.read_catalog()
    graph = c._CatalogBindingGraph(reader, catalog)
    for role in ('config', 'params'):
        with graph.stage(role) as handle:
            handle._open_table_data(handle.table)
            handle._open_table_blob(handle.table)
    return reader, catalog, graph


def read(value, binding, **kwargs):
    reader, catalog, graph = prepared(value)
    with graph.stage('records', binding=binding) as handle:
        return records.read_bound_catalog_records(reader, catalog, binding, handle=handle, **kwargs)


class BoundCatalogRecordsTests(unittest.TestCase):
    def test_current_layout_and_exact_values(self):
        value, binding = source()
        result = read(value, binding)
        self.assertEqual(result.record_size, 127)
        self.assertEqual(result.framing, 'reserved_and_active')
        self.assertEqual([x.value for x in result.rows[0].fields],
                         [b'R'*16, b'V'*16, False, b'P'*16, 'K1', 'alpha', Decimal('1.25')])
        self.assertEqual(result.native_acceptance, 'pending')

    def test_changed_metadata_layout_even_precision_and_utf16(self):
        value, binding = source(changed=True)
        with localcontext() as context:
            context.prec = 1
            result = read(value, binding)
        self.assertEqual(result.record_size, 81)
        self.assertEqual([x.offset for x in result.rows[0].fields], [17, 1, 33, 34, 50, 60, 76])
        self.assertEqual([x.value for x in result.rows[0].fields][-3:], ['K007', 'Привет!', Decimal('12.500')])
        self.assertEqual(result.rows[0].fields[-1].value.as_tuple().exponent, -3)

    def test_negative_and_signed_zero(self):
        for data, expected in ((bytes.fromhex('0000000250'), '-2.50'), (bytes(5), '-0.00')):
            value, binding = source(raw=b'\1'+bytes(126)+current_row(amount=data))
            result = read(value, binding)
            self.assertEqual(result.rows[0].fields[-1].value.as_tuple(), Decimal(expected).as_tuple())

    def test_empty_supported_shapes(self):
        for raw, framing in ((b'', 'empty_zero_length'), (b'\1'+bytes(126), 'empty_reserved')):
            value, binding = source(raw=raw)
            result = read(value, binding)
            self.assertEqual((result.rows, result.framing), ((), framing))

    def test_invalid_boolean_sign_digits_padding(self):
        cases = ((False, current_row(mark=b'\2'), 'boolean_encoding'),
                 (False, current_row(amount=bytes.fromhex('2000000125')), 'decimal_sign'),
                 (False, current_row(amount=bytes.fromhex('10000001f5')), 'decimal_digit'),
                 (True, changed_row(amount=bytes.fromhex('1000125001')), 'decimal_padding'))
        for changed, row, code in cases:
            value, binding = source(changed=changed, raw=b'\1'+bytes((80 if changed else 126))+row)
            with self.assertRaises(c.UnsupportedLayout) as caught: read(value, binding)
            self.assertEqual(caught.exception.code, code)

    def test_invalid_string_length_and_encoding(self):
        for payload, error in ((b'\x21\0'+bytes(64), 'string_length'),
                               (b'\1\0\0\xd8'+bytes(62), 'string_encoding')):
            value, binding = source(raw=b'\1'+bytes(126)+current_row(payload=payload))
            with self.assertRaises(c.CatalogError) as caught: read(value, binding)
            self.assertEqual(caught.exception.code, error)

    def test_framing_rejections(self):
        for raw, code in ((b'\0'+bytes(126), 'reserved_slot_marker'),
                          (b'\1'+bytes(126)+b'\1'+current_row()[1:], 'nonreserved_free_slot'),
                          (b'\1'+bytes(127), 'record_file_length')):
            value, binding = source(raw=raw)
            with self.assertRaises(c.CatalogError) as caught: read(value, binding)
            self.assertEqual(caught.exception.code, code)

    def test_missing_header_never_means_empty(self):
        value, binding = source(data_header=0)
        with self.assertRaises(c.UnsupportedLayout) as caught: read(value, binding)
        self.assertEqual(caught.exception.code, 'missing_table_data_header')

    def test_schema_mismatch_before_data_read(self):
        base = compiled()
        altered = base.declarations[:4] + (('_CODE', 'NVC', 0, 3, 0, 'CI'),) + base.declarations[5:]
        for kwargs, code in (({'declarations': altered}, 'declaration_mismatch'),
                             ({'declarations': base.declarations + (('EXTRA', 'L', 0, 0, 0, 'CS'),)}, 'declaration_mismatch'),
                             ({'recordlock': '1'}, 'recordlock_mismatch'),
                             ({'format_item': 2}, 'format_integer_nonzero')):
            value, binding = source(**kwargs)
            with self.assertRaises(c.UnsupportedLayout) as caught: read(value, binding)
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(any(offset == 8*P for offset, _ in value.calls))

    def test_forged_bindings_rejected_before_data_read(self):
        base = compiled()
        declarations = list(base.declarations)
        declarations[0] = ('_IDRREF', 'B', False, 16, 0, 'CS')
        placements = list(base.placements)
        mutations = [replace(base, record_size=True), replace(base, record_size=126),
                     replace(base, code_length=True), replace(base, code_length=3),
                     replace(base, recordlock=0), replace(base, format_item=False),
                     replace(base, declarations=tuple(declarations)),
                     replace(base, declarations=tuple(reversed(base.declarations))),
                     replace(base, attributes=tuple(reversed(base.attributes))),
                     replace(base, attributes=(replace(base.attributes[0], physical_name='_FLD741'),base.attributes[1])),
                     replace(base, attributes=(replace(base.attributes[0], qualifiers=(7,1)),base.attributes[1]))]
        for field, val in (('offset', -1), ('offset', True), ('offset', 16), ('width', -1), ('width', 999999)):
            places = (replace(placements[0], **{field:val}),) + tuple(placements[1:])
            mutations.append(replace(base, placements=places))
        for forged in mutations:
            value, _ = source()
            reader, catalog, graph = prepared(value)
            before = list(value.calls)
            with self.assertRaises(c.UnsupportedLayout) as caught:
                with graph.stage('records', binding=forged) as handle:
                    records.read_bound_catalog_records(reader, catalog, forged, handle=handle)
            self.assertEqual(caught.exception.code, 'compiled_binding_invalid')
            self.assertEqual(value.calls, before)
            self.assertTrue(graph.failed)

    def test_limits_cumulative_graph_and_no_second_read(self):
        value, binding = source()
        reader, catalog, graph = prepared(value)
        before = reader.usage
        with graph.stage('records', binding=binding) as handle:
            result = records.read_bound_catalog_records(reader, catalog, binding, handle=handle)
        self.assertGreater(result.usage.read_bytes, before.read_bytes)
        self.assertGreater(result.usage.output_bytes, before.output_bytes)
        with self.assertRaises(ValueError):
            records.read_bound_catalog_records(reader, catalog, binding, handle=handle)
        self.assertTrue(graph.failed)
        with self.assertRaises(ValueError): reader._open_table_data(catalog.tables[-1])

    def test_lowered_limits_and_no_widening(self):
        for limits, code in ((legacy.RecordLimits(max_slots=1), 'record_slots'),
                             (legacy.RecordLimits(max_record_bytes=126), 'record_bytes'),
                             (legacy.RecordLimits(max_fields=6), 'record_fields')):
            value, binding = source()
            with self.assertRaises(c.ResourceLimit) as caught: read(value, binding, limits=limits)
            self.assertEqual(caught.exception.code, code)
        value, binding = source()
        with self.assertRaises(ValueError): read(value, binding, limits=legacy.RecordLimits(max_slots=4097))

    def test_active_row_limit_and_failure_is_terminal(self):
        value, binding = source(raw=b'\1'+bytes(126)+current_row()+current_row())
        reader, catalog, graph = prepared(value)
        with self.assertRaises(c.ResourceLimit) as caught:
            with graph.stage('records', binding=binding) as handle:
                records.read_bound_catalog_records(reader, catalog, binding, handle=handle,
                                                  limits=legacy.RecordLimits(max_active_records=1))
        self.assertEqual(caught.exception.code, 'active_records')
        self.assertTrue(graph.failed)
        with self.assertRaises(ValueError):
            with graph.stage('records', binding=binding): pass

    def test_caught_argument_error_cannot_resume_same_stage(self):
        value, binding = source()
        reader, catalog, graph = prepared(value)
        with self.assertRaises(ValueError):
            with graph.stage('records', binding=binding) as handle:
                with self.assertRaises(ValueError):
                    records.read_bound_catalog_records(reader, replace(catalog), binding, handle=handle)
                self.assertTrue(graph.failed)
                records.read_bound_catalog_records(reader, catalog, binding, handle=handle)
        self.assertFalse(any(offset == 8*P for offset, _ in value.calls))

    def test_numeric_precision_parity_and_scale_independent_of_context(self):
        cases = ((bytes.fromhex('15'), 1, 0, '5'),
                 (bytes.fromhex('1120'), 2, 1, '1.2'),
                 (bytes.fromhex('0120'), 2, 2, '-0.12'),
                 (bytes.fromhex('1000000000000000000000000000000000000120'), 38, 3, '0.012'))
        with localcontext() as context:
            context.prec = 1
            for raw, precision, scale, expected in cases:
                result = records._decode(raw, ('F', 'N', 0, precision, scale, 'CS'))
                self.assertEqual(result.as_tuple(), Decimal(expected).as_tuple())

    def test_wrong_catalog_and_handle_role(self):
        value, binding = source()
        reader = c.CatalogReader(value.read_at, value.size)
        catalog = reader.read_catalog()
        graph = c._CatalogBindingGraph(reader, catalog)
        with self.assertRaises(ValueError):
            with graph.stage('config') as handle:
                records.read_bound_catalog_records(reader, catalog, binding, handle=handle)
        self.assertTrue(graph.failed)
        value, binding = source()
        reader, catalog, graph = prepared(value)
        with self.assertRaises(ValueError):
            with graph.stage('records', binding=binding) as handle:
                records.read_bound_catalog_records(reader, replace(catalog), binding, handle=handle)
        self.assertTrue(graph.failed)


if __name__ == '__main__': unittest.main()
