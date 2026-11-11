"""Application-local schema scope and bounded host failures, not native evidence."""
import gc
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import weakref

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi import cli
from yadinassi.async_runtime import _HostFault
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_xml import import_configuration
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.database_context import SQLiteDBContext
from configuration_runtime_fixture import module_files


class FamilyIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.files = module_files([('Tools', 'Function Ref() Export Return Catalogs.Categories.EmptyRef(); EndFunction', {})])
        self.path = Path(self.temp.name) / 'data.sqlite'
        self.context = SQLiteDBContext.create(self.path, import_configuration(self.files, module_runtime=MODULE_RUNTIME))
        self.addCleanup(self.context.close)
        self.root = Interpreter(database_context=self.context); self.addCleanup(self.root.close)

    def test_common_module_assignment_query_and_metadata(self):
        app = ConfigurationApplication.from_files(self.files, database_context=self.context, side='client')
        self.addCleanup(app.close); app.start()
        app.execute('P=Catalogs.Products.CreateItem(); P.Category=Tools.Ref(); '
                    'Q=New Query("SELECT Code FROM Catalog.Products WHERE Category=&Ref"); '
                    'Q.SetParameter("Ref",Tools.Ref()); R=Q.Execute(); '
                    'T=TypeOf(Tools.Ref()); M=Metadata.FindByType(T);')
        self.assertEqual(app.interpreter.variables['m'].get_member('Name'), 'Categories')

    def test_file_module_assignment_and_query(self):
        helper=Path(self.temp.name)/'Helper.bsl'
        helper.write_text('Function Ref() Export Return Catalogs.Categories.EmptyRef(); EndFunction', encoding='utf-8')
        self.root.execute('// #Import Helper.bsl\nP=Catalogs.Products.CreateItem(); P.Category=Helper.Ref(); '
                          'Q=New Query("SELECT Code FROM Catalog.Products WHERE Category=&Ref"); '
                          'Q.SetParameter("Ref",Helper.Ref()); R=Q.Execute();', str(helper.parent/'main.bsl'))

    def test_family_type_equality_hash_and_metadata_identity(self):
        child=Interpreter(database_context=self.context,family_owner=self.root)
        self.addCleanup(child.close)
        left=self.root._catalogs.get_index('Categories').empty_ref()
        right=child._catalogs.get_index('Categories').empty_ref()
        self.assertEqual(left,right); self.assertEqual(hash(left),hash(right))
        self.assertEqual({left:'value'}[right], 'value')
        self.assertIs(left.get_metadata(),right.get_metadata())
        self.assertIsNot(self.root._catalogs, child._catalogs)

    def test_independent_root_same_context_still_rejected(self):
        foreign=Interpreter(database_context=self.context); self.addCleanup(foreign.close)
        value=foreign._catalogs.get_index('Categories').empty_ref()
        obj=self.root._catalogs.get_index('Products').create_item()
        with self.assertRaises(TypeError): obj.set_member('Category', value)

    def test_independently_owned_context_keeps_distinct_schema_scope(self):
        other=SQLiteDBContext(self.path); self.addCleanup(other.close)
        child=Interpreter(database_context=other,family_owner=self.root)
        self.addCleanup(child.close)
        nested=Interpreter(database_context=other,family_owner=self.root)
        self.addCleanup(nested.close)
        self.assertIsNot(child._metadata,self.root._metadata)
        self.assertIs(child._metadata,nested._metadata)
        obj=self.root._catalogs.get_index('Products').create_item()
        with self.assertRaises(TypeError): obj.set_member('Category',child._catalogs.get_index('Categories').empty_ref())

    def test_close_reopen_rotates_scope_and_fences_old_children(self):
        child=Interpreter(database_context=self.context,family_owner=self.root)
        old=child._catalogs.get_index('Categories').empty_ref()
        self.root.close(); self.root.execute('X=1;')
        obj=self.root._catalogs.get_index('Products').create_item()
        with self.assertRaises(TypeError): obj.set_member('Category',old)
        with self.assertRaises(ValueError): child.execute('X=1;')

    def test_cancel_preserves_scope_and_children(self):
        child=Interpreter(database_context=self.context,family_owner=self.root)
        self.addCleanup(child.close)
        old=child._catalogs.get_index('Categories').empty_ref()
        self.root.cancel_pending(); child.execute('X=1;')
        obj=self.root._catalogs.get_index('Products').create_item(); obj.set_member('Category',old)

    def test_document_reference_type_and_query_share_family_scope(self):
        from test_document_configuration_xml import document_files
        path=Path(self.temp.name)/'documents.sqlite'
        context=SQLiteDBContext.create(path,import_configuration(document_files()))
        self.addCleanup(context.close)
        root=Interpreter(database_context=context);self.addCleanup(root.close)
        child=Interpreter(database_context=context,family_owner=root);self.addCleanup(child.close)
        own=root._documents.get_index('Orders').empty_ref()
        ref=child._documents.get_index('Orders').empty_ref()
        self.assertEqual(own,ref);self.assertEqual(hash(own),hash(ref))
        root.variables['inputref']=ref
        root.execute('Q=New Query("SELECT Number FROM Document.Orders WHERE Ref=&Ref"); '
                     'Q.SetParameter("Ref",InputRef); R=Q.Execute();')
        self.assertEqual(root.variables['r']._rows,())

    def test_child_cannot_cancel_family(self):
        child=Interpreter(database_context=self.context,family_owner=self.root)
        self.addCleanup(child.close)
        with self.assertRaises(ValueError): child.cancel_pending()

    def test_context_identity_not_host_equality_selects_scope(self):
        class EqualContext(SQLiteDBContext):
            def __eq__(self, other): return True
            def __hash__(self): raise AssertionError('context hashing')
        context=EqualContext(self.path);self.addCleanup(context.close)
        child=Interpreter(database_context=context,family_owner=self.root)
        self.addCleanup(child.close)
        self.assertIsNot(child._metadata,self.root._metadata)
        sibling=Interpreter(database_context=context,family_owner=self.root)
        self.addCleanup(sibling.close)
        self.assertIs(child._metadata,sibling._metadata)

    def test_cancellation_inside_host_callback_is_rejected(self):
        self.root.register_function('CancelInside',self.root.cancel_pending)
        with self.assertRaisesRegex(RuntimeError,'active scheduler'):
            self.root.execute('CancelInside();')
        self.assertEqual(self.root.execute('6*7'),42)


