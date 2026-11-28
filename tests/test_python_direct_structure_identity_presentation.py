"""Exact direct Structure identity and canonical collection String presentation."""
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.codegen.direct_structure import new_structure
from yadinassi.syntax.parser import parse


class DirectStructureIdentityTests(unittest.TestCase):
    def test_self_alias_equal_copy_and_cycles_are_separate(self):
        source='''S=New Structure("Self");S.Self=S;Alias=S;T=New Structure("Self");T.Self=S;
SelfEqual=(S=S);AliasEqual=(S=Alias);CopyEqual=(S=T);CopyDifferent=(S<>T);
A=New Structure("Value",1);B=New Structure("Value",1);EqualContents=(A=B);'''
        expected=(True,True,False,True,False)
        for backend in ('python-direct',):
            vm=Interpreter(execution_backend=backend);vm.execute(source)
            self.assertEqual(tuple(vm.variables[key] for key in ('selfequal','aliasequal','copyequal','copydifferent','equalcontents')),expected)
        fixture=(Path(__file__).resolve().parents[1]/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        # Native restored mutable Structures with equal contents are distinct.
        # Self/alias is a separate canonical-runtime control, not a new capture.
        self.assertIn('internal.structure.independent-equal.restored-pair-equal: [false]\n',fixture)
        self.assertIn('internal.structure.repeated-reference.restored-pair-equal: [false]\n',fixture)

    def test_routes_keep_identity_and_fill_is_shallow_without_vm(self):
        source='S=New Structure("Self");S.Self=S;T=New Structure("Self");FillPropertyValues(T,S);R=(T.Self=S);N=(T.Self<>T);'
        for route in ('source','ast','prepared','execute','eval'):
            with self.subTest(route=route),ExitStack() as stack:
                vm=Interpreter()
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                elif route=='execute':vm.execute('Var S,T,R,N;Execute("'+source.replace('"','""')+'");')
                else:
                    vm.execute(source);vm.execute('R=Eval("T.Self=S");N=Eval("T.Self<>T");')
                self.assertIs(vm.variables['r'],True);self.assertIs(vm.variables['n'],True)
                self.assertIs(vm.variables['t']['Self'],vm.variables['s'])


        # This slice deliberately does not reinterpret raw host dictionaries.


    def test_operand_effect_order_is_unchanged(self):
        vm=Interpreter(allow_extensions=True);calls=[]
        vm.register_function('Left',lambda:calls.append('left') or new_structure())
        vm.register_function('Right',lambda:calls.append('right') or new_structure())
        self.assertIs(vm.execute('(Left()=Right())'),False);self.assertEqual(calls,['left','right'])


class DirectCollectionStringTests(unittest.TestCase):
    def test_exact_containers_aliases_and_nested_cycles_do_not_visit_payload(self):
        vm=Interpreter();calls=[]
        class Hostile:
            def __str__(self):calls.append('str');raise AssertionError
            def __repr__(self):calls.append('repr');raise AssertionError
        vm.variables['payload']=Hostile()
        vm.execute('A=New Array;A.Add(Payload);A.Add(A);S=New Structure("Value",Payload);M=New Map;M.Insert("Value",Payload);R=String(A);Q=Строка(S);T=String(M);')
        self.assertEqual(tuple(vm.variables[k] for k in ('r','q','t')),('Массив','Структура','Соответствие'))
        self.assertEqual(calls,[])
        fixture=(Path(__file__).resolve().parents[1]/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        for kind,key in (('array','r'),('structure','q'),('map','t')):
            self.assertIn('internal.'+kind+'.present: ['+vm.variables[key]+']\n',fixture)

    def test_adapter_keeps_captured_exact_class_identity_after_rebinding(self):
        from yadinassi.execution.codegen import direct_structure as structures,direct_collections as collections
        vm=Interpreter();calls=[]
        class Hostile:
            def __repr__(self):calls.append('repr');raise AssertionError
        vm.variables['payload']=Hostile()
        vm.execute('S=New Structure("X",Payload);M=New Map;M.Insert("X",Payload);Warm=String(S);')
        class Foreign:pass
        with patch.object(structures,'_DirectStructure',Foreign),patch.object(collections,'_TypedMap',Foreign):
            vm.execute('R=String(S);Q=String(M);')
        self.assertEqual((vm.variables['r'],vm.variables['q']),('Структура','Соответствие'));self.assertEqual(calls,[])

    def test_overrides_and_custom_callable_equality_are_not_rewritten(self):
        vm=Interpreter(allow_extensions=True);calls=[]
        class Custom:
            def __eq__(self,other):calls.append('eq');raise AssertionError
            def __call__(self,value):calls.append('call');return 'custom'
        vm.register_function('String',Custom())
        vm.execute('A=New Array;R=String(A);Q=Строка(A);')
        self.assertEqual(vm.variables['r'],'custom');self.assertEqual(vm.variables['q'],'Массив')
        self.assertEqual(calls,['call'])

    def test_captured_canonical_service_matches_named_without_name_rebinding(self):
        vm=Interpreter(allow_extensions=True);vm.variables['saved']=vm.functions['string']
        vm.execute('A=New Array;Named=String(A);Captured=Saved(A);')
        self.assertEqual((vm.variables['named'],vm.variables['captured']),('Массив','Массив'))
        vm.register_function('String',lambda value:'custom')
        vm.execute('Named=String(A);Captured=Saved(A);')
        self.assertEqual((vm.variables['named'],vm.variables['captured']),('custom','Массив'))
        calls=[]
        def change():
            vm.variables['saved'].function=lambda value:calls.append('foreign')
            return []
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('Saved(Change());')
        self.assertEqual(calls,[])

    def test_canonical_implementation_mutation_and_revocation_stay_fatal(self):
        for action in ('replace','close'):
            vm=Interpreter(allow_extensions=True);calls=[]
            def change():
                if action=='replace':vm.functions['string'].function=lambda value:calls.append('foreign')
                else:vm.close()
                return []
            vm.register_function('Change',change)
            with self.subTest(action=action),self.assertRaises(BoundaryViolation):vm.execute('R=String(Change());')
            self.assertEqual(calls,[]);self.assertNotIn('r',vm.variables)

    def test_non_direct_values_keep_canonical_service_semantics(self):
        vm=Interpreter();calls=[]
        class Subclass(list):
            def __str__(self):calls.append('subclass');return 'host subtype'
        vm.variables['sub']=Subclass()
        vm.execute('A=String(True);B=String(1.25);C=String(Undefined);D=String(Sub);')
        self.assertEqual(tuple(vm.variables[k] for k in ('a','b','c','d')),('Да','1,25','','host subtype'))
        self.assertEqual(calls,['subclass'])

    def test_new_representation_has_no_vm_dispatch(self):
        vm=Interpreter();vm.execute_prepared(vm.prepare('R=String(New Array);'))
        self.assertEqual(vm.variables['r'],'Массив')
