"""Whole-family fixture and bounded observer checks, not native expected answers."""
import hashlib
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
import native_1c_dom_family_contract as wire

SOURCE_PATH = ROOT / 'integrational_tests/measurements/dom_family.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')


def emit(*, missing=False, source=SOURCE):
    out = []
    vm = Interpreter(out.append)
    if missing:
        for name in ('domdocument', 'документdom'):
            vm.types.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="dom-test-") as tmp, mock.patch("tempfile.gettempdir", return_value=tmp):
        vm.execute(source)
        if list(Path(tmp).iterdir()):
            raise AssertionError("Owned fixture failed to clean temporary paths")
    return ('\n'.join(out) + '\n').encode('ascii')


def synthetic_output(*, unavailable=False, observer=False):
    return wire.CALIBRATION + b''.join(
        f'DM-{index:02d}: ['.encode() +
        (b'observer-error' if observer and index == 40 else b'action-error' if unavailable and index == 1 else
         b'ok|S40:' + b'0078' * 40) + b']\n' for index in range(1, 41))


class DOMFamilyMeasurementTests(unittest.TestCase):
    def test_source_pin_and_whole_family_cases(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), wire.SOURCE_SHA256)
        parse(SOURCE)
        self.assertLessEqual(len(SOURCE.encode()), 8192)
        self.assertIn('For N=1 To 40 Do DMObserve(N);EndDo;', SOURCE)
        for number in range(1, 41):
            self.assertEqual(SOURCE.count(f'N={number} Then'), 1)
        for rejected in ('Вычислить(', 'ОписаниеОшибки', 'DOCTYPE', 'ENTITY',
                         'http://', 'file://', 'EvaluateXPath', 'ReadWithContext'):
            self.assertNotIn(rejected, SOURCE)
        self.assertEqual(SOURCE.count('Сообщить('), 5)
        self.assertIn('// !todo', SOURCE)

    def test_rectangular_wire_budget_and_rejections(self):
        raw = synthetic_output()
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(wire.MAX_ENCODED_BYTES, 8192)
        self.assertEqual(len(wire.require_available(raw)), 40)
        for bad in (raw + b'x', raw[:-1], raw.replace(b'DM-02:', b'DM-01:'),
                    raw.replace(b'S40:', b'S57:', 1), raw.replace(b'0078', b'007g', 1),
                    raw.replace(b'DM-C1: [S0:]', b'DM-C1: [S1:]')):
            with self.subTest(bad=bad[:20]), self.assertRaises(wire.ObservationError): wire.validate_output(bad)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(unavailable=True))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(observer=True))

    def test_local_runtime_observation_is_not_native_evidence(self):
        raw = emit()
        self.assertEqual(len(wire.require_available(raw)), 40)
        self.assertFalse(any(row['status'] == 'observer-error' for row in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(emit(missing=True))

    def test_action_failure_still_cleans_owned_paths(self):
        original = 'W.Write(D,X);X.Close();'
        self.assertEqual(SOURCE.count(original), 1)
        raw = emit(source=SOURCE.replace(original, 'Raise "injected";'))
        records = wire.validate_output(raw)
        self.assertTrue(any(row['status'] == 'action-error' for row in records))
        self.assertFalse(any(row['status'] == 'observer-error' for row in records))

    def test_unexpected_children_are_not_recursively_swept(self):
        import yadinassi.file_io as files
        original = files.create_directory
        def create_with_sentinel(path):
            original(path)
            (Path(path) / 'keep.bin').write_bytes(b'owned-test-sentinel')
        with tempfile.TemporaryDirectory(prefix='dom-unexpected-') as tmp, \
                mock.patch('tempfile.gettempdir', return_value=tmp):
            output = []
            vm = Interpreter(output.append)
            vm.register_function('СоздатьКаталог', create_with_sentinel, 'CreateDirectory', returns_value=False)
            vm.execute(SOURCE)
            roots = list(Path(tmp).iterdir())
            self.assertEqual(len(roots), 1)
            for root in roots:
                self.assertEqual(list(root.iterdir()), [root / 'keep.bin'])
                self.assertEqual((root / 'keep.bin').read_bytes(), b'owned-test-sentinel')
            records = wire.validate_output(('\n'.join(output) + '\n').encode())
            self.assertTrue(all(records[i]['status'] == 'action-error' for i in range(39, 40)))

    def test_existing_fixture_root_is_never_claimed_or_cleaned(self):
        with tempfile.TemporaryDirectory(prefix='dom-collision-') as tmp:
            root = Path(tmp) / 'occupied'
            root.mkdir()
            sentinel = root / 'keep.bin'
            sentinel.write_bytes(b'owned-sentinel')
            output = []
            vm = Interpreter(output.append)
            vm.register_function('ПолучитьИмяВременногоФайла', lambda *args: str(root), 'GetTempFileName')
            vm.execute(SOURCE)
            self.assertEqual(list(root.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b'owned-sentinel')
            records = wire.validate_output(('\n'.join(output) + '\n').encode())
            self.assertTrue(all(records[i]['status'] == 'action-error' for i in range(39, 40)))

    def test_owned_fixture_scope(self):
        self.assertIn('Root=GetTempFileName("dom");', SOURCE)
        self.assertIn('If F.Exists() Then', SOURCE)
        self.assertIn('L.Count()=0 Then DeleteFiles(Root)', SOURCE)
        self.assertNotIn('SetHidden', SOURCE)
        self.assertNotIn('DeleteFiles(TempFilesDir', SOURCE)
        self.assertNotIn('DOCTYPE', SOURCE)
        self.assertNotIn('http://', SOURCE)
        self.assertNotIn('file://', SOURCE)

if __name__ == '__main__': unittest.main()
