"""Source-bound extension and exact historical inverse, never native results."""
import hashlib
from pathlib import Path
import unittest
from scripts import native_historical_replay as history
from scripts import native_1c_full_host as host
import test_native_async_fixture as fixtures
import test_native_1c_full_stage as stage
from test_native_tree_move_contract import synthetic_output

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'a0212150d3d5d2a7252971aa8ba509d439ced04e85b5a157ff1148bf3eff4574'
BASE_SHA = 'ca23e52041022f2085c6cb7d4393a84834e75c69856c756b92e8531ad35c7c3e'


class MoveHarnessTests(unittest.TestCase):
    def source(self):
        data = (ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA)
        return data

    def test_exact_old_source_and_runtime_harness_inverses(self):
        source = self.source()
        previous = history.without_tree_move_probes(source.decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(previous).hexdigest(), BASE_SHA)
        self.assertEqual(stage.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, 1022)
        self.assertEqual(host.COLLECTIONS_SOURCE_SHA256, SOURCE_SHA)
        for path in ('scripts/native_1c_full_host.py', 'scripts/native_1c_bootstrap/full_suite.py'):
            raw = (ROOT/path).read_text(encoding='utf-8')
            restored = fixtures.without_tree_move_measurement(raw, host=path.endswith('full_host.py'))
            self.assertIn(BASE_SHA, restored)
            for changed in (raw+'\n', raw.replace('\n','\r\n'), raw.replace(SOURCE_SHA,'0'*64)):
                with self.assertRaises(AssertionError):
                    fixtures.without_tree_move_measurement(changed, host=path.endswith('full_host.py'))

    def test_source_inverse_never_normalizes_or_accepts_unknown_edit(self):
        source = self.source().decode('utf-8-sig')
        for changed in (source+'\n', source.replace('\n','\r\n'), source.replace('Rows.mOvE','Rows.Move')):
            with self.assertRaises(ValueError):
                history.without_tree_move_probes(changed)

    def test_complete_load_prefix_and_move_required_independently(self):
        good = synthetic_output()
        self.assertEqual(host.validate_tree_load_observations(good)['records'],45)
        self.assertEqual(host.validate_tree_move_observations(good),{'records':1,'message_units':199})
        for changed in (good.replace(b'TM: [',b'TM: [!',1),good+b'TM: [!]\n',good[:-1]):
            with self.assertRaises(host.FullError): host.validate_tree_move_observations(changed)
        with self.assertRaises(host.FullError):
            host.validate_tree_load_observations(good.replace(b'TL45: [',b'TL45: [!',1))
