"""The mixed grant does not alter durable write uncertainty or source fencing."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from business_configuration_fixture import sources
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_business_profile import import_business_configuration
from yadinassi.configuration_document import DocumentObjectSession, DocumentImage, DocumentRowImage
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.database_context import SQLiteDBContext
from yadinassi.dates import literal_date
from yadinassi.errors import BSLError
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class BusinessRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'business.sqlite'; self.files = sources()
        SQLiteCatalogBackend.create_business_application(self.path, self.files).close()
        self.context = SQLiteDBContext(self.path); self.addCleanup(self.context.close)
        schema = import_business_configuration(self.files).documents[0]
        self.session = DocumentObjectSession(self.context, schema, self.files)
        self.image = DocumentImage((('Number', ''), ('Date', literal_date('20261111000000')), ('DeletionMark', False)),
                                  (('Lines', (DocumentRowImage(None, (('Flag', True),)),)),))

    def test_lost_commit_reply_resolves_original_intent_without_replay(self):
        backend = self.context.backend; original = backend.begin_document_write
        class LostReply:
            def __init__(self, tx): self.tx = tx
            def __getattr__(self, name): return getattr(self.tx, name)
            def commit(self): self.tx.commit(); raise OSError('lost acknowledgement')
        with patch.object(backend, 'begin_document_write', side_effect=lambda op: LostReply(original(op))):
            result = self.session.save(self.image)
        self.assertEqual(result.state, 'uncertain')
        with self.assertRaises(BackendError): self.session.require_discardable()
        with patch.object(backend, 'begin_document_write') as begin:
            result = self.session.save(replace(self.image, sections=(('Lines', ()),)))
            begin.assert_not_called()
        self.assertEqual(result.state, 'saved')
        self.assertEqual(len(result.image.sections[0][1]), 1)

    def test_committed_projection_failure_refreshes_without_new_transaction(self):
        def refused_projection(result): raise ValueError('projection refused')
        first = self.session.save(self.image, validate_result=refused_projection)
        self.assertEqual((first.state, first.error), ('committed', 'refresh_required'))
        original_key = self.session.object._key
        with patch.object(self.context.backend, 'begin_document_write') as begin:
            result = self.session.save(replace(self.image, sections=(('Lines', ()),)))
            begin.assert_not_called()
        self.assertEqual(result.state, 'saved')
        self.assertEqual(result.key, original_key)
        self.assertEqual(len(result.image.sections[0][1]), 1)

    def test_mixed_form_factory_has_no_transaction_root_authority(self):
        app = ConfigurationApplication.from_database(self.context, side='server')
        self.addCleanup(lambda: app.close(force=True)); app.start()
        child = app.interpreter_factory(lambda value: None, database_context=self.context)
        self.addCleanup(child.close)
        self.assertFalse(child._transaction_activation_allowed)
        with patch.object(self.context.backend, 'begin_unit_of_work') as begin:
            with self.assertRaises(BSLError): child.execute('BeginTransaction();')
            begin.assert_not_called()
