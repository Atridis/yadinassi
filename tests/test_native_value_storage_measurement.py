"""Synthetic wire cases for the fixed ValueStorage acquisition, not a native oracle."""
import hashlib
from pathlib import Path
import re
import sys
import unittest
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_value_storage_contract as wire

SOURCE = (ROOT / 'integrational_tests/measurements/value_storage.bsl').read_bytes()
SOURCE_SHA = '08f35c3672b3f3436df451ad8f7a604e5db7729f3b42dbae645e1ac362d5ca23'

# Deliberately synthetic, in the allowed per-case grammar.
_SYNTHETIC = ('1','1','1','1','type-ok','type-ok','1','11','ABCA','ABCA',
              'ABCA','ABCAB','ABCAB','A','A','A','ABCA','A','A','1',
              'A','1','A','A','1','1','1')

def emit(*, missing=False):
    rows = [b'VS-C1: [wire-v1]\n']
    for i in wire.CASE_IDS:
        value = _SYNTHETIC[i-1]
        payload = (wire.NEGATIVE_PHASES[i] + '-error' if i in wire.NEGATIVE_PHASES
                   else 'construct-error' if missing and i == 1 else 'ok|' + value)
        rows.append(f'VS-{i:02d}: [{payload}]\n'.encode('ascii'))
    return b''.join(rows)

def with_synthetic_case(source):
    """Keep the real observer/helper; replace only unsupported storage actions."""
    start = source.index('Функция VSCase(Знач N)\n')
    end = source.index('КонецФункции\n', start) + len('КонецФункции\n')
    stub = ['Функция VSCase(Знач N)']
    stub += ['Если N = 9 Тогда VSPhase = "construct"; ВызватьИсключение "private"; КонецЕсли;',
             'Если N = 10 Тогда VSPhase = "inspect"; ВызватьИсключение "private"; КонецЕсли;',
             'Если N = 11 Тогда Возврат "bad!"; КонецЕсли;',
             'Если N = 12 Тогда Возврат "xxxxxxxxxxxxxxxxx"; КонецЕсли;']
    stub += [f'Если N = {i} Тогда Возврат "{value}"; КонецЕсли;'
             for i, value in enumerate(_SYNTHETIC, 1)]
    stub += ['ВызватьИсключение "unreachable";', 'КонецФункции']
    return source[:start] + '\n'.join(stub) + '\n' + source[end:]

