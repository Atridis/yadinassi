"""Complete, failure-only selected field names; no native compatibility evidence."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
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
import test_native_1c_db_oracle_name_diagnostic as names
import test_native_1c_db_oracle_stage as fixtures
from test_filedb_catalog import Source, descriptor
from snapshots import OracleError

NONCE = existing.NONCE
BARE = {'schema': 1, 'status': 'failed', 'category': 'name_mismatch', 'code': 'field_names_differ'}


def projection(items=(('Physical', ('Field',)),)):
    return {'schema': 1, 'target': comparison.TARGET,
            'tables': [{'name': name, 'fields': list(fields)} for name, fields in items]}


def parsed(items=(('Physical', ()),)):
    return SimpleNamespace(tables=tuple(SimpleNamespace(name=name,
        fields=tuple(SimpleNamespace(name=field) for field in fields)) for name, fields in items),
        usage=SimpleNamespace(tables=len(items)))


def field_failure(catalog=None, native=None):
    item = existing.evidence()
    item['marker']['storage_names'] = native if native is not None else projection()
    return comparison.field_names_failure(catalog if catalog is not None else parsed(), item,
        nonce=NONCE, provenance=existing.identity(), baseline=fixtures.physical('baseline'))


def fixture(failure=None, cleanup=(True, True)):
    return names.fixture(field_failure() if failure is None else failure, cleanup)


def check(report, final=False):
    return existing.comparison.validate_report(protocol.encode(report), nonce=NONCE,
        provenance=existing.identity(), final=final)


class FieldProjectionTests(unittest.TestCase):
    def failure(self, catalog, native, pair):
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.field_diagnostic(catalog, native)
        self.assertEqual((caught.exception.category, caught.exception.code), pair)
        self.assertIsNone(caught.exception.capture)

    def test_empty_fields_and_final_inequality_are_complete_distinct_observations(self):
        expected = projection((('B', ('Z', 'A')), ('A', ('N',))))
        for items in ((('B', ('Z', 'A')), ('A', ())),
                      (('B', ('Z', 'A')), ('A', ('n',)))):
            catalog = parsed(items)
            with self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.project_catalog(catalog, expected)
            self.assertEqual(caught.exception.code, 'field_names_differ')
            value = comparison.field_diagnostic(catalog, expected)
            self.assertEqual(value['native'], projection((('A', ('N',)), ('B', ('A', 'Z')))))
            self.assertEqual(value['reader']['tables'][1], {'name': 'B', 'fields': ['A', 'Z']})
            self.assertEqual(value['reader']['tables'][0]['fields'], list(items[1][1]))
            comparison.validate_field_diagnostic(value)
            self.assertEqual(expected['tables'][0]['fields'], ['Z', 'A'])

    def test_every_selected_name_rechecked_after_early_empty_not_inferred(self):
        expected = projection((('A', ('F',)), ('Z', ('F',))))
        for items, code in (((('A', ()),), 'missing_table'),
                            ((('A', ()), ('z', ('F',))), 'missing_table'),
                            ((('A', ()), ('Z', ('F',)), ('Z', ('F',))), 'duplicate_table')):
            catalog = parsed(items)
            with self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.project_catalog(catalog, expected)
            self.assertEqual(caught.exception.code, 'field_names_differ')
            self.failure(catalog, expected, ('name_mismatch', code))

    def test_later_duplicate_fields_rejects_without_early_empty_partial_capture(self):
        self.failure(parsed((('A', ()), ('Z', ('F', 'F')))),
            projection((('A', ('F',)), ('Z', ('F',)))), ('name_mismatch', 'duplicate_field'))

    def test_unrelated_table_fields_are_not_read_or_exported(self):
        class PrivateTable:
            name = 'PRIVATE_UNRELATED_TABLE'
            @property
            def fields(self):
                raise AssertionError('unrelated fields must not be read')
        catalog = parsed(); catalog.tables += (PrivateTable(), PrivateTable()); catalog.usage.tables = 3
        value = comparison.field_diagnostic(catalog, projection())
        self.assertEqual(value['reader'], projection((('Physical', ()),)))
        self.assertNotIn(b'PRIVATE', protocol.encode(value))

    def test_empty_reader_allowed_only_in_failure_validator(self):
        actual = projection((('Physical', ()),))
        comparison.validate_field_reader_projection(actual)
        with self.assertRaises(OracleError): comparison.validate_projection(actual)
        self.failure(parsed(), actual, ('resource_limit', 'projection_limit'))
        self.failure(parsed((('Physical', ('Field',)),)), projection(),
                     ('structural_rejection', 'invalid_projection'))

    def test_exact_names_preserve_case_underscores_bmp_quotes_and_backslashes(self):
        table = 'Таблица"\\'
        value = comparison.field_diagnostic(parsed(((table, ('_Поле', 'поле"\\')),)),
                                             projection(((table, ('Поле',)),)))
        self.assertEqual(value['reader']['tables'][0]['fields'], ['_Поле', 'поле"\\'])
        for name in ('physical', '_Physical', 'Physical '):
            self.failure(parsed(((name, ()),)), projection(), ('name_mismatch', 'missing_table'))

    def test_all_projection_collection_and_name_limits_reject_without_truncation(self):
        too_many_fields = tuple('F'+str(i) for i in range(33))
        values = [projection(()), projection(tuple((str(i), ()) for i in range(5))),
            projection((('P', too_many_fields),)),
            projection(tuple((str(i), tuple('F'+str(j) for j in range(32))) for i in range(3))),
            projection((('N'*65, ()),)), projection((('P', ('F'*65,)),)),
            projection((('P', tuple(str(i)+'x'*63 for i in range(8))),))]
        for value in values:
            original = copy.deepcopy(value)
            with self.subTest(value=value), self.assertRaises(OracleError):
                comparison.validate_field_reader_projection(value)
            self.assertEqual(value, original)
        for actual in (parsed((('Physical', too_many_fields),)),
                       parsed((('Physical', ('F'*65,)),)),
                       parsed((('Physical', tuple(str(i)+'x'*63 for i in range(8))),))):
            self.failure(actual, projection(), ('resource_limit', 'projection_limit'))
        expected = projection(tuple((str(i), ('F',)) for i in range(3)))
        self.failure(parsed(tuple((str(i), tuple('F'+str(j) for j in range(32))) for i in range(3))),
                     expected, ('resource_limit', 'projection_limit'))
        with mock.patch.object(comparison, 'MAX_PROJECTION_BYTES', 100):
            self.failure(parsed(), projection(), ('resource_limit', 'projection_limit'))

    def test_boundary_4_tables_32_per_table_64_total_and_512_units(self):
        # All 64 names are unique within their own table, and each is 7 or 8 BMP units.
        fields = tuple(chr(0x410+i)+'я'*6 for i in range(32))
        items = tuple((chr(0x500+i), fields if i < 2 else ()) for i in range(4))
        value = projection(items)
        value['tables'][0]['fields'][0] += 'я'*60  # Individual 64 ceiling checked separately below.
        with self.assertRaises(OracleError): comparison.validate_field_reader_projection(value)
        value = projection(items)
        for table in value['tables'][:2]:
            for index in range(30): table['fields'][index] += 'я'
        self.assertEqual(sum(len(t['name'])+sum(map(len, t['fields'])) for t in value['tables']), 512)
        comparison.validate_field_reader_projection(value)
        self.assertEqual(sum(len(t['fields']) for t in value['tables']), 64)
        # A trailing empty table still charges its name, unlike a strict nonempty loop.
        value['tables'][-1]['name'] += 'я'
        with self.assertRaises(OracleError): comparison.validate_field_reader_projection(value)
        self.failure(parsed(tuple((t['name'], tuple(t['fields'])) for t in value['tables'])),
            projection(tuple((t['name'], ('F',)) for t in value['tables'])), ('resource_limit', 'projection_limit'))
        comparison.validate_field_reader_projection(projection((('N'*64, ('F'*64,)),)))

    def test_unsupported_names_duplicate_names_and_malformed_shapes_are_finite(self):
        for bad in ('', '\n', '\x7f', '\u2028', '\ud800', '\U0001f642', None, True):
            self.failure(parsed((('Physical', (bad,)),)), projection(), ('structural_rejection', 'invalid_projection'))
        for change in (lambda c: setattr(c, 'tables', list(c.tables)),
                       lambda c: setattr(c.usage, 'tables', True),
                       lambda c: setattr(c.usage, 'tables', 0),
                       lambda c: setattr(c.tables[0], 'fields', [])):
            catalog = parsed(); change(catalog)
            self.failure(catalog, projection(), ('structural_rejection', 'invalid_projection'))
        value = projection((('A', ()), ('A', ())))
        with self.assertRaises(OracleError): comparison.validate_field_reader_projection(value)
        value = projection((('A', ('F', 'F')),))
        with self.assertRaises(OracleError): comparison.validate_field_reader_projection(value)
        with mock.patch.object(comparison, 'MAX_CENSUS_TABLES', 0):
            self.failure(parsed(), projection(), ('resource_limit', 'projection_limit'))

    def test_exact_diagnostic_shape_order_sets_and_inequality_are_independent(self):
        good = comparison.field_diagnostic(parsed((('A', ()), ('Z', ('Other', 'F')))),
            projection((('A', ('F',)), ('Z', ('F',)))))
        edits = [lambda d: d.update(target='Other'), lambda d: d.update(scope='external'),
            lambda d: d.update(status='partial'), lambda d: d.update(raw='PRIVATE'),
            lambda d: d.update(reader=copy.deepcopy(d['native'])),
            lambda d: d['reader']['tables'].reverse(),
            lambda d: d['reader']['tables'][1]['fields'].reverse(),
            lambda d: d['reader']['tables'].pop(),
            lambda d: d['reader']['tables'][1].update(name='Other'),
            lambda d: d['reader']['tables'][1].update(fields=['F', 'F']),
            lambda d: d['reader']['tables'][0].update(raw='PRIVATE'),
            lambda d: d['native']['tables'][0].update(fields=[])]
        for index, edit in enumerate(edits):
            value = copy.deepcopy(good); edit(value)
            with self.subTest(index=index), self.assertRaises(OracleError): comparison.validate_field_diagnostic(value)

    def test_deadline_and_capture_limit_do_not_retain_partial_data(self):
        with self.assertRaises(OracleError) as caught:
            comparison.field_diagnostic(parsed(), projection(), before_scan=lambda: (_ for _ in ()).throw(OracleError('timeout')))
        self.assertEqual(caught.exception.kind, 'timeout')
        with mock.patch.object(comparison, 'MAX_CAPTURE_BYTES', 100), self.assertRaises(comparison.ComparisonFailure) as caught:
            field_failure()
        self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'diagnostic_limit'))
        self.assertIsNone(caught.exception.capture)


class BoundFieldFailureTests(unittest.TestCase):
    def test_complete_bound_failure_does_not_claim_success_or_compatibility(self):
        report, _ = fixture(); check(report)
        capture = report['storage_contract']
        self.assertEqual(capture['schema'], 4)
        self.assertEqual(capture['field_diagnostic']['reader'], projection((('Physical', ()),)))
        self.assertEqual(capture['field_diagnostic']['native'], projection())
        self.assertEqual((report['status'], report['reader_validation'], report['native_compatibility']),
                         ('failed', 'failed', 'not_claimed'))
        self.assertEqual((report['failure_kind'], report['failed_stage']), ('catalog_comparison_failed', 'baseline'))
        self.assertFalse(report['accepted'])
        for forbidden in (b'raw_descriptor', b'indexes', b'attributes', b'files', b'type', b'rows', b'PRIVATE'):
            self.assertNotIn(forbidden, protocol.encode(capture))
        report['cleanup'].update(container_removed=True, private_staging_removed=True); check(report, True)
        self.assertFalse(report['accepted'])

    def test_all_binding_fields_and_exact_capture_schema_checked(self):
        edits = [lambda c: c.update(schema=True), lambda c: c.update(schema=3),
            lambda c: c.update(status='matched'), lambda c: c.update(code='missing_table'),
            lambda c: c.update(category='resource_limit'), lambda c: c.update(raw='PRIVATE'),
            lambda c: c.update(operation='audit'), lambda c: c.update(nonce='b'*32),
            lambda c: c.update(token='invalid'), lambda c: c.update(source_manifest_sha256='b'*64),
            lambda c: c.update(reader_source_sha256='b'*64), lambda c: c.update(actual_version='8.3.0.0'),
            lambda c: c['origin'].update(snapshot='restored'), lambda c: c['origin'].update(clone='writer'),
            lambda c: c['origin'].update(bytes=True), lambda c: c['origin'].update(bytes=8192),
            lambda c: c['origin'].update(sha256='b'*64), lambda c: c['origin'].update(token='d'*32),
            lambda c: c['postimage'].update(copy='baseline'), lambda c: c['postimage'].update(binding='other'),
            lambda c: c['postimage'].update(bytes=True), lambda c: c['postimage'].update(bytes=24577),
            lambda c: c['postimage'].update(bytes=8192), lambda c: c['postimage'].update(sha256='invalid'),
            lambda c: c['postimage'].update(storage_version=[8, 3, 8, False]),
            lambda c: c['postimage'].update(page_size=4096),
            lambda c: c['field_diagnostic'].update(status='partial')]
        good, _ = fixture()
        for index, edit in enumerate(edits):
            report = copy.deepcopy(good); edit(report['storage_contract'])
            with self.subTest(index=index), self.assertRaises(OracleError): check(report)
        with mock.patch.object(comparison, 'MAX_CAPTURE_BYTES', 100), self.assertRaises(OracleError): check(good)

    def test_constructor_marker_origin_and_source_bound_before_retention(self):
        for section, key, value in [('marker', 'nonce', 'b'*32), ('marker', 'token', 'b'*32),
            ('marker', 'operation', 'audit'), ('origin', 'nonce', 'b'*32), ('origin', 'token', 'b'*32),
            ('origin', 'clone', 'writer'), ('origin', 'bytes', 1), ('origin', 'sha256', 'b'*64)]:
            item = existing.evidence(); item[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(OracleError):
                comparison.field_names_failure(parsed(), item, nonce=NONCE,
                    provenance=existing.identity(), baseline=fixtures.physical('baseline'))
        report, _ = fixture()
        report['provenance']['sources'][comparison.READER_SOURCE] = 'b'*64
        with self.assertRaises(OracleError):
            comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=report['provenance'])

    def test_wrong_mode_stage_status_and_success_envelopes_reject(self):
        edits = [lambda r: r.pop('projection_mode'), lambda r: r.update(projection_mode='default'),
            lambda r: r.update(projection_mode='dbms_names_false'), lambda r: r.update(projection_mode=True),
            lambda r: r.update(lane='native-file-db-catalog-compare-v4'),
            lambda r: r.update(reader_validation=comparison.VERDICT), lambda r: r.update(status='ok'),
            lambda r: r.update(failed_stage='create'), lambda r: r.update(failure_kind='process_failed'),
            lambda r: r.update(snapshots=[]), lambda r: r.update(accepted=True)]
        good, _ = fixture()
        for edit in edits:
            report = copy.deepcopy(good); edit(report)
            with self.assertRaises(OracleError): check(report)
        successful, _ = existing.fixture(); successful['storage_contract'] = good['storage_contract']
        with self.assertRaises(OracleError): check(successful)

    def test_every_cleanup_gate_strips_complete_capture_to_bare_rejection(self):
        for cleanup in ((False, True), (True, False), (False, False)):
            report, _ = fixture(cleanup=cleanup); check(report)
            self.assertEqual(report['storage_contract'], BARE)
        spec = importlib.util.spec_from_file_location('field_diagnostic_host', ROOT/'scripts/native_1c_db_oracle.py')
        host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
        for gate in ('native_processes_stopped', 'raw_files_removed', 'container_removed', 'private_staging_removed'):
            report, _ = fixture(); report['cleanup'] = dict.fromkeys(report['cleanup'], True)
            report['cleanup'][gate] = False
            if gate in report['stages'][-1]['checks']:
                report['stages'][-1]['checks'][gate] = False; report['stages'][-1]['status'] = 'failed'
            with self.subTest(gate=gate), self.assertRaises(OracleError): check(report, True)
            host.fail_report(report, 'cleanup_unverified', 'cleanup', preserve_primary=True); check(report, True)
            self.assertEqual(report['storage_contract'], BARE)
            self.assertNotIn(b'field_diagnostic', protocol.encode(report))

    def test_tampered_capture_or_different_failure_never_released(self):
        failure = field_failure(); failure.capture['field_diagnostic']['status'] = 'partial'
        report, _ = fixture(failure); self.assertEqual(report['storage_contract'], BARE); check(report)
        for category, code in (('name_mismatch', 'missing_table'), ('name_mismatch', 'duplicate_table'),
                               ('resource_limit', 'projection_limit')):
            failure = comparison.ComparisonFailure(category, code, capture=field_failure().capture)
            report, _ = fixture(failure); check(report)
            self.assertEqual(report['storage_contract'], dict(BARE, category=category, code=code))
        failure = names.missing_failure()
        failure.category = 'name_mismatch'; failure.code = 'field_names_differ'
        report, _ = fixture(failure); check(report); self.assertEqual(report['storage_contract'], BARE)

    def test_offline_format_checks_do_not_authenticate_replaced_valid_private_bindings(self):
        for edit in (lambda c: c.update(token='b'*32), lambda c: c['postimage'].update(sha256='b'*64),
                     lambda c: c['postimage'].update(bytes=3*8192)):
            report, _ = fixture(); edit(report['storage_contract']); check(report)


@unittest.skipIf(os.name == 'nt', 'POSIX synthetic native ownership')
class RealReaderFieldTests(unittest.TestCase):
    setUp = names.NativeCollectionTests.setUp
    cleanup = names.NativeCollectionTests.cleanup

    def test_empty_and_final_inequality_use_actual_reader_once_after_hash_check(self):
        for fields, expected in (('', []), ('{"Other","X",0,0,0,""}', ['Other'])):
            self.calls.clear()
            self.post = Source().ready({2: descriptor(fields=fields), 3: descriptor('PRIVATE_UNRELATED')})
            with mock.patch.object(reader, 'read_catalog', wraps=reader.read_catalog) as read, \
                 self.assertRaises(comparison.ComparisonFailure) as caught:
                self.native.compare_catalog('baseline')
            failure = caught.exception; capture = failure.capture
            self.assertEqual((failure.category, failure.code), ('name_mismatch', 'field_names_differ'))
            self.assertEqual(read.call_count, 1); self.assertEqual(len(self.calls), 1)
            self.assertEqual(capture['token'], self.calls[0][2])
            self.assertEqual(capture['origin']['sha256'], hashlib.sha256(self.pre.full_bytes()).hexdigest())
            self.assertEqual(capture['postimage']['sha256'], hashlib.sha256(self.post.full_bytes()).hexdigest())
            self.assertEqual(capture['field_diagnostic']['reader']['tables'][0]['fields'], expected)
            self.assertNotIn(b'PRIVATE', protocol.encode(capture))
            self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())
            self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(), self.pre.full_bytes())
            self.assertEqual(set(failure.__dict__), {'kind', 'category', 'code', 'capture'})

    def test_early_empty_later_missing_duplicate_and_duplicate_fields_export_nothing(self):
        original = self.native.enterprise
        def enterprise(database, operation, *, token):
            data = original(database, operation, token=token)
            data['storage_names'] = projection((('Physical', ('Field',)), ('Z', ('Field',))))
            return data
        self.native.enterprise = enterprise
        cases = [({2: descriptor(fields='')}, 'missing_table'),
            ({2: descriptor(fields=''), 3: descriptor('Z'), 4: descriptor('Z')}, 'duplicate_table'),
            ({2: descriptor(fields=''), 3: descriptor('Z', fields='{"F","X",0,0,0,""},{"F","X",0,0,0,""}')}, 'duplicate_field')]
        for descriptions, code in cases:
            self.post = Source().ready(descriptions)
            with self.assertRaises(comparison.ComparisonFailure) as caught: self.native.compare_catalog('baseline')
            self.assertEqual(caught.exception.code, code); self.assertIsNone(caught.exception.capture)
            self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_parse_and_postimage_failure_never_reach_field_constructor(self):
        self.post = Source().ready({2: descriptor(fields='')})
        inspect = snapshots.inspect_frozen_catalog
        def changed(*args, **kwargs):
            summary, catalog = inspect(*args, **kwargs); summary['sha256'] = 'b'*64
            return summary, catalog
        for effect, code in ((changed, 'postimage_changed'), (reader.InvalidStructure('descriptor_utf8'), 'descriptor_utf8')):
            with mock.patch.object(snapshots, 'inspect_frozen_catalog', side_effect=effect), \
                 mock.patch.object(comparison, 'field_names_ascii_fields_failure', side_effect=AssertionError('must not collect')) as collect, \
                 self.assertRaises(comparison.ComparisonFailure) as caught:
                self.native.compare_catalog('baseline')
            self.assertEqual(caught.exception.code, code); self.assertIsNone(caught.exception.capture); collect.assert_not_called()

    def test_wrong_fresh_token_rejects_before_bound_field_capture(self):
        self.post = Source().ready({2: descriptor(fields='')})
        original = self.native.enterprise
        def wrong(database, operation, *, token):
            data = original(database, operation, token=token)
            data['token'] = 'b'*32 if token != 'b'*32 else 'c'*32
            return data
        self.native.enterprise = wrong
        with self.assertRaises(OracleError) as caught: self.native.compare_catalog('baseline')
        self.assertEqual(caught.exception.kind, 'snapshot_changed')
        self.assertFalse(hasattr(caught.exception, 'capture'))
        self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_success_and_other_exact_failures_do_not_collect_fields(self):
        class OtherFailure(comparison.ComparisonFailure): pass
        cases = [(None, None), (comparison.ComparisonFailure('name_mismatch', 'duplicate_table'), 'duplicate_table'),
            (comparison.ComparisonFailure('name_mismatch', 'duplicate_field'), 'duplicate_field'),
            (OtherFailure('name_mismatch', 'field_names_differ'), 'field_names_differ')]
        self.post = Source().ready()
        for failure, code in cases:
            with mock.patch.object(comparison, 'field_names_ascii_fields_failure', side_effect=AssertionError('must not collect')) as collect:
                if failure is None:
                    result = self.native.compare_catalog('baseline'); self.assertEqual(result['reader'], projection())
                else:
                    with mock.patch.object(comparison, 'project_catalog_ascii_fields', side_effect=failure), \
                         self.assertRaises(comparison.ComparisonFailure) as caught:
                        self.native.compare_catalog('baseline')
                    self.assertEqual(caught.exception.code, code); self.assertIsNone(caught.exception.capture)
                collect.assert_not_called()


def field_capture_size_upper_bound():
    """Complete fixed skeleton + two independent maximum projection sizes.

    Each projection maximum charges all 4 containers, all 64 field strings and
    512 six-byte escaped BMP units. Empty fields cannot cost more. The binding
    uses maximal file-size decimal widths; all remaining text is fixed-width.
    This intentionally combines mutually exclusive maxima, not a sample size.
    """
    capture = field_failure().capture
    capture['origin']['bytes'] = snapshots.MAX_FILE_BYTES
    capture['postimage']['bytes'] = snapshots.MAX_FILE_BYTES
    capture['field_diagnostic'].update(native=None, reader=None)
    return len(protocol.encode(capture)) - 2*len(b'null') + 2*existing.projection_size_upper_bound()


class FieldBudgetAndUnchangedSuccessTests(unittest.TestCase):
    def test_independent_complete_capture_and_universal_report_bounds(self):
        size = field_capture_size_upper_bound()
        self.assertEqual(size, 7902)
        self.assertLess(size, comparison.MAX_CAPTURE_BYTES)
        self.assertEqual(comparison.MAX_CAPTURE_BYTES, 12288)
        self.assertEqual(existing.projection_size_upper_bound(), 3469)
        self.assertEqual(existing.whole_report_size_upper_bound(), 29949)
        self.assertLess(existing.whole_report_size_upper_bound(), protocol.MAX_REPORT_BYTES)
        self.assertEqual(protocol.MAX_REPORT_BYTES, 32768)

    def test_frozen_strict_success_functions_are_byte_identical(self):
        source = (ROOT/'scripts/native_1c_db_oracle/comparison.py').read_text(encoding='utf-8')
        hashes = {'validate_projection': '1ca447f4d2e75e2c42e02dbdace7cd1668032f318d35891c9a999949a50ec417',
            'canonical_projection': '557114f065a24141a86809aa89aad2ddaf3d428a642fe2e4411c61c325e4d9cf',
            'project_catalog': '31513c93c4cac5f0574f791b42f5bbd22e262482a8c4dc70c0a5ba8cf1b5558a'}
        found = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name in hashes:
                found[node.name] = hashlib.sha256(ast.get_source_segment(source, node).encode('utf-8')).hexdigest()
        self.assertEqual(found, hashes)

    def test_new_fixture_text_io_is_explicit_utf8(self):
        for node in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
                encoding = next((kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                self.assertIsInstance(encoding, ast.Constant); self.assertEqual(encoding.value, 'utf-8')


if __name__ == '__main__':
    unittest.main()
