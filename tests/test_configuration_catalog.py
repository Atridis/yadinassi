"""Detached scalar object persistence; no native FormWrite parity claims."""
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest import mock
from uuid import UUID, uuid4

from ui_catalog_fixture import repository, configuration_files
from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_object_preparation import CatalogWriteRefused
from yadinassi.catalogs import BSLCatalogObject
from yadinassi.configuration_catalog import CatalogObjectSession
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import _View
from yadinassi.ui.protocol import CatalogRef, UIError


class CatalogObjectPersistenceTests(unittest.TestCase):
    def setUp(self):
        old, self.path, unused, self.ids = repository(self)
        old.close()
        self.context = SQLiteDBContext(self.path)
        self.addCleanup(self.context.close)
        self.sources = configuration_files()
        view = self.context.backend.begin_read()
        try:
            self.schemas = {s.name: s for s in view.catalogs()}
        finally:
            view.close()
        self.session = self.new()

    def new(self, reference=None):
        return CatalogObjectSession(self.context, self.schemas['Categories'], self.sources, reference)

    def values(self, **changes):
        result = self.session.values()
        result.update(Code='20', Description='New category')
        result.update(changes)
        return result

    def test_create_and_reopen_real_record(self):
        result = self.session.save(self.values())
        self.assertEqual(result.state, 'saved')
        self.assertIsNone(result.error)
        self.assertEqual(dict(result.values)['Description'], 'New category')
        self.assertEqual(result.listing.card(result.reference).value('Description'), 'New category')
        other = self.new(result.reference)
        self.assertEqual(other.values()['Code'], '20')
        self.assertFalse(other.object.is_new())

    def test_callback_changes_are_persisted_once(self):
        calls = []
        def prepare(values):
            calls.append(dict(values)); values['Description'] = 'Prepared'; return values
        result = self.session.save(self.values(), before_write=prepare)
        self.assertEqual(len(calls), 1)
        self.assertEqual(dict(result.values)['Description'], 'Prepared')

    def test_form_refusal_preserves_no_write(self):
        with mock.patch.object(BSLCatalogObject, 'write', side_effect=AssertionError('must not write')):
            result = self.session.save(self.values(), before_write=lambda values: None)
        self.assertEqual((result.state, result.error), ('rejected', 'form_validation'))
        self.assertTrue(self.session.object.is_new())
        self.assertEqual(self.session.values()['Code'], '')

    def test_handler_error_rejects_without_write(self):
        def fail(values):
            raise ValueError('private handler detail')
        with mock.patch.object(BSLCatalogObject, 'write', side_effect=AssertionError('must not write')):
            result = self.session.save(self.values(), before_write=fail)
        self.assertEqual(result.error, 'form_validation')
        self.assertNotIn('private', repr(result))

    def test_mandatory_object_refusal_is_not_saved(self):
        with mock.patch.object(BSLCatalogObject, 'write', side_effect=CatalogWriteRefused(())):
            result = self.session.save(self.values())
        self.assertEqual((result.state, result.error), ('rejected', 'object_validation'))
        self.assertFalse(self.session.pending_commit)

    def test_committed_uncertain_reply_resolves_without_repeating_handler_or_write(self):
        commit = _View.commit
        def lose_reply(tx):
            commit(tx); raise BackendError('uncertain_commit')
        callback = mock.Mock(side_effect=lambda values: values)
        with mock.patch.object(_View, 'commit', lose_reply):
            result = self.session.save(self.values(), before_write=callback)
        self.assertEqual(result.state, 'uncertain')
        with self.assertRaises(BackendError): self.session.require_discardable()
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('no duplicate commit')):
            result = self.session.save(self.values(Code='99'), before_write=callback)
        self.assertEqual(result.state, 'saved')
        self.assertEqual(dict(result.values)['Code'], '20')
        self.assertEqual(callback.call_count, 1)

    def test_proven_absent_receipt_reuses_frozen_intent(self):
        callback = mock.Mock(side_effect=lambda values: values)
        with mock.patch.object(_View, 'commit', side_effect=BackendError('uncertain_commit')):
            self.assertEqual(self.session.save(self.values(), before_write=callback).state, 'uncertain')
        result = self.session.save(self.values(Description='Must not replace intent'), before_write=callback)
        self.assertEqual(result.state, 'saved')
        self.assertEqual(dict(result.values)['Description'], 'New category')
        self.assertEqual(callback.call_count, 1)

    def test_refresh_failure_only_retries_read_and_result_validation(self):
        callback = mock.Mock(side_effect=lambda values: values)
        validate = mock.Mock(side_effect=ValueError('oversize form'))
        result = self.session.save(self.values(), before_write=callback, validate_result=validate)
        self.assertEqual((result.state, result.error), ('committed', 'refresh_required'))
        self.assertIsNone(self.session.listing)
        with self.assertRaises(BackendError): self.session.require_discardable()
        with mock.patch.object(BSLCatalogObject, 'write', side_effect=AssertionError('no repeated write')):
            result = self.session.save(self.values(Code='99'), before_write=callback)
        self.assertEqual(result.state, 'saved')
        self.assertEqual(dict(result.values)['Code'], '20')
        self.assertEqual(callback.call_count, 1)

    def test_sibling_original_revision_rejects_lost_update(self):
        first = self.session.save(self.values())
        sibling = self.new(first.reference)
        original = sibling.values()
        self.session.save(self.values(Description='First writer'))
        result = sibling.save(original | {'Description': 'Stale writer'})
        self.assertEqual((result.state, result.error), ('rejected', 'conflict'))
        self.assertEqual(self.new(first.reference).values()['Description'], 'First writer')

    def test_rename_and_deletion_refresh_authoritative_list(self):
        first = self.session.save(self.values())
        result = self.session.save(self.values(Description='Renamed', DeletionMark=True))
        self.assertEqual(result.reference, first.reference)
        self.assertEqual(result.listing.card(first.reference).value('Description'), 'Renamed')
        self.assertIs(result.listing.card(first.reference).value('DeletionMark'), True)

    def test_exact_source_pin_fails_before_callback(self):
        callback = mock.Mock()
        changed = dict(self.sources); changed['Ext/ManagedApplicationModule.bsl'] = b'// changed'
        with mock.patch.object(self.context.backend, 'export_configuration', return_value=changed):
            result = self.session.save(self.values(), before_write=callback)
        self.assertEqual(result.error, 'schema_changed')
        callback.assert_not_called()
        self.assertEqual(self.session.save(self.values()).error, 'schema_changed')

    def test_schema_pin_and_supported_scalar_shape(self):
        with self.assertRaises(BackendError):
            CatalogObjectSession(self.context, replace(self.schemas['Categories'], description_length=63), self.sources)
        with self.assertRaises(ValueError):
            CatalogObjectSession(self.context, self.schemas['Products'], self.sources)

    def test_wrong_empty_noncanonical_and_missing_reference(self):
        for reference in (str(uuid4()), CatalogRef(self.ids['product'], str(uuid4())),
                          CatalogRef(self.ids['category'], str(UUID(int=0)))):
            with self.subTest(reference=reference), self.assertRaises(ValueError): self.new(reference)
        with self.assertRaises(UIError): CatalogRef(self.ids['category'], '{'+str(uuid4())+'}')
        with self.assertRaises(BackendError): self.new(CatalogRef(self.ids['category'], str(uuid4())))

    def test_input_shape_and_types_do_not_partially_mutate_writer(self):
        for values in ({'Code': '20'}, self.values(Extra='no'), self.values(Code=Decimal(20))):
            with self.subTest(values=values), self.assertRaises((TypeError, ValueError)):
                self.session.save(values)
        self.assertEqual(self.session.values()['Code'], '')

    def test_recursive_save_from_handler_is_refused(self):
        def recursive(values):
            self.session.save(values)
            return values
        result = self.session.save(self.values(), before_write=recursive)
        self.assertEqual(result.error, 'form_validation')
        self.assertFalse(self.session._saving)
        self.assertEqual(self.session.save(self.values()).state, 'saved')
