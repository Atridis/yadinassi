"""Top-level JSON procedure call-site metadata, not new JSON capabilities."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.json_processing import BSLJSONWriter
from yadinassi.experimental_naked_boundaries import BoundaryViolation

class DirectJSONProceduresTests(unittest.TestCase):
    def test_routes_reject_without_mutation_or_vm(self):
        for route in ('source','ast','prepared','execute','eval'):
            with self.subTest(route=route),patch.object(Interpreter,'block',side_effect=AssertionError('VM')):
                vm=Interpreter();vm.execute('W=New JSONWriter;W.SetString();');code='X=W.WriteStartObject();'
                with self.assertRaises(BSLError):
                    if route=='source':vm.execute(code)
                    elif route=='ast':vm.execute_program(parse(code))
                    elif route=='prepared':vm.execute_prepared(vm.prepare(code))
                    elif route=='execute':vm.execute('Execute("'+code+'");')
                    else:vm.execute('Eval("W.WriteStartObject()");')
                vm.execute('W.WriteValue(1);');self.assertEqual(vm.execute('W.Close()'),'1')

    def test_bilingual_procedures_reject_before_argument_effects(self):
        for ctor,method in (('JSONWriter','WriteValue'),('ЗаписьJSON','ЗаписатьЗначение'),
                            ('JSONReader','SetString'),('ЧтениеJSON','УстановитьСтроку')):
            vm=Interpreter();vm.execute('R=New '+ctor+';');seen=[]
            vm.register_function('Effect',lambda:seen.append(1) or 'null')
            with self.subTest(method=method),self.assertRaises(BSLError):vm.execute('X=R.'+method+'(Effect());')
            self.assertEqual(seen,[])

    def test_cached_plan_live_receiver_and_captured_metadata(self):
        vm=Interpreter();vm.execute('W=New JSONWriter;W.SetString();');seen=[]
        vm.register_function('Effect',lambda:seen.append(1) or 1)
        plan=vm.prepare('X=W.WriteValue(Effect());')
        for _ in range(2):
            with self.assertRaises(BSLError):vm.execute_prepared(plan)
        vm.variables['saved']=vm.variables['w'].get_method('WriteValue')
        with self.assertRaises(BSLError):vm.execute('X=Saved(Effect());')
        self.assertEqual(seen,[])
        vm.execute('Saved(1);');self.assertEqual(vm.execute('W.Close()'),'1')

    def test_class_and_instance_metadata_hooks_reject_without_execution(self):
        for mode in ('class','instance','subclass'):
            vm=Interpreter();vm.execute('W=New JSONWriter;');seen=[]
            def hostile(*args):seen.append('hook');raise AssertionError('hook')
            with self.subTest(mode=mode):
                if mode=='class':
                    with patch.object(BSLJSONWriter,'get_member',hostile),self.assertRaises(BoundaryViolation):vm.execute('X=W.WriteValue(1);')
                elif mode=='instance':
                    vm.variables['w'].get_method=hostile
                    with self.assertRaises(BoundaryViolation):vm.execute('X=W.WriteValue(1);')
                else:
                    class Foreign(BSLJSONWriter):get_method=hostile
                    vm.variables['w']=Foreign()
                    with self.assertRaises(BoundaryViolation):vm.execute('X=W.WriteValue(1);')
                self.assertEqual(seen,[])

    def test_revocation_closed_owner_and_captured_policy_remain_fatal(self):
        from yadinassi.python_direct import make_boundary
        for mode in ('revoked','closed','context'):
            vm=Interpreter();vm.execute('W=New JSONWriter;W.SetString();')
            context=make_boundary(vm);context.start();writer=vm.variables['w']
            if mode=='revoked':context.revoke()
            elif mode=='closed':vm.close()
            else:vm._context_stack[-1]='server'
            with self.subTest(mode=mode),self.assertRaises(BoundaryViolation):
                context.resolve_member_call(writer,'WriteValue',require_value=True)
            self.assertEqual(writer._parts,[])
        vm=Interpreter();vm.execute('W=New JSONWriter;W.SetString();')
        writer=vm.variables['w'];context=make_boundary(vm);context.start()
        saved=writer.get_method('WriteValue');invoke=context.resolve_callable(saved)
        context.policy=lambda operation,name:False
        with self.assertRaises(BoundaryViolation):invoke(1)
        self.assertEqual(writer._parts,[])

    def test_canonical_control_rejects_procedure_before_effects(self):
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend);seen=[]
            vm.register_function('Effect',lambda:seen.append(1) or 1)
            vm.execute('W=New JSONWriter;W.SetString();')
            with self.subTest(backend=backend),self.assertRaises(BSLError):vm.execute('X=W.WriteValue(Effect());')
            self.assertEqual(seen,[])
            vm.execute('W.WriteValue(1);');self.assertEqual(vm.execute('W.Close()'),'1')

    def test_foreign_metaclass_not_consulted_by_new_callsite_gate(self):
        from yadinassi.python_direct_database import CatalogBoundary
        seen=[]
        class HostileMeta(type):
            def __eq__(self,other):seen.append('eq');raise AssertionError('eq')
            __hash__=type.__hash__
        class Foreign(metaclass=HostileMeta):pass
        sentinel=object()
        class ExistingBoundary:
            def resolve_member_call(self,*args,**kwargs):return sentinel
        class Context(CatalogBoundary,ExistingBoundary):pass
        self.assertIs(Context().resolve_member_call(Foreign(),'Call',require_value=True),sentinel)
        self.assertEqual(seen,[])

    def test_read_functions_and_statements_keep_existing_contract(self):
        vm=Interpreter();vm.execute('R=New JSONReader;R.SetString("1");A=R.Read();B=R.Skip();R.Close();')
        self.assertIs(vm.execute('A'),True);self.assertIs(vm.execute('B'),False)
        with self.assertRaises(BSLError):vm.execute('X=R.Close();')

if __name__=='__main__':unittest.main()
