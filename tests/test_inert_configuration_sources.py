"""Closed source archives and exact original demo admission; no native 1C run."""
from contextlib import closing
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi.catalog_backend import BackendError, CatalogSchema
from yadinassi.configuration_xml import INERT_SOURCE_ISSUE, import_configuration, import_inert_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _json, _schema_data
from yadinassi.sqlite_catalog_migration import prepare_v1

CONFIG = UUID('10000000-0000-0000-0000-000000000001')
CATALOG = UUID('10000000-0000-0000-0000-000000000002')
FORM = UUID('10000000-0000-0000-0000-000000000003')
CPATH = 'Catalogs/Items.xml'
FPATH = 'Catalogs/Items/Forms/Card.xml'
DPATH = 'Catalogs/Items/Forms/Card/Ext/Form.xml'
MPATH = 'Catalogs/Items/Forms/Card/Ext/Form/Module.bsl'


def envelope(kind, identity, properties, children=''):
    return ('\ufeff<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20">\r\n'
            f'<{kind} uuid="{identity}"><Properties>{properties}</Properties>'
            f'<ChildObjects>{children}</ChildObjects></{kind}>\r\n</MetaDataObject>\r\n').encode()


def sources():
    return {
        'Configuration.xml': envelope('Configuration', CONFIG, '<Name>SourceArchive</Name>', '<Catalog>Items</Catalog>'),
        CPATH: envelope('Catalog', CATALOG, '<Name>Items</Name><Hierarchical>false</Hierarchical>'
                       '<CodeType>String</CodeType><CodeLength>8</CodeLength><DescriptionLength>64</DescriptionLength>'
                       '<CheckUnique>true</CheckUnique><Autonumbering>true</Autonumbering>'
                       '<DefaultObjectForm>Catalog.Items.Form.Card</DefaultObjectForm>', '<Form>Card</Form>'),
        FPATH: envelope('Form', FORM, '<Name>Card</Name><FormType>Managed</FormType>'),
        DPATH: b'\xef\xbb\xbf<Form xmlns="http://v8.1c.ru/8.3/xcf/logform">\r\n<ChildItems/>\r\n</Form>\r\n',
        MPATH: '\ufeff&AtClient\r\nProcedure NeverExecute()\r\n    Raise "opaque source";\r\nEndProcedure\r\n'.encode(),
    }


