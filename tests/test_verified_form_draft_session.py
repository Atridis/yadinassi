"""Synthetic inert-storage consumer evidence, never GUI/native activation."""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from yadinassi import form_event_simulation as sim
from yadinassi.catalog_backend import BackendError, CatalogFormSource, ConfigurationSourceIdentity
from yadinassi.errors import BSLError
from yadinassi.form_module_analysis import FormModuleAnalysisError
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from test_form_module_analysis import SOURCE, CATALOG, FORM, DEFINITION, PATHS


CATALOG_ID = UUID(int=3)
CONFIGURATION = b'''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Configuration uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>DraftFixture</Name></Properties><ChildObjects><Catalog>Products</Catalog></ChildObjects></Configuration></MetaDataObject>'''


def sources():
    return {'Configuration.xml': CONFIGURATION,
            PATHS['catalog_path']: CATALOG, PATHS['form_path']: FORM,
            PATHS['definition_path']: DEFINITION, PATHS['module_path']: SOURCE,
            'Auxiliary.xml': b'<Unrelated/>'}


class VerifiedFormDraftSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'source.sqlite'
        self.files = sources()
        self.backend = SQLiteCatalogBackend.create_inert(self.path, self.files)
        self.addCleanup(self.backend.close)

    def make(self, **changes):
        args = dict(backend=self.backend, catalog_id=CATALOG_ID,
                    code='01', description=' original ')
        args.update(changes)
        return sim.VerifiedFormDraftSession(**args)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path, timeout=0)) as db, db:
            db.execute(sql, args)

    def change_source(self, path, raw):
        self.mutate('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                    (raw, sha256(raw).hexdigest(), path))

    def test_open_on_read_only_archive_does_not_run_or_normalize(self):
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        self.addCleanup(backend.close)
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')), \
             patch.object(backend, 'read_form_source', wraps=backend.read_form_source) as read:
            session = self.make(backend=backend, description=' x ')
        read.assert_called_once_with(CATALOG_ID)
        state = session.snapshot()
        self.assertEqual(state.revision, 0)
        self.assertEqual(dict(state.values), {'Code': '01', 'Description': ' x ', 'DeletionMark': False})
        self.assertEqual(state.values, state.baseline)
        self.assertEqual(state.messages, ())
        self.assertFalse(state.native_parity)
        self.assertFalse(session.stale)
        self.assertFalse(backend.capabilities().catalog_update)

    def test_binding_is_derived_from_verified_original_bytes(self):
        raw = b'\xef\xbb\xbf' + SOURCE.replace(b'\n', b'\r\n')
        self.change_source(PATHS['module_path'], raw)
        backend = SQLiteCatalogBackend(self.path)
        self.addCleanup(backend.close)
        record = backend.read_form_source(CATALOG_ID)
        with patch.object(sim, 'analyze_form_module', wraps=sim.analyze_form_module) as analyze:
            session = self.make(backend=backend)
            session.change_description(' abc ', revision=0)
            session.prepare_save(revision=1)
        self.assertEqual(analyze.call_count, 3)
        for call in analyze.call_args_list:
            source, binding = call.args
            self.assertEqual(source, raw)
            self.assertEqual((binding.database_id, binding.configuration_id,
                              binding.configuration_generation, binding.catalog_id, binding.form_id),
                             (backend.database_id, UUID(int=2), 1, CATALOG_ID, UUID(int=4)))
            self.assertEqual((binding.source_sha256, binding.catalog_sha256,
                              binding.form_sha256, binding.definition_sha256),
                             tuple(sha256(x).hexdigest() for x in (raw, CATALOG, FORM, DEFINITION)))
        self.assertEqual(backend.read_form_source(CATALOG_ID), record)

    def test_change_reads_twice_and_adopts_only_after_second_read(self):
        session = self.make(); before = session.snapshot()
        real_read = self.backend.read_form_source
        seen = []
        def observe(*args, **kwargs):
            seen.append(session.snapshot())
            return real_read(*args, **kwargs)
        with patch.object(self.backend, 'read_form_source', side_effect=observe) as read:
            state = session.change_description(' x ', revision=0)
        self.assertEqual(seen, [before, before])
        self.assertTrue(all(old is before for old in seen))
        self.assertEqual(read.call_count, 2)
        for call in read.call_args_list:
            self.assertEqual(call.args, (CATALOG_ID,))
            self.assertEqual(call.kwargs, {'expected': session._record.identity})
        self.assertIs(session.snapshot(), state)
        self.assertEqual(state.revision, 1)
        self.assertEqual(state.baseline, before.baseline)
        self.assertEqual(dict(state.values)['Description'], 'x')
        self.assertEqual(state.messages, (sim.FormEventMessage('At least three characters', 'Объект.Наименование'),))
        later = session.change_description(' longer ', revision=1)
        self.assertEqual(later.revision, 2)
        self.assertEqual(later.messages, ())
        self.assertEqual(dict(state.values)['Description'], 'x')

    def test_equal_events_advance_local_revision_once_not_private_setter_count(self):
        session = self.make()
        for revision in range(4):
            self.assertEqual(session.change_description(' same ', revision=revision).revision, revision + 1)
            self.assertEqual(session.prepare_save(revision=revision + 1).revision, revision + 1)

    def test_exact_backend_catalog_and_initial_scalars_precede_storage(self):
        class Backend(SQLiteCatalogBackend): pass
        class Text(str): pass
        class Identity(UUID): pass
        with patch.object(self.backend, 'read_form_source', side_effect=AssertionError('storage')):
            for change in ({'backend': object()}, {'backend': object.__new__(Backend)},
                           {'catalog_id': str(CATALOG_ID)}, {'catalog_id': UUID(int=0)},
                           {'catalog_id': Identity(int=3)}, {'code': Text('01')},
                           {'description': Text('abc')}, {'description': {}},
                           {'deletion_mark': 0}):
                with self.subTest(change=tuple(change)), self.assertRaises((TypeError, BackendError)):
                    self.make(**change)

    def test_stale_and_inexact_revision_precede_storage_and_execution(self):
        class Revision(int): pass
        class Hostile:
            def __eq__(self, other): raise AssertionError('comparison')
        session = self.make()
        before = session.change_description('first', revision=0)
        with patch.object(self.backend, 'read_form_source', side_effect=AssertionError('storage')), \
             patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for revision in (0, 2, -1, True, False, 1.0, '1', None, Revision(1), Hostile()):
                with self.subTest(kind=type(revision).__name__):
                    with self.assertRaisesRegex(ValueError, 'stale revision'):
                        session.change_description('next', revision=revision)
                    with self.assertRaisesRegex(ValueError, 'stale revision'):
                        session.prepare_save(revision=revision)
        self.assertIs(session.snapshot(), before)

    def test_inexact_event_scalars_precede_storage_and_hooks(self):
        class Text(str):
            def encode(self, *args, **kwargs): raise AssertionError('encode')
        class Hostile:
            def __str__(self): raise AssertionError('string')
        session = self.make(); before = session.snapshot()
        with patch.object(self.backend, 'read_form_source', side_effect=AssertionError('storage')):
            for value in (Text('x'), Hostile(), [], {}, None, b'abc', 1, True):
                with self.subTest(kind=type(value).__name__), self.assertRaises(TypeError):
                    session.change_description(value, revision=0)
            for cancel in (0, 1, None, 'false', [], {}):
                with self.subTest(cancel=cancel), self.assertRaises(TypeError):
                    session.prepare_save(revision=0, cancel=cancel)
        self.assertIs(session.snapshot(), before)

    def test_invalid_text_and_failed_qualifiers_never_execute_or_adopt(self):
        session = self.make(); before = session.snapshot()
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for value in ('x\x00y', 'x' * 65537, 'x' * 101 + '\ud800', 'a' * 99 + '\U0001f600'):
                with self.subTest(length=len(value)), self.assertRaises(ValueError):
                    session.change_description(value, revision=0)
                self.assertIs(session.snapshot(), before)
        self.assertEqual(dict(session.change_description('a' * 101, revision=0).values)['Description'], 'a' * 100)

    def test_wrong_catalog_has_no_fallback(self):
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(BackendError, 'not_found'):
                self.make(catalog_id=uuid4())

    def test_absent_default_and_absent_or_empty_module_never_execute(self):
        variants = []
        files = sources()
        files[PATHS['catalog_path']] = CATALOG.replace(b'Catalog.Products.Form.Item', b'')
        variants.append((files, 'not_found'))
        files = sources(); files.pop(PATHS['module_path']); variants.append((files, 'unsupported'))
        files = sources(); files[PATHS['module_path']] = b''; variants.append((files, 'unsupported'))
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for index, (files, code) in enumerate(variants):
                backend = SQLiteCatalogBackend.create_inert(Path(self.tmp.name) / f'variant{index}.sqlite', files)
                self.addCleanup(backend.close)
                with self.subTest(code=code), self.assertRaisesRegex(BackendError, code):
                    self.make(backend=backend)

    def test_exact_returned_dto_identity_and_scalar_field_types(self):
        class Record(CatalogFormSource): pass
        class Identity(ConfigurationSourceIdentity): pass
        class Text(str): pass
        class Bytes(bytes): pass
        record = self.backend.read_form_source(CATALOG_ID)
        invalid = [object(), object.__new__(Record), replace(record, identity=object()),
                   replace(record, identity=object.__new__(Identity)),
                   replace(record, identity=replace(record.identity, generation=True)),
                   replace(record, identity=replace(record.identity, manifest_sha256='A' * 64)),
                   replace(record, identity=replace(record.identity, catalog_id='3')),
                   replace(record, catalog_name=Text('Products')),
                   replace(record, configuration_xml=Bytes(CONFIGURATION)),
                   replace(record, module_source=bytearray(SOURCE)), replace(record, module_present=1)]
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for value in invalid:
                with self.subTest(kind=type(value).__name__), \
                     patch.object(self.backend, 'read_form_source', return_value=value), \
                     self.assertRaisesRegex(BackendError, 'invalid_input'):
                    self.make()

    def test_wrong_paths_default_and_owner_are_not_source_authority(self):
        record = self.backend.read_form_source(CATALOG_ID)
        invalid = [replace(record, **{name: '../wrong'}) for name in PATHS]
        invalid += [replace(record, default_object_form='Catalog.Other.Form.Item'),
                    replace(record, identity=replace(record.identity, database_id=uuid4())),
                    replace(record, identity=replace(record.identity, catalog_id=uuid4())),
                    replace(record, identity=replace(record.identity, form_id=uuid4())),
                    replace(record, catalog_xml=CATALOG.replace(b'Products', b'Other')),
                    replace(record, definition_xml=DEFINITION.replace(b'CatalogObject.Products', b'CatalogObject.Other'))]
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            for value in invalid:
                with self.subTest(value=value.catalog_path), \
                     patch.object(self.backend, 'read_form_source', return_value=value), \
                     self.assertRaises((BackendError, FormModuleAnalysisError)):
                    self.make()

    def test_matching_fresh_hashes_do_not_admit_arbitrary_original_source(self):
        raw = SOURCE.replace(' Объект.Наименование ='.encode(),
                             ' Объект.Записать();\n Объект.Наименование ='.encode(), 1)
        self.change_source(PATHS['module_path'], raw)
        backend = SQLiteCatalogBackend(self.path); self.addCleanup(backend.close)
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            with self.assertRaises(FormModuleAnalysisError): self.make(backend=backend)

    def test_generation_change_before_execution_locks_and_preserves_state(self):
        for action in ('change', 'prepare'):
            session = self.make(); before = session.change_description(' x ', revision=0)
            self.mutate('UPDATE database_info SET generation=2')
            with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
                with self.subTest(action=action), self.assertRaisesRegex(BackendError, 'schema_changed'):
                    if action == 'change': session.change_description('new', revision=1)
                    else: session.prepare_save(revision=1)
            self.assertIs(session.snapshot(), before)
            self.assertTrue(session.stale)
            self.mutate('UPDATE database_info SET generation=1')

    def test_full_manifest_drift_in_unrelated_file_invalidates_before_execution(self):
        session = self.make(); before = session.snapshot()
        self.change_source('Auxiliary.xml', b'<Unrelated changed="true"/>')
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                session.change_description('new', revision=0)
        self.assertTrue(session.stale)
        self.assertIs(session.snapshot(), before)

    def test_source_hash_corruption_returns_no_candidate_or_adoption(self):
        session = self.make(); before = session.snapshot()
        self.mutate('UPDATE configuration_file SET sha256=? WHERE path=?', ('0' * 64, PATHS['module_path']))
        with patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(BackendError, 'integrity'): session.prepare_save(revision=0)
        self.assertFalse(session.stale)
        self.assertIs(session.snapshot(), before)
        self.change_source(PATHS['module_path'], SOURCE)
        self.assertEqual(session.change_description('recovered', revision=0).revision, 1)

    def test_between_run_and_adoption_source_change_keeps_exact_old_snapshot(self):
        for action in ('change', 'prepare'):
            session = self.make(); before = session.change_description(' x ', revision=0)
            real_read = self.backend.read_form_source; reads = []
            def race(*args, **kwargs):
                reads.append(session.snapshot())
                if len(reads) == 2:
                    self.assertIs(session.snapshot(), before)
                    self.change_source(PATHS['module_path'], SOURCE + b'// changed\n')
                return real_read(*args, **kwargs)
            with patch.object(self.backend, 'read_form_source', side_effect=race), \
                 patch.object(sim, 'simulate_form_event', wraps=sim.simulate_form_event) as run:
                with self.subTest(action=action), self.assertRaisesRegex(BackendError, 'schema_changed'):
                    if action == 'change': session.change_description(' new ', revision=1)
                    else: session.prepare_save(revision=1)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(len(reads), 2)
            self.assertIs(session.snapshot(), before)
            self.assertTrue(session.stale)
            self.change_source(PATHS['module_path'], SOURCE)

    def test_generation_change_during_bsl_cannot_adopt_detached_change(self):
        session = self.make(); before = session.snapshot()
        real_vm = sim._EventInterpreter
        owner = self
        class Race(real_vm):
            def __init__(self, sink):
                super().__init__(sink)
                owner.mutate('UPDATE database_info SET generation=2')
        with patch.object(sim, '_EventInterpreter', Race):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                session.change_description(' x ', revision=0)
        self.assertIs(session.snapshot(), before)
        self.assertTrue(session.stale)

    def test_inconsistent_returned_record_cannot_hide_behind_matching_identity(self):
        for field, raw in (('module_source', SOURCE + b'// changed\n'),
                           ('configuration_xml', CONFIGURATION + b' ')):
            session = self.make(); before = session.snapshot()
            record = replace(session._record, **{field: raw})
            with patch.object(self.backend, 'read_form_source', return_value=record), \
                 patch.object(sim, '_EventInterpreter', side_effect=AssertionError('executed')):
                with self.subTest(field=field), self.assertRaisesRegex(BackendError, 'schema_changed'):
                    session.change_description('new', revision=0)
            self.assertTrue(session.stale)
            self.assertIs(session.snapshot(), before)

    def test_restoration_and_backend_reopen_do_not_reactivate_stale_consumer(self):
        session = self.make(); before = session.change_description(' x ', revision=0)
        self.mutate('UPDATE database_info SET generation=2')
        with self.assertRaises(BackendError): session.prepare_save(revision=1)
        self.mutate('UPDATE database_info SET generation=1')
        reopened = SQLiteCatalogBackend(self.path); self.addCleanup(reopened.close)
        # Trusted-host replacement cannot silently reset the sticky local lock.
        session._backend = reopened
        with patch.object(reopened, 'read_form_source', side_effect=AssertionError('storage')):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                session.change_description('new', revision=1)
            with self.assertRaisesRegex(BackendError, 'schema_changed'): session.prepare_save(revision=1)
        self.assertIs(session.snapshot(), before)
        fresh = self.make(backend=reopened)
        self.assertFalse(fresh.stale)
        self.assertEqual(fresh.change_description('new', revision=0).revision, 1)

    def test_reopened_backend_still_uses_previous_full_identity(self):
        session = self.make(); before = session.snapshot()
        self.change_source('Auxiliary.xml', b'<Unrelated changed="true"/>')
        reopened = SQLiteCatalogBackend(self.path); self.addCleanup(reopened.close)
        session._backend = reopened  # Internal fault seam, no public rebind API.
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            session.change_description('new', revision=0)
        self.assertTrue(session.stale)
        self.assertIs(session.snapshot(), before)

    def test_transient_read_failures_before_and_after_run_never_adopt(self):
        for action in ('change', 'prepare'):
            for failed_read in (1, 2):
                for code in ('busy', 'storage_error', 'closed', 'integrity', 'unsupported', 'not_found'):
                    session = self.make(); before = session.change_description(' x ', revision=0)
                    real_read = self.backend.read_form_source; reads = []
                    def fail(*args, **kwargs):
                        reads.append(session.snapshot())
                        if len(reads) == failed_read: raise BackendError(code)
                        return real_read(*args, **kwargs)
                    with self.subTest(action=action, read=failed_read, code=code), \
                         patch.object(self.backend, 'read_form_source', side_effect=fail), \
                         patch.object(sim, 'simulate_form_event', wraps=sim.simulate_form_event) as run:
                        with self.assertRaisesRegex(BackendError, code):
                            if action == 'change': session.change_description('new', revision=1)
                            else: session.prepare_save(revision=1)
                    self.assertEqual(len(reads), failed_read)
                    self.assertEqual(run.call_count, failed_read - 1)
                    self.assertIs(session.snapshot(), before)
                    self.assertFalse(session.stale)
                    self.assertEqual(session.change_description('recovered', revision=1).revision, 2)

    def test_interrupt_after_execution_has_no_live_adoption(self):
        session = self.make(); before = session.snapshot()
        with patch.object(self.backend, 'read_form_source', side_effect=[session._record, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt): session.change_description('new', revision=0)
        self.assertIs(session.snapshot(), before)
        self.assertFalse(session.stale)

    def test_execution_failure_after_private_change_does_not_retry_or_adopt(self):
        real_vm = sim._EventInterpreter; created = []; closed = []
        class Failure(real_vm):
            def __init__(self, sink):
                super().__init__(sink); created.append(self)
            def visit_ExpressionStatement(self, node):
                yield from super().visit_ExpressionStatement(node)
                raise ValueError('failure after private mutation and message')
            def close(self):
                closed.append(self); return super().close()
        for action in ('change', 'prepare'):
            session = self.make(description=' x '); before = session.snapshot()
            with patch.object(sim, '_EventInterpreter', Failure), \
                 patch.object(self.backend, 'read_form_source', wraps=self.backend.read_form_source) as read:
                with self.subTest(action=action), self.assertRaises((ValueError, BSLError)):
                    if action == 'change': session.change_description(' y ', revision=0)
                    else: session.prepare_save(revision=0)
            self.assertEqual(read.call_count, 1)
            self.assertIs(session.snapshot(), before)
            self.assertFalse(session.stale)
        self.assertEqual(len(created), 2)
        self.assertEqual(created, closed)
        self.assertEqual([vm.variables['объект'].get_member('Description') for vm in created], ['y', 'x'])

    def test_repeated_prepares_and_refusal_are_pure_informational_results(self):
        session = self.make(); before = session.change_description(' x ', revision=0)
        results = [session.prepare_save(revision=1) for _ in range(3)]
        for prepared in results:
            self.assertEqual(prepared.revision, 1)
            self.assertTrue(prepared.cancel)
            self.assertEqual(dict(prepared.candidate)['Description'], 'x')
            self.assertEqual(prepared.messages, (sim.FormEventMessage('Please enter a longer name', 'Объект.Наименование'),))
            self.assertNotEqual(prepared.messages, before.messages)
            self.assertFalse(prepared.native_parity)
            self.assertIs(session.snapshot(), before)
            for name in ('commit', 'write', 'adopt', 'token', 'identity', 'source'):
                self.assertFalse(hasattr(prepared, name))
        self.assertEqual(results[0], results[1])
        self.assertIsNot(results[0], results[1])
        self.assertEqual(dict(session.change_description('later', revision=1).values)['Description'], 'later')
        self.assertEqual(dict(results[0].candidate)['Description'], 'x')

    def test_success_cancel_and_deletion_early_return_never_adopt_preparation(self):
        for description, deleted, cancel in ((' original ', False, False), (' original ', False, True),
                                              (' x ', True, False), (' x ', True, True)):
            session = self.make(description=description, deletion_mark=deleted); before = session.snapshot()
            with patch.object(self.backend, 'read_form_source', wraps=self.backend.read_form_source) as read:
                prepared = session.prepare_save(revision=0, cancel=cancel)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(prepared.cancel, cancel)
            self.assertEqual(dict(prepared.candidate)['Description'], description if deleted else description.strip())
            self.assertEqual(prepared.messages, ())
            self.assertIs(session.snapshot(), before)

    def test_snapshot_and_preparation_are_recursively_immutable(self):
        session = self.make(); state = session.change_description(' x ', revision=0)
        prepared = session.prepare_save(revision=1)
        for obj, field in ((state, 'revision'), (state, 'baseline'), (state, 'values'),
                           (state.messages[0], 'text'), (prepared, 'candidate'),
                           (prepared, 'cancel'), (prepared.messages[0], 'field')):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError): setattr(obj, field, None)
        for values in (state.baseline, state.values, prepared.candidate):
            with self.assertRaises(TypeError): values[0] = ('Code', 'forged')
            with self.assertRaises(TypeError): values[0][1] = 'forged'
        with self.assertRaises(AttributeError): session.stale = False

    def test_closed_public_surface_never_accepts_sources_authority_or_callbacks(self):
        session = self.make(); before = session.snapshot()
        for name in ('source', 'record', 'binding', 'analysis', 'ast', 'receiver', 'sink',
                     'callback', 'handler', 'form_id', 'module_path', 'database_context'):
            with self.subTest(name=name):
                with self.assertRaises(TypeError): self.make(**{name: object()})
                with self.assertRaises(TypeError): session.change_description('x', revision=0, **{name: object()})
                with self.assertRaises(TypeError): session.prepare_save(revision=0, **{name: object()})
        for name in ('source', 'binding', 'backend', 'identity', 'commit', 'adopt', 'write',
                     'rebind', 'reload', 'discard', 'change_control', 'set_member'):
            self.assertFalse(hasattr(session, name))
        for name in ('code', 'deletion_mark', 'event', 'control', 'values'):
            with self.subTest(name=name), self.assertRaises(TypeError):
                session.change_description('x', revision=0, **{name: 'forged'})
        self.assertIs(session.snapshot(), before)

    def test_no_transaction_survives_reads_or_spans_bsl(self):
        real_connect = self.backend._connect; handles = []; instances = []
        real_vm = sim._EventInterpreter; owner = self
        def capture():
            handle = real_connect(); handles.append(handle); return handle
        class Spy(real_vm):
            def __init__(self, sink):
                for handle in handles:
                    with owner.assertRaises(sqlite3.ProgrammingError): handle.execute('SELECT 1')
                owner.assertIsNone(owner.backend._active)
                # A real independent writer commits during the BSL interval.
                owner.mutate('UPDATE database_info SET name=name')
                super().__init__(sink); instances.append(self)
        with patch.object(self.backend, '_connect', side_effect=capture), \
             patch.object(sim, '_EventInterpreter', Spy):
            session = self.make()
            session.change_description('new', revision=0)
            session.prepare_save(revision=1)
        self.assertEqual(len(handles), 5)
        self.assertEqual(len(instances), 2)
        for handle in handles:
            with self.assertRaises(sqlite3.ProgrammingError): handle.execute('SELECT 1')
        self.assertIsNone(self.backend._active)

    def test_no_activation_marshalling_module_registration_or_database_write(self):
        real_vm = sim._EventInterpreter; instances = []
        class Spy(real_vm):
            def __init__(self, sink):
                super().__init__(sink); instances.append(self)
        with patch.object(sim, '_EventInterpreter', Spy), \
             patch.object(sim.Interpreter, 'execute', side_effect=AssertionError('execute')), \
             patch.object(sim.Interpreter, 'execute_program', side_effect=AssertionError('module')), \
             patch.object(sim.Interpreter, '_new_server_activation', side_effect=AssertionError('marshalling')), \
             patch.object(self.backend, 'begin_write', side_effect=AssertionError('write')), \
             patch.object(self.backend, 'begin_read', side_effect=AssertionError('runtime read')):
            session = self.make()
            session.change_description('x', revision=0)
            for _ in range(3): session.prepare_save(revision=1)
        self.assertEqual(len(instances), 4)
        for vm in instances:
            self.assertIsNone(vm.database_context)
            self.assertEqual(vm.routines, {})
            self.assertEqual(vm.imports, {})
            self.assertEqual(vm.pending_promises, ())
        self.assertFalse(self.backend.activated)
        self.assertEqual(self.backend.storage_version, 5)
        for path, raw in self.files.items():
            with closing(sqlite3.connect(self.path)) as db:
                stored = db.execute('SELECT content FROM configuration_file WHERE path=?', (path,)).fetchone()[0]
            self.assertEqual(stored, raw)
