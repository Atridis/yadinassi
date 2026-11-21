"""Direct TextDocument uses finite canonical adapters, not generic host dispatch."""
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.streams.text_documents import BSLTextDocument
from yadinassi.types.values import HostFunction


class DirectTextDocumentTests(unittest.TestCase):
    def test_source_ast_prepared_dynamic_and_saved_methods_without_vm_dispatch(self):
        source = '''D=New TextDocument; D.SetText("a"); Saved=D.GetText;
D.AddLine("b"); R=Saved(); N=D.LineCount(); E=New("ТекстовыйДокумент");'''
        for route in ('source','ast','prepared'):
            with self.subTest(route=route), ExitStack() as stack:
                for method in ('block','call','call_routine','visit'):
                    stack.enter_context(patch.object(Interpreter,method,side_effect=AssertionError('legacy')))
                vm=Interpreter()
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
                self.assertEqual(vm.variables['r'],'a\nb\n')
                self.assertEqual(vm.variables['n'],Decimal(2))
                self.assertIs(type(vm.variables['e']),BSLTextDocument)
                vm.execute('R=Saved();')
                self.assertEqual(vm.variables['r'],'a\nb\n')

    def test_canonical_host_document_finite_methods_not_arbitrary_protocol(self):
        doc=BSLTextDocument(); doc.set_text('host')
        vm=Interpreter(allow_extensions=True);vm.register_function('Document',lambda:doc)
        vm.execute('D=Document();R=D.GetText();')
        self.assertEqual(vm.variables['r'],'host')
        calls=[]
        class Foreign:
            def get_method(self,*args):calls.append('foreign')
        vm.register_function('Foreign',lambda:Foreign())
        with self.assertRaises(BoundaryViolation):vm.execute('D=Foreign();D.GetText();')
        class Derived(BSLTextDocument):
            def get_method(self,*args):calls.append('derived')
        vm.register_function('Derived',lambda:Derived())
        with self.assertRaises(BoundaryViolation):vm.execute('D=Derived();D.GetText();')
        self.assertEqual(calls,[])

    def test_mutation_during_arguments_checked_before_text_effect(self):
        for tamper in ('instance','state','saved'):
            with self.subTest(tamper=tamper):
                vm=Interpreter(allow_extensions=True);vm.execute('D=New TextDocument;D.SetText("old");Saved=D.SetText;')
                doc=vm.variables['d'];calls=[]
                def change():
                    if tamper=='instance':doc.set_text=lambda *args:calls.append('hook')
                    elif tamper=='state':doc._spans=[('bad',0,0)]
                    else:vm.variables['saved'].function=lambda *args:calls.append('saved hook')
                    return 'new'
                vm.register_function('Change',change)
                with self.assertRaises(BoundaryViolation):vm.execute('Saved(Change());')
                self.assertEqual(doc._text,'old');self.assertEqual(calls,[])

    def test_closed_owner_during_arguments_cannot_mutate_or_write(self):
        for operation in ('D.SetText(Close())','Saved(Close())'):
            vm=Interpreter(allow_extensions=True);vm.execute('D=New TextDocument;D.SetText("old");Saved=D.SetText;')
            doc=vm.variables['d'];vm.register_function('Close',lambda:vm.close() or 'new')
            with self.assertRaises(BoundaryViolation):vm.execute(operation)
            self.assertEqual(doc._text,'old')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'must-not-write'
            vm=Interpreter(allow_extensions=True);vm.execute('D=New TextDocument;D.SetText("old");')
            vm.register_function('Close',lambda:vm.close() or str(path))
            with self.assertRaises(BoundaryViolation):vm.execute('D.Write(Close());')
            self.assertFalse(path.exists())

    def test_factory_class_helper_storage_and_alias_tampering_no_hooks(self):
        from yadinassi.streams import text_documents
        calls=[]
        class ChangedBase(BSLTextDocument.__bases__[0]):
            pass
        @contextmanager
        def changed_base():
            original=BSLTextDocument.__bases__
            try:
                BSLTextDocument.__bases__=(ChangedBase,)
                yield
            finally:
                BSLTextDocument.__bases__=original
        cases=[patch.object(BSLTextDocument,'__init__',lambda *a:calls.append('init')),
               patch.object(BSLTextDocument,'__getattribute__',lambda *a:calls.append('get')),
               changed_base(),
               patch.object(text_documents,'_spans',lambda *a:calls.append('spans'))]
        vm=Interpreter(allow_extensions=True);prepared=vm.prepare('D=New TextDocument;')
        for change in cases:
            with change, self.assertRaises(BoundaryViolation):vm.execute_prepared(prepared)
        vm.types['текстовыйдокумент']=HostFunction('bad',lambda:calls.append('alias'))
        with self.assertRaises(BoundaryViolation):vm.execute_prepared(prepared)
        self.assertEqual(calls,[])

    def test_server_local_resource_no_cross_context_transport(self):
        vm=Interpreter();vm.execute('''&AtServer
Function S() D=New TextDocument;D.SetText("server");Return D.GetText();EndFunction
R=S();''')
        self.assertEqual(vm.variables['r'],'server')
        vm.execute('&AtServer\nFunction F() Return New TextDocument;EndFunction')
        with self.assertRaises(BSLRuntimeError):vm.execute('F();')

    def test_property_write_reports_after_rhs_but_never_writes(self):
        vm=Interpreter(allow_extensions=True);vm.execute('D=New TextDocument;D.SetText("old");')
        calls=[];vm.register_function('Effect',lambda:calls.append('rhs') or 'new')
        with self.assertRaises(BSLRuntimeError):vm.execute('D.Text=Effect();')
        self.assertEqual(calls,['rhs']);self.assertEqual(vm.variables['d'].get_text(),'old')

    def test_saved_procedure_rejects_value_use_before_argument_effect(self):
        vm=Interpreter(allow_extensions=True);vm.execute('D=New TextDocument;Saved=D.SetText;')
        calls=[];vm.register_function('Effect',lambda:calls.append('effect') or 'new')
        with self.assertRaises(BSLRuntimeError):vm.execute('R=Saved(Effect());')
        self.assertEqual(calls,[])
