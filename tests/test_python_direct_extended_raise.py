"""Bounded direct structured Raise; native observations are a named projection."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.error_info import BSLErrorCategory, BSLErrorInfo
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse


class DirectExtendedRaiseTests(unittest.TestCase):
    def test_source_ast_prepared_all_fields_order_and_definition_location(self):
        source='''Var Order;Order="";
Function Part(Val X) Order=Order+X;Return X;EndFunction
Try Raise(Part("D"),,Part("C"),Part("A"));
Except E=ErrorInfo();EndTry;
R=E.Code;A=E.AdditionalInformation;S=E.InitialString;'''
        for route in ('source','ast','prepared'):
            with self.subTest(route=route), ExitStack() as stack:
                vm=Interpreter()
                if route=='source':vm.execute(source,'raise.bsl')
                elif route=='ast':vm.execute_program(parse(source,'raise.bsl'))
                else:vm.execute_prepared(vm.prepare(source,'raise.bsl'))
                self.assertEqual(vm.variables['order'],'DCA')
                self.assertEqual(vm.variables['r'],'C');self.assertEqual(vm.variables['a'],'A')
                self.assertEqual(vm.variables['s'],source.splitlines()[2])
                self.assertEqual(vm.variables['e'].module_name,'raise.bsl')

    def test_excess_manual_ast_arguments_do_not_run_optional_effects(self):
        from copy import deepcopy
        for route in ('ast','prepared'):
            with self.subTest(route=route):
                vm=Interpreter(allow_extensions=True);effects=[]
                vm.register_function('Description',lambda:effects.append('description') or 'x')
                vm.register_function('Optional',lambda:effects.append('optional') or 'x')
                nodes=parse('Try Raise(Description(),Optional());Except E=ErrorInfo();EndTry;')
                raised=nodes[0].body[0]
                raised.optional_arguments=[deepcopy(raised.optional_arguments[0]) for _ in range(5)]
                if route=='ast':vm.execute_program(nodes)
                else:vm.execute_prepared(vm.prepare_program(nodes))
                self.assertEqual(effects,['description'])
                self.assertIn('не более 5',vm.variables['e'].description)

    def test_all_optional_effects_before_validation_and_no_repeat(self):
        vm=Interpreter(allow_extensions=True);effects=[]
        vm.register_function('Part',lambda x:effects.append(x) or x)
        vm.execute('Try Raise(Part("D"),Part(1),Part("C"),Part("A"),Part("bad-cause"));Except E=ErrorInfo();EndTry;')
        self.assertEqual(effects,['D',1,'C','A','bad-cause'])
        self.assertIn('КатегорияОшибки',vm.variables['e'].description)
        self.assertFalse(vm.execute('E.IsErrorOfCategory(ErrorCategory.ExceptionRaisedFromScript)'))

    def test_description_conversion_precedes_optional_effects_without_host_str(self):
        vm=Interpreter(allow_extensions=True);effects=[]
        class Hostile:
            def __str__(self):effects.append('str');raise AssertionError
        vm.register_function('Value',lambda:Hostile())
        vm.register_function('Effect',lambda:effects.append('optional') or 'C')
        with self.assertRaises(BoundaryViolation):vm.execute('Raise(Value(),,Effect());')
        self.assertEqual(effects,[])
        vm.execute('Try Raise True;Except E=ErrorInfo();EndTry;')
        self.assertEqual(vm.variables['e'].description,'Да')

    def test_snapshot_and_category_queries_do_not_call_python_hooks(self):
        vm=Interpreter();vm.execute('Try Raise("inner",ErrorCategory.ConfigurationError,"I");Except Saved=ErrorInfo();EndTry;')
        plan=vm.prepare('Try Raise("outer",,"O",,Saved);Except E=ErrorInfo();EndTry;R=E.IsErrorOfCategory(ErrorCategory.ConfigurationError);C=E.Cause.Code;')
        calls=[]
        def hostile(*args):calls.append('hook');raise AssertionError('foreign hook')
        with patch.object(BSLErrorCategory,'__hash__',hostile),patch.object(BSLErrorCategory,'__eq__',hostile),patch.object(BSLErrorInfo,'__getattribute__',hostile):
            vm.execute_prepared(plan)
            self.assertTrue(vm.variables['r']);self.assertEqual(vm.variables['c'],'I')
        self.assertEqual(calls,[])

    def test_query_wrapper_does_not_use_public_hostfunction_constructor(self):
        from yadinassi.types import values
        vm=Interpreter();vm.execute('Try Raise("x",ErrorCategory.ConfigurationError);Except E=ErrorInfo();EndTry;')
        plan=vm.prepare('Q=E.IsErrorOfCategory;R=Q(ErrorCategory.ConfigurationError);S=E.IsErrorOfCategory(ErrorCategory.ConfigurationError);Before=ErrorInfo();Try Raise \"new\";Except Current=ErrorInfo();Description=ErrorDescription();EndTry;')
        calls=[]
        def foreign(*args,**kwargs):calls.append('constructor');raise AssertionError
        with patch.object(values,'HostFunction',foreign):
            vm.execute_prepared(plan)
        self.assertEqual(calls,[]);self.assertTrue(vm.variables['r']);self.assertTrue(vm.variables['s'])

    def test_foreign_categories_and_causes_do_not_call_hooks(self):
        vm=Interpreter();calls=[]
        class Hostile:
            def __hash__(self):calls.append('hash');raise AssertionError
            def __eq__(self,other):calls.append('eq');raise AssertionError
            def __str__(self):calls.append('str');raise AssertionError
        vm.variables['bad']=Hostile()
        for code in ('Raise("x",Bad);','Raise("x",,,,Bad);'):
            with self.assertRaises(BSLRuntimeError):vm.execute(code)
        self.assertEqual(calls,[])

    def test_malformed_cycle_and_foreign_cause_remain_fatal(self):
        for kind in ('cycle','foreign','categories','empty'):
            vm=Interpreter();value=BSLErrorInfo('x')
            if kind=='cycle':object.__setattr__(value,'cause',value)
            elif kind=='foreign':object.__setattr__(value,'cause',object())
            elif kind=='categories':object.__setattr__(value,'categories',frozenset((object(),)))
            else:object.__setattr__(value,'_empty',1)
            vm.variables['bad']=value
            with self.subTest(kind=kind),self.assertRaises(BoundaryViolation):
                vm.execute('Try Raise("x",,,,Bad);Except Swallowed=True;EndTry;')
            self.assertNotIn('swallowed',vm.variables)

    def test_saved_category_query_validates_current_boundary_and_cause(self):
        vm=Interpreter(allow_extensions=True);vm.execute('Try Raise("x",ErrorCategory.ConfigurationError);Except E=ErrorInfo();EndTry;Q=E.IsErrorOfCategory;')
        vm.execute('R=Q(ErrorCategory.ConfigurationError);');self.assertTrue(vm.variables['r'])
        vm.register_function('Close',lambda:vm.close() or BSLErrorCategory.CONFIGURATION_ERROR)
        with self.assertRaises(BoundaryViolation):vm.execute('Q(Close());')

    def test_last_argument_revocation_cannot_be_swallowed(self):
        vm=Interpreter(allow_extensions=True);events=[]
        vm.register_function('Close',lambda:events.append('close') or vm.close())
        with self.assertRaises(BoundaryViolation):
            vm.execute('Try Raise("x",,"C","A",Close());Except Swallowed=True;EndTry;')
        self.assertEqual(events,['close']);self.assertNotIn('swallowed',vm.variables)

    def test_undefined_cause_query_is_recoverable_but_foreign_receiver_is_not(self):
        vm=Interpreter();vm.execute('Try Raise "x";Except E=ErrorInfo();EndTry;Try R=E.Cause.Code;Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught'])
        vm.variables['foreign']=object()
        with self.assertRaises(BoundaryViolation):vm.execute('Foreign.Code')

    def test_28_named_native_exception_records_exact_not_full_functions_parity(self):
        from scripts.native_historical_replay import (EXTENDED_EXCEPTION_PROBE_BLOCKS as E,
            EXCEPTION_CONTEXT_PROBE_BLOCKS as C,without_exported_variable_probes)
        root=Path(__file__).resolve().parents[1]
        source=without_exported_variable_probes((root/'integrational_tests/tests/functions.bsl').read_text(encoding='utf-8'))
        fixture=json.loads((root/'tests/fixtures/extended_exceptions_linux.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),fixture['source_sha256'])
        parts=[]
        for start,end in (E[0],C[0],E[1],C[1]):
            self.assertEqual(source.count(start),1);self.assertEqual(source.count(end),1)
            parts.append(source.split(start)[1].split(end)[0])
        output=[]
        Interpreter(output.append,native_target=fixture['native_target']).execute('\n'.join(parts))
        self.assertEqual(len(output),28)
        self.assertEqual(output,fixture['records'])
