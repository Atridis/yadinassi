"""Existing nonposting document lifecycle contracts with legacy dispatch poisoned."""
import unittest
import test_source_document_object_modules as lifecycle
import test_source_document_module_guards as guards


class NoVM:
    def setUp(self):
        super().setUp()


class DirectDocumentLifecycleNoVM(NoVM,lifecycle.SourceDocumentModuleTests):
    def test_bare_captured_write_and_metadata(self):
        _,out=self.run_body('Procedure Save() Export F=Write; F(); Message(Metadata().Name); EndProcedure',
            lifecycle.CREATE+'D.Save(); Message(D.Ref.Number);')
        self.assertEqual(out,['Invoice','A'])

    def test_posted_stays_readonly_and_write_rolls_back(self):
        app,out=self.run_body('Procedure OnWrite(Cancel) Posted=True; EndProcedure',
            lifecycle.CREATE+'Try D.Write(); Except Message("readonly"); EndTry; Message(D.Posted);')
        self.assertEqual(out,['readonly','Нет'])
        self.assertEqual(app.constant_store.read_documents('Invoice'),[])

    def test_read_revokes_saved_section_rows_with_module(self):
        _,out=self.run_body('Procedure Reload() Export Read(); EndProcedure',
            lifecycle.CREATE+'R=D.Lines.Add(); R.Flag=True; D.Write(); D.Reload(); '
            'Try Message(R.Flag); Except Message("stale"); EndTry; Message(D.Lines.Count());',True)
        self.assertEqual(out,['stale','1'])


class DirectDocumentGuardsNoVM(NoVM,guards.SourceDocumentModuleGuardTests):
    pass


if __name__=='__main__':unittest.main()
