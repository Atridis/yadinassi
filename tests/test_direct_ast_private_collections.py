"""Fresh nonescaping data collections use direct methods, never graph admission per cell."""
import sys
import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct_static_module import analyze
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class PrivateCollectionTests(unittest.TestCase):
    def test_table_multiple_columns_aliases_branches_and_partial_error(self):
        vm=Interpreter();self.addCleanup(vm.close)
        source='T=New ValueTable;Alias=T;T.Columns.Add("A");T.Columns.Add("B");For I=0 To 5 Do Row=Alias.Add();Row.A=I;If I<3 Then Row.B=I+1;Else Row.B=I+2;EndIf;EndDo;R=0;For I=0 To 5 Do R=R+T.Get(I).A+Alias.Get(I).B;EndDo;'
        self.assertIsNotNone(analyze(parse(source)));plan=vm.prepare(source)
        self.assertNotIn('resolve_member_call',plan._plan.generated_source)
        self.assertNotIn('_collection_admitted',plan._plan.generated_source)
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(39))
        self.assertIs(vm.variables['t'],vm.variables['alias'])
        source='T=New ValueTable;T.Columns.Add("A");Row=T.Add();Row.A=7;R=Row.Missing;After=1;'
        with self.assertRaises(Exception):vm.execute(source)
        self.assertEqual(vm.variables['t'].get(D(0)).get_member('A'),D(7));self.assertNotIn('after',vm.variables)
    def test_list_direct_methods_and_native_payload(self):
        vm=Interpreter();self.addCleanup(vm.close)
        source='L=New ValueList;For I=0 To 7 Do Item=L.Add(I);Item.Value=I*2;EndDo;R=0;For I=0 To 7 Do R=R+L.Get(I).Value;EndDo;'
        self.assertIsNotNone(analyze(parse(source)));plan=vm.prepare(source)
        self.assertNotIn('resolve_member_call',plan._plan.generated_source)
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(56))
    def test_external_inputs_escape_and_unknown_calls_do_not_get_private_fact(self):
        for source in ('R=Incoming.Get(0).A;', 'T=New ValueTable;Host(T);Row=T.Add();', 'T=New ValueTable;Execute("R=1;");', 'T=New ValueTable;T.Columns.Add(Name);'):
            self.assertIsNone(analyze(parse(source)),source)
    def test_close_during_private_table_never_publishes(self):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare('T=New ValueTable;T.Columns.Add("A");For I=0 To 40 Do Row=T.Add();Row.A=I;EndDo;R=1;')
        code=plan._plan.function.__code__;events=[]
        def trace(frame,event,arg):
            if frame.f_code is code and event=='line':
                events.append(1)
                if len(events)==12:vm.close()
            return trace
        prior=sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        finally:sys.settrace(prior)
        self.assertGreaterEqual(len(events),12)
        for name in ('t','row','i','r'):self.assertNotIn(name,vm.variables)
    def test_growth_limits_are_still_real_native_boundaries(self):
        from unittest.mock import patch
        from yadinassi.collections import plain_value_table_runtime as native
        vm=Interpreter();self.addCleanup(vm.close)
        with patch.object(native,'_MAX_ROWS',2):
            with self.assertRaisesRegex(BSLRuntimeError,'growth limit'):
                vm.execute('T=New ValueTable;For I=0 To 3 Do Row=T.Add();EndDo;After=1;')
        self.assertEqual(len(vm.variables['t'].rows),2);self.assertNotIn('after',vm.variables)
