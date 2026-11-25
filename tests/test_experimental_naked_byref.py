import ast
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import HostFunction

class DirectByrefContracts(unittest.TestCase):
    def check_source(self, source, names, expected):
        vm=Interpreter();self.addCleanup(vm.close);vm.execute(source)
        self.assertEqual([vm.variables[n] for n in names], expected)

    def test_forwarded_reference_alias(self):
        self.check_source('Procedure F(x,y) x=x+1;y=y+2;EndProcedure Procedure G(z) F(z,z);EndProcedure a=1;G(a);', ['a'], [4])

    def test_value_parameter_forwarded_byref_is_local_copy(self):
        self.check_source('Procedure F(x) x=99;EndProcedure Procedure G(Val y) F(y);EndProcedure a=1;G(a);', ['a'], [1])

    def test_omitted_default_and_expression_temporary(self):
        self.check_source('Function F(x=1,y=2) x=x+1;y=y+2;Return x+y;EndFunction a=F(,);b=F(3+4,5);', ['a', 'b'], [6, 15])

    def test_attribute_reference(self):
        self.check_source('Procedure F(x) x=x+2;EndProcedure s=New Structure("x",1);F(s.x);a=s.x;', ['a'], [3])

    def test_property_output_live_module_slot_preserves_storage_rules(self):
        for prepared in (False,True):
            with self.subTest(prepared=prepared):
                vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
                output=[]
                vm.register_function('ReadOutput', lambda: output.append(vm.variables['out']))
                source=('S=New Structure("X",7); Out=0; Found=S.Свойство("x",(Out)); ReadOutput();'
                        'Try S.Property("X",NotYet); Except Rejected=True; EndTry;'
                        'NotYet=1; Absent=S.Property("no",Out); ReadOutput();')
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual(output,[7,None])
                self.assertIs(vm.variables['found'],True)
                self.assertIs(vm.variables['absent'],False)
                self.assertIs(vm.variables['rejected'],True)
                self.assertEqual(vm.variables['notyet'],1)

    def test_property_output_does_not_replace_module_host_reference_identity(self):
        from yadinassi.types.values import Reference
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        cell=[0]
        ref=Reference(lambda:cell[0],lambda value:cell.__setitem__(0,value))
        vm.variables['out']=ref
        vm.execute('S=New Structure("X",7); If False Then Out=0; EndIf; S.Property("X",Out);')
        self.assertEqual(cell,[7])
        self.assertIs(vm.variables['out'],ref)

    def test_value_collection_alias_and_rebinding(self):
        self.check_source('Procedure F(Val a) a.Add(9);a=New Array;EndProcedure x=New Array;x.Add(1);F(x);', ['x'], [[1, 9]])

    def test_loop_counter_can_be_reference(self):
        self.check_source('Procedure F(x) x=x+1;EndProcedure s=0;For i=1 To 5 Do F(i);s=s+i;EndDo;', ['s', 'i'], [12, 7])

    def test_boxed_var_initializes_none(self):
        self.check_source('Procedure F(x) Return;EndProcedure Var a;F(a);', ['a'], [None])

    def test_missing_map_key_is_valid_reference_output(self):
        self.check_source('Procedure F(x) x=7;EndProcedure a=New Map;F(a["missing"]);result=a.Get("missing");', ['result'], [7])

    def test_partial_reference_writes_survive_error(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaisesRegex(BSLRuntimeError, 'Деление на ноль'):
            vm.execute('Procedure F(x,y) x=5;y=1/0;EndProcedure a=1;b=2;F(a,b);')
        self.assertEqual((vm.variables['a'],vm.variables['b']),(5,2))

    def test_missing_references_precede_callee_effects(self):
        for setup, target in [('', 'missing'),('a=New Array;', 'a[0]'),('a=New Structure;', 'a.missing'),('a=New Structure;', 'a["missing"]')]:
            with self.subTest(target=target):
                vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);events=[]
                vm.register_function('Host',lambda:events.append('called'))
                with self.assertRaises(BSLRuntimeError) as caught:
                    vm.execute('Procedure F(x) Host();x=7;EndProcedure '+setup+'F('+target+');','refs.bsl')
                self.assertEqual(caught.exception.line,1)
                self.assertEqual(events,[])
                self.assertNotIn('missing',vm.variables)

    def test_named_module_reference_distinguishes_missing_from_undefined(self):
        source = (
            'Procedure F(A, Val B) Message("called"); A=B; EndProcedure '
            'Function Later() Message("later"); Return 9; EndFunction '
            'Try F((Missing),Later()); Except Rejected=True; EndTry; '
            'Missing=Undefined; F(Missing,Later());')
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                effects=[]
                vm=Interpreter(effects.append);self.addCleanup(vm.close)
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual(effects,['later','called'])
                self.assertIs(vm.variables['rejected'],True)
                self.assertEqual(vm.variables['missing'],9)

    def test_proven_named_numeric_reference_has_no_loop_presence_check(self):
        vm=Interpreter();self.addCleanup(vm.close)
        source=('Procedure F(X, Y) X=X+0.5; Y=Y+1; EndProcedure '
                'A=0; For I=1 To 3 Do F(A,A); EndDo;')
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        loop=next(node for node in ast.walk(tree) if type(node) is ast.While)
        hot=ast.unparse(loop)
        self.assertNotIn('_UNSET',hot)
        self.assertNotIn('_C._check',hot)
        self.assertNotIn('.checkpoint(',hot)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['a'],Decimal('4.5'))

    def test_numeric_foreach_iterator_keeps_shared_reference_before_after_loop(self):
        procedure='Procedure F(X) X=X+1; EndProcedure '
        cases=(
            ('A.Add(1); A.Add(2); S=0; For Each V In A Do F(V); S=S+V; EndDo;', 5, 3),
            ('A.Add(1); V=10; S=0; For Each V In A Do S=S+V; EndDo; F(V);', 1, 2),
            ('V=10; S=0; For Each V In A Do S=S+V; EndDo; F(V);', 0, 11),
            ('A.Add(2); V=0; F(V); S=0; For Each V In A Do V=V+1; S=S+V; EndDo;', 3, 3),
        )
        for body,total,iterator in cases:
            for prepared in (False, True):
                with self.subTest(body=body,prepared=prepared):
                    vm=Interpreter();self.addCleanup(vm.close)
                    src=procedure+'A=New Array; '+body
                    if prepared:vm.execute_prepared(vm.prepare(src))
                    else:vm.execute(src)
                    self.assertEqual((vm.variables['s'],vm.variables['v']),(total,iterator))

    def test_host_reference_parameters_keep_same_actual_alias(self):
        def host(x,y): x.set(x.get()+1); y.set(y.get()+2)
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        vm.functions['host']=HostFunction('Host',host,reference_parameters=frozenset({0,1}))
        vm.execute('a=1;Host(a,a);r=a;')
        self.assertEqual(vm.variables['r'],4)

    def test_argument_division_error_keeps_source_position(self):
        source='Procedure F(x) Return;EndProcedure F(1/0);'
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(BSLRuntimeError) as caught:vm.execute(source,'refs.bsl')
        self.assertEqual(caught.exception.message,'Деление на ноль')
        self.assertEqual(caught.exception.line,1)
        self.assertEqual(caught.exception.source_line,source)

    def test_host_attribute_proxy_forwarding_keeps_alias(self):
        from types import SimpleNamespace
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext,HostMembers
        from tests.direct_boundary_compile import compile_boundary
        obj=SimpleNamespace(value=Decimal(1))
        context=BoundaryContext(members=(HostMembers(obj,readable=('value',),writable=('value',)),))
        source='Procedure F(x,y) x=x+1;y=y+2;EndProcedure Procedure G(z) F(z,z);EndProcedure G(obj.value);'
        compile_boundary(source).run({'obj':obj},context=context)
        self.assertEqual(obj.value,4)

    def test_failure_before_reference_does_not_publish_name(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaisesRegex(BSLRuntimeError,'Деление на ноль'):
            vm.execute('Procedure F(x) x=5;EndProcedure b=1/0;F(a);')
        self.assertNotIn('a',vm.variables)

    def test_index_argument_division_keeps_position(self):
        source='Procedure F(x,y) Return;EndProcedure a=New Array;F(a[1/0],2);'
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(BSLRuntimeError) as caught:vm.execute(source,'refs.bsl')
        self.assertEqual(caught.exception.message,'Деление на ноль')
        self.assertEqual(caught.exception.line,1)
        self.assertEqual(caught.exception.source_line,source)
