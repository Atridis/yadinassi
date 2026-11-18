"""External namespace operations retain their live context boundary."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast as direct
from direct_ast_text_oracle import compile_module as oracle

class DirectASTExternalTests(unittest.TestCase):
    def paired(self,source,setup=None):
        outcomes=[]
        for compiler in (oracle,direct.compile_module,direct.compile_module_whole_source):
            vm=Interpreter()
            def touch():vm.variables['seen']=Decimal(1);return Decimal(7)
            vm.register_function('Touch',touch)
            if setup:setup(vm)
            try:
                with patch.object(python_direct,'_compile',compiler):
                    try:vm.execute(source,'externals.bsl');error=None
                    except BaseException as exc:error=(type(exc).__name__,str(exc),getattr(exc,'line',None),getattr(exc,'column',None))
                outcomes.append((dict(vm.variables),error))
            finally:vm.close()
        self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[0],outcomes[2])
        return outcomes[0]

    def test_system_reads_shadowing_and_write_effect_order(self):
        for source in (
            'R=Chars.LF;',
            'R=String(ErrorCategory.Other);',
            'Chars=Touch();',
            'For Chars=Touch() To 9 Do EndDo;',
            'A=New Array;A.Add(2);For Each Chars In A Do EndDo;',
            'Function F(Val Chars) Return Chars+1;EndFunction;R=F(3);',
            'Function F() Var Chars;Chars=7;Return Chars;EndFunction;R=F();',
            'Function F() Chars=Touch();Return 1;EndFunction;R=F();',
            'Procedure P(X) X=1;EndProcedure;P(Chars);',
            'Var Chars;R=Chars.LF;',
        ):
            with self.subTest(source=source):self.paired(source)

    def test_reserved_name_read_write_and_scope(self):
        for source in (
            'ThisObject=Touch();',
            'R=ThisObject;',
            'Var ThisObject;ThisObject=7;R=ThisObject;',
            'Function F(Val ThisObject) ThisObject=ThisObject+1;Return ThisObject;EndFunction;R=F(3);',
            'Function F() ThisObject=Touch();Return 1;EndFunction;R=F();',
        ):
            with self.subTest(source=source):self.paired(source)
        self.paired('ThisObject=Touch();R=ThisObject;',lambda vm:vm.variables.update(thisobject=Decimal(1)))
