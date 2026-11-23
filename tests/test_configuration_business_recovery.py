"""The mixed grant does not alter durable write uncertainty or source fencing."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from business_configuration_fixture import sources
from test_catalog_commit_cleanup_recovery import FaultConnection
from yadinassi.db.document.document_backend import DocumentSelection
from yadinassi.configuration.configuration_business_profile import import_business_configuration
from yadinassi.configuration.configuration_document import DocumentObjectSession, DocumentImage, DocumentRowImage
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.temporal.dates import literal_date
from yadinassi.types.errors import BSLError
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend


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

    def test_lost_commit_reply_keeps_editor_uncertain_until_explicit_reopen(self):
        backend = self.context.backend; original = backend.begin_document_write
        def lost_reply(operation):
            view = original(operation)
            view._view._connection = FaultConnection(view._view._connection, commit_fault='after')
            return view
        with patch.object(backend, 'begin_document_write', side_effect=lost_reply):
            result = self.session.save(self.image)
        self.assertEqual((result.state, result.error), ('uncertain', 'uncertain_commit'))
        self.session.require_discardable()
        with patch.object(backend, 'begin_document_write') as begin:
            result = self.session.save(replace(self.image, sections=(('Lines', ()),)))
            begin.assert_not_called()
        self.assertEqual((result.state, result.error), ('uncertain', 'uncertain_commit'))
        schema = self.session.schema
        with closing(backend.begin_document_read()) as view:
            cards = view.select_documents(schema.identity, DocumentSelection())
        self.assertEqual(len(cards), 1)
        fresh = DocumentObjectSession(self.context, schema, self.files, key=cards[0].key)
        rows = fresh.image().sections[0][1]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].values, (('Flag', True),))

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
