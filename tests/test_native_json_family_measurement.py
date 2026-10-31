"""Whole-family fixture and bounded observer checks, not native expected answers."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
import native_1c_json_family_contract as wire
import native_1c_json_family_replay as replay
import native_1c_tree_profiles as profiles

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / 'integrational_tests/measurements/json_family.bsl'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8')


def emit(*, missing=False, source=SOURCE):
    out = []
    vm = Interpreter(out.append)
    if missing:
        for name in ('прочитатьjson', 'readjson', 'записатьjson', 'writejson'):
            vm.functions.pop(name, None)
    with replay.temporary_file_helpers(vm):
        vm.execute(source)
    return ('\n'.join(out) + '\n').encode('ascii')


def synthetic_output(*, unavailable=False, observer=False):
    return wire.CALIBRATION + b''.join(
        f'JF-{index:02d}: ['.encode() +
        (b'observer-error' if observer and index == 31 else b'action-error' if unavailable and index == 1 else
         b'ok|S56:' + b'0078' * 56) + b']\n' for index in range(1, 32))


class JSONFamilyMeasurementTests(unittest.TestCase):
    def test_source_pin_and_whole_family_cases(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), profiles.JSON_FAMILY.source_sha256)
        parse(SOURCE)
        self.assertIn('Для N = 1 По 31 Цикл JFObserve(N); КонецЦикла;', SOURCE)
        for number in range(1, 32): self.assertEqual(SOURCE.count(f'N = {number} Тогда'), 1)
        self.assertNotIn('Вычислить(', SOURCE)
        self.assertNotIn('ОписаниеОшибки', SOURCE)
        self.assertEqual(SOURCE.count('Сообщить('), 5)
        self.assertIn('// !todo', SOURCE)

    def test_rectangular_wire_budget_and_rejections(self):
        raw = synthetic_output()
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(wire.MAX_ENCODED_BYTES, 8192)
        self.assertEqual(len(wire.require_available(raw)), 31)
        for bad in (raw + b'x', raw[:-1], raw.replace(b'JF-02:', b'JF-01:'),
                    raw.replace(b'S56:', b'S57:', 1), raw.replace(b'0078', b'007g', 1),
                    raw.replace(b'JF-C1: [S0:]', b'JF-C1: [S1:]')):
            with self.subTest(bad=bad[:20]), self.assertRaises(wire.ObservationError): wire.validate_output(bad)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(unavailable=True))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(synthetic_output(observer=True))

    def test_local_runtime_observation_is_not_native_evidence(self):
        raw = emit()
        self.assertEqual(len(wire.require_available(raw)), 31)
        self.assertFalse(any(row['status'] == 'observer-error' for row in wire.validate_output(raw)))
        with self.assertRaises(wire.AvailabilityError): wire.require_available(emit(missing=True))

    def test_temp_helpers_only_owned_paths_and_cleanup(self):
        vm = Interpreter(lambda _: None)
        with tempfile.TemporaryDirectory(prefix='json-unowned-') as tmp:
            outside = Path(tmp) / 'keep'; outside.write_text('keep', encoding='utf-8')
            with replay.temporary_file_helpers(vm) as allocated:
                vm.execute('p=ПолучитьИмяВременногоФайла("json");')
                path = Path(vm.variables['p']); self.assertTrue(path.is_file())
                delete = vm.functions['удалитьфайлы'].function
                with self.assertRaises(ValueError): delete(str(outside))
                self.assertEqual(outside.read_text(encoding='utf-8'), 'keep')
                allocate = vm.functions['получитьимявременногофайла'].function
                with self.assertRaises(ValueError): allocate('../escape')
                allocate('json')
                with self.assertRaises(ValueError): allocate('json')
                delete(str(path)); self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())

    def test_replay_adapter_is_explicit_and_source_bound_by_profile(self):
        import native_1c_full_host as full
        script = replay.execution_script(full.EXECUTE_SCRIPT)
        self.assertIn('with helper.temporary_file_helpers(interpreter):', script)
        self.assertEqual(script.count('interpreter.execute(source_text, str(source))'), 1)
        with self.assertRaises(ValueError): replay.execution_script('')
        with self.assertRaises(ValueError): replay.execution_script(full.EXECUTE_SCRIPT * 2)

if __name__ == '__main__': unittest.main()
