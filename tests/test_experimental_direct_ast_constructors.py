"""Broader canonical constructors through existing boundary, not new factories."""
from direct_ast_text_oracle import compile_module as text_compile
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast as direct

class DirectASTCanonicalConstructorTests(unittest.TestCase):
    def paired(self,source,setup=None):
        outcomes=[]
        for compiler in (text_compile,direct.compile_module,direct.compile_module_whole_source):
            vm=Interpreter()
            def touch():vm.variables['seen']=Decimal(1);return Decimal(3)
            vm.register_function('Touch',touch)
            if setup:setup(vm)
            try:
                try:
                    with patch.object(python_direct,'_compile',compiler):vm.execute(source,'constructors.bsl')
                    error=None
                except BaseException as exc:error=(type(exc).__name__,str(exc),getattr(exc,'line',None),getattr(exc,'column',None))
                outcomes.append((dict(vm.variables),error))
            finally:vm.close()
        self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[0],outcomes[2])
        return outcomes[0]

    def test_canonical_constructor_values(self):
        for source in (
            'A=New Array;A.Add(7);F=New FixedArray(A);R=F.Get(0);A=0;F=0;',
            'A=New Structure("N",7);F=New FixedStructure(A);R=F.N;A=0;F=0;',
            'A=New Map;A.Insert(1,7);F=New FixedMap(A);R=F.Get(1);A=0;F=0;',
            'T=New TypeDescription("Number");R=T.AdjustValue("7");T=0;',
            'T=New NumberQualifiers(8,2);R=T.Digits;T=0;',
            'T=New ValueTree;R=T.Rows.Count();T=0;',
            'U=New UUID("12345678-1234-5678-1234-567812345678");R=String(U);U=0;',
            'W=New JSONWriter;W.SetString();W.WriteStartObject();W.WritePropertyName("x");W.WriteValue(7);W.WriteEndObject();R=W.Close();W=0;',
            'R=New TextDocument;R.SetText("hello");S=R.GetText();R=0;',
        ):
            with self.subTest(source=source):self.paired(source)

    def test_unconstructible_and_invalid_arity_preserve_argument_effects(self):
        for source in (
            'X=1;R=New ValueTableRow(Touch());',
            'R=New JSONWriter(Touch());',
            'R=New UUID(Touch());',
            'R=New NumberQualifiers(Touch(),2);R=0;',
        ):
            with self.subTest(source=source):self.paired(source)

    def test_replaced_constructor_and_argument_close(self):
        def override(vm):vm.register_type('ValueList',lambda *args:object())
        self.paired('X=1;T=New ValueList(Touch());',override)
        def closing(vm):vm.register_function('Touch',lambda:vm.close())
        self.paired('X=1;T=New TypeDescription(Touch());',closing)
