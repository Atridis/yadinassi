"""Independent old/new transport equivalence on invented images, not native proof."""
from dataclasses import asdict, fields
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_catalog_binding_integration as fixture
import catalog_binding_reader as adapter
import config_framing_reader as historical


class RuntimeExtractionTests(unittest.TestCase):
    def setUp(self):
        self.modules = adapter._load_storage()
        self.transport = self.modules['config_catalog_transport']
        self.runtime = self.modules['catalog_reader']

    def run_transport(self, implementation, value=None, limits=None):
        value = fixture.source() if value is None else value
        reader = adapter.catalog_module.CatalogReader.__new__(adapter.catalog_module.CatalogReader)
        graph = None
        try:
            reader.__init__(value.read_at, value.size, limits=limits)
            catalog = reader.read_catalog()
            graph = adapter.catalog_module._CatalogBindingGraph(reader, catalog)
            with graph.stage('config') as handle:
                result = implementation._observe_catalog_attributes_from_graph(handle,
                    profile=implementation.ConfigCatalogAttributeProfile(implementation.DECLARATIONS, '0', 0))
            output = ('ok', asdict(result))
        except adapter.catalog_module.CatalogError as error:
            output = ('error', type(error).__name__, error.code)
        return output, value.calls, asdict(reader.usage), None if graph is None else (graph.failed, graph._next)

    def test_transport_same_result_reads_and_every_budget_counter(self):
        old = self.run_transport(historical)
        new = self.run_transport(self.transport)
        self.assertEqual(old, new)
        self.assertEqual(new[0][0], 'ok')
        self.assertEqual(new[3], (False, 1))
        self.assertEqual(len(new[0][1]['private_fields']), 3)

    def test_transport_corruptions_match_failure_poison_and_charged_work(self):
        # Cover header, catalog descriptors, CONFIG data/mapping/BLOB framing;
        # changing a selected transport byte need not always be semantically bad.
        rejected = 0
        for page, offset in ((0, 0), (0, 12), (1, 0), (2, 6), (3, 10),
                             (5, 0), (5, 16), (5, 24), (6, 0), (6, 16),
                             (6, 24), (8, 0), (8, 300), (9, 0), (9, 256),
                             (9, 260), (9, 261), (9, 262)):
            with self.subTest(page=page, offset=offset):
                left, right = fixture.source(), fixture.source()
                left.page(page)[offset] ^= 255
                right.page(page)[offset] ^= 255
                old, new = self.run_transport(historical, left), self.run_transport(self.transport, right)
                self.assertEqual(old, new)
                rejected += new[0][0] == 'error'
        self.assertGreaterEqual(rejected, 5)

    def test_every_lowered_catalog_budget_same_error_and_usage(self):
        from dataclasses import replace
        defaults = adapter.catalog_module.CatalogLimits()
        for field in fields(defaults):
            with self.subTest(field=field.name):
                limits = replace(defaults, **{field.name: 1})
                self.assertEqual(self.run_transport(historical, limits=limits),
                                 self.run_transport(self.transport, limits=limits))

    def test_coordinator_same_with_historical_transport_as_independent_oracle(self):
        # Compare against the still source-pinned historical parser. Same result,
        # callback order and cumulative budget; no XML or expected rows injected.
        left, right = fixture.source(), fixture.source()
        expected = self.runtime.read_catalog_binding(left.read_at, left.size,
                                                     catalog_name='NativeOracleItems')
        def old(handle, *, profile):
            return historical._observe_catalog_attributes_from_graph(handle,
                profile=historical.ConfigCatalogAttributeProfile(historical.DECLARATIONS, '0', 0))
        with mock.patch.object(self.transport, '_observe_catalog_attributes_from_graph', old):
            actual = self.runtime.read_catalog_binding(right.read_at, right.size,
                                                       catalog_name='NativeOracleItems')
        self.assertEqual(asdict(actual), asdict(expected))
        self.assertEqual(left.calls, right.calls)

    def test_adapter_preserves_input_errors_before_loading(self):
        with mock.patch.object(adapter, '_load_storage', side_effect=AssertionError('must not load')):
            for selector in ('', None, '\ud800', 'x'*257):
                with self.assertRaises(adapter.catalog_module.UnsupportedLayout) as caught:
                    adapter.read_catalog_binding(None, 0, catalog_name=selector)
                self.assertEqual(caught.exception.code, 'binding_catalog_selector')
            with self.assertRaises(adapter.catalog_module.InvalidStructure) as caught:
                adapter.read_catalog_binding(None, 0, catalog_name='Items', limits={})
            self.assertEqual(caught.exception.code, 'binding_limits')

    def test_storage_only_cold_import_and_read_without_harness_on_path(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory)/'invented.1CD'
            image.write_bytes(fixture.source().full_bytes())
            code = """
import importlib,json,pathlib,sys,types
storage=pathlib.Path(sys.argv[1])/'yadinassi/storage'
package=types.ModuleType('isolated_storage');package.__path__=[str(storage)]
sys.modules['isolated_storage']=package
reader=importlib.import_module('isolated_storage.catalog_reader')
raw=pathlib.Path(sys.argv[2]).read_bytes()
result=reader.read_catalog_binding(lambda o,n:raw[o:o+n],len(raw),catalog_name='NativeOracleItems')
assert result.records.rows[0].fields[5].value=='alpha'
assert not any(n.startswith(('scripts','config_framing_reader','catalog_binding_reader','_owned')) for n in sys.modules)
for name,module in list(sys.modules.items()):
    if name.startswith('isolated_storage.'):
        assert pathlib.Path(module.__file__).parent==storage
print('STORAGE_ONLY_OK')
"""
            result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(root), str(image)],
                                    capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'STORAGE_ONLY_OK\n')
        self.assertEqual(result.stderr, '')


if __name__ == '__main__': unittest.main()
