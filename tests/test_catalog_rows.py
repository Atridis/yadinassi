"""Opt-in typed projection of complete invented images; not native evidence."""
from dataclasses import FrozenInstanceError, asdict, replace
import importlib
import inspect
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from uuid import UUID

import test_catalog_binding_integration as fixture

# Independent runtime package: no harness adapter supplies the new API/codec.
package = types.ModuleType('row_projection_storage')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'yadinassi/storage')]
sys.modules[package.__name__] = package
entry = importlib.import_module(package.__name__ + '.catalog_reader')
codec = importlib.import_module(package.__name__ + '.catalog_reference_uuid')
c = entry.catalog_module
PHYSICAL = bytes.fromhex('8899aabbccddeeff4677445500112233')
EXPECTED = UUID('00112233-4455-4677-8899-aabbccddeeff')


def source():
    value = fixture.source()
    # Fixture's independently declared layout: reserved row, RV, then IDRREF.
    value.page(43)[127+17:127+33] = PHYSICAL
    return value


class CatalogRowsTests(unittest.TestCase):
    def read(self, image=None, raw=False, **kwargs):
        image = source() if image is None else image
        return (entry.read_catalog_binding if raw else entry.read_catalog_rows)(
            image.read_at, image.size, catalog_name='NativeOracleItems', **kwargs)

    def capture(self):
        readers, graphs = [], []
        ri, gi = c.CatalogReader.__init__, c._CatalogBindingGraph.__init__
        def reader(obj, *a, **k):
            ri(obj, *a, **k); readers.append(obj)
        def graph(obj, *a, **k):
            gi(obj, *a, **k); graphs.append(obj)
        return readers, graphs, mock.patch.object(c.CatalogReader, '__init__', reader), mock.patch.object(c._CatalogBindingGraph, '__init__', graph)

    def test_typed_identity_raw_compatibility_and_single_lifetime(self):
        left, right = source(), source()
        raw = self.read(left, raw=True)
        readers, graphs, rp, gp = self.capture()
        with rp, gp, mock.patch.object(codec, 'decode_catalog_reference_uuid', wraps=codec.decode_catalog_reference_uuid) as called:
            result = self.read(right)
        self.assertEqual(len(readers), 1)
        self.assertEqual(len(graphs), 1)
        self.assertFalse(graphs[0].failed)
        called.assert_called_once_with(PHYSICAL)
        self.assertEqual(left.calls, right.calls)
        self.assertEqual(asdict(result.records), asdict(raw.records))
        self.assertEqual(result.identity, raw.identity)
        self.assertEqual(result.identity.metadata_uuid, fixture.config_fixture.KEYS[0])
        self.assertEqual(result.binding, raw.binding)
        typed = result.rows[0]
        self.assertIs(typed.physical_record, result.records.rows[0])
        self.assertIs(type(typed.reference_uuid), UUID)
        self.assertEqual(typed.reference_uuid, EXPECTED)
        for index in (0, 1, 3):
            self.assertIs(type(typed.physical_record.fields[index].value), bytes)
        self.assertEqual(result.usage.output_bytes - raw.usage.output_bytes, 1024)
        self.assertEqual(result.usage.bytes_processed - raw.usage.bytes_processed, 512)
        self.assertFalse(hasattr(result, 'native_acceptance'))
        for obj, attr in ((result, 'rows'), (typed, 'reference_uuid')):
            with self.assertRaises(FrozenInstanceError): setattr(obj, attr, None)

    def test_codec_observes_complete_admission_and_precharge(self):
        raw = self.read(raw=True)
        readers, graphs, rp, gp = self.capture()
        original = codec.decode_catalog_reference_uuid
        def decode(value):
            self.assertEqual(graphs[0]._next, 3)
            self.assertGreater(readers[0].usage.output_bytes, raw.usage.output_bytes)
            self.assertGreater(readers[0].usage.bytes_processed, raw.usage.bytes_processed)
            return original(value)
        with rp, gp, mock.patch.object(codec, 'decode_catalog_reference_uuid', side_effect=decode): self.read()

    def test_baseline_no_rows_no_uuid(self):
        for length in (0, 127):
            image = source()
            image.page(40)[16:24] = length.to_bytes(8, 'little')
            with mock.patch.object(codec, 'decode_catalog_reference_uuid', side_effect=AssertionError('no UUID')):
                result = self.read(image)
            self.assertEqual(result.rows, ())
            self.assertEqual(result.records.rows, ())

    def test_raw_route_does_not_call_projection_or_codec(self):
        with mock.patch.object(entry, '_project_rows', side_effect=AssertionError('raw API')):
            with mock.patch.object(codec, 'decode_catalog_reference_uuid', side_effect=AssertionError('raw API')):
                self.assertEqual(self.read(raw=True).records.rows[0].fields[0].value, PHYSICAL)

    def test_metadata_derived_lengths_and_qualifiers(self):
        config = fixture.config_fixture
        matrix = list(config.policy.MATRIX)
        name, _, kind, description = matrix[0]
        matrix[0] = (name, 7, kind, description)
        original = config.constructed.attribute
        def attribute(uuid, name, pattern):
            pattern = pattern.replace('{"S",32,1}', '{"S",11,1}').replace('{"N",9,2,0}', '{"N",6,3,0}')
            return original(uuid, name, pattern)
        with mock.patch.object(config.policy, 'MATRIX', tuple(matrix)), mock.patch.object(config.constructed, 'attribute', side_effect=attribute):
            image = fixture.source()
        declarations = (('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
            ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),
            ('_CODE','NVC',0,7,0,'CI'),('_FLD62','NVC',0,11,0,'CI'),('_FLD741','N',0,6,3,'CS'))
        desc = ('_Reference19',0,('Fields',*declarations),('Indexes',),('Recordlock','0'),('Files',40,41,42))
        encoded = fixture.serialize(desc).encode()
        image.chain(tuple(range(14,14+(len(encoded)+249)//250)), encoded)
        def nvc(text, length):
            return len(text).to_bytes(2,'little') + text.encode('utf-16-le').ljust(2*length,b'\0')
        row = b'\0' + b'V'*16 + PHYSICAL + b'\0' + b'P'*16 + nvc('LONG123',7) + nvc('payload',11) + bytes.fromhex('10012340')
        data = b'\1' + bytes(len(row)-1) + row
        image.page(40)[16:24] = len(data).to_bytes(8,'little')
        image.page(43)[:len(data)] = data
        result = self.read(image)
        self.assertEqual(result.binding.code_length, 7)
        self.assertEqual(result.binding.attributes[0].qualifiers, (11,1))
        self.assertEqual(result.binding.attributes[1].qualifiers, (6,3,0))
        self.assertEqual(result.rows[0].reference_uuid, EXPECTED)
        self.assertEqual(result.records.rows[0].fields[4].value, 'LONG123')
        self.assertEqual(str(result.records.rows[0].fields[6].value), '1.234')
        # Description remains an explicitly unsupported profile, not a width
        # silently hard-coded into the typed projection.
        matrix[0] = (name, 7, kind, 10)
        with mock.patch.object(config.policy, 'MATRIX', tuple(matrix)):
            image = fixture.source()
        self.assert_rejected_before_codec(image)

    def test_selector_only_no_expected_native_inputs(self):
        self.assertEqual(tuple(inspect.signature(entry.read_catalog_rows).parameters),
                         ('read_at', 'file_size', 'catalog_name', 'limits'))

    def assert_rejected_before_codec(self, image=None, patch=None, **kwargs):
        readers, graphs, rp, gp = self.capture()
        patch = patch or mock.patch.object(entry, 'UUID', UUID)
        with rp, gp, patch, mock.patch.object(codec, 'decode_catalog_reference_uuid') as called:
            with self.assertRaises((c.CatalogError, RuntimeError)): self.read(image, **kwargs)
        called.assert_not_called()
        self.assertTrue(graphs[0].failed)

    def test_late_config_params_failure(self):
        for module, method in ((entry.core, '_observe_catalog_attributes_from_graph'),
                               (entry.dbnames, 'parse_dbnames')):
            original = getattr(module, method)
            def fail(*a, **k):
                original(*a, **k)
                raise RuntimeError('invented late failure')
            self.assert_rejected_before_codec(patch=mock.patch.object(module, method, side_effect=fail))

    def test_forged_binding_and_role_fail_before_codec(self):
        original = entry.compiler.compile_catalog_binding
        for mode in ('width', 'role', 'identity', 'foreign'):
            def forged(*a, **k):
                binding = original(*a, **k)
                if mode == 'identity': return replace(binding, metadata_uuid='bad')
                if mode == 'foreign': return replace(binding, metadata_uuid='cccccccc-cccc-cccc-cccc-cccccccccccc')
                places = list(binding.placements)
                if mode == 'width': places[0] = replace(places[0], width=15)
                else: places[0] = replace(places[0], declaration=places[3].declaration)
                return replace(binding, placements=tuple(places))
            self.assert_rejected_before_codec(patch=mock.patch.object(entry.compiler, 'compile_catalog_binding', side_effect=forged))

    def test_physical_layout_and_late_row_fail_before_codec(self):
        for mode in ('marker', 'number', 'second'):
            image = source()
            if mode == 'marker': image.page(43)[127] = 1
            elif mode == 'number': image.page(43)[253] = 255
            else:
                image.page(40)[16:24] = (381).to_bytes(8, 'little')
                image.page(43)[254:381] = image.page(43)[127:254]
            self.assert_rejected_before_codec(image)

    def test_projection_budget_failure_precedes_codec(self):
        raw = self.read(raw=True)
        for name, amount in (('output_bytes', 1024), ('bytes_processed', 512)):
            limits = replace(c.CatalogLimits(), **{'max_' + name: getattr(raw.usage, name) + amount - 1})
            self.assert_rejected_before_codec(limits=limits)
            limits = replace(limits, **{'max_' + name: getattr(raw.usage, name) + amount})
            self.assertEqual(self.read(limits=limits).rows[0].reference_uuid, EXPECTED)

    def test_forged_physical_role_rejected_before_codec(self):
        original = entry.row_reader.read_bound_catalog_records
        for mode in ('empty', 'missing', 'duplicate', 'shifted'):
            def forged(*a, **k):
                result = original(*a, **k)
                row = result.rows[0]
                fields = list(row.fields)
                if mode == 'empty': fields = []
                elif mode == 'missing': fields[0] = replace(fields[0], declaration=fields[3].declaration)
                elif mode == 'duplicate': fields[3] = replace(fields[3], declaration=fields[0].declaration)
                else: fields[0], fields[3] = fields[3], fields[0]
                return replace(result, rows=(replace(row, fields=tuple(fields)),))
            self.assert_rejected_before_codec(patch=mock.patch.object(entry.row_reader, 'read_bound_catalog_records', side_effect=forged))

    def test_real_descriptor_missing_duplicate_shifted_role(self):
        declarations = list(self.read(raw=True).binding.declarations)
        for mode in ('missing', 'duplicate', 'shifted'):
            image = source()
            fields = declarations.copy()
            if mode == 'missing': fields[0] = ('_OTHER', *fields[0][1:])
            elif mode == 'duplicate': fields[3] = fields[0]
            else: fields[0], fields[3] = fields[3], fields[0]
            desc = ('_Reference19',0,('Fields',*fields),('Indexes',),('Recordlock','0'),('Files',40,41,42))
            encoded = fixture.serialize(desc).encode()
            image.chain(tuple(range(14,14+(len(encoded)+249)//250)), encoded)
            # Duplicate descriptor names can fail during physical catalog
            # parsing, before a binding graph even exists.
            with mock.patch.object(codec, 'decode_catalog_reference_uuid') as called:
                with self.assertRaises(c.CatalogError): self.read(image)
            called.assert_not_called()

    def test_malformed_private_placements_fail_finitely(self):
        original = entry._project_rows
        for mode in ('empty', 'missing', 'duplicate', 'shifted'):
            def forged(graph, identity, binding, records):
                places = list(binding.placements)
                if mode == 'empty': places = []
                elif mode == 'missing': places[0] = places[3]
                elif mode == 'duplicate': places[3] = places[0]
                else: places[0], places[3] = places[3], places[0]
                return original(graph, identity, replace(binding, placements=tuple(places)), records)
            self.assert_rejected_before_codec(patch=mock.patch.object(entry, '_project_rows', side_effect=forged))

    def test_late_projection_failure_returns_nothing_and_poisons(self):
        readers, graphs, rp, gp = self.capture()
        original = codec.decode_catalog_reference_uuid
        seen = []
        def fail(value):
            seen.append(original(value))
            raise RuntimeError('invented after conversion')
        result = None
        with rp, gp, mock.patch.object(codec, 'decode_catalog_reference_uuid', side_effect=fail):
            with self.assertRaises(RuntimeError): result = self.read()
        self.assertEqual(seen, [EXPECTED])
        self.assertIsNone(result)
        self.assertTrue(graphs[0].failed)
        with self.assertRaises(ValueError):
            with graphs[0].stage('records'): pass


if __name__ == '__main__': unittest.main()
