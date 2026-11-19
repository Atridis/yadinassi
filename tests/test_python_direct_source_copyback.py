"""Finite source named-slot copy-out without legacy dispatch."""
import unittest
from unittest.mock import patch
from decimal import Decimal
import test_source_server_call as existing
import test_source_application_exports as exports
from yadinassi.runtime import Interpreter
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class SourceCopybackTests(unittest.TestCase):
    run_app=existing.SourceServerCallTests.run_app
    def setUp(self):
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            guard.start();self.addCleanup(guard.stop)
    test_scalar=existing.SourceServerCallTests.test_scalar_copyback
    test_collection=existing.SourceServerCallTests.test_collection_copyback
    test_exception_no_copyout=existing.SourceServerCallTests.test_error_has_no_copyback
    test_unsupported_result_no_copyout=existing.SourceServerCallTests.test_unsupported_return_no_copyback
    test_safe_mode=existing.SourceServerCallTests.test_safe_mode_cannot_cross

    def test_exported_application_slot(self):
        original=exports.SourceApplicationExportsTests();self.addCleanup(original.doCleanups)
        original.test_server_copyback_preserves_global_slot()

    def test_alias_and_val_isolation(self):
        _,out=self.run_app(existing.configuration('X=1;Message(ServerAPI.Change(X,X,X));Message(X);',
            'Function Change(A,B,Val C) Export A=7;B=8;Return C;EndFunction'))
        self.assertEqual(out,['1','8'])

    def test_collection_aliases_are_independent(self):
        _,out=self.run_app(existing.configuration('X=New Array;X.Add(1);ServerAPI.Change(X,X);Message(X.Count());',
            'Procedure Change(A,B) Export A.Add(2);A.Add(3);B.Add(4);EndProcedure'))
        self.assertEqual(out,['2'])

    def test_structure_copyback_and_late_inputs(self):
        _,out=self.run_app(existing.configuration('X=New Structure("N",1);ServerAPI.Change(X);Message(X.N);',
            'Procedure Change(X) Export X.N=7;EndProcedure'))
        self.assertEqual(out,['7'])
        app,out=self.run_app(existing.configuration('',
            'Procedure Change(X,Val Y) Export X=X+1;EndProcedure'))
        app.interpreter.execute('Var X;Function Touch() X=4;Return 0;EndFunction')
        app.interpreter.execute('X=1;ServerAPI.Change(X,Touch());Message(X);')
        self.assertEqual(out,['5'])

    def test_expression_rejected_before_any_argument_effects(self):
        app,_=self.run_app(existing.configuration('',
            'Procedure Change(Val A,X) Export EndProcedure'))
        effects=[];app.interpreter.register_function('Touch',lambda:effects.append('arg') or Decimal(1))
        with self.assertRaises((BSLError,BoundaryViolation,ValueError,TypeError)):
            app.interpreter.execute('ServerAPI.Change(Touch(),Touch());')
        self.assertEqual(effects,[])

    def test_byref_default_and_reuse_rejected_before_effects(self):
        for body,flags in (('Procedure Change(X=1) Export EndProcedure',{}),
                           ('Function Change(X) Export Return X;EndFunction',{'reuse':'DuringSession'})):
            app,_=self.run_app(existing.configuration('',body,**flags));effects=[]
            app.interpreter.register_function('Touch',lambda:effects.append('arg') or Decimal(1))
            with self.assertRaises((BSLError,BoundaryViolation,ValueError,TypeError)):
                app.interpreter.execute('ServerAPI.Change(Touch());')
            self.assertEqual(effects,[])

    def test_transaction_guard_precedes_argument_effects(self):
        from yadinassi.db import database_transactions
        app,_=self.run_app(existing.configuration('', 'Procedure Change(X,Val Y) Export X=9;EndProcedure'))
        effects=[];app.interpreter.register_function('Touch',lambda:effects.append('arg') or Decimal(1))
        with patch.object(database_transactions,'forbid_transfer',side_effect=ValueError('transaction crossing denied')):
            with self.assertRaises((BSLError,BoundaryViolation,ValueError,TypeError)):app.interpreter.execute('X=1;ServerAPI.Change(X,Touch());')
        self.assertEqual(effects,[]);self.assertEqual(app.interpreter.variables['x'],Decimal(1))
