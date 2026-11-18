"""Exact native Array operators preserve BSL identity, not Python contents."""
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.experimental_naked_scalar_semantics import array_equal,array_not_equal


class DirectArrayEqualityTests(unittest.TestCase):
    def vm(self,backend='python-direct'):
        vm=Interpreter(execution_backend=backend);self.addCleanup(vm.close);return vm

    def test_alias_distinct_empty_equal_nested_and_cyclic(self):
        for left,right in (([],[]),([1],[1]),([[1]],[[1]])):
            self.assertIs(array_equal(left,left),True)
            self.assertIs(array_not_equal(left,left),False)
            self.assertIs(array_equal(left,right),False)
            self.assertIs(array_not_equal(left,right),True)
        left=[];right=[];left.append(left);right.append(right)
        self.assertIs(array_equal(left,right),False)
        self.assertIs(array_equal(left,left),True)

    def test_no_element_or_mixed_operand_callbacks(self):
        events=[]
        class Hostile:
            def __eq__(self,other):events.append('eq');raise AssertionError('callback')
            def __ne__(self,other):events.append('ne');raise AssertionError('callback')
        first=[Hostile()];second=[Hostile()]
        for left,right in ((first,second),(first,Hostile()),(Hostile(),first)):
            self.assertIs(array_equal(left,right),False)
            self.assertIs(array_not_equal(left,right),True)
        self.assertEqual(events,[])

    def test_non_array_operators_are_unchanged(self):
        for left,right in ((True,Decimal(1)),(None,None),('a','a'),(Decimal('1'),Decimal('1.00'))):
            self.assertEqual(array_equal(left,right),left==right)
            self.assertEqual(array_not_equal(left,right),left!=right)
        class Host:
            def __eq__(self,other):return 'eq'
            def __ne__(self,other):return 'ne'
        self.assertEqual(array_equal(Host(),Host()),'eq')
        self.assertEqual(array_not_equal(Host(),Host()),'ne')

    def test_mixed_types_match_existing_legacy_contract(self):
        # Native fixed-vs-mutable comparisons and legacy values.equal's exact
        # type gate establish False for mixed kinds, symmetrically.
        for backend in ('python-direct','compiled-strict'):
            vm=self.vm(backend);vm.execute('A=New Array;F=New FixedArray(A);S=New Structure;M=New Map;')
            for other in ('F','S','M','Undefined','True','0','""','Type("Array")'):
                for left,right in (('A',other),(other,'A')):
                    with self.subTest(backend=backend,left=left,right=right):
                        self.assertIs(vm.execute('('+left+'='+right+')'),False)
                        self.assertIs(vm.execute('('+left+'<>'+right+')'),True)

    def test_source_ast_prepared_eval_execute(self):
        source='A=New Array;B=New Array;Alias=A;Same=(A=Alias);Different=(A<>B);'
        for route in ('source','ast','prepared','eval','execute'):
            vm=self.vm()
            with self.subTest(route=route):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                elif route=='execute':vm.execute('Var A,B,Alias,Same,Different;Execute("'+source+'");')
                else:
                    vm.execute('A=New Array;B=New Array;Same=Eval("A=A");Different=Eval("A<>B");')
                self.assertIs(vm.variables['same'],True);self.assertIs(vm.variables['different'],True)

    def test_effect_order_and_single_evaluation(self):
        for operator in ('=','<>'):
            vm=self.vm();events=[];left=[];right=[]
            vm.register_function('LeftValue',lambda:events.append('left') or left)
            vm.register_function('RightValue',lambda:events.append('right') or right)
            self.assertIs(vm.execute('(LeftValue()'+operator+'RightValue())'),operator=='<>')
            self.assertEqual(events,['left','right'])

    def test_experiment_opt_in_is_explicit(self):
        from tests.retired_text_compiler import prepare
        source='A=New Array;B=New Array;Same=(A=B);'
        for repairs,expected in (((),True),(('array_identity_equality',),False)):
            scope=prepare(source,repairs=repairs,_trusted_entry=True).run({})
            self.assertIs(scope['same'],expected)

    def test_direct_comparison_has_no_vm_fallback(self):
        from contextlib import ExitStack
        from unittest.mock import patch
        vm=self.vm()
        with ExitStack() as stack:
            for method in ('block','call_routine'):
                stack.enter_context(patch.object(Interpreter,method,side_effect=AssertionError('VM fallback')))
            stack.enter_context(patch('yadinassi.runtime.binary_values',side_effect=AssertionError('VM operator fallback')))
            self.assertIs(vm.execute('(New Array=New Array)'),False)

    def test_known_and_boundary_dates_match_legacy_in_both_directions(self):
        from yadinassi.dates import BSLDate,MAX_TICKS
        for backend in ('python-direct','compiled-strict'):
            vm=self.vm(backend);vm.execute('A=New Array;')
            for ticks in (0,MAX_TICKS):
                for boundary in (False,True):
                    vm.variables['d']=BSLDate(ticks,boundary=boundary)
                    for left,right in (('A','D'),('D','A')):
                        for operator in ('=','<>'):
                            with self.subTest(backend=backend,ticks=ticks,boundary=boundary,left=left,operator=operator):
                                vm.execute('Saved=7;Caught=False;Try Saved=('+left+operator+right+');Except Caught=True;EndTry;')
                                self.assertIs(vm.variables['caught'],boundary)
                                self.assertEqual(vm.variables['saved'],Decimal(7) if boundary else operator=='<>')

    def test_array_date_gate_uses_canonical_slot_not_host_callbacks(self):
        from unittest.mock import patch
        from yadinassi.dates import BSLDate,UnsupportedDateRange
        events=[];date=BSLDate(0,boundary=True)
        with patch.object(BSLDate,'require_known',lambda self:events.append('require')):
            for left,right in (([],date),(date,[])):
                with self.assertRaises(UnsupportedDateRange):array_equal(left,right)
                with self.assertRaises(UnsupportedDateRange):array_not_equal(left,right)
        with patch.object(BSLDate,'boundary',property(lambda self:events.append('descriptor') or False)):
            with self.assertRaises(UnsupportedDateRange):array_equal([],date)
        self.assertEqual(events,[])

    def test_null_enum_and_foreign_mixed_kinds_do_not_add_callbacks(self):
        from yadinassi.values import NULL,BSLType
        from yadinassi.type_qualifiers import BSLAllowedSign
        for other in (NULL,BSLType.ARRAY,BSLAllowedSign.ANY):
            for left,right in (([],other),(other,[])):
                self.assertIs(array_equal(left,right),False)
                self.assertIs(array_not_equal(left,right),True)

    def test_static_primitive_literals_exclude_helper_but_variables_do_not(self):
        from tests.retired_text_compiler import prepare
        for literal in ('1','True','"x"','Undefined'):
            for left,right in (('X',literal),(literal,'X')):
                for operator in ('=','<>'):
                    plan=prepare('X=1;R=('+left+operator+right+');',repairs=('array_identity_equality',),_trusted_entry=True)
                    self.assertNotIn('_array_equal(',plan.generated_source)
                    self.assertNotIn('_array_not_equal(',plan.generated_source)
        for operator,helper in (('=','_array_equal('),('<>','_array_not_equal(')):
            plan=prepare('X=1;Y=1;R=(X'+operator+'Y);',repairs=('array_identity_equality',),_trusted_entry=True)
            self.assertIn(helper,plan.generated_source)
        # Parenthesized literals are deliberately not inferred/unwrapped.
        plan=prepare('X=1;R=(X=(1));',repairs=('array_identity_equality',),_trusted_entry=True)
        self.assertIn('_array_equal(',plan.generated_source)

    def test_literal_comparisons_evaluate_dynamic_operand_once(self):
        for operator in ('=','<>'):
            for left,right in (('Effect()','1'),('1','Effect()')):
                vm=self.vm();events=[]
                vm.register_function('Effect',lambda:events.append('effect') or Decimal(1))
                self.assertIs(vm.execute('('+left+operator+right+')'),operator=='=')
                self.assertEqual(events,['effect'])
        # Two variable expressions still take the identity helper in LTR order.
        self.test_effect_order_and_single_evaluation()

    def test_date_unknown_vs_primitive_literals_preserves_original_errors(self):
        from yadinassi.dates import BSLDate
        vm=self.vm();vm.variables['d']=BSLDate(0,boundary=True)
        for literal in ('1','True','"date"','Undefined'):
            for left,right in (('D',literal),(literal,'D')):
                for operator in ('=','<>'):
                    with self.subTest(left=left,right=right,operator=operator):
                        vm.execute('Saved=7;Caught=False;Try Saved=('+left+operator+right+');Except Caught=True;EndTry;')
                        self.assertIs(vm.variables['caught'],True)
                        self.assertEqual(vm.variables['saved'],Decimal(7))

    def test_scalar_literal_behaviors_and_array_mixed_literals(self):
        vm=self.vm();vm.execute('N=1;A=New Array;')
        for source,expected in (('N=True',True),('N=1.00',True),('N<>"1"',True),
                                ('A=Undefined',False),('False<>A',True),('A=""',False),('1<>A',True)):
            self.assertIs(vm.execute('('+source+')'),expected)

    def test_literal_exclusion_is_exact_not_subclass_admission(self):
        from tests.retired_text_compiler import prepare
        class CustomInt(int):pass
        class CustomString(str):pass
        for value,excluded in ((1,True),(True,True),(Decimal(1),True),('x',True),(None,True),
                               (CustomInt(1),False),(CustomString('x'),False),([],False)):
            program=parse('X=1;R=X=1;');program[-1].value.right.value=value
            plan=prepare('',parsed_ast=program,repairs=('array_identity_equality',),_trusted_entry=True)
            self.assertEqual('_array_equal(' not in plan.generated_source,excluded)
