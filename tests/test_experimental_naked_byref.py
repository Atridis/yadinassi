"""Measured byref repair only; the rest of the naked contract stays unclaimed."""
import os
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from tests.retired_text_compiler import prepare,ENV

class NakedByrefRepairTests(unittest.TestCase):
    def setUp(self):
        self.enabled=patch.dict(os.environ,{ENV:'1'});self.enabled.start();self.addCleanup(self.enabled.stop)
    def pair(self,source,names):
        vm=Interpreter(execution_backend='interpreter');vm.execute(source)
        program=prepare(source,repairs=('byref_routines',));actual=program.run()
        for name in names:
            expected=vm.variables[name]
            if hasattr(expected,'items') and type(expected.items) is list:expected=expected.items
            self.assertEqual(actual[name],expected,name)
        return program
    def test_same_actual_alias_is_live_not_copyback(self):
        self.pair('Procedure F(x,y) x=x+1;y=y+2;EndProcedure a=1;F(a,a);',['a'])
    def test_forwarded_reference_alias(self):
        self.pair('Procedure F(x,y) x=x+1;y=y+2;EndProcedure Procedure G(z) F(z,z);EndProcedure a=1;G(a);',['a'])
    def test_value_parameter_forwarded_byref_is_local_copy(self):
        self.pair('Procedure F(x) x=99;EndProcedure Procedure G(Val y) F(y);EndProcedure a=1;G(a);',['a'])
    def test_defaults_are_fresh_each_call(self):
        self.pair('Function F(x=1) x=x+1;Return x;EndFunction a=F();b=F();',['a','b'])
    def test_omitted_default_and_expression_temporary(self):
        self.pair('Function F(x=1,y=2) x=x+1;y=y+2;Return x+y;EndFunction a=F(,);b=F(3+4,5);',['a','b'])
    def test_index_references_alias_same_slot(self):
        self.pair('Procedure F(x,y) x=x+1;y=y+2;EndProcedure a=New Array;a.Add(1);F(a[0],a[0]);',['a'])
    def test_attribute_reference(self):
        self.pair('Procedure F(x) x=x+2;EndProcedure s=New Structure("x",1);F(s.x);a=s.x;',['a'])
    def test_property_output_found_and_absent(self):
        self.pair('s=New Structure("x",7);a=0;r=s.Property("x",a);b=9;q=s.Property("missing",b);',['a','r','b','q'])
    def test_value_collection_alias_and_rebinding(self):
        self.pair('Procedure F(Val a) a.Add(9);a=New Array;EndProcedure x=New Array;x.Add(1);F(x);',['x'])
    def test_loop_counter_can_be_reference(self):
        self.pair('Procedure F(x) x=x+1;EndProcedure s=0;For i=1 To 5 Do F(i);s=s+i;EndDo;',['s','i'])
    def test_module_var_and_local_shadow(self):
        self.pair('Var a;Procedure F(x) x=8;EndProcedure Procedure G() Var a;a=2;F(a);EndProcedure a=1;G();',['a'])
    def test_cells_only_for_escaping_variables(self):
        p=prepare('Function F(Val x) Return x+1;EndFunction a=1;b=F(a);',repairs=('byref_routines',))
        self.assertNotIn('_Cell(',p.generated_source)
        p=prepare('Procedure F(x) x=x+1;EndProcedure a=1;z=2;F(a);',repairs=('byref_routines',))
        self.assertEqual(p.generated_source.count('_Cell('),1)
    def test_partial_writes_visible_on_exception(self):
        p=prepare('Procedure F(x,y) x=5;y=1/0;EndProcedure a=1;b=2;F(a,b);',repairs=('byref_routines',))
        with self.assertRaises(ArithmeticError):p.run()
        self.assertEqual((p.last_state['a'],p.last_state['b']),(5,2))
    def test_failure_before_reference_does_not_publish_uninitialized_name(self):
        p=prepare('Procedure F(x) x=5;EndProcedure b=1/0;F(a);',repairs=('byref_routines',))
        with self.assertRaises(ArithmeticError):p.run()
        self.assertNotIn('a',p.last_state)
    def test_uninitialized_reference_rejected_before_callee_effects(self):
        source='Procedure F(x) Message(123);x=5;EndProcedure F(a);'
        from yadinassi.errors import BSLRuntimeError
        with self.assertRaises(BSLRuntimeError):Interpreter(execution_backend='interpreter').execute(source)
        p=prepare(source,repairs=('byref_routines',))
        with self.assertRaises(NameError):p.run()
        self.assertEqual(p.output,[])
        self.assertNotIn('a',p.last_state)
    def test_boxed_var_initializes_none(self):
        self.pair('Procedure F(x) Return;EndProcedure Var a;F(a);',['a'])
    def test_uninitialized_cell_read_raises(self):
        p=prepare('Procedure F(x) x=x+1;EndProcedure F(a);',repairs=('byref_routines',))
        with self.assertRaises(NameError):p.run()
        self.assertNotIn('a',p.last_state)

    def test_missing_collection_reference_fails_before_callee_effects(self):
        from yadinassi.errors import BSLRuntimeError
        for constructor,target in [('Array','a[0]'),('Structure','a.missing'),('Structure','a["missing"]')]:
            with self.subTest(target=target):
                source=f'Procedure F(x) Host();x=7;EndProcedure a=New {constructor};F({target});'
                outcomes=[]
                for naked in (False,True):
                    events=[]
                    if naked:
                        p=prepare(source,source_name='refs.bsl',repairs=('byref_routines','array_index_contract','error_boundaries'))
                        execute=lambda:p.run({'host':lambda:events.append('called')})
                    else:
                        vm=Interpreter(execution_backend='interpreter');vm.register_function('Host',lambda:events.append('called'))
                        execute=lambda:vm.execute(source,'refs.bsl')
                    with self.assertRaises(BSLRuntimeError) as raised:execute()
                    outcomes.append((raised.exception.line,raised.exception.column))
                    self.assertEqual(events,[])
                self.assertEqual([line for line,column in outcomes],[1,1])

    def test_missing_map_key_is_valid_reference_output(self):
        self.pair('Procedure F(x) x=7;EndProcedure a=New Map;F(a["missing"]);result=a.Get("missing");',['result'])

    def test_host_reference_parameters_keep_same_actual_alias(self):
        from yadinassi.values import HostFunction
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        source='a=1;Host(a,a);r=a;'
        def host(x,y):x.set(x.get()+1);y.set(y.get()+2)
        vm=Interpreter(execution_backend='interpreter')
        vm.functions['host']=HostFunction('Host',host,reference_parameters=frozenset({0,1}))
        vm.execute(source)
        p=prepare(source,repairs=('byref_routines','service_boundaries'),service_references={'Host':(0,1)})
        result=p.run(context=BoundaryContext(services={'Host':host}))
        self.assertEqual(result['r'],vm.variables['r'])

    def test_host_attribute_proxy_forwarding_keeps_alias(self):
        from decimal import Decimal
        from types import SimpleNamespace
        from yadinassi.experimental_naked_boundaries import BoundaryContext,HostMembers
        # Compare native Structure lvalue semantics with explicitly exposed host storage.
        source='Procedure F(x,y) x=x+1;y=y+2;EndProcedure Procedure G(z) F(z,z);EndProcedure G(obj.value);'
        vm=Interpreter(execution_backend='interpreter')
        vm.execute('obj=New Structure("value",1);'+source+'result=obj.value;')
        obj=SimpleNamespace(value=Decimal(1))
        context=BoundaryContext(members=(HostMembers(obj,readable=('value',),writable=('value',)),))
        p=prepare(source,repairs=('byref_routines','service_boundaries'))
        p.run({'obj':obj},context=context)
        self.assertEqual(obj.value,vm.variables['result'])

    def test_missing_reference_error_position_matches_baseline(self):
        from yadinassi.errors import BSLRuntimeError
        source='Procedure F(x) x=7;EndProcedure a=New Array;F(a[0]);'
        outcomes=[]
        for naked in (False,True):
            try:
                if naked:prepare(source,source_name='refs.bsl',repairs=('byref_routines','array_index_contract','error_boundaries')).run()
                else:Interpreter(execution_backend='interpreter').execute(source,'refs.bsl')
            except BSLRuntimeError as error:outcomes.append((error.line,error.column))
        self.assertEqual(len(outcomes),2)
        self.assertEqual(*outcomes)

    def test_call_mapping_keeps_argument_expression_error_location(self):
        from yadinassi.errors import BSLRuntimeError
        sources=[
            'Procedure F(x) Return;EndProcedure F(1/0);',
            'Procedure F(x,y) Return;EndProcedure a=New Array;F(a[1/0],2);',
            'Procedure F(x) Return;EndProcedure a=New Array;F(a[0]);',
        ]
        for source in sources:
            with self.subTest(source=source):
                outcomes=[]
                for naked in (False,True):
                    try:
                        if naked:prepare(source,source_name='refs.bsl',repairs=('byref_routines','array_index_contract','error_boundaries')).run()
                        else:Interpreter(execution_backend='interpreter').execute(source,'refs.bsl')
                    except BSLRuntimeError as error:outcomes.append((error.message,error.line,error.column))
                self.assertEqual(len(outcomes),2)
                self.assertEqual(*outcomes)
