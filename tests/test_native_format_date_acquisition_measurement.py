"""Synthetic witnesses verify new date observers, never native date answers."""
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
KINDS = ('names', 'tokens')
PREFIX = {'names': 'FN', 'tokens': 'FT'}
COUNTS = {'names': 52, 'tokens': 56}
SHAS = {'names': '8e8de30a26b0b146232ca3e66adcc9ea333b6d94af66d5844df84e9c7d79db60',
        'tokens': 'f9483d0a8b7f63907320d0599b9cf5022247f3fef06e0efd41c59234a0ec163e'}


def source(kind):
    return (ROOT / f'integrational_tests/measurements/format_date_{kind}.bsl').read_text(encoding='utf-8')


def wire(kind):
    return importlib.import_module(f'native_1c_format_date_{kind}_contract')


def fixed_rows(kind):
    rows = []
    for line in source(kind).split('// Fixed measurement inputs start here.\n', 1)[1].splitlines():
        match = re.fullmatch(PREFIX[kind] + r'Observe\("(\d{2})", "((?:[^\"]|\"\")*)"\); // ([a-z0-9.-]+)', line)
        if not match:
            raise AssertionError('Non-fixed date expression')
        rows.append((int(match[1]), match[2].replace('""', '"'), match[3]))
    return rows


def emit(kind, witness=None, *, missing=False):
    output = []
    vm = Interpreter(output.append)
    if missing:
        vm.functions.pop('format', None)
        vm.functions.pop('формат', None)
    if witness is not None:
        vm.register_function('Format', witness)
        vm.register_function('Формат', witness)
    vm.execute(source(kind))
    return ('\n'.join(output) + '\n').encode('ascii')


