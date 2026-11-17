"""Direct storage keeps canonical transactions and refuses unconnected handlers."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_source_constant_store import configuration
from test_source_catalog_object_modules import source as catalog_source
from yadinassi.configuration_source_runtime import SourceApplication, _SourceInterpreter
from yadinassi.runtime import Interpreter
from yadinassi.source_constants_runtime import SourceConstants, ConstantCall
from yadinassi.source_constant_managers import create_manager, write_values
from yadinassi.source_references import SourceReferenceManager
from yadinassi.source_catalog_runtime import create_object
from yadinassi import source_transactions


def finish(operation):
    try:
        next(operation)
    except StopIteration as result:
        return result.value
    finally:
        operation.close()
    raise AssertionError('unexpected suspension')


class DirectSourceStorageGuards(unittest.TestCase):
    def app(self,source,*,catalog=False):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        app=SourceApplication(source,scratch_database=Path(temporary.name)/'source.sqlite',
            source_catalog_records=catalog,output=lambda value:None)
        self.addCleanup(app.close);app.start()
        caller=_SourceInterpreter(app,family_owner=app.interpreter)
        caller._logical_side='server';self.addCleanup(caller.close)
        caller._context_stack.append('server');self.addCleanup(caller._context_stack.pop)
        return app,caller

    @contextmanager
    def no_vm(self,app):
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('legacy program')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')), \
             source_transactions.execution(app),app.safe_mode.execution():
            yield

    def test_constant_module_executes_generated_initializer_and_handler_without_vm(self):
        source=configuration({'Constants/Text/Ext/ValueManagerModule.bsl':b'Value="initializer"; Procedure BeforeWrite(Cancel) Value="handler";EndProcedure'})
        app,caller=self.app(source);owner=SourceConstants(app)
        with self.no_vm(app):
            manager=finish(create_manager(caller,owner,'Text'))
            self.addCleanup(manager.interpreter.close)
            self.assertEqual(manager.value_read(caller),'initializer')
            finish(ConstantCall(owner,'Text',True).descriptor().invoke(caller,['submitted']))
            self.assertEqual(app.constant_store.get('Text'),'handler')
        self.assertFalse(app.constant_store.transaction_active)

    def test_catalog_module_refused_before_object_interpreter_construction(self):
        app,caller=self.app(catalog_source('Description="initializer";'),catalog=True)
        manager=SourceReferenceManager(app,'Catalog','Items')
        with self.no_vm(app),patch('yadinassi.source_catalog_runtime._ObjectInterpreter',side_effect=AssertionError('VM construction')):
            with self.assertRaisesRegex(ValueError,'direct source catalog handlers'):
                finish(create_object(caller,manager,app.constant_store.catalog('Items')))
        self.assertEqual(app.constant_store.read_records('Items'),[])
        self.assertFalse(app.constant_store.transaction_active)

    def test_no_module_write_uses_canonical_descriptor_transaction_pipeline(self):
        app,caller=self.app(configuration());owner=SourceConstants(app)
        descriptor=ConstantCall(owner,'Text',True).descriptor()
        with self.no_vm(app):
            descriptor.prepare(caller,1)
            finish(descriptor.invoke(caller,['saved']))
        self.assertEqual(app.constant_store.get('Text'),'saved')
        self.assertFalse(app.constant_store.transaction_active)

    def test_no_module_writer_preserves_callers_outer_transaction(self):
        app,caller=self.app(configuration());owner=SourceConstants(app)
        with self.no_vm(app):
            finish(ConstantCall(owner,'Text',True).descriptor().invoke(caller,['before']))
            app.constant_store.begin_transaction()
            finish(ConstantCall(owner,'Text',True).descriptor().invoke(caller,['temporary']))
            self.assertTrue(app.constant_store.transaction_active)
            app.constant_store.rollback_transaction()
        self.assertEqual(app.constant_store.get('Text'),'before')

    def test_late_handler_in_batch_rolls_back_without_prior_member_writes(self):
        app,caller=self.app(configuration({'Constants/Text/Ext/ValueManagerModule.bsl':b'Procedure FillCheckProcessing(Cancel,Fields) EndProcedure'}))
        owner=SourceConstants(app)
        with self.no_vm(app):
            finish(ConstantCall(owner,'Flag',True).descriptor().invoke(caller,[False]))
            with self.assertRaisesRegex(ValueError,'FillCheckProcessing'):
                finish(write_values(caller,owner,{'Flag':True,'Text':'blocked'}))
        self.assertFalse(app.constant_store.get('Flag'))
        self.assertFalse(app.constant_store.transaction_active)


if __name__=='__main__':unittest.main()
