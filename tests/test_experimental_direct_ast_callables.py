"""Expression call targets resolve before their arguments through the boundary."""
import unittest
from test_experimental_direct_ast_externals import DirectSourceAssertions

class CallableTests(DirectSourceAssertions,unittest.TestCase):
    def test_callable_expression_resolution(self):
        def setup(vm):
            vm.register_function('Get',lambda:vm.functions['touch'])
        for source, checks in (
            ('R=Get()();', dict(expected={'r':7}, touches=1)),
            ('R=(Touch)();', dict(expected={'r':7}, touches=1)),
            ('Procedure Set(X) X=9;EndProcedure;Function F() X=1;(Set)(X);Return X;EndFunction;R=F();', {'expected': {'r': 9}}),
            ('Function F() X=2;Return (Eval)("X+1");EndFunction;R=F();', {'expected': {'r': 3}}),
            ('R=(Eval)("1+1");', {'expected': {'r': 2}}),
            ('Function F() Return 2;EndFunction;R=(F)();', {'expected': {'r': 2}}),
            ('A=New Array;A.Add(1);R=(A.Count)();A=0;', {'expected': {'a': 0, 'r': 1}}),
            ('Function F() Return Get()();EndFunction;R=F();', dict(expected={'r':7}, touches=1)),
            ('R=Touch()(Touch());', dict(error='не является функцией', touches=1)),
            ('Function F() X=1;Return Get()(X);EndFunction;R=F();', dict(error='1 was given', touches=0)),
        ):
            with self.subTest(source=source):self.check_source(source,setup=setup,**checks)
