"""Synthetic source-bound names diagnostics, never native compatibility evidence."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(ROOT / 'yadinassi/storage'))
sys.path.insert(0, str(ROOT / 'tests'))
import comparison
import filedb_catalog as reader
import protocol
import snapshots
import test_native_1c_db_oracle_comparison as existing
import test_native_1c_db_oracle_stage as fixtures
from test_filedb_catalog import Source, descriptor
from snapshots import OracleError

NONCE = existing.NONCE
TOKEN = existing.TOKEN
BARE = {'schema': 1, 'status': 'failed', 'category': 'name_mismatch', 'code': 'missing_table'}


def parsed(names):
    # Size-limit tests need no fabricated raw physical layout. Real-reader tests
    # below independently cover the collection point and completed parse.
    return SimpleNamespace(tables=tuple(SimpleNamespace(name=name) for name in names),
                           usage=SimpleNamespace(tables=len(names), total_blob_bytes=comparison.MAX_CENSUS_BLOB_BYTES))


def native(names=('Physical',)):
    return {'schema': 1, 'target': comparison.TARGET,
            'tables': [{'name': name, 'fields': ['PRIVATE_FIELD']} for name in names]}


def missing_failure(names=('physical',), native_names=('Physical',)):
    item = existing.evidence()
    item['marker']['storage_names'] = native(native_names)
    return comparison.missing_table_failure(parsed(names), item, nonce=NONCE,
        provenance=existing.identity(), baseline=fixtures.physical('baseline'))


def fixture(failure=None, cleanup=(True, True)):
    provenance = existing.identity()
    report = comparison.empty_report(NONCE, provenance)
    backend = existing.ComparisonBackend(provenance)
    backend.clean = cleanup
    backend.compare_catalog = mock.Mock(side_effect=failure if failure is not None else missing_failure())
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


def check(report, final=False):
    return comparison.validate_report(protocol.encode(report), nonce=NONCE,
                                      provenance=existing.identity(), final=final)


class NameInventoryTests(unittest.TestCase):
    def test_exact_names_case_underscores_duplicates_and_complete_counts(self):
        names = ['_Reference1', 'REFERENCE1', '_Reference1', 'Reference_1']
        value = comparison.name_diagnostic(parsed(names), native(['Reference1', 'Other_2']))
        self.assertEqual(value, {'target': comparison.TARGET,
            'scope': 'own_synthetic_disposable_database', 'status': 'complete',
            'native_tables': ['Other_2', 'Reference1'],
            'reader_tables': ['REFERENCE1', 'Reference_1', '_Reference1', '_Reference1'],
            'native_table_count': 2, 'reader_table_count': 4, 'parser_table_count': 4})
        self.assertEqual(names, ['_Reference1', 'REFERENCE1', '_Reference1', 'Reference_1'])

    def test_empty_completed_reader_inventory_is_not_truncated_or_rejected(self):
        source = Source().ready({})
        catalog = reader.read_catalog(source.read_at, source.size)
        value = comparison.name_diagnostic(catalog, native())
        self.assertEqual(value['reader_tables'], [])
        self.assertEqual((value['reader_table_count'], value['parser_table_count']), (0, 0))
        self.assertEqual(value['native_table_count'], 1)

    def test_count_caps_checked_before_copy_and_failure_has_no_partial_names(self):
        for names, selected in ((['R'] * 129, ['N']), ([], []), ([], ['N'+str(i) for i in range(5)])):
            with self.subTest(reader=len(names), native=len(selected)), self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.name_diagnostic(parsed(names), native(selected))
            self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'diagnostic_limit'))
            self.assertIsNone(caught.exception.capture)
        value = comparison.name_diagnostic(parsed(['R']*128), native(['A', 'B', 'C', 'D']))
        self.assertEqual(value['reader_table_count'], 128)

    def test_parser_count_must_equal_complete_inventory_not_subset(self):
        for count in (0, 2, True, -1, 129):
            catalog = parsed(['Reader']); catalog.usage.tables = count
            with self.subTest(count=count), self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.name_diagnostic(catalog, native())
            self.assertEqual((caught.exception.category, caught.exception.code), ('structural_rejection', 'invalid_projection'))
            self.assertIsNone(caught.exception.capture)

    def test_ascii_identifier_subset_has_no_normalization_or_partial_names(self):
        for bad in ('', '1Name', 'a-b', 'a b', 'a.b', 'a\\b', 'a"b', 'a\n', 'a\x00',
                    'a\x7f', 'а', 'N\u0301', '\U0001f642', '\ud800', 'N'*65, None, True):
            for side in ('native', 'reader'):
                with self.subTest(name=repr(bad), side=side), self.assertRaises(comparison.ComparisonFailure) as caught:
                    comparison.name_diagnostic(parsed(['Valid', bad] if side == 'reader' else ['Reader']),
                                               native(['Valid', bad] if side == 'native' else ['Native']))
                self.assertEqual((caught.exception.category, caught.exception.code),
                                 ('unsupported_layout', 'diagnostic_identifier'))
                self.assertIsNone(caught.exception.capture)
        self.assertEqual(comparison.name_diagnostic(parsed(['_']), native(['A'*64]))['reader_tables'], ['_'])

    def test_one_combined_2048_character_budget_not_per_list(self):
        names = ['R'*31]*63 + ['R'*31]  # 1984 reader characters.
        selected = ['N'*64]
        value = comparison.name_diagnostic(parsed(names), native(selected))
        self.assertEqual(sum(map(len, value['reader_tables'] + value['native_tables'])), 2048)
        names[-1] += 'R'
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.name_diagnostic(parsed(names), native(selected))
        self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'diagnostic_limit'))
        self.assertIsNone(caught.exception.capture)

    def test_schema_order_uniqueness_counts_and_exact_missing_predicate(self):
        good = comparison.name_diagnostic(parsed(['A', 'B', 'B']), native(['C', 'D']))
        edits = [lambda d: d.update(target='Other'), lambda d: d.update(scope='external'),
            lambda d: d.update(status='partial'), lambda d: d.update(raw='PRIVATE'),
            lambda d: d.update(native_tables=['D', 'C']), lambda d: d.update(reader_tables=['B', 'A', 'B']),
            lambda d: d.update(native_tables=['C', 'C']), lambda d: d.update(native_tables=['A', 'B']),
            lambda d: d.update(native_table_count=True), lambda d: d.update(native_table_count=1),
            lambda d: d.update(reader_table_count=2), lambda d: d.update(parser_table_count=2),
            lambda d: d.update(parser_table_count=True), lambda d: d.update(reader_tables=('A', 'B', 'B')),
            lambda d: d.update(reader_tables=['A', 'B', '\u0410']),
            lambda d: d.update(native_tables=['C'*64]*5, native_table_count=5),
            lambda d: d.update(reader_tables=['R']*129, reader_table_count=129, parser_table_count=129),
            lambda d: d.update(reader_tables=['R'*64]*64, reader_table_count=64, parser_table_count=64)]
        for index, edit in enumerate(edits):
            value = copy.deepcopy(good); edit(value)
            with self.subTest(index=index), self.assertRaises(OracleError): comparison.validate_name_diagnostic(value)
        # Duplicates on the reader side are deliberately preserved, not rejected.
        comparison.validate_name_diagnostic(good)

    def test_capture_limit_maps_to_finite_failure_with_no_partial_names(self):
        with mock.patch.object(comparison, 'MAX_CAPTURE_BYTES', 100), self.assertRaises(comparison.ComparisonFailure) as caught:
            missing_failure()
        self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'diagnostic_limit'))
        self.assertIsNone(caught.exception.capture)

    def test_missing_predicate_respects_earlier_selected_duplicates(self):
        # The actual strict comparator stops at duplicate A, not missing B.
        with self.assertRaises(OracleError):
            comparison.name_diagnostic(parsed(['A', 'A']), native(['A', 'B']))
        # Missing A happens before later duplicate B; all B observations survive.
        value = comparison.name_diagnostic(parsed(['B', 'B']), native(['A', 'B']))
        self.assertEqual(value['reader_tables'], ['B', 'B'])


class BoundFailureTests(unittest.TestCase):
    def test_bound_failure_remains_strict_rejection_with_no_fields_or_raw_objects(self):
        failure = missing_failure(['_Physical', 'physical', 'physical'])
        report, backend = fixture(failure); check(report)
        capture = report['storage_contract']
        self.assertEqual(capture['schema'], 2)
        self.assertEqual(capture['status'], 'failed')
        self.assertEqual(report['failure_kind'], 'catalog_comparison_failed')
        self.assertEqual(report['failed_stage'], 'baseline')
        self.assertEqual(report['reader_validation'], 'failed')
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertFalse(report['accepted'])
        self.assertEqual(backend.compare_catalog.call_count, 1)
        self.assertEqual(capture['name_diagnostic']['reader_table_count'], 3)
        self.assertEqual(capture['name_diagnostic']['native_tables'], ['Physical'])
        self.assertEqual(capture['name_diagnostic']['reader_tables'], ['_Physical', 'physical', 'physical'])
        self.assertNotIn('name_census', capture)
        raw = protocol.encode(capture)
        for private in (b'PRIVATE_FIELD', b'fields', b'raw_descriptor', b'Undocumented', b'indexes', b'files'):
            self.assertNotIn(private, raw)
        self.assertEqual(set(failure.__dict__), {'kind', 'category', 'code', 'capture'})
        report['cleanup'].update(container_removed=True, private_staging_removed=True)
        check(report, True)
        self.assertFalse(report['accepted'])

    def test_each_binding_and_exact_shape_checked_independently(self):
        edits = [lambda c: c.update(schema=True), lambda c: c.update(status='matched'),
            lambda c: c.update(category='structural_rejection'), lambda c: c.update(code='duplicate_table'),
            lambda c: c.update(operation='audit'), lambda c: c.update(nonce='b'*32),
            lambda c: c.update(token='invalid'), lambda c: c.update(token='b'*31),
            lambda c: c.update(source_manifest_sha256='b'*64), lambda c: c.update(reader_source_sha256='b'*64),
            lambda c: c.update(actual_version='8.3.0.0'), lambda c: c.update(raw='PRIVATE'),
            lambda c: c['origin'].update(snapshot='restored'), lambda c: c['origin'].update(clone='writer'),
            lambda c: c['origin'].update(bytes=True), lambda c: c['origin'].update(bytes=8192),
            lambda c: c['origin'].update(sha256='b'*64), lambda c: c['origin'].update(token=TOKEN),
            lambda c: c['postimage'].update(copy='baseline'),
            lambda c: c['postimage'].update(binding='native_execution_time'),
            lambda c: c['postimage'].update(bytes=8192), lambda c: c['postimage'].update(bytes=24577),
            lambda c: c['postimage'].update(bytes=True), lambda c: c['postimage'].update(sha256='invalid'),
            lambda c: c['postimage'].update(storage_version=[8, 2, 14, 0]),
            lambda c: c['postimage'].update(storage_version=[8, 3, 8, False]),
            lambda c: c['postimage'].update(page_size=4096), lambda c: c['postimage'].update(raw='PRIVATE'),
            lambda c: c['name_diagnostic' if c['schema'] == 2 else 'name_census'].update(reader_table_count=True)]
        for count in (1, 129):
            good, _ = fixture(missing_failure(['Reader'] * count))
            for index, edit in enumerate(edits):
                report = copy.deepcopy(good); edit(report['storage_contract'])
                with self.subTest(index=index), self.assertRaises(OracleError): check(report)
            with mock.patch.object(comparison, 'MAX_CAPTURE_BYTES', 100), self.assertRaises(OracleError): check(good)

    def test_marker_nonce_token_origin_and_source_bound_before_retention(self):
        for section, key, value in [('marker', 'nonce', 'b'*32), ('marker', 'token', 'b'*32),
            ('marker', 'operation', 'audit'), ('origin', 'nonce', 'b'*32), ('origin', 'token', 'b'*32),
            ('origin', 'clone', 'writer'), ('origin', 'bytes', 1), ('origin', 'sha256', 'b'*64)]:
            item = existing.evidence(); item[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(OracleError):
                comparison.missing_table_failure(parsed(['Reader']), item, nonce=NONCE,
                    provenance=existing.identity(), baseline=fixtures.physical('baseline'))
        for count in (1, 129):
            failure = missing_failure(['Reader'] * count); report, _ = fixture(failure)
            provenance = copy.deepcopy(report['provenance']); provenance['sources'][comparison.READER_SOURCE] = 'd'*64
            report['provenance'] = provenance
            with self.assertRaises(OracleError):
                comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=provenance)

    def test_wrong_report_failure_stage_or_success_cannot_carry_diagnostic(self):
        good, _ = fixture()
        edits = [lambda r: r.update(reader_validation=comparison.VERDICT),
            lambda r: r.update(reader_validation='not_run'), lambda r: r.update(failure_kind='process_failed'),
            lambda r: r.update(failed_stage='create'), lambda r: r.update(status='ok'),
            lambda r: r.update(snapshots=[]), lambda r: r.update(native_compatibility='verified')]
        for index, edit in enumerate(edits):
            report = copy.deepcopy(good); edit(report)
            with self.subTest(index=index), self.assertRaises(OracleError): check(report)
        successful, _ = existing.fixture(); successful['storage_contract'] = good['storage_contract']
        with self.assertRaises(OracleError): check(successful)

    def test_offline_token_and_postimage_format_are_not_an_independent_archive_anchor(self):
        # A report alone cannot authenticate valid substitutions of producer-only
        # values. The next class tests fresh-token and freeze/parse comparisons at
        # construction, where those independent values actually exist.
        for edit in (lambda c: c.update(token='b'*32),
                     lambda c: c['postimage'].update(sha256='b'*64),
                     lambda c: c['postimage'].update(bytes=3*8192)):
            report, _ = fixture(); edit(report['storage_contract'])
            check(report)

    def test_native_and_raw_cleanup_each_strip_capture_and_binding_to_original_bare(self):
        for count in (1, 129):
            for cleanup in ((False, True), (True, False), (False, False)):
                report, _ = fixture(missing_failure(['Reader'] * count), cleanup=cleanup); check(report)
                self.assertEqual(report['storage_contract'], BARE)
                self.assertNotIn(b'name_diagnostic', protocol.encode(report))
                self.assertNotIn(b'name_census', protocol.encode(report))
                self.assertEqual(report['reader_validation'], 'failed')
                self.assertEqual(report['failure_kind'], 'catalog_comparison_failed')

    def test_host_cleanup_each_requires_all_four_and_strips_names(self):
        spec = importlib.util.spec_from_file_location('name_diagnostic_host', ROOT/'scripts/native_1c_db_oracle.py')
        host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
        for count in (1, 129):
            for failed in ('native_processes_stopped', 'raw_files_removed', 'container_removed', 'private_staging_removed'):
                report, _ = fixture(missing_failure(['Reader'] * count))
                report['cleanup'] = dict.fromkeys(report['cleanup'], True)
                report['cleanup'][failed] = False
                if failed in report['stages'][-1]['checks']:
                    report['stages'][-1]['checks'][failed] = False
                    report['stages'][-1]['status'] = 'failed'
                with self.subTest(failed=failed), self.assertRaises(OracleError): check(report, True)
                host.fail_report(report, 'cleanup_unverified', 'cleanup', preserve_primary=True)
                check(report, True)
                self.assertEqual(report['storage_contract'], BARE)
                self.assertFalse(report['accepted'])

    def test_invalid_attached_capture_never_released_and_other_failures_stay_bare(self):
        for category, code in [('name_mismatch', 'duplicate_table'), ('resource_limit', 'diagnostic_limit'),
                               ('unsupported_layout', 'diagnostic_identifier')]:
            failure = comparison.ComparisonFailure(category, code, capture=missing_failure().capture)
            report, _ = fixture(failure); check(report)
            self.assertEqual(report['storage_contract'], {'schema': 1, 'status': 'failed', 'category': category, 'code': code})
        failure = missing_failure(); failure.capture['name_diagnostic']['status'] = 'partial'
        report, _ = fixture(failure); check(report)
        self.assertEqual(report['storage_contract'], BARE)

    def test_generic_exceptions_and_unrecognized_subclasses_never_serialize_names(self):
        class OtherFailure(comparison.ComparisonFailure): pass
        errors = [(RuntimeError('PRIVATE EXCEPTION'), 'unexpected_failure'),
                  (OtherFailure('name_mismatch', 'missing_table', capture=missing_failure().capture), 'logical_mismatch')]
        for error, kind in errors:
            error.capture = missing_failure().capture
            report, _ = fixture(error); check(report)
            self.assertEqual(report['failure_kind'], kind)
            self.assertIsNone(report['storage_contract'])
            self.assertNotIn(b'PRIVATE', protocol.encode(report))
            self.assertNotIn(b'name_diagnostic', protocol.encode(report))
            self.assertNotIn(b'name_census', protocol.encode(report))


@unittest.skipIf(os.name == 'nt', 'POSIX pinned native harness boundary')
class NativeCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.cleanup)
        self.root = Path(self.temp.name).resolve(); self.artifacts = self.root/'artifacts'; self.artifacts.mkdir()
        existing.normalize_owners(self)
        self.seed = self.artifacts/'seed'; self.seed.mkdir()
        self.pre = Source().ready(); (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed, self.artifacts/'baseline', quiescent=lambda: True)
        self.native = fixtures.stage.Native(NONCE, existing.identity()); self.native.root = self.root
        self.native.artifacts = self.artifacts; self.native.budget_base = self.root; self.native.stage = 'baseline'
        self.native.quiescent = lambda: True; self.native.budgets = lambda *args: None
        self.post = Source().ready({2: descriptor('_Physical'), 3: descriptor('physical'), 4: descriptor('physical')})
        self.calls = []
        def enterprise(database, operation, *, token):
            self.calls.append((database, operation, token))
            (database/'1Cv8.1CD').write_bytes(self.post.full_bytes())
            return existing.marker(token)
        self.native.enterprise = enterprise

    def cleanup(self):
        for path in self.root.rglob('*'):
            if path.is_dir(): path.chmod(0o700)
        self.temp.cleanup()

    def test_complete_real_reader_and_postimage_checked_before_names_one_native_call(self):
        with mock.patch.object(reader, 'read_catalog', wraps=reader.read_catalog) as read, \
             self.assertRaises(comparison.ComparisonFailure) as caught:
            self.native.compare_catalog('baseline')
        failure = caught.exception
        self.assertEqual((failure.category, failure.code), ('name_mismatch', 'missing_table'))
        self.assertEqual(read.call_count, 1)
        self.assertEqual(len(self.calls), 1)
        capture = failure.capture
        self.assertEqual(capture['token'], self.calls[0][2])
        self.assertEqual(capture['origin']['sha256'], hashlib.sha256(self.pre.full_bytes()).hexdigest())
        self.assertEqual(capture['postimage']['sha256'], hashlib.sha256(self.post.full_bytes()).hexdigest())
        self.assertEqual(capture['name_diagnostic']['reader_table_count'], 3)
        self.assertEqual(capture['name_diagnostic']['native_tables'], ['Physical'])
        self.assertEqual(capture['name_diagnostic']['reader_tables'], ['_Physical', 'physical', 'physical'])
        self.assertNotIn('name_census', capture)
        self.assertEqual(capture['name_diagnostic']['parser_table_count'], 3)
        self.assertFalse((self.artifacts/'auditor').exists())
        self.assertFalse((self.artifacts/'auditor_frozen').exists())
        self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(), self.pre.full_bytes())
        self.assertNotIn('marker', failure.__dict__)
        self.assertNotIn('catalog', failure.__dict__)

    def test_changed_postimage_or_incomplete_reader_never_reaches_name_collection(self):
        inspect = snapshots.inspect_frozen_catalog
        def changed(*args, **kwargs):
            summary, catalog = inspect(*args, **kwargs); summary['sha256'] = 'b'*64
            return summary, catalog
        for side_effect, code in [(changed, 'postimage_changed'),
                                  (reader.InvalidStructure('descriptor_utf8'), 'descriptor_utf8')]:
            with mock.patch.object(snapshots, 'inspect_frozen_catalog', side_effect=side_effect), \
                 mock.patch.object(comparison, 'name_census', side_effect=AssertionError('must not collect')) as collect, \
                 self.assertRaises(comparison.ComparisonFailure) as caught:
                self.native.compare_catalog('baseline')
            self.assertEqual(caught.exception.code, code)
            self.assertIsNone(caught.exception.capture)
            collect.assert_not_called()

    def test_valid_hex_wrong_token_is_rejected_against_actual_fresh_launch_token(self):
        original = self.native.enterprise
        def wrong_token(database, operation, *, token):
            data = original(database, operation, token=token)
            data['token'] = 'b'*32 if token != 'b'*32 else 'c'*32
            return data
        self.native.enterprise = wrong_token
        with self.assertRaises(OracleError) as caught: self.native.compare_catalog('baseline')
        self.assertEqual(caught.exception.kind, 'snapshot_changed')
        self.assertFalse(hasattr(caught.exception, 'capture'))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((self.artifacts/'auditor').exists())
        self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_only_exact_missing_table_is_collected_other_strict_failures_unchanged(self):
        cases = [({2: descriptor(), 3: descriptor()}, 'duplicate_table'),
                 ({2: descriptor(fields='{"Other","X",0,0,0,""}')}, 'field_names_differ'),
                 ({2: descriptor(fields='{"Field","X",0,0,0,""},{"Field","X",0,0,0,""}')}, 'duplicate_field')]
        for descriptions, code in cases:
            self.post = Source().ready(descriptions)
            with mock.patch.object(comparison, 'name_census', side_effect=AssertionError('must not collect')) as collect, \
                 self.assertRaises(comparison.ComparisonFailure) as caught:
                self.native.compare_catalog('baseline')
            self.assertEqual(caught.exception.code, code)
            self.assertIsNone(caught.exception.capture)
            collect.assert_not_called()

    def test_unsupported_identifier_after_real_parse_yields_complete_counts_only(self):
        self.post = Source().ready({2: descriptor('not-supported')})
        with self.assertRaises(comparison.ComparisonFailure) as caught: self.native.compare_catalog('baseline')
        self.assertEqual((caught.exception.category, caught.exception.code), ('name_mismatch', 'missing_table'))
        self.assertEqual(caught.exception.capture['name_census']['reader_invalid_identifier_count'], 1)
        self.assertEqual(caught.exception.capture['name_census']['policy_flags'], ['reader_identifier'])
        self.assertNotIn(b'not-supported', protocol.encode(caught.exception.capture))
        self.assertEqual(len(self.calls), 1)

    def test_success_still_has_only_original_filtered_projection(self):
        self.post = Source().ready({2: descriptor(), 3: descriptor('not-supported')})
        with mock.patch.object(comparison, 'name_census', side_effect=AssertionError('must not collect')) as collect:
            evidence = self.native.compare_catalog('baseline')
        collect.assert_not_called()
        self.assertEqual(evidence['reader'], existing.projection())
        self.assertNotIn('name_diagnostic', evidence)
        self.assertEqual(len(self.calls), 1)


def maximum_name_capture():
    """An attainable names maximum, with independently maximal binding widths.

    Every accepted name is ASCII without JSON escapes. Four native and 128 reader
    names maximize per-item punctuation and decimal count widths; all 2048 name
    characters are consumed. Every other field is fixed or fixed-width, except
    file sizes, which use the largest allowed decimal width. No subbudget only.
    """
    selected = ['N'+str(index)+'x'*62 for index in range(4)]
    names = ['R'*14]*128
    item = existing.evidence(); item['marker']['storage_names'] = native(selected)
    item['origin']['bytes'] = snapshots.MAX_FILE_BYTES
    item['postimage']['bytes'] = snapshots.MAX_FILE_BYTES
    baseline = fixtures.physical('baseline'); baseline['bytes'] = snapshots.MAX_FILE_BYTES
    return comparison.missing_table_failure(parsed(names), item, nonce=NONCE,
        provenance=existing.identity(), baseline=baseline).capture


class DiagnosticBudgetTests(unittest.TestCase):
    def test_direct_complete_names_capture_maximum_and_finite_enum_bounds(self):
        capture = maximum_name_capture()
        value = capture['name_diagnostic']
        self.assertEqual((len(value['native_tables']), len(value['reader_tables'])), (4, 128))
        self.assertEqual(sum(map(len, value['native_tables'] + value['reader_tables'])), 2048)
        comparison.validate_name_diagnostic(value)
        size = len(protocol.encode(capture))
        self.assertEqual(size, 3491)
        self.assertLessEqual(size, comparison.MAX_CAPTURE_BYTES)
        self.assertEqual(comparison.MAX_CAPTURE_BYTES, 12288)
        for category, codes in comparison.DIAGNOSTICS.items():
            for code in codes:
                bare = {'schema': 1, 'status': 'failed', 'category': category, 'code': code}
                self.assertLess(len(protocol.encode(bare)), size)
        self.assertIn('diagnostic_limit', comparison.DIAGNOSTICS['resource_limit'])
        self.assertIn('diagnostic_identifier', comparison.DIAGNOSTICS['unsupported_layout'])

    def test_complete_report_bound_keeps_every_component_and_newline(self):
        # Existing executable proof enumerates all source names, stages, reports,
        # failure enums and independently maximal integer/text widths. Its full
        # capture slot is enforced for every old and new variant above.
        size = existing.whole_report_size_upper_bound()
        self.assertEqual(size, 29821)
        self.assertLess(size, protocol.MAX_REPORT_BYTES)
        self.assertEqual(protocol.MAX_REPORT_BYTES, 32768)
        # Replace that complete slot by the independently attained name bound.
        self.assertEqual(size - comparison.MAX_CAPTURE_BYTES + len(protocol.encode(maximum_name_capture())), 21024)

    def test_new_fixture_text_io_uses_explicit_utf8(self):
        tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
                encoding = next((kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                self.assertIsInstance(encoding, ast.Constant)
                self.assertEqual(encoding.value, 'utf-8')

    @unittest.skipIf(os.name == 'nt', 'POSIX synthetic native ownership')
    def test_new_native_fixture_resolves_alias_and_models_fixed_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            actual = root/'actual'; actual.mkdir()
            alias = root/'alias'; alias.symlink_to(actual, target_is_directory=True)
            real_fstat = os.fstat
            def foreign_owner(descriptor):
                info = real_fstat(descriptor)
                fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
                return SimpleNamespace(**dict(fields, st_uid=501, st_gid=20))
            case = NativeCollectionTests('test_complete_real_reader_and_postimage_checked_before_names_one_native_call')
            with mock.patch.object(tempfile, 'tempdir', str(alias)), \
                 mock.patch.object(os, 'fstat', side_effect=foreign_owner):
                result = unittest.TestResult(); case.run(result)
                self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
                self.assertIn(actual, case.root.parents)
                with snapshots._directory(actual) as descriptor, self.assertRaises(OracleError) as caught:
                    snapshots._database_contents(descriptor)
                self.assertEqual(caught.exception.kind, 'invalid_input')


if __name__ == '__main__':
    unittest.main()
