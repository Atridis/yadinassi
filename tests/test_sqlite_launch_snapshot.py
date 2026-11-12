"""Owned SQLite launch admission only; no UI, native fixture or callback replay."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration, import_inert_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View, _json, _schema_data, _APPLICATION_ID
from yadinassi.sqlite_launch import LaunchSnapshot, LaunchFile, PLAIN_PROFILE
import yadinassi.sqlite_launch as launch
from sqlite_catalog_fixture import configuration_files

ROOT = Path(__file__).resolve().parents[1]


def files_at(relative):
    root = ROOT / relative
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


class SQLiteLaunchSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.sqlite'

    def retain(self, backend):
        self.addCleanup(backend.close)
        return backend

    def plain(self, *, files=None, variant=2, activate=True):
        files = configuration_files() if files is None else dict(files)
        key = 'Catalogs/Categories.xml'
        if variant == 3:
            section = ('<TabularSection uuid="'+str(uuid4())+'"><Properties><Name>Lines</Name></Properties><ChildObjects/></TabularSection>').encode()
            files[key] = files[key].replace(b'</ChildObjects>', section+b'</ChildObjects>')
        if variant == 4:
            files[key] = files[key].replace(b'<Autonumbering>false', b'<Autonumbering>true')
        if variant == 10:
            files[key] = files[key].replace(b'<Hierarchical>false</Hierarchical>', b'<Hierarchical>true</Hierarchical><HierarchyType>HierarchyFoldersAndItems</HierarchyType>')
        config = import_configuration(files, numbering_policy='decimal_v1' if variant == 4 else 'explicit')
        backend = self.retain(SQLiteCatalogBackend.create(self.path, config, activate=activate))
        return backend, files, config

    def granted(self, method, source):
        return self.retain(getattr(SQLiteCatalogBackend, method)(self.path, source))

    def upgrade(self, *, additive=False):
        backend, files, config = self.plain()
        backend.close()
        from yadinassi.sqlite_migration_plan import prepare, apply
        apply(self.path, prepare(self.path, maintenance=True), maintenance=True)
        if additive:
            from test_configuration_evolution import append_field
            from yadinassi.sqlite_configuration_update import prepare, apply
            files = append_field(files)
            config = import_configuration(files)
            apply(self.path, prepare(self.path, config, maintenance=True), maintenance=True)
        return self.retain(SQLiteCatalogBackend(self.path)), files, config

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(statement, parameters).fetchall()

    def replace_source(self, path, raw):
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (raw, sha256(raw).hexdigest(), path))

    def assert_route(self, backend, source, route):
        result = backend.launch_snapshot()
        self.assertIs(type(result), LaunchSnapshot)
        self.assertEqual(result.database_id, backend.database_id)
        self.assertEqual(result.configuration_generation, backend.configuration_generation)
        self.assertEqual(result.route, route)
        self.assertEqual({f.path:f.content for f in result.files}, source)
        self.assertEqual(tuple(f.path for f in result.files), tuple(sorted(source)))
        for f in result.files:
            self.assertIs(type(f), LaunchFile)
            self.assertIs(type(f.content), bytes)
            self.assertEqual(f.digest, sha256(f.content).hexdigest())
        self.assertEqual(result.source_digest, sha256(_json([(f.path,f.kind,f.digest) for f in result.files]).encode()).hexdigest())
        self.assertIsNone(backend._active)
        return result

    def assert_refused(self, backend):
        with self.assertRaises(BackendError): backend.launch_snapshot()
        self.assertIsNone(backend._active)

    def test_plain_v2_with_inert_comment_module(self):
        b, files, _ = self.plain()
        self.assertEqual(self.assert_route(b, files, 'catalog').profile, PLAIN_PROFILE)

    def test_legacy_v1_canonical_source(self):
        from yadinassi.sqlite_catalog_migration import _V1_DDL
        files = configuration_files(); config = import_configuration(files)
        with closing(sqlite3.connect(self.path)) as db, db:
            for ddl in _V1_DDL: db.execute(ddl)
            db.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
            db.execute('PRAGMA user_version=1')
            db.execute('INSERT INTO database_info VALUES(1,?,1,?,?,1,?)', (str(uuid4()), str(config.config_uuid), config.name, '[]'))
            for f in config.files: db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)', (f.path,f.kind,f.content,sha256(f.content).hexdigest()))
            for s in config.catalogs: db.execute('INSERT INTO catalog_schema VALUES(?,?,?)', (str(s.identity),s.name,_json(_schema_data(s))))
        self.assert_route(self.retain(SQLiteCatalogBackend(self.path)), files, 'catalog')

    def test_plain_v3_sections(self):
        b, files, _ = self.plain(variant=3)
        self.assertEqual(b.format_version, 3)
        self.assert_route(b, files, 'catalog')

    def test_plain_v4_numbering_policy_preserved(self):
        b, files, _ = self.plain(variant=4)
        self.assertEqual(b.format_version, 4)
        self.assert_route(b, files, 'catalog')
        self.assertEqual(b._schemas[0].numbering, 'decimal_v1')

    def test_plain_v10_catalog_only_hierarchy(self):
        b, files, _ = self.plain(variant=10)
        self.assertEqual(b.format_version, 10)
        self.assert_route(b, files, 'catalog')

    def test_plain_v11_existing_transaction_profile(self):
        b, files, _ = self.upgrade()
        self.assertEqual(b.format_version, 11)
        self.assert_route(b, files, 'catalog')

    def test_plain_v12_existing_additive_generation(self):
        b, files, _ = self.upgrade(additive=True)
        self.assertEqual((b.format_version,b.configuration_generation),(12,2))
        self.assert_route(b, files, 'catalog')

    def test_three_exact_demo_grants_use_catalog_route(self):
        files = files_at('tests/fixtures/demo_cf/source')
        for name in ('kinds','directories','products'):
            with self.subTest(profile=name):
                self.path = Path(self.temp.name) / (name+'.sqlite')
                b = self.granted('create_demo_'+name, files)
                self.assert_route(b, files, 'catalog')

    def test_catalog_forms_grant(self):
        files = files_at('examples/configuration-catalog-forms')
        self.assert_route(self.granted('create_catalog_forms', files), files, 'catalog-forms')

    def test_application_grant_does_not_execute_onstart(self):
        from test_configuration_application_profile import application_sources
        from yadinassi.configuration_runtime import ConfigurationApplication
        files = application_sources()
        b = self.granted('create_application', files)
        with mock.patch.object(ConfigurationApplication, 'start', side_effect=AssertionError('execution forbidden')):
            self.assert_route(b, files, 'application')

    def test_document_forms_grant(self):
        files = files_at('examples/configuration-document-forms')
        self.assert_route(self.granted('create_document_forms', files), files, 'documents')

    def test_business_grant(self):
        files = files_at('examples/configuration-business-application')
        self.assert_route(self.granted('create_business_application', files), files, 'business')

    def test_reference_grant(self):
        files = files_at('examples/configuration-reference-application')
        self.assert_route(self.granted('create_reference_application', files), files, 'references')

    def posting(self):
        from yadinassi.configuration_posting_application import import_posting_application, PROFILE
        files = files_at('examples/configuration-posting-application')
        config = import_posting_application(files, posting_runtime=PROFILE)
        return self.retain(SQLiteCatalogBackend.create_posting(self.path,config)), files

    def test_posting_full_original_source_not_core_projection(self):
        b, files = self.posting()
        result = self.assert_route(b, files, 'posting')
        self.assertIn('PostingApplication.xml', {f.path for f in result.files})
        self.assertTrue(any('/Forms/' in f.path for f in result.files))
        self.assertEqual(result.profile, b.posting_configuration.profile)

    def test_raw_posting_v13_has_no_ui_grant(self):
        from test_configuration_posting import source
        from yadinassi.configuration_posting import import_posting_configuration, PROFILE
        b = self.retain(SQLiteCatalogBackend.create_posting(self.path, import_posting_configuration(source(), posting_runtime=PROFILE)))
        self.assert_refused(b)

    def test_accumulation_v14_has_no_ui_grant(self):
        from test_sqlite_accumulation_profile import accumulation_source
        from yadinassi.configuration_accumulation import import_accumulation_configuration, PROFILE
        b = self.retain(SQLiteCatalogBackend.create_accumulation(self.path, import_accumulation_configuration(accumulation_source(), accumulation_runtime=PROFILE)))
        with mock.patch.object(b, 'begin_read', side_effect=AssertionError('unsupported profile must not lease')):
            self.assert_refused(b)

    def test_raw_document_storage_has_no_form_grant(self):
        from test_document_configuration_xml import document_files
        files = document_files(catalogs=False, fields=False)
        b = self.retain(SQLiteCatalogBackend.create(self.path, import_configuration(files)))
        self.assertEqual(b.format_version, 7)
        self.assert_refused(b)

    def test_unknown_and_future_profiles_denied_before_lease(self):
        b, _, _ = self.plain()
        # Exact full forms15/16 are supported; raw core profiles still have no UI grant.
        for version in (0, 8, 9, 17, 999):
            with self.subTest(version=version), mock.patch.object(b, 'format_version', version), mock.patch.object(b, 'begin_read', side_effect=AssertionError('unsupported profile must not lease')):
                self.assert_refused(b)

    def test_inactive_database_not_activated(self):
        b, _, _ = self.plain(activate=False)
        before = self.path.read_bytes()
        self.assert_refused(b)
        self.assertEqual(self.path.read_bytes(),before)

    def test_inert_v5_source_not_activated(self):
        files = files_at('tests/fixtures/demo_cf/source')
        b = self.retain(SQLiteCatalogBackend.create(self.path,import_inert_configuration(files),activate=False))
        self.assertEqual(b.format_version,5)
        self.assert_refused(b)

    def test_immutable_detached_entries_survive_backend_close(self):
        b, files, _ = self.plain(); result = b.launch_snapshot(); b.close()
        with self.assertRaises(FrozenInstanceError): result.route = 'posting'
        with self.assertRaises(FrozenInstanceError): result.files[0].content = b'changed'
        with self.assertRaises(TypeError): result.files[0] = result.files[0]
        files.clear()
        self.assertTrue(result.files)
        self.assertFalse(any(hasattr(result,name) for name in ('_connection','_backend','configuration')))

    def test_readonly_backend_has_same_snapshot(self):
        b, files, _ = self.plain(); expected = b.launch_snapshot(); b.close()
        other = self.retain(SQLiteCatalogBackend(self.path,read_only=True))
        self.assertEqual(other.launch_snapshot(), expected)

    def test_snapshot_never_writes_database(self):
        b, _, _ = self.plain(); before = self.path.read_bytes()
        b.launch_snapshot(); self.assertEqual(self.path.read_bytes(),before)

    def test_one_read_lease_no_export_or_second_connection(self):
        b, _, _ = self.plain()
        with mock.patch.object(b,'begin_read',wraps=b.begin_read) as begin, mock.patch.object(b,'_connect',wraps=b._connect) as connect, mock.patch.object(b,'export_configuration',side_effect=AssertionError('second read forbidden')):
            b.launch_snapshot()
        self.assertEqual(begin.call_count,1); self.assertEqual(connect.call_count,1)
        self.assertIsNone(b._active)

    def test_source_admission_exception_releases_same_lease(self):
        b, _, _ = self.plain()
        with mock.patch.object(launch,'_admit',side_effect=BackendError('integrity')):
            self.assert_refused(b)
        b.launch_snapshot()

    def test_source_admission_interruption_releases_same_lease(self):
        b, _, _ = self.plain()
        with mock.patch.object(launch,'_admit',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): b.launch_snapshot()
        self.assertIsNone(b._active); b.launch_snapshot()

    def test_fallible_close_never_returns_snapshot_or_discards_owner(self):
        b, _, _ = self.plain()
        with mock.patch.object(_View,'close',side_effect=RuntimeError('close unavailable')):
            with self.assertRaisesRegex(RuntimeError,'close unavailable'): b.launch_snapshot()
        self.assertIsNotNone(b._active)
        b._active.close(); self.assertIsNone(b._active)

    def test_existing_reader_is_not_borrowed(self):
        b, _, _ = self.plain()
        with closing(b.begin_read()) as reader:
            with self.assertRaisesRegex(BackendError,'busy'): b.launch_snapshot()
            self.assertIs(b._active,reader)

    def test_existing_writer_is_not_borrowed(self):
        b, _, _ = self.plain()
        with closing(b.begin_write(uuid4())) as writer:
            with self.assertRaisesRegex(BackendError,'busy'): b.launch_snapshot()
            self.assertIs(b._active,writer)

    def test_closed_backend_denied_before_lease(self):
        b, _, _ = self.plain(); b.close()
        with mock.patch.object(b,'begin_read',side_effect=AssertionError('closed')):
            with self.assertRaisesRegex(BackendError,'closed'): b.launch_snapshot()

    def test_current_transaction_owner_cannot_launch_or_borrow(self):
        from yadinassi import database_transactions as tx
        b, _, _ = self.upgrade()
        with tx.execution(b):
            tx.begin(b); owner=b._bsl_transaction
            try:
                with self.assertRaisesRegex(BackendError,'unsupported'): b.launch_snapshot()
                self.assertIs(b._bsl_transaction,owner); self.assertEqual(owner.leases,0)
            finally: tx.rollback(b)

    def test_foreign_transaction_owner_cannot_launch_or_adopt(self):
        from yadinassi import database_transactions as tx
        b, _, _ = self.upgrade()
        with tx.execution(b):
            tx.begin(b); owner=b._bsl_transaction; old=owner.owner; owner.owner=object()
            try:
                with self.assertRaisesRegex(BackendError,'unsupported'): b.launch_snapshot()
                self.assertIs(b._bsl_transaction,owner); self.assertEqual(owner.leases,0)
            finally: owner.owner=old; tx.rollback(b)

    def test_wrong_source_digest_refused_same_generation(self):
        b, _, _ = self.plain()
        self.sql("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'",('0'*64,))
        self.assert_refused(b)

    def test_source_schema_drift_with_rehashed_bytes_refused(self):
        b, files, _ = self.plain(); p='Catalogs/Categories.xml'
        self.replace_source(p,files[p].replace(b'<DescriptionLength>64',b'<DescriptionLength>63'))
        self.assert_refused(b)

    def test_new_executable_module_never_acquires_ui_authority(self):
        b, _, _ = self.plain()
        self.replace_source('Catalogs/Products/Ext/ObjectModule.bsl',b'Procedure BeforeWrite(Cancel) EndProcedure')
        self.assert_refused(b)

    def test_wrong_file_kind_refused(self):
        b, _, _ = self.plain(); self.sql("UPDATE configuration_file SET kind='module' WHERE path='Configuration.xml'")
        self.assert_refused(b)

    def test_unknown_source_path_refused(self):
        b, _, _ = self.plain(); raw=b'<unknown/>'
        self.sql('INSERT INTO configuration_file VALUES(?,?,?,?)',('Unexpected.xml','xml',raw,sha256(raw).hexdigest()))
        self.assert_refused(b)

    def test_generation_drift_refused(self):
        b, _, _ = self.plain(); self.sql('UPDATE database_info SET generation=generation+1')
        self.assert_refused(b)

    def test_database_identity_drift_refused(self):
        b, _, _ = self.plain(); self.sql('UPDATE database_info SET database_uuid=?',(str(uuid4()),))
        self.assert_refused(b)

    def test_configuration_identity_must_match_canonical_source(self):
        b, _, _ = self.plain(); self.sql('UPDATE database_info SET configuration_uuid=?',(str(uuid4()),))
        self.assert_refused(b)

    def test_configuration_name_must_match_canonical_source(self):
        b, _, _ = self.plain(); self.sql("UPDATE database_info SET name='Different'")
        self.assert_refused(b)

    def test_activation_issue_drift_refused(self):
        b, _, _ = self.plain(); self.sql('UPDATE database_info SET activation_issues=?',('["unknown"]',))
        self.assert_refused(b)

    def test_activation_flag_drift_refused(self):
        b, _, _ = self.plain(); self.sql('UPDATE database_info SET activated=0')
        self.assert_refused(b)

    def test_persisted_schema_definition_drift_refused(self):
        b, _, config = self.plain(); schema=config.catalogs[0]
        changed=replace(schema,description_length=63)
        self.sql('UPDATE catalog_schema SET definition=? WHERE identity=?',(_json(_schema_data(changed)),str(schema.identity)))
        self.assert_refused(b)

    def test_persisted_schema_name_must_match_definition(self):
        b, _, config = self.plain()
        self.sql("UPDATE catalog_schema SET name='Wrong' WHERE identity=?",(str(config.catalogs[0].identity),))
        self.assert_refused(b)

    def test_generic_form_source_comment_drift_refuses_stale_grant(self):
        files=files_at('examples/configuration-catalog-forms'); b=self.granted('create_catalog_forms',files)
        path=next(p for p in files if p.endswith('.bsl'));self.replace_source(path,files[path]+b'\n// changed\n')
        self.assert_refused(b)

    def test_posting_marker_variant_cannot_be_retargeted(self):
        b, _ = self.posting(); self.sql("UPDATE posting_profile SET profile='document-recorder-scalar-v1'")
        self.assert_refused(b)

    def test_posting_manifest_mutation_is_not_core_projection(self):
        b, files = self.posting()
        self.replace_source('PostingApplication.xml',files['PostingApplication.xml']+b'\n')
        self.assert_refused(b)

    def test_plain_current_bytes_change_launch_binding_without_historical_claim(self):
        b, files, _ = self.plain(); first=b.launch_snapshot()
        self.replace_source('Configuration.xml',files['Configuration.xml']+b'\n')
        second=b.launch_snapshot()
        self.assertEqual(first.configuration_generation,second.configuration_generation)
        self.assertNotEqual(first.source_digest,second.source_digest)

    def test_schema_order_does_not_change_identity_binding(self):
        b, files, _ = self.plain()
        with mock.patch.object(b,'_schemas',tuple(reversed(b._schemas))):
            self.assert_route(b,files,'catalog')
