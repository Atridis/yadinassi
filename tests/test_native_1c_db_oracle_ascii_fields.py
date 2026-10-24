"""Versioned own-fixture ASCII identifiers, not general native compatibility."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(ROOT/'yadinassi/storage'))
sys.path.insert(0, str(ROOT/'tests'))
import comparison
import filedb_catalog as reader
import protocol
import snapshots
import test_native_1c_db_oracle_comparison as existing
import test_native_1c_db_oracle_field_diagnostic as fields
import test_native_1c_db_oracle_name_diagnostic as names
import test_native_1c_db_oracle_stage as fixtures
from test_filedb_catalog import Source, descriptor
from snapshots import OracleError

NONCE = existing.NONCE
# Exact seven-field audited pair from native run 40128721635. This synthetic
# replay tests the new policy only, never upgrades that historical failed run.
NATIVE_FIELDS = ('_Code', '_Fld54', '_Fld55', '_IDRRef', '_Marked', '_PredefinedID', '_Version')
READER_FIELDS = ('_CODE', '_FLD54', '_FLD55', '_IDRREF', '_MARKED', '_PREDEFINEDID', '_VERSION')


def projection(names=NATIVE_FIELDS, table='_Reference53'):
    return fields.projection(((table, names),))


def parsed(names=READER_FIELDS, table='_Reference53'):
    return fields.parsed(((table, names),))


def source(names=READER_FIELDS, table='_Reference53'):
    data = Source().ready({3: descriptor('PRIVATE_UNSELECTED')})
    raw = descriptor(table, fields=','.join('{"'+name+'","X",0,0,0,""}' for name in names))
    data.catalog((2, 3))
    # The audited seven-field descriptor exceeds one 250-byte BLOB payload.
    data.chain((2, *range(4, 4+(len(raw)-1)//250)), raw)
    return data


def evidence():
    item = existing.evidence()
    item['marker']['storage_names'] = projection()
    data = source()
    native, actual = comparison.project_catalog_ascii_fields(existing.catalog(data), projection())
    item['reader'] = actual
    item['postimage'] = {'bytes': data.size, 'sha256': hashlib.sha256(data.full_bytes()).hexdigest()}
    return item


def fixture(fail=None, cleanup=(True, True)):
    provenance = existing.identity()
    report = comparison.empty_report(NONCE, provenance)
    backend = existing.ComparisonBackend(provenance, fail); backend.clean = cleanup
    backend.compare_catalog = lambda identifier: evidence()
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


def check(report, final=False):
    return comparison.validate_report(protocol.encode(report), nonce=NONCE,
                                      provenance=existing.identity(), final=final)


def policy_failure(actual=None, native=None):
    item = evidence()
    item['marker']['storage_names'] = projection() if native is None else native
    return comparison.field_names_ascii_fields_failure(parsed(()) if actual is None else actual,
        item, nonce=NONCE, provenance=existing.identity(), baseline=fixtures.physical('baseline'))


class AsciiFieldProjectionTests(unittest.TestCase):
    def reject(self, actual, native, code=None):
        original = copy.deepcopy(native)
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.project_catalog_ascii_fields(actual, native)
        self.assertIsNone(caught.exception.capture)
        if code is not None: self.assertEqual(caught.exception.code, code)
        self.assertEqual(native, original)
        return caught.exception

    def test_exact_audited_pair_real_reader_preserves_both_spellings(self):
        data = source(); actual = existing.catalog(data); before = copy.deepcopy(projection())
        native, projected = comparison.project_catalog_ascii_fields(actual, before)
        self.assertEqual(native, projection()); self.assertEqual(projected, projection(READER_FIELDS))
        self.assertNotEqual(native, projected); self.assertEqual(before, projection())
        self.assertEqual([field.name for field in actual.tables[0].fields], list(READER_FIELDS))
        self.assertTrue(data.calls)
        for private in (b'PRIVATE', b'Undocumented', b'raw'):
            self.assertNotIn(private, protocol.encode(projected))

    def test_strict_projection_and_binder_remain_negative_controls(self):
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.project_catalog(parsed(), projection())
        self.assertEqual(caught.exception.code, 'field_names_differ')
        report, _ = fixture()
        with self.assertRaises(OracleError): comparison.bind_capture(evidence(), report)
        self.assertEqual(comparison.canonical_projection(projection()), projection())
        strict = existing.evidence()
        self.assertEqual(comparison.bind_capture(strict, report)['schema'], 1)
        self.assertEqual(comparison.bind_capture(strict, report)['native'], strict['reader'])

    def test_raw_duplicates_and_ascii_collisions_reject_on_each_side(self):
        for duplicate in (('F', 'F'), ('F', 'f'), ('_IDRRef', '_IDRREF')):
            for side in ('native', 'reader'):
                native = projection(duplicate) if side == 'native' else projection(('F',))
                actual = parsed(duplicate) if side == 'reader' else parsed(('F',))
                with self.subTest(names=duplicate, side=side):
                    failure = self.reject(actual, native)
                    self.assertEqual(failure.code, 'ascii_field_key_collision' if duplicate[0] != duplicate[1]
                                     else 'duplicate_field' if side == 'reader' else 'invalid_projection')

    def test_unicode_lookalikes_and_nonidentifier_syntax_never_fold(self):
        for bad in ('Ｆ', 'а', 'K', 'İ', 'ı', 'ß', 'ſ', 'e\u0301', 'F ', ' F',
                    'F.', 'F-', 'F\\', 'F"', '1F', 'F\n', '', '\ud800', '\U0001f642', None, True):
            for side in ('native', 'reader'):
                with self.subTest(bad=repr(bad), side=side):
                    self.reject(parsed((bad,)) if side == 'reader' else parsed(('F',)),
                                projection((bad,)) if side == 'native' else projection(('F',)))
        for valid in ('_', 'A', 'a0_', '_123', 'Z'*64):
            self.assertEqual(comparison.project_catalog_ascii_fields(parsed((valid,)), projection((valid,)))[0],
                             projection((valid,)))

    def test_entire_field_grammar_checked_before_deriving_collision_keys(self):
        for side in ('native', 'reader'):
            malformed = ('F', 'f', 'K')
            self.reject(parsed(malformed) if side == 'reader' else parsed(('F',)),
                        projection(malformed) if side == 'native' else projection(('F',)),
                        'ascii_field_identifier')

    def test_bijection_requires_every_field_no_prefix_or_digit_rewriting(self):
        for actual in (READER_FIELDS[:-1], READER_FIELDS+('_EXTRA',), (),
                       ('CODE',)+READER_FIELDS[1:], ('_CODE1',)+READER_FIELDS[1:],
                       ('_COD',)+READER_FIELDS[1:]):
            self.reject(parsed(actual), projection(), 'field_names_differ')
        self.reject(parsed(), projection(()), 'projection_limit')

    def test_table_matching_is_exact_and_selected_duplicates_reject(self):
        for table in ('_REFERENCE53', '_reference53', 'Reference53', '_Reference053'):
            self.reject(parsed(table=table), projection(), 'missing_table')
        actual = parsed(); actual.tables += actual.tables; actual.usage.tables = 2
        self.reject(actual, projection(), 'duplicate_table')
        native = projection(); native['tables'] += copy.deepcopy(native['tables'])
        self.reject(parsed(), native, 'invalid_projection')

    def test_multiple_complete_tables_sort_raw_only_and_unrelated_fields_stay_private(self):
        class Private:
            name = 'PRIVATE'
            @property
            def fields(self): raise AssertionError('must not inspect unrelated fields')
        native = fields.projection((('Z', ('z', 'a')), ('A', ('q',))))
        actual = fields.parsed((('A', ('Q',)), ('Z', ('A', 'Z'))))
        actual.tables += (Private(), Private()); actual.usage.tables = 4
        expected, found = comparison.project_catalog_ascii_fields(actual, native)
        self.assertEqual(expected, fields.projection((('A', ('q',)), ('Z', ('a', 'z')))))
        self.assertEqual(found, fields.projection((('A', ('Q',)), ('Z', ('A', 'Z')))))
        self.assertEqual(native['tables'][0]['fields'], ['z', 'a'])

    def test_every_existing_projection_bound_still_rejects_without_truncation(self):
        too_many = tuple('F'+str(i) for i in range(33))
        for bad in (projection(too_many), projection(('F'*65,)),
                    projection(tuple('F'+str(i)+'x'*61 for i in range(8))),
                    fields.projection(tuple(('T'+str(i), ('F',)) for i in range(5))),
                    fields.projection(tuple(('T'+str(i), tuple('F'+str(j) for j in range(32))) for i in range(3)))):
            with self.subTest(bad=bad): self.reject(parsed(), bad, 'projection_limit')
        for actual in (parsed(too_many), parsed(('F'*65,)), parsed(tuple('F'+str(i)+'x'*61 for i in range(8)))):
            self.reject(actual, projection(), 'projection_limit')
        native = fields.projection(tuple(('T'+str(i), ('F',)) for i in range(3)))
        actual = fields.parsed(tuple(('T'+str(i), tuple('F'+str(j) for j in range(32))) for i in range(3)))
        self.reject(actual, native, 'projection_limit')
        with mock.patch.object(comparison, 'MAX_PROJECTION_BYTES', 100):
            self.reject(parsed(), projection(), 'projection_limit')
        boundary = fields.projection(tuple(('T'+str(i), tuple('F'+str(j) for j in range(16))) for i in range(4)))
        comparison.ascii_field_keys(boundary)
        self.assertEqual(sum(len(t['fields']) for t in boundary['tables']), 64)

    def test_table_names_are_not_subject_to_field_ascii_grammar(self):
        table = 'Таблица"\\'
        native, actual = comparison.project_catalog_ascii_fields(parsed(('F',), table), projection(('f',), table))
        self.assertEqual(native['tables'][0]['name'], table); self.assertEqual(actual['tables'][0]['name'], table)


class AsciiPolicyEnvelopeTests(unittest.TestCase):
    def test_versioned_success_is_narrow_bound_and_retains_raw_differences(self):
        report, _ = fixture(); check(report)
        capture = report['storage_contract']
        self.assertEqual((report['schema'], capture['schema']), (4, 5))
        self.assertEqual(report['lane'], 'native-file-db-catalog-compare-dbms-names-true-ascii-fields-v1')
        self.assertEqual(report['projection_mode'], 'dbms_names_true')
        self.assertEqual(report['comparison_policy'], 'exact_tables_ascii_fields_v1')
        self.assertEqual(capture['comparison_policy'], report['comparison_policy'])
        self.assertEqual(report['reader_validation'], 'filtered_table_ascii_field_identifiers_match')
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertEqual(capture['native'], projection()); self.assertEqual(capture['reader'], projection(READER_FIELDS))
        self.assertNotEqual(capture['native'], capture['reader'])
        self.assertEqual((len(report['stages']), len(report['snapshots'])), (13, 11))
        self.assertFalse(report['accepted'])
        report['cleanup'].update(container_removed=True, private_staging_removed=True); report['accepted'] = True
        check(report, True)

    def test_missing_wrong_mode_policy_lane_and_capture_versions_reject(self):
        edits = [lambda r: r.pop('comparison_policy'), lambda r: r.pop('projection_mode'),
            lambda r: r.update(lane='native-file-db-catalog-compare-dbms-names-true-v4'),
            lambda r: r.update(reader_validation='filtered_table_field_names_match')]
        edits += [lambda r, v=v: r.update(comparison_policy=v)
                  for v in (None, True, 1, '', [], {}, 'exact', 'EXACT_TABLES_ASCII_FIELDS_V1', 'exact_tables_ascii_fields_v2')]
        edits += [lambda r, v=v: r.update(projection_mode=v) for v in (None, True, 'default', 'dbms_names_false')]
        for stage in (None, 'preflight', 'create'):
            original, _ = fixture(stage)
            for edit in edits:
                value = copy.deepcopy(original); edit(value); before = copy.deepcopy(value)
                with self.subTest(stage=stage, value=value.get('comparison_policy')), self.assertRaises(OracleError): check(value)
                self.assertEqual(value, before)
        original, _ = fixture()
        for version in (True, 1, 2, 3, 4, 6, '5', None):
            value = copy.deepcopy(original); value['storage_contract']['schema'] = version
            with self.subTest(version=version), self.assertRaises(OracleError): check(value)
        for edit in (lambda c: c.pop('comparison_policy'), lambda c: c.update(comparison_policy='exact'),
                     lambda c: c.update(keys='PRIVATE'), lambda c: c['reader']['tables'][0]['fields'].pop()):
            value = copy.deepcopy(original); edit(value['storage_contract'])
            with self.assertRaises(OracleError): check(value)

    def test_new_binder_requires_new_envelope_and_current_policy(self):
        good, _ = fixture()
        for edit in (lambda r: r.pop('comparison_policy'), lambda r: r.update(comparison_policy='exact'),
                     lambda r: r.update(lane='native-file-db-catalog-compare-dbms-names-true-v4'),
                     lambda r: r.update(projection_mode='default'), lambda r: r.update(schema=3)):
            report = copy.deepcopy(good); edit(report)
            with self.assertRaises(OracleError): comparison.bind_ascii_fields_capture(evidence(), report)
        with mock.patch.object(comparison, 'MAX_CAPTURE_BYTES', 100), self.assertRaises(OracleError):
            comparison.bind_ascii_fields_capture(evidence(), good)

    def test_all_native_origin_source_and_postimage_bindings_remain_required(self):
        good, _ = fixture()
        for section, key, value in [('marker', 'nonce', 'b'*32), ('marker', 'token', 'b'*32),
            ('marker', 'operation', 'audit'), ('origin', 'nonce', 'b'*32), ('origin', 'token', 'b'*32),
            ('origin', 'clone', 'writer'), ('origin', 'bytes', 1), ('origin', 'sha256', 'b'*64)]:
            item = evidence(); item[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(OracleError):
                comparison.bind_ascii_fields_capture(item, good)
        edits = [lambda c: c.update(source_manifest_sha256='b'*64), lambda c: c.update(reader_source_sha256='b'*64),
            lambda c: c.update(actual_version='8.3.0.0'), lambda c: c.update(nonce='b'*32),
            lambda c: c.update(token='stale'), lambda c: c['origin'].update(sha256='b'*64),
            lambda c: c['postimage'].update(binding='native_execution_time'),
            lambda c: c['postimage'].update(storage_version=[8, 2, 14, 0]),
            lambda c: c['postimage'].update(page_size=4096), lambda c: c['postimage'].update(bytes=8192)]
        for edit in edits:
            report = copy.deepcopy(good); edit(report['storage_contract'])
            with self.assertRaises(OracleError): check(report)
        report = copy.deepcopy(good); report['provenance']['sources'][comparison.READER_SOURCE] = 'b'*64
        with self.assertRaises(OracleError):
            comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=report['provenance'])

    def test_missing_extra_empty_failures_retain_complete_raw_projections(self):
        for raw in (READER_FIELDS[:-1], READER_FIELDS+('_EXTRA',), ()):
            failure = policy_failure(parsed(raw)); report, _ = names.fixture(failure); check(report)
            self.assertEqual(report['storage_contract']['schema'], 4)
            diagnostic = report['storage_contract']['field_diagnostic']
            self.assertEqual(diagnostic['native'], projection())
            self.assertEqual(diagnostic['reader'], comparison.canonical_field_reader_projection(projection(raw)))
            self.assertEqual(report['reader_validation'], 'failed'); self.assertFalse(report['accepted'])
            report['cleanup'].update(container_removed=True, private_staging_removed=True); check(report, True)

    def test_strict_case_only_failure_cannot_be_relabeled_as_policy_failure(self):
        old = comparison.field_names_failure(parsed(), evidence(), nonce=NONCE,
            provenance=existing.identity(), baseline=fixtures.physical('baseline'))
        comparison.validate_field_diagnostic(old.capture['field_diagnostic'])
        with self.assertRaises(OracleError): comparison.validate_ascii_field_diagnostic(old.capture['field_diagnostic'])
        with self.assertRaises(OracleError): policy_failure(parsed())
        report, _ = names.fixture(old); check(report)
        self.assertEqual(report['storage_contract'], fields.BARE)
        report['storage_contract'] = old.capture
        with self.assertRaises(OracleError): check(report)

    def test_collisions_and_unsupported_identifiers_cannot_be_accepted_in_capture(self):
        good, _ = fixture()
        for side in ('native', 'reader'):
            for bad in (['_CODE', '_code'], ['_СODE'], [], ['_CODE', '_CODE']):
                report = copy.deepcopy(good); report['storage_contract'][side]['tables'][0]['fields'] = bad
                with self.subTest(side=side, bad=bad), self.assertRaises(OracleError): check(report)
        for nameset in (('_CODE', '_code'), ('_СODE',)):
            with self.assertRaises(OracleError): policy_failure(parsed(nameset))

    def test_all_lifecycle_failures_and_four_cleanup_gates_discard_success(self):
        for stage in protocol.STAGES[:-1]:
            report, _ = fixture(stage); check(report); self.assertIsNone(report['storage_contract'])
        for cleanup in ((False, True), (True, False), (False, False)):
            report, _ = fixture(cleanup=cleanup); check(report)
            self.assertIsNone(report['storage_contract']); self.assertEqual(report['reader_validation'], 'discarded')
        spec = importlib.util.spec_from_file_location('ascii_policy_host', ROOT/'scripts/native_1c_db_oracle.py')
        host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
        for gate in ('native_processes_stopped', 'raw_files_removed', 'container_removed', 'private_staging_removed'):
            report, _ = fixture(); report['cleanup'] = dict.fromkeys(report['cleanup'], True)
            report['cleanup'][gate] = False; report['accepted'] = True
            if gate in report['stages'][-1]['checks']:
                report['stages'][-1]['checks'][gate] = False; report['stages'][-1]['status'] = 'failed'
            with self.subTest(gate=gate), self.assertRaises(OracleError): check(report, True)
            host.fail_report(report, 'cleanup_unverified', 'cleanup', preserve_primary=True); check(report, True)
            self.assertIsNone(report['storage_contract']); self.assertFalse(report['accepted'])

    def test_controller_wrong_lane_never_calls_policy_reader(self):
        report = comparison.empty_report(NONCE, existing.identity())
        report['lane'] = 'native-file-db-catalog-compare-dbms-names-true-v4'
        backend = existing.ComparisonBackend(existing.identity())
        backend.compare_catalog = mock.Mock(side_effect=AssertionError('must not enter new policy'))
        controller = fixtures.stage.Controller(backend, report); backend.controller = controller
        controller.run(); backend.compare_catalog.assert_not_called()


@unittest.skipIf(os.name == 'nt', 'POSIX synthetic native ownership')
class ActualPolicyReaderTests(unittest.TestCase):
    setUp = existing.AuditedPostimageTests.setUp
    cleanup = existing.AuditedPostimageTests.cleanup

    def test_new_route_reads_audited_pair_once_preserves_raw_and_removes_private_clones(self):
        original = self.native.enterprise
        def enterprise(database, operation, *, token):
            item = original(database, operation, token=token)
            item['storage_names'] = projection(); return item
        self.native.enterprise = enterprise; self.post = source()
        with mock.patch.object(reader, 'read_catalog', wraps=reader.read_catalog) as read, \
             mock.patch.object(comparison, 'project_catalog', side_effect=AssertionError('strict legacy route')):
            item = self.native.compare_catalog('baseline')
        self.assertEqual(read.call_count, 1); self.assertEqual(len(self.calls), 1)
        self.assertEqual(item['marker']['storage_names'], projection()); self.assertEqual(item['reader'], projection(READER_FIELDS))
        self.assertEqual(item['origin']['sha256'], hashlib.sha256(self.pre.full_bytes()).hexdigest())
        self.assertEqual(item['postimage']['sha256'], hashlib.sha256(self.post.full_bytes()).hexdigest())
        self.assertEqual(item['origin']['token'], item['marker']['token'])
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_actual_route_collision_unicode_and_missing_fields_are_finite(self):
        for raw, expected in ((('Field', 'field'), 'ascii_field_key_collision'),
                              (('Fіeld',), 'ascii_field_identifier'), ((), 'field_names_differ')):
            self.post = source(raw, 'Physical')
            with self.assertRaises(comparison.ComparisonFailure) as caught:
                self.native.compare_catalog('baseline')
            failure = caught.exception; self.assertEqual(failure.code, expected)
            if expected == 'field_names_differ': self.assertEqual(failure.capture['schema'], 4)
            else: self.assertIsNone(failure.capture)
            self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())


def matched_capture_size_upper_bound():
    report, _ = fixture(); capture = report['storage_contract']
    capture['origin']['bytes'] = snapshots.MAX_FILE_BYTES
    capture['postimage']['bytes'] = snapshots.MAX_FILE_BYTES
    capture.update(native=None, reader=None)
    return len(protocol.encode(capture)) - 2*len(b'null') + 2*existing.projection_size_upper_bound()


class PolicyBudgetAndSourceTests(unittest.TestCase):
    def test_complete_capture_and_whole_report_maxima_fit_unchanged_caps(self):
        self.assertEqual(existing.projection_size_upper_bound(), 3469)
        self.assertEqual(matched_capture_size_upper_bound(), 7724)
        self.assertLess(matched_capture_size_upper_bound(), comparison.MAX_CAPTURE_BYTES)
        self.assertEqual(fields.field_capture_size_upper_bound(), 7902)
        self.assertEqual(existing.whole_report_size_upper_bound(), 29949)
        self.assertEqual((comparison.MAX_CAPTURE_BYTES, protocol.MAX_REPORT_BYTES), (12288, 32768))
        self.assertLess(existing.whole_report_size_upper_bound(), protocol.MAX_REPORT_BYTES)

    def test_policy_never_changes_native_call_parser_or_legacy_helpers(self):
        source_text = (ROOT/'scripts/native_1c_db_oracle/comparison.py').read_text(encoding='utf-8')
        tree = ast.parse(source_text)
        binder = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'bind_capture')
        self.assertEqual(hashlib.sha256(ast.get_source_segment(source_text, binder).encode('utf-8')).hexdigest(),
                         'cc2785302ad1ae7913363369c4d238630a290db1986565aea894201b32b13efe')
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in ('ascii_field_keys', 'project_catalog_ascii_fields', 'bind_ascii_fields_capture'):
                code = ast.get_source_segment(source_text, node)
                self.assertNotIn('.casefold(', code); self.assertNotIn('.upper(', code)
                self.assertNotIn('.lower(', code); self.assertNotIn('.strip(', code)
        fields.FieldBudgetAndUnchangedSuccessTests('test_frozen_strict_success_functions_are_byte_identical').run(
            result := unittest.TestResult())
        self.assertTrue(result.wasSuccessful(), result.errors+result.failures)

    def test_text_io_is_explicit_utf8(self):
        for node in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
                encoding = next((kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                self.assertIsInstance(encoding, ast.Constant); self.assertEqual(encoding.value, 'utf-8')


if __name__ == '__main__':
    unittest.main()
