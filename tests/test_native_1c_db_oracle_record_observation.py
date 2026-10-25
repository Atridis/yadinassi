"""Synthetic protocol/privacy mechanics, not native mapping or row evidence."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unicodedata
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(ROOT / 'yadinassi/storage'))
sys.path.insert(0, str(ROOT / 'tests'))
import comparison
import contract
import filedb_catalog as reader
import inputs
import protocol
import record_observation as observation
from snapshots import OracleError
import test_native_1c_db_oracle_contract as historical
import test_native_1c_db_oracle_stage as fixtures
from test_filedb_catalog import Source, descriptor

NONCE = fixtures.NONCE
TOKEN = 'd' * 32


def projection():
    # Deliberately synthetic labels, never predictions of native storage names.
    return {'schema': 1, 'target': observation.TARGET, 'table': {
        'storage_name': 'Physical', 'logical_name': 'Unmeasured.Table', 'metadata_name': '',
        'fields': [{'storage_name': 'Field', 'logical_name': '',
                    'metadata_name': 'Unmeasured.Field', 'type_text': 'uninterpreted'}]}}


def native_marker(token=TOKEN):
    value = historical.marker(token)
    del value['storage_shape']
    value.update(operation=observation.OPERATION, record_metadata=projection())
    return value


def identity():
    value = fixtures.provenance()
    value['sources'] = {source: 'c' * 64 for source in inputs.RECORD_SOURCE_FILES}
    value['actual_version'] = protocol.VERSION
    return value


def catalog(descriptions=None):
    source = Source().ready(descriptions or {2: descriptor(field_type='X')})
    return reader.read_catalog(source.read_at, source.size)


def evidence():
    source = Source().ready({2: descriptor(field_type='X')})
    parsed = reader.read_catalog(source.read_at, source.size)
    _, actual = observation.project_catalog(parsed, projection())
    return {'marker': native_marker(), 'origin': {'nonce': NONCE, 'token': TOKEN,
        'clone': 'auditor', **{key: fixtures.physical('baseline')[key] for key in ('bytes', 'sha256')}},
        'postimage': {'bytes': source.size, 'sha256': hashlib.sha256(source.full_bytes()).hexdigest()},
        'reader': actual}


def fixture(fail=None):
    report, _ = fixtures.fixture_report(fail)
    current = observation.empty_report(NONCE, identity())
    report.update({key: current[key] for key in observation.EXTRA_KEYS | {'schema', 'lane', 'provenance'}})
    if fail is None:
        report['record_observation'] = observation.bind_capture(evidence(), report)
        report.update(reader_validation=observation.VERDICT, metadata_validation=observation.METADATA_VERDICT,
                      layout_validation='declarations_only')
    return report


def failure_report():
    report = fixture('create')
    report.update(failed_stage='baseline', failure_kind=observation.FAILURE_KIND)
    report['stages'][protocol.STAGES.index('baseline')]['status'] = 'failed'
    report['stages'][protocol.STAGES.index('create')] = {'id': 'create', 'status': 'not_started',
        'checks': {key: False for key in protocol.CHECKS['create']}}
    return report


class NativeProjectionTests(unittest.TestCase):
    def test_uninterpreted_empty_and_changed_labels_are_observations(self):
        value = projection()
        for key in ('logical_name', 'metadata_name'):
            value['table'][key] = ''
        for key in ('logical_name', 'metadata_name', 'type_text'):
            value['table']['fields'][0][key] = ''
        self.assertIs(observation.validate_native_projection(value), value)
        native, actual = observation.project_catalog(catalog(), value)
        self.assertIs(native, value)
        native['table']['fields'][0].update(logical_name='Unknown', type_text='not X')
        observation.validate_names_bijection(native, actual)
        self.assertEqual(native['table']['fields'][0]['type_text'], 'not X')

    def test_every_cell_is_strict_and_no_unknown_fields(self):
        bad_cells = (None, False, 0, {}, [], b'bytes', '\n', '\x7f', '\u0085', '\u00a0',
                     '\u2028', '\ud800', '\ue000', '\uffff', '\U0001f642')
        for bad in bad_cells:
            for owner, key in (('table', 'logical_name'), ('table', 'metadata_name'),
                               ('field', 'logical_name'), ('field', 'metadata_name'), ('field', 'type_text')):
                value = projection()
                target = value['table'] if owner == 'table' else value['table']['fields'][0]
                target[key] = bad
                with self.subTest(bad=repr(bad), key=key), self.assertRaises(OracleError):
                    observation.validate_native_projection(value)
        edits = [lambda p: p.update(schema=True), lambda p: p.update(target='Other'),
                 lambda p: p.update(tables=[]), lambda p: p['table'].update(raw='PRIVATE'),
                 lambda p: p['table']['fields'][0].update(offset=1),
                 lambda p: p['table']['fields'][0].pop('type_text')]
        for edit in edits:
            value = projection(); edit(value)
            with self.assertRaises(OracleError): observation.validate_native_projection(value)

    def test_storage_identifiers_ascii_raw_duplicates_and_collisions(self):
        for name in ('', '0Field', 'two words', 'é', 'A.B', 'A-B', 'A\\B'):
            for table in (True, False):
                value = projection()
                target = value['table'] if table else value['table']['fields'][0]
                target['storage_name'] = name
                with self.subTest(name=name, table=table), self.assertRaises(OracleError):
                    observation.validate_native_projection(value)
        for second, code in (('Field', 'duplicate_field'), ('field', 'ascii_field_key_collision')):
            value = projection(); value['table']['fields'].append(dict(value['table']['fields'][0]))
            value['table']['fields'][1]['storage_name'] = second
            with self.assertRaises(observation.ObservationFailure) as caught:
                observation.validate_native_projection(value)
            self.assertEqual(caught.exception.code, code)

    def test_counts_cell_text_total_text_and_serialized_caps(self):
        cases = []
        value = projection(); value['table']['fields'] = []; cases.append(value)
        value = projection(); value['table']['fields'] *= 17; cases.append(value)
        value = projection(); value['table']['logical_name'] = 'x' * 65; cases.append(value)
        value = projection()
        value['table']['fields'] = [{'storage_name': 'F' + str(i), 'logical_name': 'x' * 64,
            'metadata_name': 'y' * 64, 'type_text': 'z' * 64} for i in range(4)]
        cases.append(value)
        for value in cases:
            original = copy.deepcopy(value)
            with self.assertRaises(OracleError) as caught: observation.validate_native_projection(value)
            self.assertEqual(caught.exception.kind, 'artifact_limit')
            self.assertEqual(value, original)
        with mock.patch.object(observation, 'MAX_NATIVE_BYTES', 10), self.assertRaises(OracleError):
            observation.validate_native_projection(projection())

    def test_frozen_printable_bmp_agrees_with_unicode15_for_every_unit(self):
        self.assertEqual(unicodedata.unidata_version, '15.0.0')
        for unit in range(65536):
            observed = observation.bisect_right(observation.PRINTABLE_BMP_BOUNDARIES, unit) % 2 == 1
            self.assertEqual(observed, chr(unit).isprintable(), hex(unit))


class PhysicalProjectionTests(unittest.TestCase):
    def test_complete_original_order_tokens_numbers_and_only_names_compared(self):
        parsed = catalog({2: descriptor(fields='{"B","B",0,16,0,""},{"a","N",1,9,2,"CS"}'),
                          3: descriptor('PRIVATE_UNRELATED')})
        native = projection()
        native['table']['fields'] = [{'storage_name': name, 'logical_name': '', 'metadata_name': '',
                                     'type_text': 'not a type token'} for name in ('A', 'b')]
        returned, actual = observation.project_catalog(parsed, native)
        self.assertIs(returned, native)
        self.assertEqual(actual['table'], {'name': 'Physical', 'record_lock_token': '1', 'fields': [
            {'name': 'B', 'type_token': 'B', 'nullability': 0, 'length': 16, 'precision': 0, 'case_token': ''},
            {'name': 'a', 'type_token': 'N', 'nullability': 1, 'length': 9, 'precision': 2, 'case_token': 'CS'}]})
        raw = protocol.encode(actual)
        for secret in (b'PRIVATE_UNRELATED', b'Indexes', b'Files', b'descriptor', b'offset', b'Raw'):
            self.assertNotIn(secret, raw)

    def test_private_reader_attributes_are_never_accessed(self):
        class StrictObject:
            def __init__(self, **allowed): self.__dict__.update(allowed)
            def __getattr__(self, key): raise AssertionError('private attribute access: ' + key)
        field = StrictObject(name='Field', type_name='X', null_marker=0, declared_length=4,
                             precision=0, case_marker='')
        table = StrictObject(name='Physical', recordlock='1', fields=(field,))
        parsed = StrictObject(tables=(StrictObject(name='Unrelated'), table))
        _, result = observation.project_catalog(parsed, projection())
        self.assertEqual(result['table']['fields'][0]['length'], 4)

    def test_complete_bijection_without_table_casefolding_or_field_loss(self):
        cases = [({2: descriptor('physical', field_type='X')}, 'missing_table'),
                 ({2: descriptor(field_type='X'), 3: descriptor(field_type='X')}, 'duplicate_table'),
                 ({2: descriptor(fields='')}, 'field_names_differ'),
                 ({2: descriptor(fields='{"Field","X",0,0,0,""},{"Extra","X",0,0,0,""}')}, 'field_names_differ'),
                 ({2: descriptor(fields='{"Field","X",0,0,0,""},{"Field","X",0,0,0,""}')}, 'duplicate_field'),
                 ({2: descriptor(fields='{"Field","X",0,0,0,""},{"field","X",0,0,0,""}')}, 'ascii_field_key_collision')]
        for descriptions, code in cases:
            with self.subTest(code=code), self.assertRaises(observation.ObservationFailure) as caught:
                observation.project_catalog(catalog(descriptions), projection())
            self.assertEqual(caught.exception.code, code)
        _, actual = observation.project_catalog(catalog({2: descriptor(fields='{"field","X",0,0,0,""}')}), projection())
        self.assertEqual(actual['table']['fields'][0]['name'], 'field')

    def test_tokens_are_uninterpreted_empty_or_ascii_not_a_layout_profile(self):
        _, physical = observation.project_catalog(catalog(), projection())
        for token in ('', '1', 'NotKnown', '_', 'n1234567'):
            value = copy.deepcopy(physical)
            value['table']['record_lock_token'] = token
            value['table']['fields'][0].update(type_token=token, case_token=token)
            observation.validate_physical_projection(value)
        for token in ('ninechars', 'é', '-1', 'two words', '\n', None, False, 1):
            for key in ('record_lock_token', 'type_token', 'case_token'):
                value = copy.deepcopy(physical)
                target = value['table'] if key == 'record_lock_token' else value['table']['fields'][0]
                target[key] = token
                with self.subTest(token=token, key=key), self.assertRaises(observation.ObservationFailure) as caught:
                    observation.validate_physical_projection(value)
                self.assertEqual(caught.exception.code, 'declaration_token')

    def test_declaration_integer_and_private_extra_fields_rejected(self):
        _, physical = observation.project_catalog(catalog(), projection())
        for key in ('nullability', 'length', 'precision'):
            for number in (-1, 65536, True, 1.0, '1', None):
                value = copy.deepcopy(physical); value['table']['fields'][0][key] = number
                with self.subTest(key=key, number=number), self.assertRaises(observation.ObservationFailure) as caught:
                    observation.validate_physical_projection(value)
                self.assertEqual(caught.exception.code, 'declaration_integer')
            for number in (0, 65535):
                value = copy.deepcopy(physical); value['table']['fields'][0][key] = number
                observation.validate_physical_projection(value)
        for target in ('root', 'table', 'field'):
            value = copy.deepcopy(physical)
            dest = value if target == 'root' else value['table'] if target == 'table' else value['table']['fields'][0]
            dest['raw'] = 'PRIVATE'
            with self.assertRaises(OracleError): observation.validate_physical_projection(value)

    def test_count_text_and_byte_limits_checked_before_copying_excess_fields(self):
        class ForbiddenField:
            def __getattribute__(self, key): raise AssertionError('field read before count cap')
        parsed = SimpleNamespace(tables=(SimpleNamespace(name='Physical', fields=(ForbiddenField(),) * 17),))
        with self.assertRaises(observation.ObservationFailure) as caught:
            observation.project_catalog(parsed, projection())
        self.assertEqual(caught.exception.code, 'projection_limit')
        _, physical = observation.project_catalog(catalog(), projection())
        with mock.patch.object(observation, 'MAX_PHYSICAL_BYTES', 10), self.assertRaises(OracleError):
            observation.validate_physical_projection(physical)
        physical['table']['fields'] = [dict(physical['table']['fields'][0], name='F' + str(i) + 'x' * 60)
                                      for i in range(13)]
        with self.assertRaises(OracleError) as caught: observation.validate_physical_projection(physical)
        self.assertEqual(caught.exception.kind, 'artifact_limit')


class MarkerBoundaryTests(unittest.TestCase):
    def test_fresh_baseline_setup_marker_and_historical_api_separation(self):
        value = native_marker(); raw = protocol.encode(value)
        self.assertEqual(observation.marker(raw, nonce=NONCE, token=TOKEN), value)
        edits = [lambda m: m.update(operation='audit_contract'), lambda m: m.update(token='e' * 32),
                 lambda m: m.update(nonce='b' * 32), lambda m: m.update(user='NativeOracleCRUD'),
                 lambda m: m.update(nonprivileged=False), lambda m: m.update(role_verified=False),
                 lambda m: m.update(users_verified=False), lambda m: m.update(metadata_version=2, payload_length=64),
                 lambda m: m.update(count=1), lambda m: m.update(raw='PRIVATE')]
        for edit in edits:
            changed = copy.deepcopy(value); edit(changed)
            with self.assertRaises(OracleError): observation.marker(protocol.encode(changed), nonce=NONCE, token=TOKEN)
        for version in (3, 4, 5):
            with self.assertRaises(OracleError):
                protocol.marker(raw, nonce=NONCE, token=TOKEN, operation=observation.OPERATION, contract_version=version)
        for bad in ('x', 'A' * 32, True):
            value = native_marker(bad)
            with self.assertRaises(OracleError): observation.marker(protocol.encode(value), nonce=NONCE, token=bad)

    def test_completion_new_phases_only_and_old_validator_stays_closed(self):
        value = {'schema': 1, 'nonce': NONCE, 'token': TOKEN, 'operation': observation.OPERATION,
                 'status': 'error', 'phase': 'record_call'}
        for phase in observation.PHASES:
            value['phase'] = phase
            self.assertEqual(observation.completion_marker(protocol.encode(value), nonce=NONCE, token=TOKEN), value)
        for phase in ('contract_call', 'contract_scan', 'contract_limit', 'readback', 'complete', 'PRIVATE'):
            value['phase'] = phase
            with self.assertRaises(OracleError): observation.completion_marker(protocol.encode(value), nonce=NONCE, token=TOKEN)
        value.update(status='ok', phase='complete')
        observation.completion_marker(protocol.encode(value), nonce=NONCE, token=TOKEN)
        with self.assertRaises(OracleError):
            protocol.completion_marker(protocol.encode(value), nonce=NONCE, token=TOKEN, operation=observation.OPERATION)
        value.update(operation='dispatch', status='error', phase='control')
        observation.completion_marker(protocol.encode(value), nonce=NONCE, token=TOKEN)
        value.update(phase='record_call')
        with self.assertRaises(OracleError): observation.completion_marker(protocol.encode(value), nonce=NONCE, token=TOKEN)

    def test_failure_context_new_operation_only_in_baseline_no_cross_lane_phase(self):
        value = {'operation': 'enterprise_' + observation.OPERATION, 'site': 'result',
                 'bsl_phase': 'record_scan', 'region': None, 'reason': None}
        original = copy.deepcopy(value)
        self.assertIs(observation.validate_failure_context(value, 'baseline'), value)
        self.assertEqual(value, original)
        with self.assertRaises(OracleError): protocol.validate_failure_context(value, 'baseline')
        for edit in (lambda v: v.update(bsl_phase='contract_scan'), lambda v: v.update(site='launch'),
                     lambda v: v.update(operation='enterprise_observe'), lambda v: v.update(raw='PRIVATE')):
            changed = dict(value); edit(changed)
            with self.assertRaises(OracleError): observation.validate_failure_context(changed, 'baseline')
        with self.assertRaises(OracleError): observation.validate_failure_context(value, 'create')


class ReportBoundaryTests(unittest.TestCase):
    def check(self, report, *, final=False, provenance=None):
        return observation.validate_report(protocol.encode(report), nonce=NONCE,
            provenance=provenance or identity(), final=final)

    def test_complete_lifecycle_one_replacement_capture_and_no_mapping_claim(self):
        report = fixture(); self.check(report)
        self.assertNotIn('storage_contract', report)
        self.assertEqual((len(report['stages']), len(report['snapshots'])), (13, 11))
        capture = report['record_observation']
        self.assertNotEqual(capture['origin']['sha256'], capture['postimage']['sha256'])
        self.assertEqual((report['mapping_validation'], report['layout_validation'], report['record_validation'],
                          report['native_compatibility']), ('not_run', 'declarations_only', 'not_run', 'not_claimed'))
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        report['accepted'] = True
        self.check(report, final=True)

    def test_old_reports_and_old_validators_reject_new_identity_or_fields(self):
        report = fixture(); raw = protocol.encode(report)
        for validator in (protocol.validate_report, contract.validate_report, comparison.validate_report):
            with self.assertRaises(OracleError): validator(raw, nonce=NONCE, provenance=identity())
        old, _ = fixtures.fixture_report()
        with self.assertRaises(OracleError): self.check(old)
        old['record_observation'] = None
        with self.assertRaises(OracleError): protocol.validate_report(protocol.encode(old), nonce=NONCE, provenance=fixtures.provenance())

    def test_report_identity_provenance_and_all_success_claims_are_strict(self):
        edits = [lambda r: r.update(schema=True), lambda r: r.update(schema=4), lambda r: r.update(lane=comparison.LANE),
                 lambda r: r.update(projection_mode='default'), lambda r: r.update(comparison_policy='strict'),
                 lambda r: r.update(record_observation=None), lambda r: r.update(storage_contract=None),
                 lambda r: r.update(reader_validation='matched'), lambda r: r.update(metadata_validation='not_run'),
                 lambda r: r.update(mapping_validation='accepted'), lambda r: r.update(layout_validation='fixed'),
                 lambda r: r.update(record_validation='passed'), lambda r: r.update(native_compatibility='verified')]
        for edit in edits:
            report = fixture(); edit(report)
            with self.assertRaises(OracleError): self.check(report)
        for key in ('commit', 'tree'):
            report = fixture(); report['provenance'][key] = 'd' * 40
            with self.assertRaises(OracleError): self.check(report)
        for key in ('image', 'platform', 'locale', 'timezone'):
            report = fixture(); report['provenance'][key] = 'forged'
            with self.assertRaises(OracleError): self.check(report, provenance=report['provenance'])
        for source in inputs.RECORD_SOURCE_FILES:
            report = fixture(); del report['provenance']['sources'][source]
            with self.assertRaises(OracleError): self.check(report, provenance=report['provenance'])

    def test_binding_nonce_token_sources_origin_and_postimage_mutations(self):
        edits = [lambda c: c.update(schema=5), lambda c: c.update(operation='audit_contract'),
                 lambda c: c.update(nonce='b' * 32), lambda c: c.update(token='stale'),
                 lambda c: c.update(source_manifest_sha256='f' * 64), lambda c: c.update(reader_source_sha256='f' * 64),
                 lambda c: c.update(actual_version='8.3.0.0'), lambda c: c.update(raw='PRIVATE'),
                 lambda c: c['origin'].update(snapshot='created'), lambda c: c['origin'].update(clone='observer'),
                 lambda c: c['origin'].update(bytes=True), lambda c: c['origin'].update(sha256='f' * 64),
                 lambda c: c['postimage'].update(copy='baseline'), lambda c: c['postimage'].update(binding='origin'),
                 lambda c: c['postimage'].update(bytes=8192), lambda c: c['postimage'].update(bytes=24577),
                 lambda c: c['postimage'].update(sha256='invalid'), lambda c: c['postimage'].update(page_size=4096),
                 lambda c: c['postimage'].update(storage_version=[8, 3, 8, False]),
                 lambda c: c['reader']['table'].update(name='Other')]
        for edit in edits:
            report = fixture(); edit(report['record_observation'])
            with self.assertRaises(OracleError): self.check(report)
        # Offline shape validation cannot authenticate a substituted valid token
        # or postimage digest; producer freshness is enforced before bind_capture.
        report = fixture(); report['record_observation']['token'] = 'e' * 32
        self.check(report)

    def test_binding_rechecks_producer_origin_token_and_native_marker(self):
        for edit in (lambda e: e['origin'].update(token='e' * 32), lambda e: e['origin'].update(nonce='b' * 32),
                     lambda e: e['origin'].update(bytes=1), lambda e: e['origin'].update(sha256='f' * 64),
                     lambda e: e['marker'].update(metadata_version=2, payload_length=64),
                     lambda e: e['postimage'].update(raw='PRIVATE')):
            value = evidence(); edit(value)
            with self.assertRaises(OracleError): observation.bind_capture(value, fixture())

    def test_every_later_failure_discards_both_projections_and_success_verdicts(self):
        good = fixture()
        for stage in protocol.STAGES[:-1]:
            report = fixture(stage)
            if stage not in ('preflight', 'seed_v1', 'baseline'):
                report.update({key: good[key] for key in ('record_observation', 'reader_validation',
                                                         'metadata_validation', 'layout_validation')})
            observation.discard_capture(report)
            self.assertIsNone(report['record_observation'])
            self.assertNotEqual(report['metadata_validation'], observation.METADATA_VERDICT)
            self.assertNotEqual(report['reader_validation'], observation.VERDICT)
            self.check(report)

    def test_all_cleanup_gates_and_failed_reports_strip_projection(self):
        for gate in fixture()['cleanup']:
            report = fixture()
            report['cleanup'].update(container_removed=True, private_staging_removed=True)
            report['cleanup'][gate] = False
            report.update(status='failed', failed_stage='cleanup', failure_kind='cleanup_unverified', artifacts=[])
            report['stages'][-1].update(status='failed', checks={key: report['cleanup'][key]
                for key in ('native_processes_stopped', 'raw_files_removed')})
            with self.assertRaises(OracleError): self.check(report, final=True)
            observation.discard_capture(report)
            self.assertIsNone(report['record_observation'])
            self.assertEqual(report['metadata_validation'], 'discarded')
            self.check(report, final=True)

    def test_finite_failure_survives_cleanup_without_any_evidence_payload(self):
        for category, codes in observation.DIAGNOSTICS.items():
            for code in codes:
                report = failure_report()
                observation.discard_capture(report, observation.ObservationFailure(category, code))
                self.check(report)
                self.assertEqual(report['record_observation'], {'schema': observation.CAPTURE_SCHEMA,
                    'status': 'failed', 'category': category, 'code': code})
                observation.discard_capture(report)
                self.check(report)
        for category, code in (('PRIVATE', 'PRIVATE'), ('unsupported_layout', 'private-code')):
            with self.assertRaises(OracleError): observation.ObservationFailure(category, code)

    def test_new_failure_context_mapping_validated_before_legacy_copy(self):
        report = fixture('baseline')
        report['failure_context'] = {'operation': 'enterprise_' + observation.OPERATION, 'site': 'result',
            'bsl_phase': 'record_limit', 'region': None, 'reason': None}
        report['failure_kind'] = 'artifact_limit'
        self.check(report)
        original = copy.deepcopy(report)
        self.check(report)
        self.assertEqual(report, original)
        report['failure_context']['bsl_phase'] = 'contract_limit'
        with self.assertRaises(OracleError): self.check(report)


if __name__ == '__main__':
    unittest.main()
