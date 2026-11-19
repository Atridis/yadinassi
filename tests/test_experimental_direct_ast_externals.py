"""External namespace operations retain their live context boundary."""
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported

class DirectSourceAssertions:
    def check_source(self, source, *, expected=None, error=None, touches=0, setup=None, kind=BSLRuntimeError):
        vm=Interpreter(allow_extensions=True)
        calls=[]
        def touch():
            calls.append('touch')
            return Decimal(7)
        vm.register_function('Touch',touch)
        try:
            if setup:setup(vm)
            if error is None:
                vm.execute(source,'externals.bsl')
                self.assertEqual(vm.variables,expected)
            else:
                with self.assertRaises(kind) as caught:
                    vm.execute(source,'externals.bsl')
                self.assertNotIn('r',vm.variables)
            self.assertEqual(calls,['touch']*touches)
            if error is not None:self.assertIn(error,str(caught.exception))
        finally:
            vm.close()


class DirectASTExternalTests(DirectSourceAssertions,unittest.TestCase):
    def test_system_reads_shadowing_and_write_effect_order(self):
        for source, checks in (
            ('R=Chars.LF;', {'expected': {'r': '\n'}}),
            ('R=String(ErrorCategory.Other);', dict(error='Other', touches=0)),
            ('Chars=Touch();', dict(error='read-only', touches=1)),
            ('For Chars=Touch() To 9 Do EndDo;', dict(error='read-only', touches=1)),
            ('A=New Array;A.Add(2);For Each Chars In A Do EndDo;', dict(error='read-only', touches=0)),
            ('Function F(Val Chars) Return Chars+1;EndFunction;R=F(3);', {'expected': {'r': 4}}),
            ('Function F() Var Chars;Chars=7;Return Chars;EndFunction;R=F();', {'expected': {'r': 7}}),
            ('Function F() Chars=Touch();Return 1;EndFunction;R=F();', dict(error='read-only', touches=1)),
            ('Procedure P(X) X=1;EndProcedure;P(Chars);', dict(error='передача реквизита', touches=0)),
            ('Var Chars;R=Chars.LF;', dict(error='external names collide', touches=0, kind=PythonDirectUnsupported)),
        ):
            with self.subTest(source=source):self.check_source(source,**checks)

    def test_reserved_name_read_write_and_scope(self):
        for source, checks in (
            ('ThisObject=Touch();', dict(error='только для чтения', touches=1)),
            ('R=ThisObject;', dict(error='не определена', touches=0)),
            ('Var ThisObject;ThisObject=7;R=ThisObject;', {'expected': {'r': 7, 'thisobject': 7}}),
            ('Function F(Val ThisObject) ThisObject=ThisObject+1;Return ThisObject;EndFunction;R=F(3);', {'expected': {'r': 4}}),
            ('Function F() ThisObject=Touch();Return 1;EndFunction;R=F();', dict(error='только для чтения', touches=1)),
        ):
            with self.subTest(source=source):self.check_source(source,**checks)
        self.check_source('ThisObject=Touch();R=ThisObject;',setup=lambda vm:vm.variables.update(thisobject=Decimal(1)),expected={'r':7,'thisobject':7},touches=1)
