"""Implicit manager namespace locals are an ordinary-source-only profile."""
import unittest
from unittest.mock import patch
import test_source_manager_modules as managers
import test_source_application_exports as exports
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse
from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax

class SourceShadowingTests(unittest.TestCase):
    def setUp(self):
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name));guard.start();self.addCleanup(guard.stop)
    def run_app(self,config):
        out=[];app=SourceApplication(config,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_read_before_write_and_false_branch(self):
        _,out=self.run_app(managers.configuration('Message(Catalogs.Items.Answer());If False Then Catalogs=8;EndIf;Message(Catalogs.Items.Answer());Catalogs=7;Message(Catalogs);'))
        self.assertEqual(out,['42','42','7'])
    def test_bilingual_and_loop_targets(self):
        for name in ('Catalogs','Справочники','Documents','Документы','Reports','Отчеты'):
            _,out=self.run_app(managers.configuration('For '+name+'=1 To 2 Do Message('+name+');EndDo;'))
            self.assertEqual(out,['1','2'])
        _,out=self.run_app(managers.configuration('A=New Array;A.Add(9);For Each Catalogs In A Do Message(Catalogs);EndDo;'))
        self.assertEqual(out,['9'])
    def test_sibling_and_explicit_locals(self):
        code='''Procedure OnStart() First();Second();Third(6);EndProcedure
Procedure First() Catalogs=7;Message(Catalogs);EndProcedure
Procedure Second() Var Catalogs;Catalogs=8;Message(Catalogs);EndProcedure
Procedure Third(Val Catalogs) Message(Catalogs);EndProcedure'''
        _,out=self.run_app(source(code.encode()));self.assertEqual(out,['7','8','6'])
        package=managers.configuration('Change();Message(Catalogs.Items.Answer());')
        # A sibling is available in this source session, but its local is not.
        from yadinassi.configuration_source import import_source
        files={f.path:f.content for f in package.files}
        files['Ext/SessionModule.bsl']+=b'\nProcedure Change() Catalogs=7;EndProcedure'
        _,out=self.run_app(import_source(files));self.assertEqual(out,['42'])
    def test_exported_and_module_slots_preserved(self):
        cfg=exports.configuration('Var Catalogs Export;Procedure OnStart() Catalogs=1;Helpers.Run();Message(Catalogs);EndProcedure',
                                  'Procedure Run() Export Catalogs=9;EndProcedure')
        _,out=self.run_app(cfg);self.assertEqual(out,['9'])
        _,out=self.run_app(source(b'Var Catalogs;Procedure OnStart() Catalogs=8;Message(Catalogs);EndProcedure'))
        self.assertEqual(out,['8'])
    def test_unset_byref_does_not_make_namespace_writable(self):
        code='''Procedure OnStart() Try Change(Catalogs);Except Message("denied");EndTry;Catalogs=1;Change(Catalogs);Message(Catalogs);EndProcedure
Procedure Change(X) X=9;EndProcedure'''
        _,out=self.run_app(source(code.encode()));self.assertEqual(out,['denied','9'])
    def test_fragment_combination_rejected_before_effects(self):
        for fragment in ('Execute("Catalogs=8;");','X=Eval("Catalogs");'):
            out=[];app=SourceApplication(source(('Procedure OnStart() Message("bad");Catalogs=7;'+fragment+'EndProcedure').encode()),output=out.append);self.addCleanup(app.close)
            with self.assertRaises(UnsupportedNakedSyntax):app.start()
            self.assertEqual(out,[])
    def test_private_compiler_contract_requires_source_trust(self):
        with self.assertRaises(ValueError):compile_owned([],source_text='',source_name='shadow.bsl',shadowable_externals=('catalogs',))

    def test_late_export_conflict_rejected_before_routine_effects(self):
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        app,out=self.run_app(source(b'Procedure P() Message("bad");Catalogs=7;EndProcedure'))
        app.interpreter.exported_variables.add('catalogs')
        with self.assertRaises(BoundaryViolation):app.interpreter.execute('P();')
        self.assertEqual(out,[])

    def test_noncanonical_export_inventory_rejected_without_iteration(self):
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        calls=[]
        class Poison(set):
            def __iter__(self):calls.append('iter');raise AssertionError('callback')
        app,out=self.run_app(source(b'Procedure P() Catalogs=7;EndProcedure'))
        original=app.interpreter.exported_variables
        app.interpreter.exported_variables=Poison()
        try:
            # Validate the existing routine plan directly, without first
            # compiling a new statement plan from the poisoned inventory.
            from yadinassi.python_direct_source import _check_plan
            plan=app.interpreter._direct_source_plans['p'][1]
            with self.assertRaises(BoundaryViolation):_check_plan(app.interpreter,plan)
        finally:app.interpreter.exported_variables=original
        self.assertEqual(calls,[])
