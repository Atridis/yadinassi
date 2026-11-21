"""One UI source boundary before execution and one before detached adoption."""
import unittest
from unittest.mock import patch
import sqlite3
from contextlib import closing
import test_imported_kind_editor as fixture
from yadinassi.forms.form_event_simulation import FormDraftSession
from yadinassi.db.catalog.catalog_backend import BackendError

class ScalarEditorSourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ImportedKindEditorTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_description_checks_twice_without_standalone_source_reads(self):
        f=self.f;b=f.context.backend
        with patch.object(b,'read_catalog_editor_source',wraps=b.read_catalog_editor_source) as checked,patch.object(b,'read_form_source',side_effect=AssertionError('nested source read')):
            f.change('  Valid name  ')
        self.assertEqual(checked.call_count,2)
        self.assertEqual(f.editor.snapshot()['fields'][1]['inputText'],'Valid name')
    def test_source_drift_after_handler_does_not_adopt_result(self):
        f=self.f;f.change('Original name');before=f.editor.snapshot()['fields']
        original=FormDraftSession.change_description
        def drift(session,*args,**kw):
            result=original(session,*args,**kw)
            with closing(sqlite3.connect(f.path)) as db,db:
                db.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'",(b'<changed/>',))
            return result
        with patch.object(FormDraftSession,'change_description',drift),patch.object(f.editor.object,'write',side_effect=AssertionError('write')):
            with self.assertRaises(BackendError):f.change('Replacement name')
        self.assertEqual(f.editor.snapshot()['fields'],before)
        self.assertTrue(f.editor.snapshot()['sourceStale'])
    def test_backend_drift_after_prepare_never_writes(self):
        f=self.f;f.change('Original name');before=f.editor.snapshot()['fields']
        original=FormDraftSession.prepare_save;backend=f.editor.manager._backend
        def drift(session,*args,**kw):
            result=original(session,*args,**kw)
            f.context._backend=object()
            return result
        try:
            with patch.object(FormDraftSession,'prepare_save',drift),patch.object(f.editor.object,'write',side_effect=AssertionError('write')):
                f.editor.command('SaveButton')
        finally:f.context._backend=backend
        self.assertEqual(f.editor.snapshot()['fields'],before)
        self.assertTrue(f.editor.snapshot()['sourceStale'])
        self.assertEqual(f.editor.save_state,'rejected')
