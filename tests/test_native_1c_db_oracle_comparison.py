"""Schema-4 synthetic mechanics, not native execution or compatibility evidence."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
sys.path.insert(0, str(ROOT / 'yadinassi/storage'))
sys.path.insert(0, str(ROOT / 'tests'))
import comparison
import filedb_catalog as reader
import inputs
import protocol
import snapshots
import test_native_1c_db_oracle_contract as historical
import test_native_1c_db_oracle_stage as fixtures
from test_filedb_catalog import Source, descriptor
from test_native_1c_db_oracle_catalog_reader import normalize_owners
from snapshots import OracleError

NONCE = fixtures.NONCE
TOKEN = 'd' * 32


def projection():
    # Arbitrary synthetic names, never predictions of the native storage values.
    return {'schema': 1, 'target': comparison.TARGET,
            'tables': [{'name': 'Physical', 'fields': ['Field']}]}


def identity():
    value = fixtures.provenance()
    value['sources'] = {source: 'c' * 64 for source in inputs.SOURCE_FILES}
    return value


def marker(token=TOKEN):
    value = historical.marker(token)
    del value['storage_shape']
    value['storage_names'] = projection()
    return value


def catalog(source=None):
    source = source or Source().ready()
    return reader.read_catalog(source.read_at, source.size)


def evidence(token=TOKEN):
    # Invoke the real reader, not a fixture-produced validation result.
    source = Source().ready()
    native, actual = comparison.project_catalog(catalog(source), projection())
    return {'marker': marker(token),
        'origin': {'nonce': NONCE, 'token': token, 'clone': 'auditor',
                   **{key: fixtures.physical('baseline')[key] for key in ('bytes', 'sha256')}},
        'postimage': {'bytes': source.size, 'sha256': hashlib.sha256(source.full_bytes()).hexdigest()},
        'reader': actual}


class ComparisonBackend(fixtures.FixtureNative):
    def compare_catalog(self, identifier):
        self.event('compare_catalog', identifier)
        return evidence()


def fixture(fail=None, cleanup=(True, True)):
    provenance = identity()
    report = comparison.empty_report(NONCE, provenance)
    backend = ComparisonBackend(provenance, fail); backend.clean = cleanup
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


class ProjectionTests(unittest.TestCase):
    def test_real_reader_exact_names_canonical_order_and_unrelated_tables_private(self):
        source = Source().ready({2: descriptor('Physical', fields='{"B","X",0,0,0,""},{"A","Q",0,0,0,""}'),
                                 3: descriptor('PRIVATE_UNRELATED')})
        expected = projection(); expected['tables'][0]['fields'] = ['B', 'A']
        native, actual = comparison.project_catalog(catalog(source), expected)
        self.assertEqual(actual, native)
        self.assertEqual(actual['tables'][0]['fields'], ['A', 'B'])
        self.assertNotIn(b'PRIVATE_UNRELATED', protocol.encode(actual))
        self.assertNotIn(b'Undocumented', protocol.encode(actual))
        self.assertTrue(source.calls)

    def test_missing_extra_duplicate_case_sensitive_and_no_normalization(self):
        cases = [({2: descriptor('Other')}, 'missing_table'),
                 ({2: descriptor('physical')}, 'missing_table'),
                 ({2: descriptor('_Physical')}, 'missing_table'),
                 ({2: descriptor('Physical'), 3: descriptor('Physical')}, 'duplicate_table'),
                 ({2: descriptor(fields='{"Field","X",0,0,0,""},{"Field","X",0,0,0,""}')}, 'duplicate_field'),
                 ({2: descriptor(fields='{"Field","X",0,0,0,""},{"Extra","X",0,0,0,""}')}, 'field_names_differ'),
                 ({2: descriptor(fields='{"field","X",0,0,0,""}')}, 'field_names_differ'),
                 ({2: descriptor(fields='{"_Field","X",0,0,0,""}')}, 'field_names_differ'),
                 ({2: descriptor(fields='{"Other","X",0,0,0,""}')}, 'field_names_differ'),
                 ({2: descriptor(fields='')}, 'field_names_differ')]
        for descriptions, code in cases:
            with self.subTest(code=code), self.assertRaises(comparison.ComparisonFailure) as caught:
                comparison.project_catalog(catalog(Source().ready(descriptions)), projection())
            self.assertEqual((caught.exception.category, caught.exception.code), ('name_mismatch', code))

    def test_missing_field_and_total_reader_fields_rejected_before_copy(self):
        expected = projection(); expected['tables'][0]['fields'].append('Missing')
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.project_catalog(catalog(), expected)
        self.assertEqual(caught.exception.code, 'field_names_differ')
        # The parser result has bounded tuples; count before copying any fields
        # from the table which would exceed the aggregate projection ceiling.
        from types import SimpleNamespace
        expected = {'schema': 1, 'target': comparison.TARGET,
                    'tables': [{'name': str(i), 'fields': ['F']} for i in range(3)]}
        parsed = SimpleNamespace(tables=tuple(SimpleNamespace(name=str(i), fields=tuple(
            SimpleNamespace(name='F'+str(j)) for j in range(32))) for i in range(3)))
        with self.assertRaises(comparison.ComparisonFailure) as caught:
            comparison.project_catalog(parsed, expected)
        self.assertEqual((caught.exception.category, caught.exception.code), ('resource_limit', 'projection_limit'))

    def test_unrelated_duplicates_are_private_not_a_new_reader_policy(self):
        source = Source().ready({2: descriptor(), 3: descriptor('Other'), 4: descriptor('Other')})
        self.assertEqual(comparison.project_catalog(catalog(source), projection()), (projection(), projection()))

    def test_each_projection_limit_rejects_without_truncation(self):
        values = []
        value = projection(); value['tables'] = [{'name': str(i), 'fields': ['F']} for i in range(5)]; values.append(value)
        value = projection(); value['tables'][0]['fields'] = ['F'+str(i) for i in range(33)]; values.append(value)
        value = projection(); value['tables'] = [{'name': str(i), 'fields': ['F'+str(j) for j in range(32)]} for i in range(3)]; values.append(value)
        value = projection(); value['tables'][0]['name'] = 'x'*65; values.append(value)
        value = projection(); value['tables'][0]['fields'] = [str(i)+'x'*63 for i in range(8)]; values.append(value)
        value = projection(); value['tables'] = []; values.append(value)
        value = projection(); value['tables'][0]['fields'] = []; values.append(value)
        for value in values:
            original = copy.deepcopy(value)
            with self.subTest(value=value), self.assertRaises(OracleError) as caught:
                comparison.validate_projection(value)
            self.assertEqual(caught.exception.kind, 'artifact_limit')
            self.assertEqual(value, original)
        with mock.patch.object(comparison, 'MAX_PROJECTION_BYTES', 10), self.assertRaises(OracleError):
            comparison.validate_projection(projection())

    def test_invalid_projection_and_unique_names_fail_closed(self):
        edits = [lambda p: p.update(schema=True), lambda p: p.update(target='Other'),
            lambda p: p.update(raw='PRIVATE'), lambda p: p['tables'][0].update(name=''),
            lambda p: p['tables'][0].update(name='x\n'),
            lambda p: p['tables'][0].update(name='x\x7f'), lambda p: p['tables'][0].update(name='x\u2028'), lambda p: p['tables'][0].update(name='\ud800'),
            lambda p: p['tables'][0].update(name='\U0001f642'),
            lambda p: p['tables'][0].update(fields=['F', 'F']),
            lambda p: p['tables'].append(copy.deepcopy(p['tables'][0])),
            lambda p: p['tables'][0].update(fields=[False]),
            lambda p: p['tables'][0].update(fields=[''])]
        for edit in edits:
            value = projection(); edit(value)
            with self.subTest(value=value), self.assertRaises(OracleError): comparison.validate_projection(value)

    def test_escaped_bmp_names_preserved_exactly(self):
        value = projection(); value['tables'][0].update(name='Таблица"\\', fields=['Поле"\\'])
        self.assertEqual(comparison.canonical_projection(value), value)

    def test_error_classes_and_codes_are_independently_allowlisted(self):
        for error_type, (category, codes) in comparison.READER_ERRORS.items():
            for code in codes:
                error = comparison.reader_failure(error_type(code))
                self.assertEqual((error.category, error.code), (category, code))
            for bad in ('SECRET /private/path', 123, None):
                with self.assertRaises(OracleError) as caught: comparison.reader_failure(error_type(bad))
                self.assertEqual(caught.exception.kind, 'unexpected_failure')
        class Forged(reader.UnsupportedLayout): pass
        for error in (Forged('page_size'), reader.CatalogError('page_size'), reader.ResourceLimit('page_size')):
            with self.assertRaises(OracleError): comparison.reader_failure(error)
        # Catalog-path raises retain the old exact class/code inventory. The two
        # private data/BLOB entry points are not reachable from read_catalog and
        # have their own exact raises; never widen either historical policy.
        tree = ast.parse((ROOT/comparison.READER_SOURCE).read_text(encoding='utf-8'))
        mapped = {kind.__name__: codes for kind, (_, codes) in comparison.READER_ERRORS.items()}
        helpers = {('InternalFile','_table_data'):{('InvalidStructure','table_data_header_role')},
            ('InternalFile','_table_blob'):{('InvalidStructure','table_blob_header_role')},
            ('CatalogReader','_open_table_blob'):{('UnsupportedLayout','missing_table_blob_header'),
                ('ValueError','table must belong to this completed catalog'),
                ('ValueError','table BLOB requires the same opened data table'),
                ('ValueError','table BLOB opening is single-use')},
            ('CatalogReader','_open_table_data'):{('UnsupportedLayout','missing_table_data_header'),
                ('ValueError','table must belong to this completed catalog'),
                ('ValueError','table data opening is single-use')}}
        helper_nodes = {}
        for owner in tree.body:
            if isinstance(owner,ast.ClassDef):
                for method in owner.body:
                    if isinstance(method,ast.FunctionDef) and (owner.name,method.name) in helpers:
                        helper_nodes[(owner.name,method.name)] = method
        self.assertEqual(set(helper_nodes),set(helpers))
        excluded = set()
        for key,method in helper_nodes.items():
            raises = [node for node in ast.walk(method) if isinstance(node,ast.Raise)]
            observed = set()
            for node in raises:
                self.assertIsInstance(node.exc,ast.Call)
                self.assertIsInstance(node.exc.func,ast.Name)
                self.assertEqual(len(node.exc.args),1)
                self.assertIsInstance(node.exc.args[0],ast.Constant)
                observed.add((node.exc.func.id,node.exc.args[0].value))
            self.assertEqual(observed,helpers[key])
            excluded.update(id(node) for node in raises)
        # No catalog method or module wrapper calls the row opener. The sole
        # lower-level factory call is inside that unreachable private opener.
        calls = [node for node in ast.walk(tree) if isinstance(node,ast.Call)
                 and isinstance(node.func,ast.Attribute)]
        for role in ('data','blob'):
            self.assertFalse([node for node in calls if node.func.attr=='_open_table_'+role])
            lower_calls = [node for node in calls if node.func.attr=='_table_'+role]
            self.assertEqual(len(lower_calls),1)
            self.assertIn(lower_calls[0],list(ast.walk(helper_nodes[('CatalogReader','_open_table_'+role)])))
        import record_observation
        for kind,code in ((reader.InvalidStructure,'table_data_header_role'),
                          (reader.UnsupportedLayout,'missing_table_data_header'),
                          (reader.InvalidStructure,'table_blob_header_role'),
                          (reader.UnsupportedLayout,'missing_table_blob_header')):
            for policy in (comparison,record_observation):
                with self.assertRaises(OracleError) as caught: policy.reader_failure(kind(code))
                self.assertEqual(caught.exception.kind,'unexpected_failure')
        for node in ast.walk(tree):
            if id(node) in excluded: continue
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and isinstance(node.exc.func, ast.Name):
                name = node.exc.func.id
                if name in mapped and isinstance(node.exc.args[0], ast.Constant):
                    self.assertIn(node.exc.args[0].value, mapped[name])


class ComparisonEnvelopeTests(unittest.TestCase):
    def check(self, report, final=False):
        return comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity(), final=final)

    def test_exact_lifecycle_counts_and_narrow_success_only(self):
        report, backend = fixture(); self.check(report)
        self.assertEqual((len(report['stages']), len(report['snapshots'])), (13, 11))
        self.assertEqual([event for event in backend.events if event[0] in ('compare_catalog', 'audit_clone')],
                         [('compare_catalog', 'baseline'), ('audit_clone', 'restored')])
        self.assertEqual(report['reader_validation'], comparison.VERDICT)
        self.assertEqual(report['native_compatibility'], 'not_claimed')
        self.assertEqual(report['schema'], 4)
        self.assertEqual(report['lane'], 'native-file-db-catalog-compare-dbms-names-true-ascii-fields-v1')
        self.assertEqual(report['comparison_policy'], 'exact_tables_ascii_fields_v1')
        self.assertEqual(report['storage_contract']['schema'], 5)
        self.assertEqual(report['projection_mode'], 'dbms_names_true')
        self.assertNotEqual(report['storage_contract']['origin']['sha256'], report['storage_contract']['postimage']['sha256'])
        self.assertFalse(report['accepted'])
        report['cleanup'].update(container_removed=True, private_staging_removed=True); report['accepted'] = True
        self.check(report, True)

    def test_historical_v2_v3_not_accepted_or_upgraded(self):
        for report in (fixtures.fixture_report()[0], historical.fixture()[0]):
            original = copy.deepcopy(report)
            with self.assertRaises(OracleError): self.check(report)
            self.assertEqual(report, original)
        self.assertEqual(len(inputs.LEGACY_V3_SOURCE_FILES), 18)
        self.assertEqual(len(inputs.SOURCE_FILES), 20)
        self.assertEqual(historical.whole_report_size_upper_bound(), 25875)

    def test_default_v4_missing_wrong_mode_and_lane_rejected_without_upgrade(self):
        # Both success and early-return failure envelopes require the new mode.
        edits = [lambda r: r.pop('projection_mode'),
                 lambda r: r.update(lane='native-file-db-catalog-compare-v4'),
                 lambda r: (r.pop('projection_mode'), r.update(lane='native-file-db-catalog-compare-v4')),
                 lambda r: r.update(lane='native-file-db-catalog-compare-dbms-names-false-v4')]
        edits += [lambda r, mode=mode: r.update(projection_mode=mode)
                  for mode in (None, False, True, 1, '', 'default', 'dbms_names_false',
                               'DBMS_NAMES_TRUE', ['dbms_names_true'], {'dbms_names_true': True})]
        for failed_stage in (None, 'preflight', 'create'):
            good, _ = fixture(failed_stage)
            for index, edit in enumerate(edits):
                report = copy.deepcopy(good); edit(report)
                original = copy.deepcopy(report)
                with self.subTest(stage=failed_stage, index=index), self.assertRaises(OracleError):
                    self.check(report)
                self.assertEqual(report, original)

    def test_capture_binding_pins_native_source_even_with_current_mode(self):
        report, _ = fixture()
        report['provenance']['sources']['scripts/native_1c_db_oracle/modules/NativeOracleServer.bsl'] = 'b'*64
        with self.assertRaises(OracleError):
            comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=report['provenance'])

    def test_only_exact_source_inventory_and_constant_provenance(self):
        for source in inputs.SOURCE_FILES:
            report, _ = fixture(); del report['provenance']['sources'][source]
            with self.assertRaises(OracleError):
                comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=report['provenance'])
        for key in ('image', 'platform', 'locale', 'timezone'):
            report, _ = fixture(); report['provenance'][key] = 'x'*1000
            with self.assertRaises(OracleError):
                comparison.validate_report(protocol.encode(report), nonce=NONCE, provenance=report['provenance'])

    def test_forged_binding_and_compatibility_claims_rejected(self):
        edits = [lambda r: r.update(schema=3), lambda r: r.update(native_compatibility='verified'),
            lambda r: r.update(reader_validation='not_run'), lambda r: r.update(storage_contract=None),
            lambda r: r['storage_contract'].update(status='shape_captured'),
            lambda r: r['storage_contract'].update(nonce='b'*32),
            lambda r: r['storage_contract'].update(token='stale'),
            lambda r: r['storage_contract'].update(source_manifest_sha256='b'*64),
            lambda r: r['storage_contract'].update(reader_source_sha256='b'*64),
            lambda r: r['storage_contract'].update(actual_version='8.3.0.0'),
            lambda r: r['storage_contract']['origin'].update(snapshot='restored'),
            lambda r: r['storage_contract']['origin'].update(clone='writer'),
            lambda r: r['storage_contract']['origin'].update(sha256='b'*64),
            lambda r: r['storage_contract']['origin'].update(bytes=True),
            lambda r: r['storage_contract']['postimage'].update(copy='baseline'),
            lambda r: r['storage_contract']['postimage'].update(binding='native_execution_time'),
            lambda r: r['storage_contract']['postimage'].update(sha256='stale'),
            lambda r: r['storage_contract']['postimage'].update(bytes=1),
            lambda r: r['storage_contract']['postimage'].update(storage_version=[8, 2, 14, 0]),
            lambda r: r['storage_contract']['postimage'].update(page_size=4096),
            lambda r: r['storage_contract']['reader']['tables'][0].update(fields=['Other']),
            lambda r: r['storage_contract'].update(raw='PRIVATE')]
        good, _ = fixture()
        for index, edit in enumerate(edits):
            report = copy.deepcopy(good); edit(report)
            with self.subTest(index=index), self.assertRaises(OracleError): self.check(report)
        with mock.patch.object(comparison, 'MAX_CAPTURE_BYTES', 100), self.assertRaises(OracleError): self.check(good)

    def test_nonce_token_and_prelaunch_origin_bound_before_capture(self):
        report, _ = fixture()
        for key, value in (('nonce', 'b'*32), ('token', 'b'*32), ('clone', 'writer'), ('sha256', 'b'*64), ('bytes', 123)):
            item = evidence(); item['origin'][key] = value
            with self.subTest(key=key), self.assertRaises(OracleError): comparison.bind_capture(item, report)

    def test_failures_never_retain_success_and_cleanup_discards(self):
        for stage in protocol.STAGES[:-1]:
            report, _ = fixture(stage); self.check(report)
            self.assertIsNone(report['storage_contract'])
            self.assertEqual(report['reader_validation'], 'not_run' if protocol.STAGES.index(stage) <= 2 else 'discarded')
        for cleanup in ((False, True), (True, False), (False, False)):
            report, _ = fixture(cleanup=cleanup); self.check(report)
            self.assertIsNone(report['storage_contract'])
            self.assertEqual(report['reader_validation'], 'discarded')
            self.assertEqual(report['failure_kind'], 'cleanup_unverified')
        good, _ = fixture(); failed, _ = fixture('create')
        failed['storage_contract'] = good['storage_contract']; failed['reader_validation'] = comparison.VERDICT
        with self.assertRaises(OracleError): self.check(failed)

    def test_only_finite_diagnostic_survives_reader_failure(self):
        for category, codes in comparison.DIAGNOSTICS.items():
            code = next(iter(codes)); provenance = identity(); report = comparison.empty_report(NONCE, provenance)
            backend = ComparisonBackend(provenance); controller = fixtures.stage.Controller(backend, report); backend.controller = controller
            backend.compare_catalog = mock.Mock(side_effect=comparison.ComparisonFailure(category, code))
            report = controller.run(); self.check(report)
            self.assertEqual(report['storage_contract'], {'schema': 1, 'status': 'failed', 'category': category, 'code': code})
            self.assertEqual(report['reader_validation'], 'failed')
            report['storage_contract']['code'] = 'PRIVATE'
            with self.assertRaises(OracleError): self.check(report)

    def test_reader_failure_kind_requires_baseline_snapshot_and_finite_diagnostic(self):
        for stage in ('preflight', 'baseline', 'create'):
            report, _ = fixture(stage)
            report.update(failure_kind='catalog_comparison_failed', reader_validation='failed')
            with self.subTest(stage=stage), self.assertRaises(OracleError): self.check(report)
        provenance = identity(); report = comparison.empty_report(NONCE, provenance)
        backend = ComparisonBackend(provenance); controller = fixtures.stage.Controller(backend, report); backend.controller = controller
        backend.compare_catalog = mock.Mock(side_effect=comparison.ComparisonFailure('name_mismatch', 'missing_table'))
        report = controller.run(); self.check(report)
        finite = copy.deepcopy(report['storage_contract'])
        comparison.discard_capture(report)
        self.assertEqual(report['storage_contract'], finite)
        self.check(report)
        report['snapshots'] = []
        with self.assertRaises(OracleError): self.check(report)

    def test_versioned_marker_schemas_are_strict_and_mutually_exclusive(self):
        current = marker(); old = historical.marker()
        protocol.marker(protocol.encode(current), nonce=NONCE, token=TOKEN, operation='audit_contract', contract_version=4)
        protocol.marker(protocol.encode(old), nonce=NONCE, token=TOKEN, operation='audit_contract', contract_version=3)
        for version, data in ((4, old), (3, current), (True, current)):
            with self.assertRaises(OracleError):
                protocol.marker(protocol.encode(data), nonce=NONCE, token=TOKEN, operation='audit_contract', contract_version=version)
        edits = [lambda d: d.update(user='NativeOracleCRUD'), lambda d: d.update(nonprivileged=False),
            lambda d: d.update(users_verified=False), lambda d: d.update(token='b'*32),
            lambda d: d.update(nonce='b'*32), lambda d: d.update(metadata_version=2),
            lambda d: d.update(storage_shape=historical.shape()), lambda d: d.update(raw='PRIVATE')]
        for edit in edits:
            data = marker(); edit(data)
            with self.assertRaises(OracleError):
                protocol.marker(protocol.encode(data), nonce=NONCE, token=TOKEN, operation='audit_contract', contract_version=4)


@unittest.skipIf(os.name == 'nt', 'POSIX pinned native harness boundary')
class AuditedPostimageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.cleanup)
        self.root = Path(self.temp.name).resolve(); self.artifacts = self.root/'artifacts'; self.artifacts.mkdir()
        normalize_owners(self)
        self.seed = self.artifacts/'seed'; self.seed.mkdir()
        self.pre = Source().ready(); (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed, self.artifacts/'baseline', quiescent=lambda: True)
        self.native = fixtures.stage.Native(NONCE, identity()); self.native.root = self.root
        self.native.artifacts = self.artifacts; self.native.stage = 'baseline'
        self.native.quiescent = lambda: True; self.native.budgets = lambda *args: None
        self.post = Source().ready({2: descriptor(), 3: descriptor('PRIVATE_UNRELATED')})
        self.calls = []
        def enterprise(database, operation, *, token):
            self.calls.append((database, operation, token))
            (database/'1Cv8.1CD').write_bytes(self.post.full_bytes())
            return marker(token)
        self.native.enterprise = enterprise

    def cleanup(self):
        for path in self.root.rglob('*'):
            if path.is_dir(): path.chmod(0o700)
        self.temp.cleanup()

    def test_real_reader_runs_on_post_audit_frozen_copy_and_both_removed(self):
        with mock.patch.object(reader, 'read_catalog', wraps=reader.read_catalog) as read:
            result = self.native.compare_catalog('baseline')
        self.assertEqual(read.call_count, 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][:2], (self.artifacts/'auditor', 'audit_contract'))
        self.assertEqual(result['origin']['sha256'], hashlib.sha256(self.pre.full_bytes()).hexdigest())
        self.assertEqual(result['postimage']['sha256'], hashlib.sha256(self.post.full_bytes()).hexdigest())
        self.assertNotEqual(result['origin']['sha256'], result['postimage']['sha256'])
        self.assertEqual(result['origin']['token'], result['marker']['token'])
        self.assertEqual(result['reader'], projection())
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())
        self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(), self.pre.full_bytes())

    def test_origin_change_rejected_before_native_launch(self):
        original = self.native.clone
        def clone(*args):
            path = original(*args); (path/'1Cv8.1CD').write_bytes(self.post.full_bytes()); return path
        self.native.clone = clone
        with self.assertRaises(comparison.ComparisonFailure) as caught: self.native.compare_catalog('baseline')
        self.assertEqual(caught.exception.code, 'origin_changed'); self.assertEqual(self.calls, [])

    def test_postimage_binding_change_rejected_and_cleanup_required(self):
        original = snapshots.inspect_frozen_catalog
        def inspect(*args, **kwargs):
            summary, parsed = original(*args, **kwargs); summary['sha256'] = 'b'*64; return summary, parsed
        with mock.patch.object(snapshots, 'inspect_frozen_catalog', side_effect=inspect), self.assertRaises(comparison.ComparisonFailure) as caught:
            self.native.compare_catalog('baseline')
        self.assertEqual(caught.exception.code, 'postimage_changed')
        original_remove = self.native.remove
        def remove(path):
            if path.name == 'auditor_frozen': raise OracleError('cleanup_unverified')
            return original_remove(path)
        self.native.remove = remove
        with self.assertRaises(OracleError) as caught: self.native.compare_catalog('baseline')
        self.assertEqual(caught.exception.kind, 'cleanup_unverified')

    def test_real_parse_failure_has_only_allowlisted_diagnostic_and_no_capture(self):
        data = bytearray(self.post.full_bytes()); data[8:12] = bytes((8, 2, 14, 0))
        self.native.enterprise = lambda database, operation, token: ((database/'1Cv8.1CD').write_bytes(data), marker(token))[1]
        with self.assertRaises(comparison.ComparisonFailure) as caught: self.native.compare_catalog('baseline')
        self.assertEqual((caught.exception.category, caught.exception.code), ('unsupported_layout', 'storage_version'))
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_exact_reader_errors_and_inspection_failures_survive_no_raw_text(self):
        cases = [(reader.UnsupportedSharing('physical_page_role_overlap'), 'unsupported_sharing_policy', 'physical_page_role_overlap'),
                 (reader.InvalidStructure('descriptor_utf8'), 'structural_rejection', 'descriptor_utf8'),
                 (reader.ResourceLimit('read_bytes'), 'resource_limit', 'read_bytes'),
                 (reader.SourceIOError('read_failed'), 'io_or_change', 'read_failed'),
                 (OracleError('snapshot_changed'), 'io_or_change', 'snapshot_changed')]
        for error, category, code in cases:
            with self.subTest(category=category), mock.patch.object(snapshots, 'inspect_frozen_catalog', side_effect=error):
                with self.assertRaises(comparison.ComparisonFailure) as caught: self.native.compare_catalog('baseline')
                self.assertEqual((caught.exception.category, caught.exception.code), (category, code))
                self.assertFalse((self.artifacts/'auditor').exists())
                self.assertFalse((self.artifacts/'auditor_frozen').exists())
        for error in (reader.UnsupportedLayout('PRIVATE'), OracleError('timeout')):
            with mock.patch.object(snapshots, 'inspect_frozen_catalog', side_effect=error), self.assertRaises(OracleError) as caught:
                self.native.compare_catalog('baseline')
            self.assertEqual(caught.exception.kind, 'timeout' if type(error) is OracleError else 'unexpected_failure')
            self.assertNotIn('PRIVATE', str(caught.exception))

    def test_reader_callback_checks_existing_work_deadline(self):
        self.native.deadline = 0
        with self.assertRaises(OracleError) as caught: self.native.compare_catalog('baseline')
        self.assertEqual(caught.exception.kind, 'timeout')
        self.assertFalse((self.artifacts/'auditor').exists())
        self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_wrong_stage_or_snapshot_never_launches(self):
        with self.assertRaises(OracleError): self.native.compare_catalog('restored')
        self.native.stage = 'verify_restore'
        with self.assertRaises(OracleError): self.native.compare_catalog('baseline')
        self.assertEqual(self.calls, [])


@unittest.skipIf(os.name == 'nt', 'POSIX pinned native harness boundary')
class FixturePortabilityTests(unittest.TestCase):
    def test_postimage_fixture_resolves_alias_and_models_native_owners(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            actual = root/'actual'; actual.mkdir()
            alias = root/'alias'; alias.symlink_to(actual, target_is_directory=True)
            real_fstat = os.fstat

            def foreign_owner(descriptor):
                info = real_fstat(descriptor)
                fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
                return SimpleNamespace(**dict(fields, st_uid=501, st_gid=20))

            case = AuditedPostimageTests('test_real_reader_runs_on_post_audit_frozen_copy_and_both_removed')
            with mock.patch.object(tempfile, 'tempdir', str(alias)), \
                    mock.patch.object(os, 'fstat', side_effect=foreign_owner):
                result = unittest.TestResult(); case.run(result)
                self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
                self.assertIn(actual, case.root.parents)
                # Fixture normalization must not relax the real ownership gate.
                with snapshots._directory(actual) as descriptor, self.assertRaises(OracleError) as caught:
                    snapshots._database_contents(descriptor)
                self.assertEqual(caught.exception.kind, 'invalid_input')


def projection_size_upper_bound():
    # Independent maxima: 4 containers, 64 fields, 512 fully escaped BMP units.
    # Nonempty/unique/individual bounds can only reduce this serialization.
    value = {'schema': 1, 'target': comparison.TARGET,
             'tables': [{'name': '', 'fields': []} for _ in range(comparison.MAX_TABLES)]}
    for index in range(comparison.MAX_TOTAL_FIELDS):
        value['tables'][index % comparison.MAX_TABLES]['fields'].append('')
    value['tables'][0]['name'] = '\uffff' * comparison.MAX_TEXT_UNITS
    return len(protocol.encode(value))


def whole_report_size_upper_bound():
    """Complete schema-4 envelope bound, including all independently maximal data.

    Combine even mutually exclusive fields. Bound the complete capture by its
    enforced 12288-byte cap, not only its two projections. All exact source paths,
    stage/check names, exact lane/mode, diagnostic enums, integer widths and
    newline are charged.
    """
    longest = lambda values: max(values, key=lambda value: len(protocol.encode(value)))
    report = comparison.empty_report(NONCE, identity())
    report.update(status='failed', failed_stage=longest(protocol.STAGES), failure_kind=longest(protocol.FAILURES),
                  reader_validation=longest(('not_run', 'failed', 'discarded', comparison.VERDICT)))
    report['provenance']['actual_version'] = protocol.VERSION
    physical = {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f'*64,
        'header': {'status': 'header_layout_match', 'version': [8, 2, 14, 0],
                   'page_size': 65536, 'page_count': (1 << 32)-1}, 'page_analysis': 'unsupported'}
    report['snapshots'] = [{'id': name, 'physical': copy.deepcopy(physical),
        'logical': protocol.expected_logical(name), 'quiescent': True, 'copy_verified': True} for name in protocol.SNAPSHOTS]
    report['artifacts'] = [{'id': name, 'source': source, 'status': 'ok',
        'physical': {'bytes': snapshots.MAX_FILE_BYTES, 'sha256': 'f'*64,
                     'header': 'unknown', 'page_analysis': 'unsupported'}} for name, source in protocol.ARTIFACTS.items()]
    counts = {key: snapshots.MAX_FILE_BYTES for key in ('changed_bytes', 'unchanged_bytes', 'added_bytes', 'removed_bytes', 'changed_windows')}
    counts['size_delta'] = -snapshots.MAX_FILE_BYTES
    samples = [snapshots.MAX_FILE_BYTES]*snapshots.MAX_SAMPLES
    for name, (source, control, treatment) in protocol.COMPARISONS.items():
        pair = {'predecessor_bytes': snapshots.MAX_FILE_BYTES, 'treatment_bytes': snapshots.MAX_FILE_BYTES, 'treatment': counts.copy()}
        windows = {'window_bytes': snapshots.WINDOW_BYTES, 'count': snapshots.MAX_FILE_BYTES}
        if control is None:
            pair['interpretation'] = 'observational_before_after_not_causation'
            windows.update(changed_count=snapshots.MAX_FILE_BYTES, changed_sample=samples.copy())
        else:
            pair.update(control_bytes=snapshots.MAX_FILE_BYTES, control=counts.copy(), interpretation='physical_byte_differences_not_causation')
            for category in ('overlap', 'control_only', 'treatment_only'):
                windows[category+'_count'] = snapshots.MAX_FILE_BYTES
                windows[category+'_sample'] = samples.copy()
        pair['byte_windows'] = windows
        report['comparisons'].append({'id': name, 'kind': 'observational' if control is None else 'matched_control',
            'source': source, 'control': control, 'treatment': treatment, 'physical': pair})
    report['rejected_basename'] = '1Cv8'+'X'*48
    report['failure_context'] = {'operation': longest(protocol.COMMAND_STAGES), 'site': longest(protocol.CONTEXT_SITES),
        'bsl_phase': longest(protocol.BSL_PHASES), 'region': longest(protocol.INVENTORY_REGIONS),
        'reason': longest(protocol.INVENTORY_REASONS), 'entry_class': longest(snapshots.ENTRY_CLASSES),
        'entry_shape': longest(snapshots.ENTRY_SHAPES)}
    # All fixed/variable capture keys, success/failure statuses and finite codes
    # fit inside this enforced enclosing bound, including both projections.
    assert report['storage_contract'] is None
    return len(protocol.encode(report)) - len(b'null') + comparison.MAX_CAPTURE_BYTES + 1


class WholeReportBudgetTests(unittest.TestCase):
    def test_projection_independent_maxima_and_whole_envelope(self):
        self.assertEqual(projection_size_upper_bound(), 3469)
        self.assertLessEqual(projection_size_upper_bound(), comparison.MAX_PROJECTION_BYTES)
        self.assertEqual(len(inputs.SOURCE_FILES), 20)
        self.assertIn(comparison.READER_SOURCE, inputs.SOURCE_FILES)
        self.assertIn('scripts/native_1c_db_oracle/comparison.py', inputs.SOURCE_FILES)
        self.assertLess(whole_report_size_upper_bound(), protocol.MAX_REPORT_BYTES)
        self.assertEqual(protocol.MAX_REPORT_BYTES, 32768)
        # Pin exact computed maximum once, preventing unnoticed enum/source growth.
        self.assertEqual(whole_report_size_upper_bound(), 29949)

    def test_failure_capture_also_within_enclosing_cap(self):
        for category, codes in comparison.DIAGNOSTICS.items():
            for code in codes:
                value = {'schema': 1, 'status': 'failed', 'category': category, 'code': code}
                self.assertLessEqual(len(protocol.encode(value)), comparison.MAX_CAPTURE_BYTES)

    def test_new_fixture_text_io_uses_explicit_utf8(self):
        for path in (Path(__file__), ROOT/'tests/test_native_1c_db_oracle_contract.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
                    encoding = next((kw.value for kw in node.keywords if kw.arg == 'encoding'), None)
                    self.assertIsInstance(encoding, ast.Constant)
                    self.assertEqual(encoding.value, 'utf-8')


class NativeProjectionSourceTests(unittest.TestCase):
    def source(self):
        value = (ROOT/'scripts/native_1c_db_oracle/modules/NativeOracleServer.bsl').read_text(encoding='utf-8')
        return value[value.index('// Exact filtered name projection.'):value.index('Функция NativeНовыйРезультат')]

    def test_measured_three_columns_and_one_explicit_true_filtered_experiment(self):
        value = self.source()
        self.assertEqual(value.count('ПолучитьСтруктуруХраненияБазыДанных('), 1)
        self.assertIn('ПолучитьСтруктуруХраненияБазыДанных(Отбор, Истина)', value)
        self.assertNotIn('ПолучитьСтруктуруХраненияБазыДанных(Отбор)', value)
        self.assertEqual(value.count('Отбор.Добавить('), 1)
        self.assertIn('Отбор.Добавить("Справочник.NativeOracleItems")', value)
        for name in ('ИмяТаблицыХранения', 'Поля', 'ИмяПоляХранения'): self.assertIn(name, value)
        self.assertNotRegex(value, r'(?<![\w])Строка\(')
        for forbidden in ('Метаданные.', 'Назначение', 'ТипПоля', 'Индексы', 'ИмяТаблицы"',
                          'ОписаниеОшибки', 'Выполнить(', '_Reference', '_Fld', 'НРег(', 'ВРег('):
            self.assertNotIn(forbidden, value)
        self.assertEqual(protocol.COMMAND_STAGES['enterprise_audit_contract'], ('baseline',))
        self.assertIn('Колонка.ТипЗначения.Типы().Количество() <> 1', value)
        self.assertIn('Колонка.ТипЗначения.СодержитТип(ОжидаемыйТип)', value)

    def test_current_production_host_and_runtime_explicitly_select_v4(self):
        source = (ROOT/'scripts/native_1c_db_oracle/run.py').read_text(encoding='utf-8')
        host = (ROOT/'scripts/native_1c_db_oracle.py').read_text(encoding='utf-8')
        self.assertIn('report=comparison.empty_report(nonce,provenance)', source)
        self.assertIn('contract_version=comparison.SCHEMA', source)
        self.assertIn('from comparison import empty_report, validate_report, discard_capture', host)
        self.assertNotIn('inspect_catalog(', source)
        self.assertNotIn('from yadinassi', source)

    def test_exact_staged_reader_imports_without_interpreter_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary).resolve()/'inputs'
            provenance = identity(); provenance['sources'] = inputs.source_hashes(ROOT)
            try:
                inputs.stage_inputs(ROOT, staged, NONCE, provenance)
                code = ("import sys; sys.path.insert(0, sys.argv[1]); import run, comparison, filedb_catalog; "
                        "assert 'yadinassi' not in sys.modules; "
                        "assert run.filedb_catalog is comparison.reader is filedb_catalog; "
                        "assert comparison.SCHEMA == 4; "
                        "assert comparison.PROJECTION_MODE == 'dbms_names_true'; "
                        "sys.stdout.buffer.write(b'standalone\\n')")
                result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(staged)],
                                        capture_output=True, timeout=30, check=False)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
                self.assertEqual(result.stdout, b'standalone\n')
                self.assertEqual(inputs.staged_hashes(staged), provenance['sources'])
            finally:
                for path in (staged, *staged.rglob('*')):
                    path.chmod(0o700 if path.is_dir() else 0o600)

    def run_probe(self, setup, *, fields_declared=True, reject_call=False):
        from yadinassi import Interpreter
        from yadinassi.native_targets import LINUX_8_3_27_1508
        from test_native_async_error_transport import encode as transport_encode
        vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
        vm.execute(setup); calls = []
        # Test-only input metadata: the interpreter intentionally supports only
        # scalar TypeDescription construction. Model the observed native column
        # declaration without changing the runtime or the production BSL helper.
        from yadinassi.values import BSLType
        if fields_declared:
            column = vm.execute('ТестоваяТаблица').columns.find('Поля')
            object.__setattr__(column.value_type, 'types', (BSLType.VALUE_TABLE,))
        table = vm.execute('ТестоваяТаблица')
        def get_structure(selector, dbms_names):
            calls.append((selector, dbms_names))
            if reject_call: raise ValueError('synthetic API rejection')
            return table
        vm.register_function('ПолучитьСтруктуруХраненияБазыДанных', get_structure)
        vm.execute(self.source()+'\nКонтекст = Новый Структура("phase", "dispatch");')
        result = None
        try: vm.execute('Проекция = NativeИменаХранения(Контекст);')
        except BaseException: pass
        else: result = json.loads(transport_encode(vm.execute('Проекция')))
        # Assert outside the caught native failure so a wrong mode cannot hide
        # behind a negative projection test. This double proves call mechanics,
        # not the real platform's argument semantics or returned names.
        self.assertEqual(len(calls), 1)
        selector, dbms_names = calls[0]
        self.assertEqual(list(selector), [comparison.TARGET])
        self.assertIs(dbms_names, True)
        return vm, result

    SETUP = '''
        ТестоваяТаблица = Новый ТаблицаЗначений;
        ТестоваяТаблица.Колонки.Добавить("ИмяТаблицыХранения", Новый ОписаниеТипов("Строка"));
        ТестоваяТаблица.Колонки.Добавить("Поля");
        ТестоваяТаблица.Колонки.Добавить("Метаданные", Новый ОписаниеТипов("Строка"));
        СтрокаТеста = ТестоваяТаблица.Добавить();
        СтрокаТеста.ИмяТаблицыХранения = "Physical";
        СтрокаТеста.Метаданные = "PRIVATE SCALAR";
        Вложенная = Новый ТаблицаЗначений;
        Вложенная.Колонки.Добавить("ИмяПоляХранения", Новый ОписаниеТипов("Строка"));
        Вложенная.Колонки.Добавить("ТипПоля", Новый ОписаниеТипов("Строка"));
        ПолеТеста = Вложенная.Добавить();
        ПолеТеста.ИмяПоляХранения = "Field";
        ПолеТеста.ТипПоля = "PRIVATE TYPE";
        СтрокаТеста.Поля = Вложенная;
    '''

    def test_actual_current_helper_returns_only_complete_names(self):
        _, value = self.run_probe(self.SETUP)
        self.assertEqual(value, projection())
        comparison.validate_projection(value)
        self.assertNotIn(b'PRIVATE', protocol.encode(value))

    def test_explicit_true_call_rejection_is_not_retried_or_fallen_back(self):
        vm, result = self.run_probe(self.SETUP, reject_call=True)
        self.assertIsNone(result)
        self.assertEqual(vm.execute('Контекст.phase'), 'contract_call')

    def test_actual_current_helper_rejects_missing_wrong_declared_and_runtime_types(self):
        cases = [self.SETUP+'ТестоваяТаблица.Колонки.Найти("ИмяТаблицыХранения").Имя = "Missing";',
                 self.SETUP.replace('"ИмяПоляХранения", Новый ОписаниеТипов("Строка")', '"ИмяПоляХранения"'),
                 self.SETUP+'СтрокаТеста.Поля = Неопределено;',
                 self.SETUP+'ПолеТеста.ИмяПоляХранения = "";',
                 self.SETUP+'Вложенная.Очистить();',
                 self.SETUP+'ТестоваяТаблица.Очистить();',
                 self.SETUP+'ПолеТеста.ИмяПоляХранения = Символ(10);',
                 self.SETUP+'Вложенная.Добавить().ИмяПоляХранения = "Field";',
                 self.SETUP+'Дубль = ТестоваяТаблица.Добавить(); Дубль.ИмяТаблицыХранения = "Physical"; Дубль.Поля = Вложенная;']
        for setup in cases:
            with self.subTest(setup=setup):
                _, result = self.run_probe(setup)
                self.assertIsNone(result)
        _, result = self.run_probe(self.SETUP, fields_declared=False)
        self.assertIsNone(result)

    def test_native_caps_match_python_and_executed_limits_fail_closed(self):
        for snippet in ('ЧислоТаблиц <= 4', 'ЧислоПолей <= 32', 'Бюджет.fields + ЧислоПолей <= 64',
                        'Длина <= 64', 'Бюджет.units + Длина <= 512'):
            self.assertIn(snippet, self.source())
        cases = [self.SETUP+'ПолеТеста.ИмяПоляХранения = "'+'x'*65+'";',
                 self.SETUP+'''Для Н = 1 По 4 Цикл
                     Новая = ТестоваяТаблица.Добавить(); Новая.ИмяТаблицыХранения = "T" + Строка(Н); Новая.Поля = Вложенная;
                     КонецЦикла;''',
                 self.SETUP+'''Для Н = 1 По 32 Цикл Вложенная.Добавить().ИмяПоляХранения = "F" + Строка(Н); КонецЦикла;''',
                 self.SETUP+'''Для Н = 1 По 16 Цикл Вложенная.Добавить().ИмяПоляХранения = "F" + Строка(Н); КонецЦикла;
                     Для Н = 1 По 3 Цикл Новая = ТестоваяТаблица.Добавить();
                     Новая.ИмяТаблицыХранения = "T" + Строка(Н); Новая.Поля = Вложенная; КонецЦикла;''',
                 self.SETUP+'''Для Н = 1 По 8 Цикл Вложенная.Добавить().ИмяПоляХранения = "'''+('x'*63)+'''" + Строка(Н); КонецЦикла;''']
        for setup in cases:
            with self.subTest(setup=setup):
                vm, result = self.run_probe(setup)
                self.assertIsNone(result)
                self.assertEqual(vm.execute('Контекст.phase'), 'contract_limit')


if __name__ == '__main__': unittest.main()
