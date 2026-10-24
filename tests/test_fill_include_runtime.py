"""Linux-only FillPropertyValues INCLUDE behavior bound to audited native PR86."""
import hashlib
from pathlib import Path
import unittest

from scripts.native_historical_replay import without_fill_exclude_probes
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context, current_native_target
from yadinassi.structures import BSLStructure, BSLFixedStructure, fill_property_values
from test_fill_include_checkpoint import CASES

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232'
# Native run 39825533352, attempt 1, synthetic 53af5fb18ce6ef6692f656dace7173485209fd68.
# Both source-bound native server and managed-client output independently audited.
NATIVE = (
    ('ok', 10, 20), ('ok', 1, 2), ('error', 1, 2), ('ok', 1, 2),
    ('ok', 10, 20), ('ok', 10, 20), ('ok', 10, 20),
    ('ok', 10, 20), ('ok', 10, 20), ('ok', 10, 20),
    ('error', 1, 20), ('error', 1, 20), ('error', 1, 20),
)
# Preexisting Windows interpreter contract, not new Windows native evidence.
WINDOWS = (
    ('ok', 10, 20), ('error', 1, 2), ('error', 1, 2), ('error', 1, 2),
    ('error', 1, 2), ('error', 10, 2), ('error', 10, 20),
    ('error', 1, 2), ('error', 1, 2), ('error', 10, 2),
    ('error', 10, 2), ('error', 10, 2), ('error', 10, 2),
)


def observe(include, target=None, exclude=None):
    destination = BSLStructure('First,Last', 1, 2)
    source = BSLStructure('First,Last', 10, 20)
    status = 'ok'
    try:
        if target is None:
            fill_property_values(destination, source, include, exclude)
        else:
            with target_context(target):
                fill_property_values(destination, source, include, exclude)
    except (ValueError, TypeError):
        status = 'error'
    return status, destination.get_member('First'), destination.get_member('Last')


class FillIncludeNativeRuntimeTests(unittest.TestCase):
    def test_exact_native_13_record_replay_with_unchanged_full_source_pin(self):
        raw = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
        canonical = without_fill_exclude_probes(raw.replace(b'\r\n', b'\n').decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), SOURCE_SHA256)
        expected = [f'fill.include-normalization.{label}: [{status};{{"N",{first}}};{{"N",{last}}}]'
                    for (label, _), (status, first, last) in zip(CASES, NATIVE)]
        self.assertEqual(hashlib.sha256(('\n'.join(expected) + '\n').encode()).hexdigest(), NATIVE_SUFFIX_SHA256)
        messages = []
        Interpreter(messages.append, native_target=LINUX_8_3_27_1508).execute(canonical.decode('utf-8-sig'))
        self.assertEqual(len(messages), 841)
        self.assertEqual(messages[828:], expected)

    def test_linux_only_matrix_and_unchanged_windows_and_direct_default(self):
        for (_, include), expected_linux, expected_windows in zip(CASES, NATIVE, WINDOWS):
            with self.subTest(include=include):
                self.assertEqual(observe(include, LINUX_8_3_27_1508), expected_linux)
                self.assertEqual(observe(include, WINDOWS_8_3_27_2342), expected_windows)
                self.assertEqual(observe(include), expected_windows)
        self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)

    def test_empty_vs_whitespace_distinction_and_lazy_right_to_left_copy(self):
        self.assertEqual(observe('', LINUX_8_3_27_1508), ('ok', 1, 2))
        self.assertEqual(observe(',', LINUX_8_3_27_1508), ('ok', 1, 2))
        self.assertEqual(observe(' ', LINUX_8_3_27_1508), ('error', 1, 2))
        for include in ('First,Missing,Last', 'First, Missing ,Last', 'First, ,Last'):
            self.assertEqual(observe(include, LINUX_8_3_27_1508), ('error', 1, 20))

    def test_unmeasured_whitespace_identifiers_exclude_and_simultaneous_lists_stay_guarded(self):
        for target in (LINUX_8_3_27_1508, WINDOWS_8_3_27_2342):
            for include in ('\tFirst', 'First\t', '\u00a0First', 'First\u00a0', '\u2003First', 'First\n', 'First-X', '1First'):
                with self.subTest(target=target, include=include):
                    self.assertEqual(observe(include, target), ('error', 1, 2))
            for excluded in ('', ',', ' First', 'First ', 'First,,Last', 'First, Last'):
                self.assertEqual(observe(None, target, excluded), ('error', 1, 2))
            self.assertEqual(observe('First', target, 'Last'), ('error', 1, 2))

    def test_fixed_target_guard_and_context_restoration_on_error_remain(self):
        for target in (LINUX_8_3_27_1508, WINDOWS_8_3_27_2342):
            destination = BSLFixedStructure(BSLStructure('First,Last', 1, 2))
            with self.assertRaises(ValueError):
                with target_context(target):
                    fill_property_values(destination, BSLStructure('First,Last', 10, 20), '')
            self.assertEqual(destination.get_member('First'), 1)
            self.assertEqual(destination.get_member('Last'), 2)
            self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)


NATIVE_SUFFIX_SHA256 = '938ea70845e61675a16974c6449db577a873b999e01e233025c54458bca5f216'

if __name__ == '__main__':
    unittest.main()
