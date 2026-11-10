"""Host document form persistence uses real owned SQLite, not posting emulation."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_document import DocumentObjectSession, DocumentImage, DocumentRowImage
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.dates import literal_date
from test_document_configuration_xml import document_files


class ConfigurationDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.files = document_files(catalogs=False, fields=False)
        config = import_configuration(self.files)
        self.schema = config.documents[0]
        self.path = Path(self.temp.name) / 'documents.sqlite'
        self.context = SQLiteDBContext.create(self.path, config); self.addCleanup(self.context.close)
        self.owned = DocumentObjectSession(self.context, self.schema, self.files)

    def image(self, *, number='', flags=(True, False)):
        old = self.owned.image()
        values = (('Number', number), ('Date', literal_date('20261110000000')), ('DeletionMark', False))
        return DocumentImage(values, (('Lines', tuple(DocumentRowImage(None, (('Flag', flag),)) for flag in flags)),))

    def test_create_whole_document_and_reopen(self):
        result = self.owned.save(self.image())
        self.assertEqual(result.state, 'saved')
        self.assertEqual(dict(result.image.values)['Number'], '000000001')
        self.assertEqual(len(result.listing), 1)
        self.context.close(); self.context = SQLiteDBContext(self.path); self.addCleanup(self.context.close)
        opened = DocumentObjectSession(self.context, self.schema, self.files, result.key)
        self.assertEqual(opened.image(), result.image)
        self.assertFalse(opened.object.get_member('Posted'))

    def test_reorder_delete_and_add_preserve_retained_row_identity(self):
        first = self.owned.save(self.image())
        rows = first.image.sections[0][1]
        changed = replace(first.image, sections=(('Lines', (rows[1], DocumentRowImage(None, (('Flag', True),)))),))
        saved = self.owned.save(changed)
        self.assertEqual(saved.state, 'saved')
        actual = saved.image.sections[0][1]
        self.assertEqual(actual[0].identity, rows[1].identity)
        self.assertNotEqual(actual[1].identity, rows[0].identity)
        self.assertEqual([dict(row.values)['Flag'] for row in actual], [False, True])

    def test_foreign_or_duplicate_row_identity_refused_before_write(self):
        image = self.owned.save(self.image()).image
        rows = image.sections[0][1]
        for invalid in [(rows[0], rows[0]), (replace(rows[0], identity=uuid4()),)]:
            with self.subTest(invalid=invalid):
                with patch.object(self.context.backend, 'begin_document_write') as begin:
                    with self.assertRaises(ValueError): self.owned.save(replace(image, sections=(('Lines', invalid),)))
                    begin.assert_not_called()

    def test_stale_editor_cannot_overwrite_new_revision(self):
        first = self.owned.save(self.image())
        other = DocumentObjectSession(self.context, self.schema, self.files, first.key)
        changed = replace(first.image, values=tuple((k, True if k=='DeletionMark' else v) for k,v in first.image.values))
        self.assertEqual(other.save(changed).state, 'saved')
        refused = self.owned.save(first.image)
        self.assertEqual(refused.state, 'rejected')
        self.assertFalse(self.owned.pending_commit)
        current = DocumentObjectSession(self.context, self.schema, self.files, first.key)
        self.assertTrue(dict(current.image().values)['DeletionMark'])

    def test_confirmed_write_refresh_failure_never_replays_write(self):
        def invalid(result): raise ValueError('bounded projection refused')
        result = self.owned.save(self.image(), validate_result=invalid)
        self.assertEqual((result.state, result.error), ('committed', 'refresh_required'))
        with self.assertRaises(BackendError): self.owned.require_discardable()
        with patch.object(self.context.backend, 'begin_document_write') as begin:
            result = self.owned.save(self.image(number='changed', flags=()))
            begin.assert_not_called()
        self.assertEqual(result.state, 'saved')
        self.assertEqual(dict(result.image.values)['Number'], '000000001')
        self.assertEqual(len(result.image.sections[0][1]), 2)

    def test_uncertain_commit_resolves_original_header_and_lines(self):
        backend = self.context.backend
        original = backend.begin_document_write
        class LostReply:
            def __init__(self, tx): self.tx = tx
            def __getattr__(self, name): return getattr(self.tx, name)
            def commit(self): self.tx.commit(); raise OSError('lost acknowledgement')
        with patch.object(backend, 'begin_document_write', side_effect=lambda op: LostReply(original(op))):
            uncertain = self.owned.save(self.image())
        self.assertEqual(uncertain.state, 'uncertain')
        with self.assertRaises(BackendError): self.owned.require_discardable()
        with patch.object(backend, 'begin_document_write') as begin:
            result = self.owned.save(self.image(number='wrong', flags=()))
            begin.assert_not_called()
        self.assertEqual(result.state, 'saved')
        self.assertEqual(dict(result.image.values)['Number'], '000000001')
        self.assertEqual(len(result.image.sections[0][1]), 2)

    def test_source_mismatch_does_not_activate_document_editor(self):
        changed = dict(self.files); changed['Configuration.xml'] += b'\n'
        with self.assertRaises(BackendError): DocumentObjectSession(self.context, self.schema, changed)

    def test_reference_fields_and_posting_are_not_silently_enabled(self):
        schema = import_configuration(document_files()).documents[0]
        with self.assertRaises(ValueError): DocumentObjectSession(self.context, schema, self.files)
        with self.assertRaises(ValueError): self.owned.object.set_member('Posted', True)
        with self.assertRaises(TypeError): self.owned.object.write('Posting')
