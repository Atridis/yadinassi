"""Audited Execute checkpoint, exact history and fresh direct-witness packaging."""
import hashlib
import json
from pathlib import Path
import re
import unittest

from scripts.native_historical_replay import (
    TRAILING_OMITTED_BASE_BLOB, TRAILING_OMITTED_BASE_SHA256,
    TRAILING_OMITTED_SOURCE_SHA256, TRAILING_OMITTED_PROBE_BLOCKS,
    TRAILING_OMITTED_DIRECT_SOURCE_SHA256, TRAILING_OMITTED_DIRECT_BLOCK,
    without_trailing_omitted_direct_probe,
    HISTORICAL_FUNCTIONS_BLOB, git_blob, historical_functions_source,
    without_trailing_omitted_probes,
)
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.native_targets import WINDOWS_8_3_27_2342, LINUX_8_3_27_1508
from yadinassi.syntax.parser import parse

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    'OmitProbeDefaults()',
    'OmitProbeRequired()',
    'OmitProbeRequired(,)',
    'OmitProbeRequired(,,)',
    'OmitProbeDefaults(5,)',
    'OmitProbeDefaults(5,Undefined)',
    'OmitProbeOne(OmitProbeTick(),)',
    'OmitProbeOne(OmitProbeTick(),2,)',
    'OmitProbeRequired(OmitProbeTick(),,)',
)


class TrailingOmittedCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'integrational_tests/tests/functions.bsl').read_bytes().replace(b'\r\n', b'\n')
        cls.source = cls.raw.decode('utf-8')
        cls.measurement = without_trailing_omitted_direct_probe(cls.source)
        cls.previous = without_trailing_omitted_probes(cls.source)
        cls.fixture = json.loads((ROOT / 'tests/fixtures/trailing_omitted_linux.json').read_text(encoding='utf-8'))

    def test_exact_full_source_and_three_part_inverse(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), TRAILING_OMITTED_DIRECT_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(self.measurement.encode()).hexdigest(), TRAILING_OMITTED_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(self.previous.encode()).hexdigest(), TRAILING_OMITTED_BASE_SHA256)
        self.assertEqual(git_blob(self.previous.encode()), TRAILING_OMITTED_BASE_BLOB)
        self.assertEqual(len(TRAILING_OMITTED_PROBE_BLOCKS), 3)
        for start, end in TRAILING_OMITTED_PROBE_BLOCKS:
            self.assertEqual(self.source.count(start), 1)
            self.assertEqual(self.source.count(end), 1)
        for ending in ('\n', '\r\n'):
            transported = self.source.replace('\n', ending).replace('\r\n', '\n')
            self.assertEqual(without_trailing_omitted_probes(transported), self.previous)

    def test_inverse_rejects_old_new_and_boundary_mutations(self):
        mutants = [self.source + '\n', '\ufeff' + self.source,
                   self.source.replace('OmitProbeDefaults(5,)', 'OmitProbeDefaults(6,)', 1),
                   self.source.replace('Result = 99;', 'Result = 98;', 1),
                   self.source.replace('Перем МодульноеВычисления;', 'Перем Изменено;', 1)]
        for start, end in TRAILING_OMITTED_PROBE_BLOCKS:
            mutants.extend((self.source.replace(start, '// removed\n', 1),
                            self.source.replace(end, '// removed\n', 1), self.source + start))
        for mutant in mutants:
            with self.subTest(tail=mutant[-70:]), self.assertRaises(ValueError):
                without_trailing_omitted_probes(mutant)

    def test_frozen_windows_replay_retains_its_entire_original_source(self):
        output = (ROOT / 'tests/fixtures/native_windows/functions.out').read_bytes()
        for ending in (b'\n', b'\r\n'):
            source = self.raw.replace(b'\n', ending)
            replay = historical_functions_source(source, output)
            self.assertEqual(git_blob(replay), HISTORICAL_FUNCTIONS_BLOB)
            self.assertEqual(replay, historical_functions_source(self.previous.encode(), output))

    def test_nine_cases_remain_dynamic_with_one_valid_direct_positive(self):
        start, end = TRAILING_OMITTED_PROBE_BLOCKS[1]
        helpers = self.source.split(start)[1].split(end)[0]
        cases = re.findall(r'OmitProbeObserve\("([^"\n]+)"\)', helpers)
        self.assertEqual(tuple(cases), CASES)
        self.assertEqual(len(set(cases)), 9)
        self.assertEqual(helpers.count('Execute("Result = " + Expression + ";");'), 1)
        self.assertNotRegex(helpers, r'\b(?:While|For|Goto|New|Import)\b')
        for private in ('ErrorDescription', 'ErrorInfo', 'Description', 'ModuleName', 'LineNumber'):
            self.assertNotIn(private, helpers)
        for case in CASES:
            # Only the measured valid default call is also a literal direct witness.
            direct = 1 if case == 'OmitProbeDefaults(5,)' else 0
            self.assertEqual(helpers.count(case), helpers.count('"' + case + '"') + direct)
        self.assertEqual(helpers.count('Result = OmitProbeDefaults(5,);'), 1)
        self.assertEqual(helpers.count('Raise "omit-probe-direct";'), 1)

    def test_native_module_order_and_existing_postcreate_directive_remain(self):
        self.assertTrue(self.source.startswith('// NativePostCreate: ExportProbeAfterCreate\n'))
        helpers_started = body_started = False
        for node in parse(self.source):
            if isinstance(node, ast.Var):
                self.assertFalse(helpers_started or body_started)
            elif isinstance(node, ast.Routine):
                self.assertFalse(body_started)
                helpers_started = True
            else:
                body_started = True
        start, end = TRAILING_OMITTED_PROBE_BLOCKS[2]
        observations = self.source.split(start)[1].split(end)[0]
        self.assertEqual(observations.count('Message(CollectTrailingOmittedProbe());'), 1)
        self.assertEqual(self.source.count('ExportProbeAfterCreate('), 1)

    def test_all_136_initialization_and_18_postcreate_records_are_retained(self):
        def run(source, target):
            output = []
            interpreter = Interpreter(output.append, native_target=target)
            try:
                interpreter.execute(source)
                initial = len(output)
                interpreter.execute('ThisObject.ExportProbeAfterCreate(ThisObject);')
                interpreter.ensure_complete()
                return output, initial
            finally:
                interpreter.close()

        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                previous, previous_count = run(self.previous, target)
                current, current_count = run(self.source, target)
                self.assertEqual((previous_count, current_count), (136, 137))
                self.assertEqual(current[:136], previous[:136])
                self.assertEqual(current[137:], previous[136:])
                self.assertEqual(len(current[137:]), 18)
                # Bound to the independently audited Execute capture, not guessed.
                self.assertEqual(current[136], self.fixture['native_token'])
                self.assertRegex(current[136], r'^omit\.v1:(?:[SE][0-9]{4}){9}$')
                self.assertEqual(len(current[136].encode('ascii')), 53)

    def test_live_native_module_is_complete_not_historical_projection(self):
        from test_native_1c_full_stage import suite
        self.assertEqual(suite.SCENARIOS, ('collections', 'dates', 'functions', 'numbers', 'strings', 'values'))
        self.assertEqual(suite.INPUT_FILES['integrational_tests/tests/functions.bsl'], 'scenarios/functions.bsl')
        self.assertEqual(suite.generated_module(self.raw).decode('utf-8-sig'), self.source)
        self.assertNotIn('without_trailing_omitted_probes',
                         (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8'))
        self.assertNotIn('without_trailing_omitted_probes',
                         (ROOT / 'scripts/native_1c_bootstrap/full_suite.py').read_text(encoding='utf-8'))

    def test_capture_provenance_and_complete_measured_source_replay(self):
        from scripts import native_1c_full_host as host
        fixture = self.fixture
        self.assertEqual(fixture['schema'], 'trailing-omitted-native-v1')
        self.assertEqual(fixture['native_target'], 'linux-8.3.27.1508')
        self.assertEqual(fixture['capture']['run_id'], 40029817101)
        self.assertEqual(fixture['capture']['source_sha256'], TRAILING_OMITTED_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(host.generated_module(self.measurement.encode())).hexdigest(),
                         fixture['capture']['module_sha256'])
        self.assertEqual(len(fixture['records']), 9)
        token = 'omit.v1:' + ''.join(row['status'] + str(row['argument_calls'])
                    + str(row['body_calls']) + f"{row['result']:02d}" for row in fixture['records'])
        self.assertEqual(token, fixture['native_token'])
        self.assertEqual(fixture['capture']['acceptance_status'], 'rejected_measurement_only')
        for source in (self.measurement, self.source):
            output = []
            interpreter = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
            try:
                interpreter.execute(source)
                output.append('export-phase.post-create: [begin]')
                interpreter.execute('ThisObject.ExportProbeAfterCreate(ThisObject);')
                output.append('export-phase.post-create: [ok]')
                interpreter.ensure_complete()
            finally:
                interpreter.close()
            raw = ('\n'.join(output) + '\n').encode()
            self.assertEqual(len(output), fixture['capture']['functions_message_count'])
            self.assertEqual(len(raw), fixture['capture']['functions_output_bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture['capture']['functions_output_sha256'])

    def test_direct_inverse_rejects_witness_and_note_mutations(self):
        start, end = TRAILING_OMITTED_DIRECT_BLOCK
        self.assertEqual(self.source.count(start), 1)
        self.assertEqual(self.source.count(end), 1)
        for source in (self.source.replace('Result <> 52', 'Result <> 51', 1),
                       self.source.replace(start, '', 1), self.source + end,
                       self.source.replace('direct positive witness requires', 'changed witness requires', 1)):
            with self.assertRaises(ValueError):
                without_trailing_omitted_direct_probe(source)


if __name__ == '__main__':
    unittest.main()