class HostFailureLifetimeTests(unittest.TestCase):
    def test_repeated_await_does_not_keep_caller_frames(self):
        vm=Interpreter(); self.addCleanup(vm.close)
        def fail(): raise RuntimeError('host fault') from KeyError('cause')
        vm.register_function('HostFail',fail)
        vm.execute('Var p; Async Function F() Await 0; HostFail(); EndFunction '
                   'Async Function W() Return Await p; EndFunction')
        with self.assertRaises(RuntimeError): vm.execute('p=F();')
        class Payload: pass
        def await_once():
            payload=Payload(); ref=weakref.ref(payload)
            try: vm.execute('q=W();')
            except RuntimeError: pass
            return ref
        refs=[await_once() for _ in range(30)]
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertEqual(vm.pending_promises,())
        self.assertFalse(vm._scheduler._tasks)
        result=vm.variables['p'].result
        self.assertIsNone(result.__traceback__)
        self.assertIsInstance(result.__cause__,KeyError)
        self.assertIsNone(result.__cause__.__traceback__)
        self.assertIsNot(result,vm.variables['p'].result)
        vm.close();gc.collect();self.assertTrue(all(ref() is None for ref in refs))

    def test_custom_exception_constructors_not_replayed(self):
        calls=[]
        class Fault(RuntimeError):
            def __init__(self, message): calls.append(message); super().__init__(message)
        snapshot=_HostFault.capture(Fault('reason'))
        for _ in range(3): self.assertIsInstance(snapshot.deliver(),Fault)
        self.assertEqual(calls,['reason'])

    def test_mutable_payload_and_exception_attributes_not_retained(self):
        class Payload: pass
        value=Payload(); ref=weakref.ref(value)
        error=RuntimeError(value);error.payload=value
        snapshot=_HostFault.capture(error)
        del error,value;gc.collect()
        self.assertIsNone(ref());self.assertIn('host argument',snapshot.deliver().args[0])

    def test_custom_attribute_hooks_and_properties_are_not_called(self):
        calls=[]
        class Fault(RuntimeError):
            def __getattribute__(self, name):
                calls.append(('get',name)); raise AssertionError('custom get')
            def __setattr__(self, name, value):
                calls.append(('set',name)); raise AssertionError('custom set')
            @property
            def args(self): raise AssertionError('custom args descriptor')
        error=BaseException.__new__(Fault,'reason')
        snapshot=_HostFault.capture(error)
        delivered=snapshot.deliver()
        self.assertEqual(BaseException.args.__get__(delivered),('reason',))
        self.assertEqual(calls,[])

    def test_failed_await_does_not_read_custom_class_attribute(self):
        from yadinassi.async_runtime import Scheduler, AwaitRequest
        from yadinassi.native_targets import WINDOWS_8_3_27_2342
        calls=[]
        class Fault(RuntimeError):
            def __getattribute__(self,name):
                if name == '__class__':
                    calls.append(name); raise AssertionError('class hook')
                return BaseException.__getattribute__(self,name)
        scheduler=Scheduler(WINDOWS_8_3_27_2342)
        source=scheduler.new_pending()
        scheduler._settle(source,'failed',Fault('reason'))
        def consumer():
            return (yield AwaitRequest(source))
        pending=scheduler.start(consumer())
        with self.assertRaises(Fault): scheduler.run_until_idle()
        self.assertEqual(pending.state,'failed');self.assertEqual(calls,[])
        self.assertFalse(scheduler.pending);self.assertFalse(scheduler._tasks)

    def test_specialized_payload_falls_back_without_delivery_failure(self):
        # OSError subclasses with a custom allocator cannot be reconstructed
        # with BaseException.__new__; no arbitrary allocator is invoked.
        class Fault(OSError):
            def __new__(cls, *args): raise AssertionError('custom allocator')
        error=OSError.__new__(Fault,5,'reason')
        result=_HostFault.capture(error).deliver()
        self.assertIs(type(result),RuntimeError)
        self.assertEqual(result.args,('Fault',5,'reason'))

    def test_builtin_specialized_failure_remains_readable(self):
        for error in (OSError(5,'io'),UnicodeDecodeError('utf-8',b'\xff',0,1,'bad byte'),KeyboardInterrupt('stop')):
            result=_HostFault.capture(error).deliver()
            self.assertIs(type(result),type(error))
            self.assertEqual(str(result),str(error))
            self.assertIsNone(result.__traceback__)

    def test_chain_cycle_bounded_and_notes_preserved(self):
        error=RuntimeError('one');other=ValueError('two')
        error.__cause__=other;other.__cause__=error;error.__notes__=['note']
        result=_HostFault.capture(error).deliver()
        self.assertEqual(result.__notes__,['note'])
        self.assertEqual(result.__cause__.args,('two',))
        self.assertIsNone(result.__cause__.__cause__)


class ReplCancellationTests(unittest.TestCase):
    def test_interrupt_keeps_import_and_repeat_import_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'Helper.bsl';path.write_text('Function F() Export Return 42; EndFunction',encoding='utf-8')
            vm=Interpreter();self.addCleanup(vm.close)
            vm.execute('// #Import Helper.bsl\n', str(path.parent/'main.bsl'))
            handle=vm.imports['helper']
            def interrupt(): raise KeyboardInterrupt()
            vm.register_function('Interrupt',interrupt)
            session=Mock();session.prompt.side_effect=['Interrupt();','X=Helper.F();','/exit']
            with patch('prompt_toolkit.PromptSession',return_value=session),patch('sys.stdin.isatty',return_value=True),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(cli.repl(vm),0)
            self.assertEqual(vm.variables['x'],42)
            vm.execute('// #Import Helper.bsl\nY=Helper.F();', str(path.parent/'main.bsl'))
            self.assertEqual(vm.variables['y'],42);self.assertIs(vm.imports['helper'],handle)
