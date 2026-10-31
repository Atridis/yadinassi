"""Whole-family fixture and bounded observer checks, not native expected answers."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
import native_1c_xml_workflow_family_contract as wire
import native_1c_tree_profiles as profiles

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / 'integrational_tests/measurements/xml_workflow_family.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')


def emit(*, missing=False, source=SOURCE):
    out = []
    vm = Interpreter(out.append)
    if missing:
        for name in ('xmlreader', 'чтениеxml'):
            vm.types.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="xml-workflow-test-") as tmp, mock.patch("tempfile.gettempdir", return_value=tmp):
        vm.execute(source)
        if list(Path(tmp).iterdir()):
            raise AssertionError("Owned fixture failed to clean temporary paths")
    return ('\n'.join(out) + '\n').encode('ascii')


def synthetic_output(*, unavailable=False, observer=False):
    return wire.CALIBRATION + b''.join(
        f'XF-{index:02d}: ['.encode() +
        (b'observer-error' if observer and index == 33 else b'action-error' if unavailable and index == 1 else
         b'ok|S56:' + b'0078' * 56) + b']\n' for index in range(1, 34))


class XMLWorkflowFamilyMeasurementTests(unittest.TestCase):
    def test_source_pin_and_whole_family_cases(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), profiles.XML_WORKFLOW_FAMILY.source_sha256)
        parse(SOURCE)
        self.assertIn('Для N = 1 По 33 Цикл XFObserve(N); КонецЦикла;', SOURCE)
        for number in range(1, 34): self.assertEqual(SOURCE.count(f'N = {number} Тогда'), 1)
        self.assertNotIn('Вычислить(', SOURCE)
        self.assertNotIn('ОписаниеОшибки', SOURCE)
        self.assertEqual(SOURCE.count('Сообщить('), 5)
        self.assertIn('// !todo', SOURCE)

    def test_rectangular_wire_budget_and_rejections(self):
        raw = synthetic_output()
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(wire.MAX_ENCODED_BYTES, 8192)
        self.assertEqual(len(wire.require_available(raw)), 33)
        for bad in (raw + b'x', raw[:-1], raw.replace(b'XF-02:', b'XF-01:'),
                    raw.replace(b'S56:', b'S57:', 1), raw.replace(b'0078', b'007g', 1),
                    raw.replace(b'XF-C1: [S0:]', b'XF-C1: [S1:]')):
            with self.subTest(bad=bad[:20]), self.assertRaises(wire.ObservationError): wire.validate_output(bad)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(unavailable=True))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(observer=True))

    def test_local_runtime_observation_is_not_native_evidence(self):
        raw = emit()
        self.assertEqual(len(wire.require_available(raw)), 33)
        self.assertFalse(any(row['status'] == 'observer-error' for row in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(emit(missing=True))

    def test_action_failure_still_cleans_owned_paths(self):
        from yadinassi.xml_writer import BSLXMLWriter
        with mock.patch.object(BSLXMLWriter, 'write_text', side_effect=ValueError('injected')):
            raw = emit()
        records = wire.validate_output(raw)
        self.assertTrue(any(row['status'] == 'action-error' for row in records))
        self.assertFalse(any(row['status'] == 'observer-error' for row in records))

    def test_unexpected_children_are_not_recursively_swept(self):
        import yadinassi.file_io as files
        original = files.create_directory
        def create_with_sentinel(path):
            original(path)
            (Path(path) / 'keep.bin').write_bytes(b'owned-test-sentinel')
        with tempfile.TemporaryDirectory(prefix='xml-workflow-unexpected-') as tmp, \
                mock.patch('tempfile.gettempdir', return_value=tmp):
            output = []
            vm = Interpreter(output.append)
            vm.register_function('СоздатьКаталог', create_with_sentinel, 'CreateDirectory', returns_value=False)
            vm.execute(SOURCE)
            roots = list(Path(tmp).iterdir())
            self.assertEqual(len(roots), 3)
            for root in roots:
                self.assertEqual(list(root.iterdir()), [root / 'keep.bin'])
                self.assertEqual((root / 'keep.bin').read_bytes(), b'owned-test-sentinel')
            records = wire.validate_output(('\n'.join(output) + '\n').encode())
            self.assertTrue(all(records[i]['status'] == 'action-error' for i in (26, 27, 28)))

    def test_owned_fixture_scope(self):
        self.assertIn('Root = GetTempFileName("xml-workflow");', SOURCE)
        self.assertIn('Если F.Exists() Тогда', SOURCE)
        self.assertIn('Remaining.Count() = 0 Тогда DeleteFiles(Root)', SOURCE)
        self.assertNotIn('SetReadOnly', SOURCE)
        self.assertNotIn('SetHidden', SOURCE)
        self.assertNotIn('DeleteFiles(TempFilesDir', SOURCE)
        self.assertNotIn('DOCTYPE', SOURCE)
        self.assertNotIn('http://', SOURCE)
        self.assertNotIn('file://', SOURCE)

if __name__ == '__main__': unittest.main()
