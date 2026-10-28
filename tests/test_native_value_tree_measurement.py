"""Offline contract for candidate observations; does not establish native behavior."""
import hashlib
import os
from pathlib import Path
import unittest
import test_native_1c_full_stage as fixtures

ROOT = Path(__file__).resolve().parents[1]
START = b'// Begin bounded ValueTree core observations (candidate; not native evidence).\n'
END = b'// End bounded ValueTree core observations.\n'
PREFIX_SHA = '42c1fedddb8a689f3ba2ca6a241b1d19d38c0bea4da8a29e5934b3082a43fdfb'

def offline_checkout_bytes(raw, platform):
    # Offline fixtures model the LF-pinned Linux executor under Git autocrlf.
    # Never normalize production input or edit repository source fixtures.
    return raw.replace(b'\r\n', b'\n') if platform == 'nt' else raw


class ValueTreeMeasurementContract(unittest.TestCase):
    def setUp(self):
        self.source = offline_checkout_bytes(
            (ROOT/'integrational_tests/tests/collections.bsl').read_bytes(), os.name)
        self.template = offline_checkout_bytes(
            (ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes(), os.name)

    def test_append_only_fixed_budget(self):
        from scripts.native_historical_replay import without_tree_findrows_probes
        source = without_tree_findrows_probes(self.source.decode('utf-8-sig')).encode('utf-8-sig')
        prefix, marker, block = source.partition(START)
        self.assertEqual(hashlib.sha256(prefix).hexdigest(), PREFIX_SHA)
        self.assertEqual(source.count(START), 1)
        self.assertTrue(block.endswith(END))
        self.assertLess(len(marker + block), 6000)
        self.assertEqual(block.count('Показать("tree.core.'.encode()), 12)
        self.assertEqual(block.count('Новый ДеревоЗначений'.encode()), 1)
        for forbidden in ('Сообщить(', 'Выполнить(', 'Пока ', 'Для ', 'ЗначениеВСтрокуВнутр(', 'Записать', 'Прочитать'):
            self.assertNotIn(forbidden.encode(), block)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 1023)

    def test_full_client_adapter_preserves_probe_expressions(self):
        source = self.source
        template = self.template
        module = fixtures.suite.client_collections_module(source, template)
        block = source[source.index(START):]
        self.assertIn(block, module)
        self.assertEqual(module.count(START), 1)

    def test_probe_cannot_be_rebased_by_only_replacing_top_level_hash(self):
        from unittest import mock
        source = self.source
        template = self.template
        tampered = source.replace(b'VTChild.Level()', b'VTChild.Level(1)', 1)
        with mock.patch.object(fixtures.suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256', hashlib.sha256(tampered).hexdigest()):
            with self.assertRaises(fixtures.suite.FullError):
                fixtures.suite.client_collections_module(tampered, template)

    def test_fresh_comparison_cannot_accept_historical_prefix_or_drop_tree_records(self):
        import test_native_1c_map_contract as map_fixtures
        from scripts import native_1c_map_contract as contract
        rows = map_fixtures.records()
        self.assertEqual(len(rows), 1023)
        fresh = map_fixtures.encode(rows)
        old = map_fixtures.encode(rows[:854])
        current_sha = fixtures.suite.CLIENT_COLLECTIONS_SOURCE_SHA256
        self.assertEqual(contract.compare_collections(old, old, current_sha)['reason'], 'record_mismatch')
        self.assertEqual(contract.compare_collections(fresh, fresh, PREFIX_SHA)['reason'], 'source_mismatch')
        self.assertEqual(contract.compare_collections(fresh, old, current_sha)['status'], 'rejected')

    def test_historical_adapter_inverse_is_isolated_and_exact(self):
        from test_native_async_fixture import historical_tree_collections_module
        source = self.source
        template = self.template
        current = fixtures.suite.client_collections_module(source, template)
        historical = historical_tree_collections_module(source, template)
        self.assertEqual(hashlib.sha256(historical).hexdigest(),
                         'b8d28abf2a28f7ff11958f9f3a31a966e3032484b8f0cf7d316b24ef8fb847e8')
        self.assertEqual(fixtures.suite.client_collections_module(source, template), current)
        self.assertIn(START, current)
        self.assertNotIn(START, historical)
        with self.assertRaises(ValueError):
            historical_tree_collections_module(source + b'\n', template)
        prefix = source.partition(START)[0]
        with self.assertRaises(fixtures.suite.FullError):
            fixtures.suite.client_collections_module(prefix, template)

    def test_simulated_crlf_checkout_preserves_canonical_contract(self):
        source_crlf = self.source.replace(b'\n', b'\r\n')
        template_crlf = self.template.replace(b'\n', b'\r\n')
        source = offline_checkout_bytes(source_crlf, 'nt')
        template = offline_checkout_bytes(template_crlf, 'nt')
        self.assertEqual(source, self.source)
        self.assertEqual(template, self.template)
        self.assertEqual(offline_checkout_bytes(source_crlf, 'posix'), source_crlf)
        self.assertEqual(offline_checkout_bytes(template_crlf, 'posix'), template_crlf)
        from scripts.native_historical_replay import without_tree_findrows_probes
        old_source = without_tree_findrows_probes(source.decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(old_source.partition(START)[0]).hexdigest(), PREFIX_SHA)
        self.assertEqual(fixtures.suite.client_collections_module(source, template),
                         fixtures.suite.client_collections_module(self.source, self.template))
        from test_native_async_fixture import historical_tree_collections_module
        self.assertEqual(hashlib.sha256(historical_tree_collections_module(source, template)).hexdigest(),
                         'b8d28abf2a28f7ff11958f9f3a31a966e3032484b8f0cf7d316b24ef8fb847e8')

    def test_production_adapter_still_rejects_raw_crlf_bom_changes_and_tampering(self):
        bom = b'\xef\xbb\xbf'
        for name, raw in (('source', self.source), ('template', self.template)):
            for change, changed in (
                    ('crlf', raw.replace(b'\n', b'\r\n')),
                    ('extra_bom', bom + raw),
                    ('remove_bom', raw[len(bom):] if raw.startswith(bom) else bom + raw),
                    ('tamper', raw + b'// tampered\n')):
                with self.subTest(input=name, change=change):
                    source = changed if name == 'source' else self.source
                    template = changed if name == 'template' else self.template
                    with self.assertRaisesRegex(fixtures.suite.FullError, '^invalid_input$'):
                        fixtures.suite.client_collections_module(source, template)