class DateAcquisitionObserverTests(unittest.TestCase):
    def test_source_pins_fixed_literal_calls_and_archives(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                text = source(kind)
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), SHAS[kind])
                self.assertEqual((ROOT / f'tests/fixtures/format_dates/{kind}{COUNTS[kind]}.bsl').read_bytes(), text.encode())
                rows = fixed_rows(kind)
                self.assertEqual([r[0] for r in rows], list(range(1, COUNTS[kind] + 1)))
                self.assertEqual(len({r[2] for r in rows}), COUNTS[kind])
                parse(text)
                for _, expression, _ in rows:
                    statements = parse(expression)
                    self.assertEqual(len(statements), 1)
                    call = statements[0].expression
                    self.assertIsInstance(call, ast.Call)
                    self.assertIsInstance(call.callee, ast.Name)
                    self.assertIn(call.callee.name, ('Format', 'Формат'))
                    self.assertEqual(len(call.arguments), 2)
                    self.assertTrue(all(isinstance(arg, ast.Literal) for arg in call.arguments))
                self.assertEqual(text.count('Вычислить(Expression)'), 1)
                self.assertNotIn('ОписаниеОшибки', text)
                self.assertNotIn('Выполнить(', text)
                self.assertLessEqual(len(text.encode()), 8192)

    def test_input_mapping_never_claims_acquisition_or_predicted_answers(self):
        for kind in KINDS:
            manifest = json.loads((ROOT / f'tests/fixtures/format_dates/{kind}{COUNTS[kind]}-mapping.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['source_sha256'], SHAS[kind])
            self.assertEqual(manifest['locale'], 'ru')
            self.assertEqual(manifest['evidence_status'], 'not_acquired')
            self.assertFalse(manifest['native_measurement_accepted'])
            self.assertFalse(manifest['runtime_parity_accepted'])
            self.assertEqual(manifest['documentation']['archive_sha256'], 'a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642')
            self.assertEqual([r['expression'] for r in manifest['cases']], [r[1] for r in fixed_rows(kind)])
            self.assertTrue(all(set(r) == {'case', 'expression', 'topic'} for r in manifest['cases']))

    def test_all_months_have_standalone_and_day_context_measurements(self):
        rows = fixed_rows('names')[4:]
        self.assertEqual(len(rows), 48)
        for month in range(1, 13):
            selected = [r for r in rows if r[2].startswith(f'm{month:02}.')]
            self.assertEqual(len(selected), 4)
            self.assertTrue(all(f"'2026{month:02}02153456'" in r[1] for r in selected))
            for token in ('MMM', 'MMMM', 'd MMM', 'd MMMM'):
                value = repr(token) if ' ' in token else token
                self.assertTrue(any(f';DF={value}")' in r[1] for r in selected))

    def test_intended_composite_masks_reach_scanner_without_bare_fallback(self):
        from yadinassi import formatting
        sentinel = ((False, 'synthetic-token'),)
        for kind, count in [('names', 26), ('tokens', 8)]:
            seen = []
            def witness(value, format_string):
                seen.append(format_string)
                return 'synthetic'
            wire(kind).require_available(emit(kind, witness))
            composites = []
            for format_string in seen:
                match = re.fullmatch(r'(?:L|Л)=ru;(DF|ДФ)=(.+)', format_string)
                if match is None or ' ' not in match[2]:
                    continue
                raw = match[2]
                self.assertIn(raw[0], ("'", '"'), format_string)
                self.assertEqual(raw[-1], raw[0], format_string)
                mask = raw[1:-1]
                composites.append(format_string)
                # The token witness isolates parameter selection, including MMM
                # spellings not yet admitted by the runtime. No native answer.
                with mock.patch.object(formatting, '_date_tokens', return_value=sentinel) as scanner:
                    self.assertEqual(formatting._parameters(format_string)['DF'], sentinel)
                    scanner.assert_called_once_with(mask)
                if not any(quote in mask for quote in ("'", '"')):
                    bare = format_string[:-len(raw)] + mask
                    with mock.patch.object(formatting, '_date_tokens', return_value=sentinel):
                        self.assertIsNone(formatting._parameters(bare)['DF'])
            self.assertEqual(len(composites), count)
            if kind == 'tokens':
                self.assertIn("L=ru;DF='MMMM dd'", composites)
                self.assertIn('L=ru;DF="\'d\' MMMM"', composites)
                self.assertIn("L=ru;DF='dddd MMMM'", composites)
                self.assertIn('L=ru;DF="MMMM \'d\'"', composites)
            # Both numeric positive controls also reach the real token scanner.
            for format_string in seen[:2]:
                tokens = formatting._parameters(format_string)['DF']
                self.assertIsNotNone(tokens)
                self.assertIn((True, 'yyyy'), tokens)
                self.assertIn((True, 'HH'), tokens)

    def test_weekdays_hour_boundaries_aliases_styles_and_precedence_are_fixed(self):
        rows = fixed_rows('tokens')
        for group, count in [('weekday.', 10), ('context.', 4), ('ru.', 5), ('year-quarter.', 4),
                             ('hour.', 10), ('local.', 10), ('precedence.', 9)]:
            self.assertEqual(sum(r[2].startswith(group) for r in rows), count)
        expressions = '\n'.join(r[1] for r in rows)
        for token in ('ddd|dddd', 'ддд|дддд', 'h|hh|H|HH|tt', 'ч|чч|Ч|ЧЧ|вв',
                      'y|yy|yyyy|q', 'д|дд|М|ММ|г|гг|гггг|к'):
            self.assertIn(token, expressions)
        for value in ('D', 'DD', 'T', 'DT', 'DDT'):
            self.assertIn(f'DLF={value}")', expressions)
        for value in ('Д', 'ДД', 'В', 'ДВ', 'ДДВ'):
            self.assertIn(f'ДЛФ={value}")', expressions)

    def test_witness_receives_explicit_ru_inputs_unchanged(self):
        for kind in KINDS:
            seen = []
            def witness(*args):
                seen.append(args)
                return 'synthetic'
            records = wire(kind).require_available(emit(kind, witness))
            self.assertEqual(len(seen), COUNTS[kind])
            self.assertTrue(all(r['status'] == 'ok' for r in records))
            self.assertTrue(all(fmt.startswith(('L=ru;', 'Л=ru;')) for _, fmt in seen))
            self.assertEqual([args[1] for args in seen],
                             [parse(expr)[0].expression.arguments[1].value for _, expr, _ in fixed_rows(kind)])

    def test_utf16_empty_nbsp_and_supplementary_outputs_are_lossless(self):
        for kind in KINDS:
            for text, units in [('', ()), (' \u00a0\U0001f600', (32, 160, 55357, 56832))]:
                records = wire(kind).require_available(emit(kind, lambda *args: text))
                self.assertTrue(all(r['units'] == units for r in records))

    def test_rectangular_maximum_fits_unchanged_output_cap(self):
        for kind, maximum in [('names', 7590), ('tokens', 8170)]:
            raw = emit(kind, lambda *args: 'x' * 32)
            contract = wire(kind)
            self.assertEqual(len(raw), maximum)
            self.assertEqual(contract.MAX_ENCODED_BYTES, maximum)
            self.assertEqual(contract.MAX_OUTPUT_BYTES, 8192)
            self.assertLessEqual(maximum, contract.MAX_OUTPUT_BYTES)
            contract.require_available(raw)

    def test_action_and_observer_failures_are_distinct_and_private(self):
        def fails(*args):
            raise ValueError('PRIVATE must not be exported')
        for kind in KINDS:
            contract = wire(kind)
            raw = emit(kind, fails)
            self.assertNotIn(b'PRIVATE', raw)
            self.assertTrue(all(r['status'] == 'action-error' for r in contract.validate_output(raw)))
            with self.assertRaises(contract.AvailabilityError):
                contract.require_available(raw)
            for value in (None, Decimal(1), True, 'x' * 33):
                raw = emit(kind, lambda *args: value)
                self.assertTrue(all(r['status'] == 'observer-error' for r in contract.validate_output(raw)))
                with self.assertRaises(contract.AvailabilityError):
                    contract.require_available(raw)

    def test_unsupported_tokens_can_be_acquired_but_controls_cannot_fail(self):
        for kind in KINDS:
            raw = emit(kind, lambda *args: 'A')
            prefix = PREFIX[kind].encode()
            unsupported = raw.replace(prefix + b'-05: [ok|S1:0041]', prefix + b'-05: [action-error]')
            self.assertEqual(wire(kind).require_available(unsupported)[4]['status'], 'action-error')
            for case in (b'01', b'02', b'03', b'04'):
                unavailable = raw.replace(prefix + b'-' + case + b': [ok|S1:0041]', prefix + b'-' + case + b': [action-error]')
                with self.assertRaises(wire(kind).AvailabilityError):
                    wire(kind).require_available(unavailable)
            observer = raw.replace(prefix + b'-05: [ok|S1:0041]', prefix + b'-05: [observer-error]')
            with self.assertRaises(wire(kind).AvailabilityError):
                wire(kind).require_available(observer)

    def test_missing_api_is_not_successful_acquisition(self):
        for kind in KINDS:
            with self.assertRaises(wire(kind).AvailabilityError):
                wire(kind).require_available(emit(kind, missing=True))

    def test_noncanonical_hostile_wire_is_rejected(self):
        for kind in KINDS:
            raw = emit(kind, lambda *args: 'A')
            prefix = PREFIX[kind].encode()
            mutations = [raw[:-1], raw + b'\n', raw.replace(prefix + b'-01:', prefix + b'-02:', 1),
                         raw.replace(b'S1:0041', b'S01:0041', 1), raw.replace(b'S1:0041', b'S2:0041', 1),
                         raw.replace(b'S1:0041', b'S1:004X', 1), raw.replace(b'S1:0041', b'S1:0041secret', 1),
                         raw.replace(b'S6:0041', b'S6:0042', 1), raw.replace(b'\n', b'\r\n'),
                         bytearray(raw), raw.decode(), b'x' * 8193]
            for mutated in mutations:
                with self.assertRaises(wire(kind).ObservationError):
                    wire(kind).validate_output(mutated)

    def test_profiles_cannot_substitute_one_anothers_wire(self):
        for left, right in [('names', 'tokens'), ('tokens', 'names')]:
            with self.assertRaises(wire(left).ObservationError):
                wire(left).validate_output(emit(right, lambda *args: 'A'))


if __name__ == '__main__':
    unittest.main()