class InertSourceImportTests(unittest.TestCase):
    def test_identity_only_stubs_and_exact_opaque_source(self):
        files = sources()
        value = import_inert_configuration(files)
        self.assertEqual(value.catalogs, (CatalogSchema(CATALOG, 'Items', 0, 0),))
        self.assertEqual(value.modules, ())
        self.assertEqual(value.activation_issues, (INERT_SOURCE_ISSUE,))
        self.assertEqual({f.path: f.content for f in value.files}, files)

    def test_ordinary_import_does_not_admit_autonumber_or_forms(self):
        with self.assertRaises(ValueError):
            import_configuration(sources())
        files = sources()
        files[CPATH] = files[CPATH].replace(b'<Autonumbering>true', b'<Autonumbering>false')
        try:
            value = import_configuration(files)
        except ValueError:
            return
        self.assertTrue(value.activation_issues)

    def test_unsafe_paths_case_collisions_and_extensions(self):
        for path in ('../x.xml', '/x.xml', 'a//x.xml', 'a/./x.xml', 'a\\x.xml',
                     'C:x.xml', 'x\x00.xml', 'x\n.xml', 'x.cf', 'configuration.xml', 'x'*253+'.xml'):
            files = sources(); files[path] = b'<x/>'
            with self.subTest(path=path), self.assertRaises(ValueError):
                import_inert_configuration(files)

    def test_exact_input_types_and_utf8(self):
        for raw in ('<x/>', bytearray(b'<x/>'), b'\xff'):
            files = sources(); files['Extra.xml'] = raw
            with self.subTest(raw=repr(raw)), self.assertRaises(ValueError):
                import_inert_configuration(files)
        files = sources(); files[1] = b'<x/>'
        with self.assertRaises(ValueError): import_inert_configuration(files)

    def test_source_bounds(self):
        files = sources(); files['Extra.bsl'] = b' ' * (1024*1024+1)
        with self.assertRaises(ValueError): import_inert_configuration(files)
        files = sources(); files.update({f'Extra{i}.bsl': b'' for i in range(2048)})
        with self.assertRaises(ValueError): import_inert_configuration(files)
        files = sources(); files.update({f'Extra{i}.bsl': b' ' * (1024*1024) for i in range(17)})
        with self.assertRaises(ValueError): import_inert_configuration(files)

    def test_xml_dtd_pi_depth_and_malformed_refused_even_auxiliary(self):
        for raw in (b'<!DOCTYPE x [<!ENTITY e "x">]><x/>', b'<?unsafe instruction?><x/>',
                    b'<x>'*33+b'</x>'*33, b'<x>'):
            files = sources(); files['Extra.xml'] = raw
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError): import_inert_configuration(files)

    def test_required_owner_form_and_definition_paths(self):
        for path in ('Configuration.xml', CPATH, FPATH, DPATH):
            files = sources(); files['Unrelated/'+path] = files.pop(path)
            with self.subTest(path=path), self.assertRaises(ValueError): import_inert_configuration(files)

    def test_names_defaults_and_definition_namespace_must_match(self):
        for path, old, new in (
            (CPATH, b'<Name>Items</Name>', b'<Name>Other</Name>'),
            (FPATH, b'<Name>Card</Name>', b'<Name>Other</Name>'),
            (CPATH, b'Catalog.Items.Form.Card', b'Catalog.Other.Form.Card'),
            (CPATH, b'Catalog.Items.Form.Card', b'Catalog.Items.Form.Missing'),
            (FPATH, b'<FormType>Managed', b'<FormType>Ordinary'),
            (DPATH, b'http://v8.1c.ru/8.3/xcf/logform', b'urn:wrong')):
            files = sources(); files[path] = files[path].replace(old, new)
            with self.subTest(path=path, new=new), self.assertRaises(ValueError): import_inert_configuration(files)

    def test_duplicate_ids_properties_and_declarations(self):
        for path, old, new in (
            (CPATH, str(CATALOG).encode(), str(CONFIG).encode()),
            (FPATH, str(FORM).encode(), str(CATALOG).encode()),
            (CPATH, b'<Name>Items</Name>', b'<Name>Items</Name><Name>Items</Name>'),
            (FPATH, b'<Name>Card</Name>', b'<Name>Card</Name><Name>Card</Name>'),
            (CPATH, b'<Form>Card</Form>', b'<Form>Card</Form><Form>card</Form>'),
            ('Configuration.xml', b'<Catalog>Items</Catalog>', b'<Catalog>Items</Catalog><Catalog>items</Catalog>'),
            (CPATH, b'<Form>Card</Form>', f'<Form>Card</Form><Attribute uuid="{FORM}"/>'.encode())):
            files = sources(); files[path] = files[path].replace(old, new)
            with self.subTest(new=new), self.assertRaises(ValueError): import_inert_configuration(files)


class InertSourceStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'archive.sqlite'
        self.files = sources()
        self.backend = SQLiteCatalogBackend.create_inert(self.path, self.files)
        self.addCleanup(self.backend.close)

    def mutate(self, sql, args=()):
        # sqlite Connection.__exit__ commits but does not close: always closing.
        with closing(sqlite3.connect(self.path, timeout=0)) as db, db:
            db.execute(sql, args)

    def change_source(self, path, content):
        self.mutate('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                    (content, hashlib.sha256(content).hexdigest(), path))

    def test_v5_reopen_is_permanently_inactive_and_runtime_refuses(self):
        self.backend.close()
        backend = SQLiteCatalogBackend(self.path)
        self.addCleanup(backend.close)
        self.assertEqual(backend.storage_version, 5)
        self.assertFalse(backend.activated)
        caps = backend.capabilities()
        for name in ('catalog_read', 'catalog_create', 'catalog_update', 'atomic_transactions', 'catalog_tabular_sections'):
            self.assertIs(getattr(caps, name), False)
        with self.assertRaises(BackendError): backend.begin_read()
        with self.assertRaises(BackendError): backend.begin_write(uuid4())
        context = SQLiteDBContext(self.path)
        self.addCleanup(context.close)
        from yadinassi import Interpreter
        with self.assertRaises(BackendError): Interpreter(database_context=context)
        with self.assertRaises(BackendError): prepare_v1(self.path, maintenance=True)

    def test_cannot_activate_or_forge_identity_stubs_at_creation(self):
        value = import_inert_configuration(self.files)
        with self.assertRaises(BackendError): SQLiteCatalogBackend.create(Path(self.tmp.name)/'active.sqlite', value)
        for forged in (replace(value, catalogs=(replace(value.catalogs[0], code_length=8),)),
                       replace(value, activation_issues=(INERT_SOURCE_ISSUE, 'extra')),
                       replace(value, name='Other')):
            with self.subTest(forged=forged.name), self.assertRaises(BackendError):
                SQLiteCatalogBackend.create(Path(self.tmp.name)/'forged.sqlite', forged, activate=False)

    def test_exact_bytes_paths_identity_and_detached_repeated_reads(self):
        result = self.backend.read_form_source(CATALOG)
        self.assertEqual((result.identity.configuration_id, result.identity.catalog_id, result.identity.form_id), (CONFIG, CATALOG, FORM))
        self.assertEqual(result.identity.database_id, self.backend.database_id)
        self.assertEqual(result.identity.generation, 1)
        self.assertEqual(len(result.identity.manifest_sha256), 64)
        for attr, path in (('configuration_xml', 'Configuration.xml'), ('catalog_xml', CPATH),
                           ('form_xml', FPATH), ('definition_xml', DPATH), ('module_source', MPATH)):
            self.assertEqual(getattr(result, attr), self.files[path])
        self.assertEqual((result.catalog_path, result.form_path, result.definition_path, result.module_path), (CPATH, FPATH, DPATH, MPATH))
        self.assertTrue(result.module_present)
        self.assertEqual(self.backend.read_form_source(CATALOG, expected=result.identity), result)
        self.assertIsNone(self.backend._active)

    def test_absent_and_empty_module_are_distinguished(self):
        for present in (False, True):
            files = sources(); files.pop(MPATH)
            if present: files[MPATH] = b''
            backend = SQLiteCatalogBackend.create_inert(Path(self.tmp.name)/f'module-{present}.sqlite', files)
            try:
                value = backend.read_form_source(CATALOG)
                self.assertEqual(value.module_source, b'')
                self.assertIs(value.module_present, present)
            finally: backend.close()

    def test_no_default_never_falls_back_to_only_form(self):
        files = sources(); files[CPATH] = files[CPATH].replace(b'Catalog.Items.Form.Card', b'')
        backend = SQLiteCatalogBackend.create_inert(Path(self.tmp.name)/'no-default.sqlite', files)
        try:
            with self.assertRaisesRegex(BackendError, 'not_found'): backend.read_form_source(CATALOG)
        finally: backend.close()
        with self.assertRaisesRegex(BackendError, 'not_found'): self.backend.read_form_source(uuid4())

    def test_expected_identity_validates_every_component(self):
        identity = self.backend.read_form_source(CATALOG).identity
        for name in ('database_id', 'configuration_id', 'catalog_id', 'form_id'):
            with self.subTest(name=name), self.assertRaisesRegex(BackendError, 'schema_changed'):
                self.backend.read_form_source(CATALOG, expected=replace(identity, **{name: uuid4()}))
        for changes in ({'generation': 2}, {'manifest_sha256': '0'*64}):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                self.backend.read_form_source(CATALOG, expected=replace(identity, **changes))
        for changes in ({'generation': True}, {'generation': 0}, {'generation': 2**63},
                        {'manifest_sha256': 'A'*64}, {'manifest_sha256': 'g'*64}, {'database_id': str(uuid4())}):
            with self.assertRaisesRegex(BackendError, 'invalid_input'):
                self.backend.read_form_source(CATALOG, expected=replace(identity, **changes))
        with self.assertRaisesRegex(BackendError, 'invalid_input'): self.backend.read_form_source(CATALOG, expected=object())

    def test_whole_manifest_includes_unselected_auxiliary_source(self):
        old = self.backend.read_form_source(CATALOG).identity
        self.mutate('INSERT INTO configuration_file VALUES(?,?,?,?)', ('Extra.bsl', 'module', b'// inert', hashlib.sha256(b'// inert').hexdigest()))
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.backend.read_form_source(CATALOG)
        reopened = SQLiteCatalogBackend(self.path)
        try:
            self.assertNotEqual(reopened.read_form_source(CATALOG).identity.manifest_sha256, old.manifest_sha256)
            with self.assertRaisesRegex(BackendError, 'schema_changed'): reopened.read_form_source(CATALOG, expected=old)
        finally: reopened.close()

    def test_changed_module_with_updated_sha_still_invalidates_open_identity(self):
        self.change_source(MPATH, self.files[MPATH]+b'// changed\r\n')
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.backend.read_form_source(CATALOG)

    def test_sha_kind_content_type_and_byte_bound_tampering(self):
        mutations = (
            ('UPDATE configuration_file SET sha256=? WHERE path=?', ('0'*64, MPATH)),
            ('UPDATE configuration_file SET kind=? WHERE path=?', ('xml', MPATH)),
            ('UPDATE configuration_file SET kind=? WHERE path=?', ('unknown', MPATH)),
            ('UPDATE configuration_file SET content=? WHERE path=?', ('not a blob', MPATH)),
            ('UPDATE configuration_file SET content=? WHERE path=?', (b' '*1048577, MPATH)),
            ('UPDATE configuration_file SET path=? WHERE path=?', ('../escape.bsl', MPATH)),
        )
        for sql, args in mutations:
            with self.subTest(sql=sql, value=str(args[0])[:30]):
                self.mutate(sql, args)
                with self.assertRaises(BackendError): self.backend.read_form_source(CATALOG)
                self.mutate('DELETE FROM configuration_file WHERE path IN (?,?)', (MPATH, '../escape.bsl'))
                self.mutate('INSERT INTO configuration_file VALUES(?,?,?,?)', (MPATH, 'module', self.files[MPATH], hashlib.sha256(self.files[MPATH]).hexdigest()))

    def test_activation_issue_and_version_flips_refused_live_and_reopen(self):
        for sql, undo in (
            ('UPDATE database_info SET activated=1', 'UPDATE database_info SET activated=0'),
            ("UPDATE database_info SET activation_issues='[]'", 'UPDATE database_info SET activation_issues=?'),
            ('PRAGMA user_version=2', 'PRAGMA user_version=5'),
        ):
            with self.subTest(sql=sql):
                self.mutate(sql)
                with self.assertRaises(BackendError): self.backend.read_form_source(CATALOG)
                with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)
                self.mutate(undo, (_json([INERT_SOURCE_ISSUE]),) if '?' in undo else ())

    def test_stub_definition_tampering_is_not_runtime_metadata(self):
        self.mutate('UPDATE catalog_schema SET definition=?', (_json(_schema_data(CatalogSchema(CATALOG, 'Items', 8, 0))),))
        with self.assertRaises(BackendError): self.backend.read_form_source(CATALOG)
        with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)

    def test_configuration_identity_and_generation_tampering(self):
        for column, value, original in (('configuration_uuid', str(uuid4()), str(CONFIG)),
                                        ('generation', 2, 1), ('database_uuid', str(uuid4()), str(self.backend.database_id))):
            with self.subTest(column=column):
                self.mutate(f'UPDATE database_info SET {column}=?', (value,))
                with self.assertRaises(BackendError): self.backend.read_form_source(CATALOG)
                self.mutate(f'UPDATE database_info SET {column}=?', (original,))

    def test_snapshot_blocks_interleaved_writer_commit(self):
        original = self.backend._inert_source_snapshot
        attempts = []
        def interleave(connection, **kwargs):
            snapshot = original(connection, **kwargs)
            with closing(sqlite3.connect(self.path, isolation_level=None, timeout=0)) as writer:
                try:
                    writer.execute('BEGIN IMMEDIATE')
                    writer.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                                   (b'// later', hashlib.sha256(b'// later').hexdigest(), MPATH))
                    with self.assertRaises(sqlite3.OperationalError): writer.execute('COMMIT')
                    attempts.append(True)
                finally:
                    if writer.in_transaction: writer.execute('ROLLBACK')
            return snapshot
        with patch.object(self.backend, '_inert_source_snapshot', side_effect=interleave):
            self.assertEqual(self.backend.read_form_source(CATALOG).module_source, self.files[MPATH])
        self.assertEqual(attempts, [True])
        self.assertEqual(self.backend.read_form_source(CATALOG).module_source, self.files[MPATH])

    def test_connection_closes_on_success_lookup_failure_and_interrupt(self):
        connect = self.backend._connect
        handles = []
        def capture():
            handle = connect(); handles.append(handle); return handle
        with patch.object(self.backend, '_connect', side_effect=capture):
            self.backend.read_form_source(CATALOG)
            with self.assertRaises(BackendError): self.backend.read_form_source(uuid4())
            with patch.object(self.backend, '_inert_source_snapshot', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt): self.backend.read_form_source(CATALOG)
        self.assertEqual(len(handles), 3)
        for handle in handles:
            with self.assertRaises(sqlite3.ProgrammingError): handle.execute('SELECT 1')
        self.assertIsNone(self.backend._active)
        # A subsequent independent write proves no read transaction remains.
        self.mutate('UPDATE database_info SET name=name')

    def test_closed_backend_refuses_source_read(self):
        self.backend.close()
        with self.assertRaisesRegex(BackendError, 'closed'): self.backend.read_form_source(CATALOG)

    def test_version_discriminator_denies_runtime_even_if_python_flag_changes(self):
        self.backend.activated = True
        try:
            caps = self.backend.capabilities()
            self.assertFalse(caps.catalog_read)
            self.assertFalse(caps.catalog_create)
            self.assertFalse(caps.catalog_update)
            self.assertFalse(caps.atomic_transactions)
            with self.assertRaisesRegex(BackendError, 'unsupported'): self.backend.begin_read()
            with self.assertRaisesRegex(BackendError, 'unsupported'): self.backend.begin_write(uuid4())
            with self.assertRaisesRegex(BackendError, 'unsupported'): self.backend.committed_operation(uuid4())
            with self.assertRaisesRegex(BackendError, 'unsupported'): self.backend.resolve_write(uuid4(), None)
        finally: self.backend.activated = False

    def test_ordinary_database_never_falls_back_to_source_reader(self):
        files = {p: self.files[p] for p in ('Configuration.xml', CPATH)}
        files[CPATH] = files[CPATH].replace(b'<Autonumbering>true', b'<Autonumbering>false')
        files[CPATH] = files[CPATH].replace(b'<Form>Card</Form>', b'')
        files[CPATH] = files[CPATH].replace(b'<DefaultObjectForm>Catalog.Items.Form.Card</DefaultObjectForm>', b'')
        backend = SQLiteCatalogBackend.create(Path(self.tmp.name)/'ordinary.sqlite', import_configuration(files))
        try:
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.read_form_source(CATALOG)
        finally: backend.close()

    def test_read_only_archive_returns_same_bytes_without_write_capabilities(self):
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        try:
            self.assertEqual(backend.read_form_source(CATALOG), self.backend.read_form_source(CATALOG))
            self.assertFalse(backend.capabilities().catalog_read)
            with self.assertRaisesRegex(BackendError, 'unsupported'): backend.begin_write(uuid4())
        finally: backend.close()

    def test_storage_registry_drift_invalidates_live_source_read(self):
        self.mutate('UPDATE catalog_storage_map SET physical_name=? WHERE catalog_id=?',
                    ('catalog_changed', str(CATALOG)))
        with self.assertRaises(BackendError) as error:
            self.backend.read_form_source(CATALOG)
        self.assertIn(error.exception.code, ('schema_changed', 'integrity'))


