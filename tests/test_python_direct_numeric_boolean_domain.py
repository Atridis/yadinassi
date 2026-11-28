"""Exact BSL Number/Boolean operator domain does not admit Python numeric hosts."""
from decimal import Decimal,localcontext,Inexact,Rounded
import unittest
from yadinassi import Interpreter,BSLError
from yadinassi.syntax.parser import parse

class DirectNumericBooleanDomainTests(unittest.TestCase):
    def test_host_values_both_orders_bool_values_literal_and_variable_routes(self):
        class Child(Decimal):pass
        for host in (0,1,0.0,1.0,Child('0'),Child('1')):
            for boolean in (False,True):
                code='A=(Host=B);C=(B=Host);D=(Host<>B);E=(B<>Host);F=(Host=True);G=(False=Host);'
                for route in ('source','ast','prepared','execute','eval'):
                    vm=Interpreter();vm.variables.update(host=host,b=boolean)
                    with self.subTest(host=type(host).__name__,boolean=boolean,route=route):
                        if route=='source':vm.execute(code)
                        elif route=='ast':vm.execute_program(parse(code))
                        elif route=='prepared':vm.execute_prepared(vm.prepare(code))
                        elif route=='execute':vm.execute('Var A,C,D,E,F,G;Execute("'+code+'");')
                        else:vm.execute('A=Eval("Host=B");C=Eval("B=Host");D=Eval("Host<>B");E=Eval("B<>Host");F=Eval("Host=True");G=Eval("False=Host");')
                    self.assertEqual(tuple(vm.variables[k] for k in ('a','c','d','e','f','g')),(False,False,True,True,False,False))


    def test_all_comparison_operand_effects_once_in_order_without_host_hooks(self):
        events=[]
        class HostDecimal(Decimal):
            def __eq__(self,other):raise AssertionError('host equality')
            def __lt__(self,other):raise AssertionError('host ordering')
            def __gt__(self,other):raise AssertionError('host ordering')
        vm=Interpreter(allow_extensions=True);vm.register_function('L',lambda:events.append('left') or HostDecimal(1));vm.register_function('R',lambda:events.append('right') or True)
        for operation in ('=','<>','<','<=','>','>='):
            events.clear()
            if operation in ('=','<>'):self.assertIs(vm.execute('(L()'+operation+'R())'),operation=='<>')
            else:
                with self.assertRaises(BSLError):vm.execute('(L()'+operation+'R())')
            self.assertEqual(events,['left','right'])


    def test_registered_host_objects_keep_unrelated_equality(self):
        from yadinassi.types.values import BSLObject
        events=[]
        class Host(BSLObject):
            def __eq__(self,other):events.append('eq');return True
            def __ne__(self,other):events.append('ne');return False
        vm=Interpreter(allow_extensions=True);vm.register_function('Factory',Host)
        vm.execute('L=Factory();R=Factory();A=(L=R);B=(L<>R);C=(L=True);D=(False<>R);')
        self.assertEqual((vm.variables['a'],vm.variables['b'],vm.variables['c'],vm.variables['d']),(True,False,False,True))
        self.assertEqual(events,['eq','ne'])

    def test_cached_plan_uses_live_types(self):
        code='R=(Host=True);'
        vm=Interpreter();plan=vm.prepare(code)
        for value,expected in ((Decimal(1),True),(1,False),(True,True),(1.0,False)):
            vm.variables['host']=value;vm.execute_prepared(plan);self.assertIs(vm.variables['r'],expected)


if __name__=='__main__':unittest.main()
