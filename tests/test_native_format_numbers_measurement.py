"""Synthetic wire cases for a temporary ValueStorage acquisition, not a native oracle."""
import hashlib
from pathlib import Path
import re
import sys
import unittest
from yadinassi import Interpreter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_format_numbers_contract as wire

SOURCE = (ROOT / 'integrational_tests/measurements/format_numbers.bsl').read_bytes()
SOURCE_SHA = '0d6c7ddc213df18af0140a4ecff88246bfc293fd4483746f3137f96ca853ca2e'

# Deliberately synthetic, in the allowed per-case grammar.
_SYNTHETIC = ('1','1','1','1','type-ok','type-ok','1','11','ABCA','ABCA',
              'ABCA','ABCAB','ABCAB','A','A','A','ABCA','A','A','1',
              'A','1','A','A','1','1','1')

def emit(*, missing=False):
    rows = [b'VS-C1: [wire-v1]\n']
    for i, value in enumerate(_SYNTHETIC, 1):
        payload = 'construct-error' if missing and i == 1 else 'ok|' + value
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
        self.assertEqual(list(map(int, cases)), list(range(1, 28)))
        self.assertEqual(text.count('Перем VSPhase;'), 1)
        self.assertLess(text.index('Перем VSPhase;'), text.index('Функция '))
        self.assertEqual(text.count('Сообщить('), 5)
        self.assertEqual(text.count('Вычислить('), 5)
        self.assertNotIn('ОписаниеОшибки', text)
        self.assertNotIn('Выполнить(', text)
        self.assertIn('Для N = 1 По 27 Цикл VSObserve(N); КонецЦикла;', text)

    def test_fixed_wire_and_rectangular_budget(self):
        self.assertEqual(wire.CASE_COUNT, 27)
        self.assertEqual(wire.MESSAGE_COUNT, 28)
        self.assertEqual(wire.MAX_ENCODED_BYTES, 854)
        self.assertEqual(wire.MAX_OUTPUT_BYTES, 854)
        self.assertEqual(len(wire.require_available(emit())), 27)

    def test_real_observer_with_synthetic_case_and_phases(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute(with_synthetic_case(SOURCE.decode('utf-8')))
        raw = ('\n'.join(output) + '\n').encode('ascii')
        self.assertEqual(len(output), 28)
        self.assertIn(b'VS-09: [construct-error]\n', raw)
        self.assertIn(b'VS-10: [inspect-error]\n', raw)
        self.assertIn(b'VS-11: [observer-error]\n', raw)
        self.assertIn(b'VS-12: [observer-error]\n', raw)
        self.assertNotIn(b'private', raw)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)

    def test_action_errors_are_observed_separately(self):
        raw = emit().replace(b'VS-19: [ok|A]', b'VS-19: [construct-error]', 1)
        self.assertEqual(wire.require_available(raw)[18]['status'], 'action-error')
        raw = emit().replace(b'VS-24: [ok|A]', b'VS-24: [get2-error]', 1)
        self.assertEqual(wire.require_available(raw)[23]['phase'], 'get2')

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
                     bytearray(raw), raw.decode('ascii'), b'x'*855)
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)[:40]), self.assertRaises(wire.ObservationError):
                wire.validate_output(mutation)

if __name__ == '__main__': unittest.main()
