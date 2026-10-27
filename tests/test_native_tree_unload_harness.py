"""Exact test-only inversion of the UnloadColumn input adapter, not native answers."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import test_native_async_fixture as history
import test_native_1c_full_stage as fixtures
from scripts.native_historical_replay import without_tree_unload_probes

ROOT = Path(__file__).resolve().parents[1]
PATHS = ('scripts/native_1c_bootstrap/full_suite.py', 'scripts/native_1c_full_host.py')
BASE_MODULE_SHA = '9edae1c1032ef2e98895e53269a7e4be294a282b42ce4abddcf3b65f44dc0035'


class UnloadHarnessHistoryTests(unittest.TestCase):
    def inventory(self):
        return json.loads((ROOT/'tests/tree_unload_source_inverse.json').read_text(encoding='utf-8'))

    def test_exact_harness_restore_precedes_all_existing_history(self):
        inventory = self.inventory()
        self.assertEqual(set(inventory), set(PATHS))
        for path in PATHS:
            source = history.without_tree_unload_supplement_measurement((ROOT/path).read_text(encoding='utf-8'), host=path.endswith('full_host.py'))
            restored = history.without_tree_unload_measurement(source, host=path.endswith('full_host.py'))
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), inventory[path]['base_sha256'])
            self.assertIn('946', restored)
            self.assertNotEqual(restored, source)
            if path.endswith('full_host.py'):
                # The original cleanup implementation is retained in the first
                # inverse, and only the established next layer removes it.
                self.assertIn('def _finish_child(', restored)
                older = history.without_child_cleanup(source)
                self.assertNotIn('def _finish_child(', older)
            self.assertTrue(history.without_tree_find_measurement(source, host=path.endswith('full_host.py')))

    def test_full_previous_module_not_output_prefix_is_restored(self):
        source = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n', b'\n')
        template = (ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes().replace(b'\r\n', b'\n')
        previous = without_tree_unload_probes(source.decode('utf-8-sig')).encode('utf-8-sig')
        module = history.historical_tree_unload_collections_module(source, template)
        self.assertEqual(hashlib.sha256(module).hexdigest(), BASE_MODULE_SHA)
        self.assertEqual(hashlib.sha256(previous).hexdigest(), '9de2d85c0b8409b83ccf62e4824ef7a8186518d0bdffc92b53bd98b1f98da0b3')
        self.assertNotIn(b'tree.unload.', module)
        with self.assertRaises(fixtures.suite.FullError):
            fixtures.suite.client_collections_module(previous, template)

    def test_inverse_rejects_source_drift_without_normalization(self):
        for path in PATHS:
            source = history.without_tree_unload_supplement_measurement((ROOT/path).read_text(encoding='utf-8'), host=path.endswith('full_host.py'))
            for changed in (source+'\n', source.replace('\n', '\r\n'), source.replace('973', '974', 1)):
                with self.subTest(path=path), self.assertRaises(AssertionError):
                    history.without_tree_unload_measurement(changed, host=path.endswith('full_host.py'))

    def test_rebased_outer_hash_cannot_hide_changed_pinned_block_or_suffix(self):
        inventory = self.inventory()
        for path in PATHS:
            source = history.without_tree_unload_supplement_measurement((ROOT/path).read_text(encoding='utf-8'), host=path.endswith('full_host.py'))
            for changed in (source+'\n', source.replace('973', '974', 1)):
                forged = copy.deepcopy(inventory)
                forged[path]['candidate_sha256'] = hashlib.sha256(changed.encode()).hexdigest()
                with mock.patch.object(history.json, 'loads', return_value=forged), self.assertRaises(AssertionError):
                    history.without_tree_unload_measurement(changed, host=path.endswith('full_host.py'))


class UnloadSupplementHarnessHistoryTests(unittest.TestCase):
    def test_exact973_harness_and_complete_module_restored(self):
        for path in PATHS:
            current = (ROOT/path).read_text(encoding='utf-8')
            original = history.without_tree_unload_supplement_measurement(current, host=path.endswith('full_host.py'))
            old_contract = json.loads((ROOT/'tests/tree_unload_source_inverse.json').read_text(encoding='utf-8'))[path]
            self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), old_contract['candidate_sha256'])
            self.assertNotEqual(current, original)
            if not path.endswith('full_host.py'):
                namespace = {'__name__': 'historical_original27'}
                exec(compile(original, path, 'exec'), namespace)
                from scripts.native_historical_replay import without_tree_unload_supplement
                source = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n',b'\n')
                source = without_tree_unload_supplement(source.decode('utf-8-sig')).encode('utf-8-sig')
                template = (ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes().replace(b'\r\n',b'\n')
                self.assertEqual(namespace['CLIENT_COLLECTIONS_MESSAGE_COUNT'],973)
                self.assertEqual(hashlib.sha256(namespace['client_collections_module'](source,template)).hexdigest(),
                                 '66b2e8263c9a1a68c21996e02dd153bb3390cb3fb2481456b54d0c5990e39188')

    def test_supplement_inverse_rejects_drift_even_with_rebased_outer_hash(self):
        inventory = json.loads((ROOT/'tests/tree_unload_supplement_source_inverse.json').read_text(encoding='utf-8'))
        for path in PATHS:
            source = (ROOT/path).read_text(encoding='utf-8')
            for changed in (source+'\n',source.replace('976','977',1),source.replace('\n','\r\n')):
                with self.subTest(path=path), self.assertRaises(AssertionError):
                    history.without_tree_unload_supplement_measurement(changed,host=path.endswith('full_host.py'))
                forged = copy.deepcopy(inventory)
                forged[path]['candidate_sha256'] = hashlib.sha256(changed.encode()).hexdigest()
                with mock.patch.object(history.json,'loads',return_value=forged), self.assertRaises(AssertionError):
                    history.without_tree_unload_supplement_measurement(changed,host=path.endswith('full_host.py'))


if __name__ == '__main__':
    unittest.main()
