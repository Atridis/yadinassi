"""Offline wire tests only; synthetic records are not native 1C evidence."""
from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest

import test_native_client_collections_host as fixtures

full = fixtures.full
suite = fixtures.suite
encode = fixtures.host_fixture.encode


class ClientWireV3Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ClientCollectionsHostTests()
        self.fixture.setUp()
        self.stage = self.fixture.all_clients()
        # The codec is identity-agnostic: semantic identities are independently
        # bound by host validators after expansion, not inferred from neighbours.
        self.stage['client_numbers'] = dict(copy.deepcopy(self.stage['client_values']),
            source_sha256='1' * 64, module_sha256='2' * 64, roundtrip_sha256='3' * 64,
            conversion_verified=True)

    def roundtrip(self, stage):
        before = copy.deepcopy(stage)
        wire = suite.encode_stage_wire(stage)
        snapshot = copy.deepcopy(wire)
        self.assertEqual(wire['schema'], 3)
        self.assertEqual(suite.decode_stage_wire(wire), before)
        self.assertEqual(full.decode_stage3_wire(wire), before)
        self.assertEqual(wire, snapshot)
        self.assertEqual(stage, before)
        self.assertLessEqual(len(encode(wire)), 8192)
        return wire

    def reject_wire(self, wire):
        with self.assertRaises(suite.FullError):
            suite.decode_stage_wire(wire)
        with self.assertRaises(ValueError):
            full.decode_stage3_wire(wire)

    def test_six_record_roundtrip_retains_every_hash_proof_and_conversion_flag(self):
        wire = self.roundtrip(self.stage)
        legacy_shape = fixtures.ClientCollectionsHostTests.compact(self.stage)
        numbers = legacy_shape['client_numbers']
        numbers['hashes'] = [numbers.pop(name) for name in full.CLIENT_WIRE_HASHES]
        numbers['proof'] = [numbers.pop(name) for name in full.CLIENT_WIRE_PROOF]
        self.assertEqual(len(encode(legacy_shape)) - len(encode(wire)), 792)
        for key in full.CLIENT_WIRE_V3_RECORDS:
            self.assertEqual(len(wire[key]['process_diagnostics']), 5)
            self.assertEqual(len(wire[key]['process_diagnostics'][4]), 7)
        self.assertIs(wire['client_numbers']['conversion_verified'], True)

    def test_numbers_alone_and_every_optional_combination_roundtrip(self):
        optional = ('client_dates', 'client_values', 'client_collections', 'client_watchdog')
        for selected in itertools.product((False, True), repeat=len(optional)):
            stage = copy.deepcopy(self.stage)
            for key, present in zip(optional, selected):
                if not present:
                    del stage[key]
            with self.subTest(selected=selected):
                self.roundtrip(stage)

    def test_existing_schema_one_and_two_wire_are_unchanged(self):
        stage = copy.deepcopy(self.stage)
        del stage['client_numbers']
        expected = fixtures.ClientCollectionsHostTests.compact(stage)
        self.assertEqual(suite.encode_stage_wire(stage), expected)
        self.assertEqual(full.decode_stage3_wire(expected), stage)
        self.assertEqual(suite.decode_stage_wire(expected), stage)
        del stage['client_collections']
        self.assertEqual(suite.encode_stage_wire(stage), stage)
        self.assertEqual(full.decode_stage3_wire(stage), stage)

    def test_legacy_schemas_reject_v3_diagnostics(self):
        stage = copy.deepcopy(self.stage)
        del stage['client_numbers']
        for baseline in (stage, fixtures.ClientCollectionsHostTests.compact(stage)):
            wire = copy.deepcopy(baseline)
            wire['client_probe']['process_diagnostics'] = ['after_exit', 'none', 0, 0, [0] * 7]
            self.reject_wire(wire)

    def test_schema_family_and_unknown_client_families_fail_closed(self):
        baseline = suite.encode_stage_wire(self.stage)
        for value in (True, False, '3', 0, 4, None, 1, 2):
            wire = copy.deepcopy(baseline)
            wire['schema'] = value
            self.reject_wire(wire)
        for schema in (1, 2, 3):
            wire = copy.deepcopy(self.stage if schema == 1 else baseline)
            wire['schema'] = schema
            wire['client_unknown'] = copy.deepcopy(wire['client_probe'])
            self.reject_wire(wire)
        del baseline['client_numbers']
        self.reject_wire(baseline)

    def test_every_record_rejects_mixed_missing_or_named_wire_fields(self):
        baseline = suite.encode_stage_wire(self.stage)
        for key in full.CLIENT_WIRE_V3_RECORDS:
            edits = [lambda d, key=key: d.update({key: copy.deepcopy(self.stage[key])}),
                     lambda d, key=key: d[key].update(process_diagnostics=copy.deepcopy(
                         self.stage[key]['process_diagnostics']))]
            edits += [lambda d, key=key, field=field: d[key].pop(field)
                      for field in ('hashes', 'proof', 'process_diagnostics')]
            edits += [lambda d, key=key, field=field: d[key].update({field: self.stage[key][field]})
                      for field in full.CLIENT_WIRE_HASHES + full.CLIENT_WIRE_PROOF]
            for edit in edits:
                wire = copy.deepcopy(baseline)
                edit(wire)
                with self.subTest(key=key, edit=edit):
                    self.reject_wire(wire)

    def test_diagnostic_array_shape_types_enums_and_bounds_are_strict(self):
        baseline = suite.encode_stage_wire(self.stage)
        good = baseline['client_numbers']['process_diagnostics']
        bad = [None, {}, True, 'PRIVATE', [], good[:4], good + [0]]
        for index, values in ((0, (None, True, 0, [], 'unknown')),
                              (1, (None, True, 0, {}, 'unknown')),
                              (2, (None, True, False, -1, 257, 1.0, '0', float('inf'), float('nan'))),
                              (3, (None, True, False, -1, 257, 1.0, '0', float('inf'), float('nan'))),
                              (4, (None, True, {}, 'PRIVATE', [], [0] * 6, [0] * 8))):
            for value in values:
                diagnostic = copy.deepcopy(good)
                diagnostic[index] = value
                bad.append(diagnostic)
        for index in range(7):
            for value in (None, True, False, -1, 257, 1.0, '0', float('inf'), float('nan')):
                diagnostic = copy.deepcopy(good)
                diagnostic[4][index] = value
                bad.append(diagnostic)
        bad.extend([
            ['after_exit', 'none', 0, 1, [0] * 7],
            ['before_probe', 'unexpected_processes', 1, 0, [0] * 7],
            ['before_probe', 'none', 1, 0, [1, 0, 0, 0, 0, 0, 0]],
        ])
        for diagnostic in bad:
            wire = copy.deepcopy(baseline)
            wire['client_numbers']['process_diagnostics'] = diagnostic
            with self.subTest(diagnostic=diagnostic):
                self.reject_wire(wire)

    def test_hash_and_proof_arrays_remain_exact_and_typed(self):
        baseline = suite.encode_stage_wire(self.stage)
        for field, valid in (('hashes', ['1' * 64] * 3), ('proof', [True] * 5)):
            bad = [None, {}, True, 'PRIVATE', [], valid[:-1], valid + [valid[0]]]
            for index in range(len(valid)):
                for value in ((True, 1, 'A' * 64, '0' * 63) if field == 'hashes'
                              else (None, 0, 1, 'true')):
                    item = valid.copy()
                    item[index] = value
                    bad.append(item)
            for value in bad:
                wire = copy.deepcopy(baseline)
                wire['client_numbers'][field] = value
                with self.subTest(field=field, value=value):
                    self.reject_wire(wire)

    def test_encoder_rejects_named_diagnostic_loss_and_hybrids(self):
        baseline = copy.deepcopy(self.stage)
        edits = [lambda d: d.pop('process_diagnostics'),
                 lambda d: d.update(process_diagnostics=[]),
                 lambda d: d.update(hashes=[None] * 3),
                 lambda d: d.update(proof=[False] * 5)]
        edits += [lambda d, field=field: d['process_diagnostics'].pop(field)
                  for field in suite.CLIENT_WIRE_DIAGNOSTICS]
        edits += [lambda d: d['process_diagnostics'].update(extra='PRIVATE'),
                  lambda d: d['process_diagnostics']['classes'].update(extra=0),
                  lambda d: d['process_diagnostics']['classes'].pop('native'),
                  lambda d: d['process_diagnostics'].update(unexpected_count=True)]
        for edit in edits:
            stage = copy.deepcopy(baseline)
            edit(stage['client_numbers'])
            with self.subTest(edit=edit), self.assertRaises(suite.FullError):
                suite.encode_stage_wire(stage)

    def test_process_class_position_and_every_proof_value_are_preserved(self):
        stage = copy.deepcopy(self.stage)
        diagnostic = fixtures.process_diagnostics(stage='before_probe', reason='unexpected_processes',
            classes=dict(zip(suite.CLIENT_WIRE_CLASSES, (1, 2, 3, 4, 5, 6, 7))), zombie_count=8)
        record = stage['client_numbers']
        record.update(process_diagnostics=diagnostic, conversion_verified=False)
        for bits in itertools.product((False, True), repeat=5):
            record.update(zip(suite.CLIENT_WIRE_PROOF, bits))
            wire = self.roundtrip(stage)
            self.assertEqual(wire['client_numbers']['proof'], list(bits))
            self.assertEqual(wire['client_numbers']['process_diagnostics'][4], [1, 2, 3, 4, 5, 6, 7])
        # Null identities and unreached proofs also remain data, not defaults.
        stage['client_numbers'] = dict(suite.empty_client_report(),
            **dict.fromkeys(fixtures.OUTPUT_KEYS), conversion_verified=False)
        self.roundtrip(stage)

    def test_six_record_maximum_failure_budget_preserves_all_diagnostics(self):
        stage = copy.deepcopy(self.stage)
        stage.update(status='failed', failure_kind='unexpected_failure')
        stage['client_watchdog'].update(status='failed', failure_kind='unexpected_failure',
            timeout_verified=False, process_diagnostics=fixtures.process_diagnostics(
                stage='before_probe', reason='unexpected_processes',
                classes={'native': 100, 'display': 26, 'session_bus': 26, 'shell': 26,
                         'python': 26, 'other': 26, 'unreadable': 26}, zombie_count=256))
        # Deliberately overstate client counts/sizes rather than quietly omit
        # any evidence. This is a conservative codec budget, not host acceptance.
        for case in stage['cases']:
            case.update(output_size=209715, message_count=32768)
        for key in ('client_dates', 'client_values', 'client_collections', 'client_numbers'):
            stage[key].update(output_size=1048576, message_count=32768)
        wire = self.roundtrip(stage)
        self.assertGreater(len(encode(stage)), 8192)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stage3.json'
            suite.write_report(path, stage)
            self.assertLessEqual(path.stat().st_size, 8192)
            self.assertEqual(full.decode_stage3_wire(full.strict_json(path.read_bytes(), 8192)), stage)
            self.assertEqual(suite.decode_stage_wire(json.loads(path.read_bytes())), stage)
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT),
                         (8192, 8192, 32768))

    def test_collections_mismatch_and_unreached_numbers_preserve_named_metadata(self):
        stage = copy.deepcopy(self.stage)
        stage.update(status='failed', failure_kind='output_mismatch')
        stage['client_collections'].update(status='failed', failure_kind='output_mismatch',
            witness_verified=False, **dict.fromkeys(fixtures.OUTPUT_KEYS),
            mismatch={'count': 698, 'first': 100, 'ordinals': list(range(100, 116)),
                      'client_sha256': 'a' * 64, 'server_sha256': 'b' * 64,
                      'client_size': 1048576, 'server_size': 1048576})
        stage['client_numbers'] = dict(suite.empty_client_report(),
            **dict.fromkeys(fixtures.OUTPUT_KEYS), conversion_verified=False)
        stage['client_watchdog'] = dict(suite.empty_client_report(), timeout_verified=False)
        wire = self.roundtrip(stage)
        self.assertEqual(wire['client_collections']['mismatch'], stage['client_collections']['mismatch'])

    def test_stage_cap_is_checked_before_diagnostic_expansion(self):
        wire = suite.encode_stage_wire(self.stage)
        wire['client_numbers']['failure_kind'] = 'x' * 8192
        with self.assertRaisesRegex(ValueError, 'stage wire limit'):
            full.decode_stage3_wire(wire)
        with self.assertRaises(suite.FullError) as caught:
            suite.decode_stage_wire(wire)
        self.assertEqual(caught.exception.kind, 'export_failed')


if __name__ == '__main__':
    unittest.main()
