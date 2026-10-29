"""Production entrypoint on invented complete images, no native expectations."""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import inspect
import subprocess
import tempfile
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import test_catalog_binding_integration as fixture
import catalog_binding_reader as entry


class CatalogBindingReaderTests(unittest.TestCase):
    def read(self, value=None, **kwargs):
        value = fixture.source() if value is None else value
        kwargs.setdefault('catalog_name', 'NativeOracleItems')
        return entry.read_catalog_binding(value.read_at, value.size, **kwargs)

    def captured(self):
        readers, graphs, roles = [], [], []
        c = entry.catalog_module
        reader_init, graph_init, stage = c.CatalogReader.__init__, c._CatalogBindingGraph.__init__, c._CatalogBindingGraph.stage
        def rinit(obj, *args, **kwargs):
            reader_init(obj, *args, **kwargs); readers.append(obj)
        def ginit(obj, *args, **kwargs):
            graph_init(obj, *args, **kwargs); graphs.append(obj)
        def staged(obj, role, **kwargs):
            roles.append(role); return stage(obj, role, **kwargs)
        return readers, graphs, roles, (mock.patch.object(c.CatalogReader, '__init__', rinit),
                                       mock.patch.object(c._CatalogBindingGraph, '__init__', ginit),
                                       mock.patch.object(c._CatalogBindingGraph, 'stage', staged))

    def test_production_entry_single_reader_complete_graph(self):
        readers, graphs, roles, patches = self.captured()
        with patches[0], patches[1], patches[2]: result = self.read()
        self.assertEqual(len(readers), 1)
        self.assertEqual(len(graphs), 1)
        self.assertEqual(roles, ['config', 'params', 'records'])
        self.assertEqual(graphs[0]._next, 3)
        self.assertFalse(graphs[0].failed)
        self.assertEqual(len(result.config_observation.private_fields), 3)
        self.assertEqual(result.identity.metadata_uuid, fixture.config_fixture.KEYS[0])
        self.assertEqual(result.binding.table_name, '_Reference19')
        self.assertEqual([x.physical_name for x in result.binding.attributes], ['_FLD62', '_FLD741'])
        self.assertEqual([x.value for x in result.records.rows[0].fields][4:], ['K1', 'alpha', Decimal('1.25')])
        self.assertEqual(result.usage, readers[0].usage)
        self.assertEqual(result.records.native_acceptance, 'pending')
        with self.assertRaises(FrozenInstanceError): result.identity = None

    def test_selector_only_signature(self):
        self.assertEqual(tuple(inspect.signature(entry.read_catalog_binding).parameters),
                         ('read_at', 'file_size', 'catalog_name', 'limits'))

    def test_unknown_and_wrongcase_selector_after_complete_config(self):
        for selector in ('Missing', 'nativeoracleitems'):
            value = fixture.source()
            readers, graphs, roles, patches = self.captured()
            with patches[0], patches[1], patches[2]:
                with self.assertRaises(entry.catalog_module.UnsupportedLayout) as caught:
                    self.read(value, catalog_name=selector)
            self.assertEqual(caught.exception.code, 'binding_catalog_missing')
            self.assertEqual(roles, ['config'])
            self.assertTrue(graphs[0].failed)
            self.assertFalse(any(offset == 30*fixture.P for offset, _ in value.calls))

    def test_ambiguous_selector_and_all_catalog_uuid_consistency(self):
        original = entry._load_storage()['config_catalog_transport']._observe_catalog_attributes_from_graph
        for mode, expected in (('ambiguous', 'binding_catalog_ambiguous'), ('identity', 'binding_catalog_identity')):
            def changed(*args, **kwargs):
                value = original(*args, **kwargs)
                fields = list(value.private_fields)
                key, identity, attributes = fields[-1]
                if mode == 'ambiguous': identity = replace(identity, name='NativeOracleItems')
                else: key = 'ffffffff-ffff-ffff-ffff-ffffffffffff'
                fields[-1] = (key, identity, attributes)
                return replace(value, private_fields=tuple(fields))
            readers, graphs, roles, patches = self.captured()
            with patches[0], patches[1], patches[2], mock.patch.object(entry._load_storage()['config_catalog_transport'], '_observe_catalog_attributes_from_graph', changed):
                with self.assertRaises(entry.catalog_module.CatalogError) as caught: self.read()
            self.assertEqual(caught.exception.code, expected)
            self.assertTrue(graphs[0].failed)
            self.assertEqual(roles, ['config'])

    def test_late_config_failure_poison_no_params(self):
        original = entry._load_storage()['config_catalog_transport']._ConfigContentDecoder.decode
        calls = []
        def decode(obj, *args, **kwargs):
            calls.append(1)
            result = original(obj, *args, **kwargs)
            if len(calls) == 4: raise RuntimeError('invented late decode failure')
            return result
        readers, graphs, roles, patches = self.captured()
        with patches[0], patches[1], patches[2], mock.patch.object(entry._load_storage()['config_catalog_transport']._ConfigContentDecoder, 'decode', decode):
            with self.assertRaises(RuntimeError): self.read()
        self.assertEqual(len(calls), 4)
        self.assertTrue(graphs[0].failed)
        self.assertEqual(roles, ['config'])

    def test_params_parser_and_compile_failure_poison_no_rows(self):
        modules = entry._load_storage()
        for module, function in ((modules['filedb_dbnames'], 'parse_dbnames'),
                                 (modules['config_catalog_binding'], 'compile_catalog_binding')):
            value = fixture.source()
            readers, graphs, roles, patches = self.captured()
            with patches[0], patches[1], patches[2], mock.patch.object(module, function, side_effect=RuntimeError('invented parse failure')):
                with self.assertRaises(RuntimeError): self.read(value)
            self.assertTrue(graphs[0].failed)
            self.assertEqual(roles, ['config', 'params'])
            self.assertFalse(any(offset == 40*fixture.P for offset, _ in value.calls))

    def test_row_failure_poison_no_partial_result(self):
        value = fixture.source()
        value.page(43)[127] = 1
        readers, graphs, roles, patches = self.captured()
        with patches[0], patches[1], patches[2]:
            with self.assertRaises(entry.catalog_module.UnsupportedLayout) as caught: self.read(value)
        self.assertEqual(caught.exception.code, 'nonreserved_free_slot')
        self.assertEqual(roles, ['config', 'params', 'records'])
        self.assertTrue(graphs[0].failed)

    def test_one_row_limit_is_explicit(self):
        modules = entry._load_storage()
        original = modules['config_catalog_records'].read_bound_catalog_records
        observed = []
        def rows(*args, **kwargs):
            observed.append(kwargs['limits'].max_active_records)
            return original(*args, **kwargs)
        with mock.patch.object(modules['config_catalog_records'], 'read_bound_catalog_records', rows): self.read()
        self.assertEqual(observed, [1])

    def test_dbnames_reservation_charged_before_parse_including_tokens(self):
        modules = entry._load_storage()
        original = modules['filedb_dbnames'].parse_dbnames
        readers, graphs, roles, patches = self.captured()
        observations = []
        def parse(data, **kwargs):
            budget = readers[0]._budget
            observations.append(dict(budget.counts))
            self.assertGreaterEqual(budget.counts['tokens'], len(data))
            self.assertGreaterEqual(budget.counts['output_bytes'], 1024)
            return original(data, **kwargs)
        with patches[0], patches[1], patches[2], mock.patch.object(modules['filedb_dbnames'], 'parse_dbnames', parse): self.read()
        self.assertEqual(len(observations), 1)
        self.assertGreater(readers[0].usage.tokens, observations[0]['tokens'])

    def test_known_parser_compiler_errors_have_finite_catalog_contract(self):
        modules = entry._load_storage()
        cases = ((modules['filedb_dbnames'], 'parse_dbnames', modules['filedb_dbnames'].InvalidDBNames('dbnames_utf8'), 'binding_dbnames_invalid'),
                 (modules['filedb_dbnames'], 'parse_dbnames', modules['filedb_dbnames'].DBNamesParseResourceLimit('dbnames_tokens'), 'binding_dbnames_limits'),
                 (modules['config_catalog_binding'], 'compile_catalog_binding', modules['config_catalog_binding'].CatalogBindingError('qualifiers'), 'binding_metadata_profile'))
        for module, function, failure, code in cases:
            readers, graphs, roles, patches = self.captured()
            with patches[0], patches[1], patches[2], mock.patch.object(module, function, side_effect=failure):
                with self.assertRaises(entry.catalog_module.CatalogError) as caught: self.read()
            self.assertEqual(str(caught.exception), code)
            self.assertTrue(graphs[0].failed)

    def test_loader_same_file_aliases_and_no_installed_runtime(self):
        modules = entry._load_storage()
        package = entry._PACKAGE
        self.assertEqual(sys.modules[package].__path__, [])
        self.assertIs(sys.modules[package+'.filedb_catalog'], entry.catalog_module)
        self.assertIs(sys.modules[package+'.config_catalog_name'], entry.name_parser)
        self.assertIs(sys.modules[package+'.config_catalog_attributes'], entry.core.load_catalog_attribute_projector())
        for key, module in modules.items():
            self.assertEqual(Path(module.__file__).resolve().name, key+'.py')
            self.assertTrue(module.__name__.startswith(package+'.'))
        self.assertIs(entry._load_storage()['config_catalog_records'], modules['config_catalog_records'])

    def test_loader_rejects_foreign_cached_alias_and_sibling(self):
        entry._load_storage()
        foreign = types.ModuleType('foreign')
        foreign.__file__ = '/tmp/not_the_verified_sibling.py'
        for key in (entry._PACKAGE+'.filedb_catalog', entry._PACKAGE+'.filedb_dbnames',
                    '_owned_catalog_attribute_storage.config_catalog_attributes'):
            with mock.patch.dict(sys.modules, {key: foreign}):
                with self.assertRaises(ValueError): entry._load_storage()

    def test_isolated_production_loader_reads_without_runtime_package(self):
        root = Path(__file__).resolve().parents[1]
        value = fixture.source()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'invented.bin'
            image.write_bytes(value.full_bytes())
            code = """
import pathlib,sys
root=pathlib.Path(sys.argv[1])
sys.path[:0]=[str(root/'scripts/native_1c_db_oracle'),str(root/'yadinassi/storage')]
import catalog_binding_reader
raw=pathlib.Path(sys.argv[2]).read_bytes()
result=catalog_binding_reader.read_catalog_binding(lambda o,n:raw[o:o+n],len(raw),catalog_name='NativeOracleItems')
assert result.records.rows[0].fields[5].value=='alpha'
assert not any(n=='yadinassi' or n.startswith('yadinassi.') for n in sys.modules)
print('ISOLATED_BINDING_OK')
"""
            child = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(root), str(image)],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(child.stdout, 'ISOLATED_BINDING_OK\n')
        self.assertEqual(child.stderr, '')

    def test_bad_selector_and_limits_before_source_read(self):
        for value in ('', 'x'*257, '\ud800', 'bad\x00', None):
            image = fixture.source()
            with self.assertRaises(entry.catalog_module.UnsupportedLayout): self.read(image, catalog_name=value)
            self.assertEqual(image.calls, [])
        image = fixture.source()
        with self.assertRaises(entry.catalog_module.InvalidStructure): self.read(image, limits={})
        self.assertEqual(image.calls, [])


if __name__ == '__main__': unittest.main()
