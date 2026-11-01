"""Whole-family fixture and bounded observer checks, not native expected answers."""
import hashlib
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
import native_1c_zip_family_contract as wire
import native_1c_tree_profiles as profiles

SOURCE_PATH = ROOT / 'integrational_tests/measurements/zip_family.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')


def emit(*, missing=False, source=SOURCE):
    out = []
    vm = Interpreter(out.append)
    if missing:
        for name in ('zipfilewriter', 'записьzipфайла'):
            vm.types.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="zip-test-") as tmp, mock.patch("tempfile.gettempdir", return_value=tmp):
        vm.execute(source)
        if list(Path(tmp).iterdir()):
            raise AssertionError("Owned fixture failed to clean temporary paths")
    return ('\n'.join(out) + '\n').encode('ascii')


def synthetic_output(*, unavailable=False, observer=False):
    return wire.CALIBRATION + b''.join(
        f'ZF-{index:02d}: ['.encode() +
        (b'observer-error' if observer and index == 32 else b'action-error' if unavailable and index == 1 else
         b'ok|S40:' + b'0078' * 40) + b']\n' for index in range(1, 33))


class ZipFamilyMeasurementTests(unittest.TestCase):
    def test_source_pin_and_whole_family_cases(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), profiles.ZIP_FAMILY.source_sha256)
        parse(SOURCE)
        self.assertLessEqual(len(SOURCE.encode()), 8192)
        self.assertIn('For N=1 To 32 Do ZFObserve(N);EndDo;', SOURCE)
        for number in range(1, 33): self.assertRegex(SOURCE, rf'\bN={number}\b')
        self.assertNotIn('Вычислить(', SOURCE)
        self.assertNotIn('ОписаниеОшибки', SOURCE)
        self.assertEqual(SOURCE.count('Сообщить('), 5)
        self.assertIn('// !todo', SOURCE)

    def test_rectangular_wire_budget_and_rejections(self):
        raw = synthetic_output()
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(wire.MAX_ENCODED_BYTES, 8192)
        self.assertEqual(len(wire.require_available(raw)), 32)
        for bad in (raw + b'x', raw[:-1], raw.replace(b'ZF-02:', b'ZF-01:'),
                    raw.replace(b'S40:', b'S57:', 1), raw.replace(b'0078', b'007g', 1),
                    raw.replace(b'ZF-C1: [S0:]', b'ZF-C1: [S1:]')):
            with self.subTest(bad=bad[:20]), self.assertRaises(wire.ObservationError): wire.validate_output(bad)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(unavailable=True))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(observer=True))

    def test_cleanup_sentinel_is_never_available_with_other_positive_controls(self):
        raw = synthetic_output()
        for number in (1, 24, 32):
            lines = raw.splitlines(keepends=True)
            encoded = ''.join(f'{u:04x}' for u in wire.CLEANUP_FAILURE_UNITS)
            lines[number+1] = f'ZF-{number:02d}: [ok|S8:{encoded}]\n'.encode()
            capture = b''.join(lines)
            self.assertEqual(len(wire.validate_output(capture)), 32)
            with self.assertRaises(wire.AvailabilityError): wire.require_available(capture)

    def test_local_runtime_observation_is_not_native_evidence(self):
        raw = emit()
        records = wire.validate_output(raw)
        if os.open in os.supports_dir_fd and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY'):
            self.assertEqual(len(wire.require_available(raw)), 32)
        else:
            # Temporary explicit Windows extraction gap, not native parity.
            self.assertEqual([r['case'] for r in records if r['status'] != 'ok'],
                             [6,7,8,9,10,11,12,21,22,25,26])
            with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)
        self.assertFalse(any(row['status'] == 'observer-error' for row in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(emit(missing=True))

    def test_action_failure_still_cleans_owned_paths(self):
        records = wire.validate_output(emit(missing=True))
        self.assertTrue(all(row['status'] == 'action-error' for row in records))

    def test_unexpected_children_are_not_recursively_swept(self):
        import yadinassi.file_io as files
        original = files.create_directory
        def create_with_sentinel(path):
            original(path)
            if Path(path).parent == Path(tmp):
                (Path(path) / 'keep.sentinel').write_bytes(b'owned-test-sentinel')
        with tempfile.TemporaryDirectory(prefix='zip-unexpected-') as tmp, \
                mock.patch('tempfile.gettempdir', return_value=tmp):
            output = []
            vm = Interpreter(output.append)
            vm.register_function('СоздатьКаталог', create_with_sentinel, 'CreateDirectory', returns_value=False)
            vm.execute(SOURCE)
            roots = list(Path(tmp).iterdir())
            self.assertEqual(len(roots), 32)
            for root in roots:
                self.assertEqual(list(root.iterdir()), [root / 'keep.sentinel'])
                self.assertEqual((root / 'keep.sentinel').read_bytes(), b'owned-test-sentinel')
            records = wire.validate_output(('\n'.join(output) + '\n').encode())
            self.assertTrue(all(records[i]['status'] == 'action-error' for i in range(32) if i != 23))
            self.assertEqual(records[23]['units'], wire.CLEANUP_FAILURE_UNITS)
            with self.assertRaises(wire.AvailabilityError): wire.require_available(('\n'.join(output)+'\n').encode())

    def test_owned_fixture_scope(self):
        self.assertIn('Root=GetTempFileName("zip-family");', SOURCE)
        self.assertIn('If F.Exists() Then', SOURCE)
        self.assertIn('If A.Count()=0 Then DeleteFiles(D)', SOURCE)
        self.assertNotIn('SetHidden', SOURCE)
        self.assertNotIn('DeleteFiles(TempFilesDir', SOURCE)
        self.assertNotIn('DOCTYPE', SOURCE)
        self.assertNotIn('http://', SOURCE)
        self.assertNotIn('file://', SOURCE)

if __name__ == '__main__': unittest.main()
