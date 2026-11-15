"""Exact interpreter-aware constants dispatch; no arbitrary invoke capability."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from test_source_constant_store import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constants_runtime import SourceConstants, SourceConstant, SourceConstantSet, ConstantCall, ConstantSetCall
from yadinassi.source_constant_managers import SourceConstantValueManager, ValueManagerCall
from yadinassi.values import InterpreterCall
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLError


class ConstantDispatchTests(unittest.TestCase):
    def app(self,module=''):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        path=Path(directory.name)/'scratch.sqlite'
        files={'Ext/SessionModule.bsl':b'Procedure SessionParametersSetting(Names) EndProcedure'}
        if module:files['Constants/Text/Ext/ValueManagerModule.bsl']=module.encode()
        app=SourceApplication(configuration(files),scratch_database=path,output=lambda _:None)
        self.addCleanup(app.close);app.start()
        return app,path

    def run_server(self,app,code):
        caller=app._session_owner
        caller._context_stack.append('server')
        try:return caller.execute(code)
        finally:caller._context_stack.pop()

    def descriptors(self,app):
        owner=SourceConstants(app)
        return [ConstantCall(owner,'Text',True).descriptor(),
                ConstantSetCall(owner,'create').descriptor(),
                ValueManagerCall(SourceConstant(owner,'Text'),'create').descriptor()]

    def test_all_producers_are_exact_descriptors(self):
        app,_=self.app();owner=SourceConstants(app);constant=SourceConstant(owner,'Text')
        receivers=[(owner,['CreateSet']),(constant,['Get','Set','CreateValueManager']),
                   (SourceConstantSet(owner,['Text']),['Read','Write']),
                   (SourceConstantValueManager(owner,'Text'),['Read','Write','Metadata'])]
        for receiver,names in receivers:
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(type(receiver.get_method(name).function),InterpreterCall)

    def test_foreign_descriptor_authorizes_before_arguments(self):
        owner,_=self.app();other,_=self.app();effects=[]
        other._session_owner.register_function('Touch',lambda:effects.append('bad') or 'x')
        for descriptor in self.descriptors(owner):
            other._session_owner.register_function('Captured',descriptor)
            with self.subTest(descriptor=descriptor),self.assertRaises(BSLError):
                self.run_server(other,'Captured(Touch())')
        self.assertEqual(effects,[])

    def test_arity_before_argument_effects(self):
        app,_=self.app();effects=[]
        app._session_owner.register_function('Touch',lambda:effects.append('bad') or 'x')
        for code in ['Constants.Text.Get(Touch())','Constants.Text.Set(Touch(),Touch());',
                     'Constants.CreateSet(Touch(),Touch())','Constants.Text.CreateValueManager(Touch())']:
            with self.subTest(code=code),self.assertRaises(BSLError):self.run_server(app,code)
        self.run_server(app,'M=Constants.Text.CreateValueManager();')
        for code in ['M.Read(Touch());','M.Write(Touch());','M.Metadata(Touch())']:
            with self.subTest(code=code),self.assertRaises(BSLError):self.run_server(app,code)
        self.assertEqual(effects,[])

    def test_procedure_returns_value_guard_precedes_arguments(self):
        app,_=self.app();effects=[]
        app._session_owner.register_function('Touch',lambda:effects.append('bad') or 'x')
        with self.assertRaises(BSLError):self.run_server(app,'X=Constants.Text.Set(Touch());')
        self.assertEqual(effects,[])

    def test_argument_can_invalidate_owner_and_invoke_reauthorizes(self):
        app,path=self.app()
        def close():
            # Full app.close() intentionally refuses resetting an active
            # scheduler. Model an external owner/database invalidation without
            # weakening that scheduler rule.
            app.constant_store.close()
            app.state='closed'
            return 'x'
        app._session_owner.register_function('CloseOwner',close)
        with self.assertRaises(BSLError):self.run_server(app,'Constants.Text.Set(CloseOwner());')
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0],0)

    def test_all_write_paths_still_dispatch_generator_handlers(self):
        for code in ['Constants.Text.Set("raw");',
                     'M=Constants.Text.CreateValueManager();M.Value="raw";M.Write();',
                     'S=Constants.CreateSet("Text");S.Text="raw";S.Write();']:
            app,_=self.app('Procedure BeforeWrite(Cancel) Value="hook";EndProcedure')
            with self.subTest(code=code):
                self.run_server(app,code)
                self.assertEqual(app.constant_store.get('Text'),'hook')

    def test_all_write_paths_keep_handler_cancel_atomic(self):
        for code in ['Constants.Text.Set("raw");',
                     'M=Constants.Text.CreateValueManager();M.Value="raw";M.Write();',
                     'S=Constants.CreateSet("Text");S.Text="raw";S.Write();']:
            app,path=self.app('Procedure OnWrite(Cancel) Cancel=True;EndProcedure')
            with self.subTest(code=code),self.assertRaises(BSLError):self.run_server(app,code)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0],0)

    def test_raw_marker_does_not_gain_interpreter_dispatch(self):
        app,_=self.app();owner=SourceConstants(app)
        for marker in [ConstantCall(owner,'Text',False),ConstantSetCall(owner,'create'),
                       ValueManagerCall(SourceConstant(owner,'Text'),'create')]:
            app._session_owner.register_function('Raw',marker)
            with self.subTest(marker=marker),self.assertRaisesRegex(BSLError,'interpreter invocation'):
                self.run_server(app,'Raw()')

    def test_duck_invoke_and_descriptor_subclass_not_admitted(self):
        effects=[]
        class Ordinary:
            def __call__(self):return 'ordinary'
            def invoke(self,*args):effects.append('bad')
        class Derived(InterpreterCall):pass
        vm=Interpreter(lambda _:None);self.addCleanup(vm.close)
        vm.register_function('Ordinary',Ordinary())
        self.assertEqual(vm.execute('Ordinary()'),'ordinary')
        vm.register_function('Derived',Derived(0,0,lambda caller:effects.append('bad'),lambda caller,args:iter(())))
        with self.assertRaises(BSLError):vm.execute('Derived()')
        self.assertEqual(effects,[])

    def test_descriptor_is_frozen_and_dispatch_requires_generator(self):
        effects=[]
        descriptor=InterpreterCall(0,0,lambda caller:effects.append('authorize'),lambda caller,args:[])
        with self.assertRaises(AttributeError):descriptor.maximum_arguments=2
        vm=Interpreter(lambda _:None);self.addCleanup(vm.close);vm.register_function('Bad',descriptor)
        with self.assertRaisesRegex(BSLError,'requires a generator'):vm.execute('Bad()')
        self.assertEqual(effects,['authorize','authorize'])

    def test_closed_value_manager_descriptor_rejects_before_arguments(self):
        app,_=self.app();owner=SourceConstants(app)
        descriptor=ValueManagerCall(SourceConstantValueManager(owner,'Text'),'write').descriptor()
        app.close();vm=Interpreter(lambda _:None);self.addCleanup(vm.close);effects=[]
        vm.register_function('Captured',descriptor,returns_value=False)
        vm.register_function('Touch',lambda:effects.append('bad'))
        with self.assertRaises(BSLError):vm.execute('Captured(Touch());')
        self.assertEqual(effects,[])