class ValueStorageWireTests(unittest.TestCase):
    def test_source_identity_and_finite_cases(self):
        self.assertEqual(hashlib.sha256(SOURCE).hexdigest(), SOURCE_SHA)
        text = SOURCE.decode('utf-8')
        cases = re.findall(r'(?:Если|ИначеЕсли) N = (\d+) Тогда', text)
        self.assertEqual(list(map(int, cases)), list(wire.CASE_IDS))
        self.assertEqual(text.count('Перем VSPhase;'), 1)
        self.assertLess(text.index('Перем VSPhase;'), text.index('Функция '))
        self.assertEqual(text.count('Сообщить('), 5)
        self.assertEqual(text.count('Вычислить('), 5)
        self.assertNotIn('ОписаниеОшибки', text)
        self.assertNotIn('Выполнить(', text)
        self.assertIn('Для N = 1 По 27 Цикл Если N <> 18 Тогда VSObserve(N); КонецЕсли; КонецЦикла;', text)

    def test_source_is_exact_historical_projection_and_replays_capture(self):
        fixture = ROOT / 'tests/fixtures/value_storage'
        self.assertEqual(hashlib.sha256((fixture / 'native27.bsl').read_bytes()).hexdigest(),
                         '0d6c7ddc213df18af0140a4ecff88246bfc293fd4483746f3137f96ca853ca2e')
        self.assertEqual(hashlib.sha256((fixture / 'provenance.json').read_bytes()).hexdigest(),
                         '1a5d5d4d5785b836c46f2b835cf40d52d5c432af8c345ad407791e9db8b20ec4')
        previous = (fixture / 'native27.bsl').read_text(encoding='utf-8')
        start = previous.index('    ИначеЕсли N = 18 Тогда\n')
        end = previous.index('    ИначеЕсли N = 19 Тогда\n', start)
        projected = (previous[:start] + previous[end:]).replace(
            'Для N = 1 По 27 Цикл VSObserve(N); КонецЦикла;',
            'Для N = 1 По 27 Цикл Если N <> 18 Тогда VSObserve(N); КонецЕсли; КонецЦикла;').replace(
            '// SOURCE ONLY. No native expectations. Run only after isolated acquisition review.',
            '// Fixed ValueStorage measurement, excluding unimplemented compression case 18.')
        self.assertEqual(projected.encode('utf-8'), SOURCE)
        old = (fixture / 'native27-linux-8.3.27.1508.out').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), '99e0452fe2e13973ba80bb057b202d0beb3aa9fd32c95729c0716670c957c7cd')
        expected = b''.join(line for line in old.splitlines(keepends=True) if not line.startswith(b'VS-18:'))
        wire.require_available(expected)
        actual = []
        Interpreter(actual.append).execute(SOURCE.decode('utf-8'))
        self.assertEqual(('\n'.join(actual)+'\n').encode('ascii'), expected)

    def test_fixed_wire_and_rectangular_budget(self):
        self.assertEqual(wire.CASE_COUNT, 26)
        self.assertEqual(wire.MESSAGE_COUNT, 27)
        self.assertEqual(wire.MAX_ENCODED_BYTES, 823)
        self.assertEqual(wire.MAX_OUTPUT_BYTES, 823)
        self.assertEqual(len(wire.require_available(emit())), 26)

    def test_real_observer_with_synthetic_case_and_phases(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute(with_synthetic_case(SOURCE.decode('utf-8')))
        raw = ('\n'.join(output) + '\n').encode('ascii')
        self.assertEqual(len(output), 27)
        self.assertIn(b'VS-09: [construct-error]\n', raw)
        self.assertIn(b'VS-10: [inspect-error]\n', raw)
        self.assertIn(b'VS-11: [observer-error]\n', raw)
        self.assertIn(b'VS-12: [observer-error]\n', raw)
        self.assertNotIn(b'private', raw)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)

    def test_action_errors_are_observed_separately(self):
        records = {record['case']: record for record in wire.require_available(emit())}
        for case, phase in wire.NEGATIVE_PHASES.items():
            self.assertEqual(records[case]['status'], 'action-error')
            self.assertEqual(records[case]['phase'], phase)
        raw = emit().replace(b'VS-24: [ok|A]', b'VS-24: [get2-error]', 1)
        self.assertEqual(wire.validate_output(raw)[22]['phase'], 'get2')
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)

    def test_all_supported_positive_cases_require_success(self):
        self.assertEqual(wire.POSITIVE_CASE_IDS, tuple(range(1, 18)) + tuple(range(23, 28)))
        for case in wire.POSITIVE_CASE_IDS:
            original = f'VS-{case:02d}: [ok|{_SYNTHETIC[case-1]}]'.encode('ascii')
            for phase in sorted(wire._phases(case) & wire._ACTION):
                raw = emit().replace(original, f'VS-{case:02d}: ['.encode() + phase + b'-error]', 1)
                with self.subTest(case=case, phase=phase), self.assertRaises(wire.AvailabilityError):
                    wire.require_available(raw)
            if case != 23:
                raw = emit().replace(original, f'VS-{case:02d}: [ok|type]'.encode(), 1)
                with self.subTest(case=case, wrong_type=True), self.assertRaises(wire.AvailabilityError):
                    wire.require_available(raw)

    def test_invalid_input_controls_require_exact_observed_phase(self):
        self.assertEqual(wire.NEGATIVE_PHASES, {19: 'construct', 20: 'construct', 21: 'get1', 22: 'construct'})
        for case, phase in wire.NEGATIVE_PHASES.items():
            original = f'VS-{case:02d}: [{phase}-error]'.encode('ascii')
            alternatives = [f'ok|{_SYNTHETIC[case-1]}']
            alternatives += [value.decode()+'-error' for value in sorted(wire._phases(case))
                             if value.decode() != phase]
            for payload in alternatives:
                raw = emit().replace(original, f'VS-{case:02d}: [{payload}]'.encode(), 1)
                with self.subTest(case=case, payload=payload), self.assertRaises(wire.AvailabilityError):
                    wire.require_available(raw)

    def test_observer_and_control_errors_reject_acquisition(self):
        for phase in (b'setup', b'mutate-original', b'mutate-get1', b'inspect', b'observer'):
            raw = emit().replace(b'VS-09: [ok|ABCA]', b'VS-09: [' + phase + b'-error]', 1)
            self.assertEqual(wire.validate_output(raw)[8]['status'], 'observer-error')
            with self.subTest(phase=phase), self.assertRaises(wire.AvailabilityError):
                wire.require_available(raw)
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(emit(missing=True))
        for case in (1, 2, 3, 4):
            raw = emit().replace(f'VS-{case:02d}: [ok|1]'.encode(), f'VS-{case:02d}: [ok|0]'.encode(), 1)
            with self.subTest(case=case), self.assertRaises(wire.AvailabilityError):
                wire.require_available(raw)
        raw = emit().replace(b'VS-23: [ok|A]', b'VS-23: [ok|B]', 1)
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)

    def test_strict_closed_per_case_grammar(self):
        raw = emit()
        mutations = (raw[:-1], raw+b'\n', raw.replace(b'VS-01:', b'VS-02:', 1),
                     raw.replace(b'wire-v1', b'wire-v2', 1), raw.replace(b'\n',b'\r\n'),
                     raw.replace(b'VS-01: [ok|1]', b'VS-01: [ok|A]',1),
                     raw.replace(b'VS-09: [ok|ABCA]', b'VS-09: [ok|ABCD]',1),
                     raw.replace(b'VS-01: [ok|1]', b'VS-01: [get2-error]',1),
                     raw.replace(b'VS-01: [ok|1]', b'VS-01: [observer-error private]',1),
                     raw.replace(b'VS-01: [ok|1]', b'VS-01: [ok|11111111111111111]',1),
                     raw.replace(b'VS-01: [ok|1]', b'VS-01: [ok|\xff]',1),
                     bytearray(raw), raw.decode('ascii'), b'x'*824)
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)[:40]), self.assertRaises(wire.ObservationError):
                wire.validate_output(mutation)

if __name__ == '__main__': unittest.main()
