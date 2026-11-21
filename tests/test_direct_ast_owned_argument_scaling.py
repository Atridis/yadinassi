"""Each nested actual is lowered once, for native and owning-host selections."""
import unittest
from unittest.mock import patch
from yadinassi.execution.codegen.experimental_direct_ast import Emitter,compile_owned
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast

class OwnedArgumentScalingTests(unittest.TestCase):
    def test_nested_actuals_lower_once_in_both_profiles(self):
        for source_scopes in (False,True):
            sizes=[]
            for depth in (2,4,8,16):
                hits=[];original=Emitter.expr
                def observed(emitter,node,*args,**kwargs):
                    if type(node) is ast.Call and type(node.callee) is ast.Name and node.callee.name=='Leaf':hits.append(1)
                    return original(emitter,node,*args,**kwargs)
                text='R='+'A.F('*depth+'Leaf()'+')'*depth+';'
                with patch.object(Emitter,'expr',observed):
                    plan=compile_owned(parse(text),source_text=text,source_name='<scaling>',host_bindings=not source_scopes,source_scopes=source_scopes,authority_checks=True)
                self.assertEqual(len(hits),1,(source_scopes,depth))
                sizes.append(len(plan.generated_source))
            self.assertLess(sizes[-1],sizes[0]*10)

    def test_nested_omitted_source_actuals_lower_once(self):
        hits=[];original=Emitter.expr
        def observed(emitter,node,*args,**kwargs):
            if type(node) is ast.Call and type(node.callee) is ast.Name and node.callee.name=='Leaf':hits.append(1)
            return original(emitter,node,*args,**kwargs)
        text='R='+'A.F(,'*8+'Leaf()'+')'*8+';'
        with patch.object(Emitter,'expr',observed):
            compile_owned(parse(text),source_text=text,source_name='<scaling>',source_scopes=True,authority_checks=True)
        self.assertEqual(len(hits),1)

    def test_native_selected_callable_skips_host_protocol_and_preserves_arity_effects(self):
        from decimal import Decimal
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        from yadinassi.types.values import HostFunction
        for source_scopes in (False,True):
            effects=[]
            context=BoundaryContext(services={'touch':HostFunction('Touch',lambda x:effects.append(x) or x)})
            text='A=New Array;A.Add(0);R=A.Get(A.Get(Touch(0)));Try A.Add(Touch(1),Touch(2));Except Caught=True;EndTry;'
            plan=compile_owned(parse(text),source_text=text,source_name='<native-selection>',host_bindings=not source_scopes,source_scopes=source_scopes,authority_checks=True)
            state=plan.run({},context=context)
            self.assertEqual(state['r'],0);self.assertEqual(state['a'],[0]);self.assertTrue(state['caught'])
            self.assertEqual(effects,[Decimal(0),Decimal(1),Decimal(2)])
