"""Restored mutable Structure properties are exact local ByRef addresses."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.collections.structures import BSLFixedStructure, BSLStructure
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.codegen.direct_reference_runtime import local_field_reference
from yadinassi.execution.direct.python_direct import make_boundary


SETUP = '''
Var Obj, Trace; Trace="";
Obj=ValueFromStringInternal(ValueToStringInternal(New Structure("Abc",1)));
'''
STORE = 'Procedure Store(X,Val Value) X=Value; EndProcedure '


class LocalStructureCellsTests(unittest.TestCase):
    def vm(self, **options):
        vm=Interpreter(**options)
        self.addCleanup(vm.close)
        return vm

    def test_restored_property_address_tracks_reinserted_field_and_spelling(self):
        vm=self.vm()
        vm.execute_prepared(vm.prepare(SETUP+'''
            Function Earlier() Trace=Trace+"R"; Return Obj; EndFunction
            Function Later()
                Trace=Trace+"V"; Obj.Delete("aBC"); Obj.Insert("ABC",6); Return 1;
            EndFunction
            Function Step(X,Val N) X=X+N; Return X; EndFunction
            R=Step(Earlier().AbC,Later());
        '''))
        obj=vm.variables['obj']
        self.assertIs(type(obj),BSLStructure)
        self.assertEqual(obj._items,{'abc':('ABC',Decimal(7))})
        self.assertEqual(vm.variables['r'],7)
        self.assertEqual(vm.variables['trace'],'RV')
        self.assertEqual(vm.execute('Obj.aBC'),7)

    def test_missing_field_fails_at_binding_or_live_use(self):
        vm=self.vm()
        with self.assertRaisesRegex(BSLError,'Свойство структуры не найдено'):
            vm.execute(SETUP+STORE+'''
                Function Later() Trace="ran"; Return 9; EndFunction
                Store(Obj.Absent,Later());
            ''')
        self.assertEqual(vm.variables['trace'],'')
        with self.assertRaisesRegex(BSLError,'Свойство структуры не найдено'):
            vm.execute(SETUP+STORE+'''
                Function Later() Trace="ran"; Obj.Delete("abc"); Return 9; EndFunction
                Store(Obj.ABC,Later());
            ''')
        self.assertEqual(vm.variables['trace'],'ran')
        self.assertEqual(vm.variables['obj']._items,{})

    def test_binding_does_not_read_an_unused_property(self):
        vm=self.vm()
        vm.execute(SETUP)
        plan=vm.prepare('Procedure Ignore(X) EndProcedure Ignore(Obj.ABC);')
        hits=[]
        original=BSLStructure.get_member
        def observe(receiver, name):
            hits.append(name)
            return original(receiver, name)
        with patch.object(BSLStructure, 'get_member', observe):
            vm.execute_prepared(plan)
        self.assertEqual(hits,[])

    def test_same_property_alias_writes_through_with_partial_failure(self):
        vm=self.vm()
        vm.execute(SETUP+'''
            Procedure Pair(X,Y) X=8; Y=X+Y; Raise "after writes"; EndProcedure
            Try Pair(Obj.AbC,Obj.aBC); Except EndTry;
        ''')
        self.assertEqual(vm.variables['obj']._items,{'abc':('Abc',Decimal(16))})

    def test_only_own_live_backing_namespace_and_touched_hooks(self):
        vm=self.vm()
        context=make_boundary(vm)
        context.enter()
        self.addCleanup(context.leave)
        obj=BSLStructure('U',1)
        address=local_field_reference(context,obj,'u')
        backing=obj._items
        seen=[]
        def hostile(*_args):seen.append('hook');raise AssertionError
        with patch.object(BSLStructure,'set',hostile):
            with self.assertRaises(BoundaryViolation):address.set(7)
        obj._items={'u':('U',6)}
        with self.assertRaises(BoundaryViolation):address.set(7)
        self.assertEqual((backing,obj._items),({'u':('U',1)},{'u':('U',6)}))
        obj._items=backing
        context.revoke()
        with self.assertRaisesRegex(BoundaryViolation,'authority revoked'):address.get()
        self.assertEqual(seen,[])

    def test_hostile_raw_key_is_not_hashed_or_compared_in_bsl(self):
        vm=self.vm()
        seen=[]
        class Hostile:
            def __hash__(self):return hash('abc')
            def __eq__(self,other):seen.append('key');raise AssertionError
        obj=BSLStructure()
        obj._items[Hostile()]=('Abc',1)
        vm.variables['obj']=obj
        with self.assertRaises(BoundaryViolation):vm.execute(STORE+'Store(Obj.Abc,9);')
        self.assertEqual(seen,[])
        self.assertEqual(list(obj._items.values()),[('Abc',1)])

    def test_subclasses_fixed_and_dynamic_calls_keep_prior_surface(self):
        vm=self.vm()
        vm.execute(SETUP)
        vm.execute(STORE)
        with self.assertRaises(BoundaryViolation):vm.execute('Store(Obj.Abc,9);')
        obj=vm.variables['obj']
        vm.variables['fixed']=BSLFixedStructure(obj)
        with self.assertRaises(BSLError):vm.execute(STORE+'Store(Fixed.Abc,9);')
        self.assertEqual(vm.variables['fixed'].get('abc'),1)
        seen=[]
        class Foreign(BSLStructure):
            def get_member(self,name):seen.append(name);raise AssertionError
        vm.variables['obj']=Foreign('Abc',1)
        with self.assertRaises(BoundaryViolation):vm.execute(STORE+'Store(Obj.Abc,9);')
        self.assertEqual(seen,[])
