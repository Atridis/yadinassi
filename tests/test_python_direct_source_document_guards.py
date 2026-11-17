"""Direct documents refuse module VM entry and retain canonical atomic writes."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import test_source_document_records as documents
import test_source_document_sections as sections
from yadinassi.configuration_source_runtime import SourceApplication,_SourceInterpreter
from yadinassi.source_document_runtime import create_object,write_object
from yadinassi.source_document_sections import SourceDocumentSectionCall
from yadinassi.source_references import SourceReferenceManager
from yadinassi.python_direct_source_storage import finish
from yadinassi.runtime import Interpreter
from yadinassi.dates import BSLDate
from yadinassi import source_transactions


class DirectDocumentGuards(unittest.TestCase):
    def app(self,source,*,section=False):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        app=SourceApplication(source,scratch_database=Path(tmp.name)/'documents.sqlite',
            source_document_sections=section,source_document_records=not section,output=lambda value:None)
        self.addCleanup(app.close);app.start()
        caller=_SourceInterpreter(app,family_owner=app.interpreter);self.addCleanup(caller.close)
        caller._logical_side='server';caller._context_stack.append('server');self.addCleanup(caller._context_stack.pop)
        return app,caller,SourceReferenceManager(app,'Document','Invoice')

    @contextmanager
    def no_vm(self,app):
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('legacy program')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')), \
             source_transactions.execution(app),app.safe_mode.execution():yield

    def test_module_initialization_executes_without_vm(self):
        for module in (b'Number="INIT";',b'Procedure OnWrite(Cancel) EndProcedure'):
            with self.subTest(module=module):
                app,caller,manager=self.app(documents.package(extra={'Documents/Invoice/Ext/ObjectModule.bsl':module}))
                with self.no_vm(app):
                    obj=finish(create_object(caller,manager,app.constant_store.document('Invoice')))
                    self.addCleanup(obj.interpreter.close)
                    if module.startswith(b'Number='):
                        self.assertEqual(obj.property_read(caller,'Number'),'INIT')
                self.assertFalse(app.constant_store.transaction_active)
                self.assertEqual(app.constant_store.read_documents('Invoice'),[])

    def test_no_module_scalar_and_section_write_uses_canonical_transaction(self):
        app,caller,manager=self.app(sections.package(),section=True)
        with self.no_vm(app):
            obj=finish(create_object(caller,manager,app.constant_store.document('Invoice')))
            obj.property_write(caller,'Number','A');obj.property_write(caller,'Date',BSLDate(0))
            row=SourceDocumentSectionCall(obj.sections['lines'],'add').invoke(caller,[])
            row.property_write(caller,'Flag',True)
            finish(write_object(caller,obj))
        self.assertEqual(app.constant_store.read_document_bundle('Invoice',obj.identity)[3]['lines'],({'flag':True},))
        self.assertEqual(obj.revision,1)
        self.assertEqual(len(app.constant_store.read_documents('Invoice')),1)
        self.assertFalse(app.constant_store.transaction_active)

    def test_no_module_writer_preserves_outer_transaction(self):
        app,caller,manager=self.app(documents.package())
        with self.no_vm(app):
            obj=finish(create_object(caller,manager,app.constant_store.document('Invoice')))
            obj.property_write(caller,'Number','A');obj.property_write(caller,'Date',BSLDate(0))
            app.constant_store.begin_transaction();finish(write_object(caller,obj))
            self.assertTrue(app.constant_store.transaction_active)
            app.constant_store.rollback_transaction()
        self.assertEqual(app.constant_store.read_documents('Invoice'),[])


if __name__=='__main__':unittest.main()
