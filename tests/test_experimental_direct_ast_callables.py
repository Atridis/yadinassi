"""Expression call targets resolve before their arguments through the boundary."""
from test_experimental_direct_ast_externals import DirectASTExternalTests

class CallableTests(DirectASTExternalTests):
    def test_callable_expression_resolution(self):
        def setup(vm):
            vm.register_function('Get',lambda:vm.functions['touch'])
        for source in (
            'R=Get()();',
            'R=(Touch)();',
            'Procedure Set(X) X=9;EndProcedure;Function F() X=1;(Set)(X);Return X;EndFunction;R=F();',
            'Function F() X=2;Return (Eval)("X+1");EndFunction;R=F();',
            'R=(Eval)("1+1");',
            'Function F() Return 2;EndFunction;R=(F)();',
            'A=New Array;A.Add(1);R=(A.Count)();A=0;',
            'Function F() Return Get()();EndFunction;R=F();',
            'R=Touch()(Touch());',
            'Function F() X=1;Return Get()(X);EndFunction;R=F();',
        ):
            with self.subTest(source=source):self.paired(source,setup)