class DemoKindsSourceImportTests(unittest.TestCase):
    """Original source admission evidence only, never native 1C parity."""
    CATALOG = 'Catalogs/ВидыНоменклатуры.xml'
    MODULE = 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form/Module.bsl'

    def source(self):
        from legacy_demo_fixture import legacy_demo_files
        return legacy_demo_files()

    def test_original_full_source_retained_with_only_numbered_kinds(self):
        from yadinassi.configuration_xml import DEMO_KINDS_PROFILE, DEMO_KINDS_SOURCE_ISSUE, import_demo_kinds_configuration
        files = self.source()
        imported = import_demo_kinds_configuration(files)
        self.assertEqual(DEMO_KINDS_PROFILE, 'demo_kinds_v1')
        self.assertEqual(imported.catalogs, (CatalogSchema(
            UUID('a4bf60fb-591d-5927-ba65-a2ae8af699fa'), 'ВидыНоменклатуры',
            9, 100, numbering='decimal_v1'),))
        self.assertEqual(imported.activation_issues, (DEMO_KINDS_SOURCE_ISSUE,))
        self.assertEqual(imported.modules, ())
        self.assertEqual(len(imported.files), 19)
        self.assertEqual({f.path: f.content for f in imported.files}, files)
        self.assertEqual(sum(f.kind == 'module' for f in imported.files), 4)
        for f in imported.files:
            self.assertIs(f.content, files[f.path])

    def test_original_all_catalog_and_form_identity_inventory_retained(self):
        from yadinassi.configuration_xml import _demo_kinds_configuration, _inert_configuration
        files = self.source()
        imported, inventory = _demo_kinds_configuration(files)
        inert, expected = _inert_configuration(files)
        self.assertEqual(inventory, expected)
        self.assertEqual({c.name for c in inventory}, {'ВидыНоменклатуры', 'Номенклатура', 'Склады'})
        self.assertEqual(sum(len(c.forms) for c in inventory), 3)
        self.assertEqual(imported.config_uuid, inert.config_uuid)
        self.assertEqual(imported.name, inert.name)
        kinds = next(c for c in inventory if c.name == 'ВидыНоменклатуры')
        self.assertEqual(kinds.identity, imported.catalogs[0].identity)
        self.assertEqual(kinds.forms[0].identity, UUID('437eff36-576b-5d96-80e4-06117a7874e2'))
        self.assertEqual(kinds.default_object_form, 'Catalog.ВидыНоменклатуры.Form.ФормаЭлемента')

    def test_admission_uses_original_immutable_snapshot_and_stable_order(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        files = self.source()
        snapshot = dict(files)
        imported = import_demo_kinds_configuration(files)
        self.assertEqual(imported, import_demo_kinds_configuration(dict(reversed(tuple(files.items())))))
        self.assertEqual(files, snapshot)
        files[self.MODULE] = b'changed after admission'
        self.assertEqual({f.path: f.content for f in imported.files}, snapshot)

    def test_every_source_is_hash_bound_even_harmless_whitespace(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        original = self.source()
        for path in original:
            files = dict(original); files[path] += b'\n'
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'demo_kinds_v1 source mismatch'):
                import_demo_kinds_configuration(files)

    def test_recognized_catalog_settings_are_not_projection_admission(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        for old, new in ((b'<CodeLength>9', b'<CodeLength>8'),
                         (b'<DescriptionLength>100', b'<DescriptionLength>64'),
                         (b'<Hierarchical>false', b'<Hierarchical>true'),
                         (b'<Autonumbering>true', b'<Autonumbering>false'),
                         (b'<CheckUnique>true', b'<CheckUnique>false'),
                         (b'<CodeAllowedLength>Variable', b'<CodeAllowedLength>Fixed'),
                         (b'<DataHistory>DontUse', b'<DataHistory>Use'),
                         (b'<FullTextSearch>Use', b'<FullTextSearch>DontUse'),
                         (b'<PredefinedDataUpdate>Auto', b'<PredefinedDataUpdate>DontAutoUpdate'),
                         (b'<DataLockControlMode>Managed', b'<DataLockControlMode>Automatic')):
            files = self.source()
            self.assertIn(old, files[self.CATALOG])
            files[self.CATALOG] = files[self.CATALOG].replace(old, new)
            with self.subTest(setting=old), self.assertRaisesRegex(ValueError, 'demo_kinds_v1 source mismatch'):
                import_demo_kinds_configuration(files)

    def test_original_and_inert_module_changes_are_rejected(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        original = self.source()
        for path in (p for p in original if p.endswith('.bsl')):
            files = dict(original); files[path] += b'\n// harmless additional comment\n'
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'demo_kinds_v1 source mismatch'):
                import_demo_kinds_configuration(files)
        files = self.source()
        old = 'Название вида должно'.encode()
        self.assertIn(old, files[self.MODULE])
        files[self.MODULE] = files[self.MODULE].replace(old, 'Имя вида должно'.encode())
        with self.assertRaisesRegex(ValueError, 'demo_kinds_v1 source mismatch'):
            import_demo_kinds_configuration(files)

    def test_every_missing_file_fails_closed_including_inert_sources(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        original = self.source()
        for path in original:
            files = dict(original); del files[path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                import_demo_kinds_configuration(files)

    def test_extra_files_and_path_aliases_fail_closed(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        for path, raw in (('Extra.xml', b'<x/>'), ('Ext/SessionModule.bsl', b''),
                          ('Catalogs/ВидыНоменклатуры/Ext/ObjectModule.bsl', b''),
                          ('Catalogs/Склады/Ext/ObjectModule.bsl', b''),
                          ('configuration.xml', b'<x/>'), ('../Extra.xml', b'<x/>')):
            files = self.source(); files[path] = raw
            with self.subTest(path=path), self.assertRaises(ValueError):
                import_demo_kinds_configuration(files)
        files = self.source(); files['Other/'+self.MODULE] = files.pop(self.MODULE)
        with self.assertRaises(ValueError): import_demo_kinds_configuration(files)

    def test_exact_bytes_do_not_normalize_bom_or_line_endings(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        original = self.source()
        for raw in (b'\xef\xbb\xbf'+original[self.MODULE], original[self.MODULE].replace(b'\n', b'\r\n')):
            files = dict(original); files[self.MODULE] = raw
            with self.subTest(raw=raw[:20]), self.assertRaisesRegex(ValueError, 'demo_kinds_v1 source mismatch'):
                import_demo_kinds_configuration(files)

    def test_original_form_analyzer_runs_and_its_rejection_is_not_ignored(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        from yadinassi import form_module_analysis as analysis
        files = self.source()
        with patch.object(analysis, 'analyze_form_module', wraps=analysis.analyze_form_module) as analyze:
            import_demo_kinds_configuration(files)
        analyze.assert_called_once()
        args, kwargs = analyze.call_args
        self.assertEqual(args[0], files[self.MODULE])
        self.assertEqual(args[1].catalog_name, 'ВидыНоменклатуры')
        self.assertEqual(kwargs['catalog_xml'], files[self.CATALOG])
        self.assertEqual(kwargs['module_path'], self.MODULE)
        with patch.object(analysis, 'analyze_form_module', side_effect=analysis.FormModuleAnalysisError('refused')):
            with self.assertRaises(analysis.FormModuleAnalysisError):
                import_demo_kinds_configuration(files)

    def test_generic_import_and_activation_remain_closed(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        files = self.source()
        for policy in ('explicit', 'decimal_v1'):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                import_configuration(files, numbering_policy=policy)
        imported = import_demo_kinds_configuration(files)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'not-v6.sqlite'
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                SQLiteCatalogBackend.create(target, imported)
            self.assertFalse(target.exists())

    def test_exact_input_types_and_source_budgets_remain_enforced(self):
        from yadinassi.configuration_xml import import_demo_kinds_configuration
        for raw in (None, '', bytearray(b''), b'\xff', b' '*(1024*1024+1)):
            files = self.source(); files[self.MODULE] = raw
            with self.subTest(kind=type(raw)), self.assertRaises(ValueError):
                import_demo_kinds_configuration(files)
        for files in (None, (), [], {}):
            with self.subTest(kind=type(files)), self.assertRaises(ValueError):
                import_demo_kinds_configuration(files)
