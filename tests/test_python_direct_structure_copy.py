"""Direct mutable snapshots of exact FixedStructure, without VM dispatch."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.experimental_naked_structure import new_structure, structure_items, _DirectStructure
from yadinassi.collections.structures import BSLFixedStructure
from yadinassi.syntax.parser import parse


class DirectStructureCopyTests(unittest.TestCase):
    def vm(self,backend='python-direct', *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions, execution_backend=backend);self.addCleanup(vm.close);return vm

    def test_routes_shallow_copy_case_spelling_order_and_independent_top_level(self):
        source='''A=New Array;A.Add(1);S=New Structure("ß,SS,Child",0,2,A);
F=New FixedStructure(S);T=New Structure(F);U=New Структура(F);
T.sS=7;T.Child.Add(3);T.Insert("Other",9);T.Delete("Child");
R=F.ss;V=U.SS;N=F.Child.Count();M=U.Count();'''
        for route in ('source','ast','prepared'):
            with self.subTest(route=route):
                vm=self.vm()
                with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                    if route=='source':vm.execute(source)
                    elif route=='ast':vm.execute_program(parse(source))
                    else:vm.execute_prepared(vm.prepare(source))
                self.assertEqual(tuple(vm.variables[k] for k in ('r','v','n','m')),(2,2,2,2))
                self.assertEqual(list(structure_items(vm.variables['t'])),[('SS',Decimal(7)),('Other',Decimal(9))])
                self.assertIs(vm.variables['u']['Child'],vm.variables['a'])
                self.assertIsNot(vm.variables['t'],vm.variables['u'])
                self.assertIsNot(vm.variables['u'],vm.variables['f']._items)
                self.assertIs(type(vm.variables['t']),_DirectStructure)

    def test_native_copy_contract_and_empty(self):
        source='''F=New FixedStructure("Name,Count",1,2);T=New Structure(F);
T.Name=3;T.Delete("Count");T.Insert("Next",4);R=F.Name;N=F.Count();
Empty=New Structure(New FixedStructure);E=Empty.Count();'''
        observations=[]
        for backend in ('python-direct','compiled-strict'):
            vm=self.vm(backend);vm.execute(source)
            observations.append(tuple(vm.variables[k] for k in ('r','n','e')))
        self.assertEqual(observations,[(1,2,0),(1,2,0)])

    def test_extra_actuals_run_then_error_and_old_target_is_not_replaced(self):
        for backend in ('python-direct','compiled-strict'):
            vm=self.vm(backend, allow_extensions=True);events=[]
            vm.register_function('Effect',lambda:events.append('rhs') or 4)
            vm.execute('F=New FixedStructure("X",1);T=7;Try T=New Structure(F,Effect());Except Error=ErrorDescription();EndTry;')
            self.assertEqual(events,['rhs']);self.assertEqual(vm.variables['t'],7)
            self.assertIn('Копирование структуры ожидает один аргумент',vm.variables['error'])

    def test_dynamic_constructor_uses_same_thaw(self):
        vm=self.vm();vm.execute('F=New FixedStructure("X",1);Args=New Array;Args.Add(F);T=New("Structure",Args);T.X=2;R=F.X;')
        self.assertIs(type(vm.variables['t']),_DirectStructure)
        self.assertEqual(vm.variables['r'],1)

    def test_payload_aliases_cycles_and_no_protocol_calls(self):
        events=[]
        class Evil:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
            def __eq__(self,other):events.append('eq');raise AssertionError('eq')
        value=Evil();fixed=BSLFixedStructure('Value',value)
        result=new_structure(fixed)
        self.assertIs(result['Value'],value);self.assertEqual(events,[])
        vm=self.vm();vm.execute('S=New Structure("Self");S.Self=S;F=New FixedStructure(S);T=New Structure(F);')
        self.assertIs(vm.variables['t']['Self'],vm.variables['s'])

    def test_rejects_subclasses_foreign_and_malformed_storage_without_hooks(self):
        events=[]
        class Child(BSLFixedStructure):
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        class Foreign:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        class EvilDict(dict):
            def items(self):events.append('items');raise AssertionError('items')
        for value in (object.__new__(Child),Foreign(),{},[],''):
            if type(value) is str:continue
            with self.assertRaises(TypeError):new_structure(value)
        for storage in (EvilDict(),{'x':['X',1]},{'x':('Wrong',1)},{1:('X',1)}):
            fixed=BSLFixedStructure();fixed._items=storage
            with self.assertRaises(TypeError):new_structure(fixed)
        self.assertEqual(events,[])

    def test_rebound_class_and_receiver_hooks_are_not_called(self):
        fixed=BSLFixedStructure('X',1);events=[]
        def hook(self,name):events.append(name);raise AssertionError(name)
        with patch.object(BSLFixedStructure,'__getattribute__',hook):
            result=new_structure(fixed)
        self.assertEqual(result['X'],1);self.assertEqual(events,[])
        class Fake:pass
        with patch('yadinassi.collections.structures.BSLFixedStructure',Fake):
            self.assertEqual(new_structure(fixed)['X'],1)
            with self.assertRaises(TypeError):new_structure(Fake())

    def test_definition_identity_survives_pre_lazy_name_rebinding(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            from unittest.mock import patch
            from yadinassi.collections import structures
            source=structures.BSLFixedStructure('X',1)
            class Fake:pass
            with patch.object(structures,'BSLFixedStructure',Fake):
                from yadinassi.execution.codegen.experimental_naked_structure import new_structure
                if new_structure(source)['X']!=1:raise AssertionError('lost canonical copy')
                try:new_structure(Fake())
                except TypeError:pass
                else:raise AssertionError('counterfeit admitted')
        ''')
        result=subprocess.run([sys.executable]+(['-O'] if not __debug__ else [])+['-c',script],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_foreach_on_exact_boxed_structure_and_map(self):
        from yadinassi.collections.maps import BSLMap
        from yadinassi.collections.structures import BSLStructure

        vm = self.vm(allow_extensions=True)
        mapping = BSLMap()
        mapping.insert("Key", Decimal(7))
        vm.variables.update(structure=BSLStructure("Key", Decimal(3)), mapping=mapping)
        source = """
            Total=0; Names="";
            For Each Entry In Structure Do
                Total=Total+Entry.Value; Names=Names+Entry.Key;
            EndDo;
            For Each Entry In Mapping Do
                Total=Total+Entry.Value; Names=Names+Entry.Key;
            EndDo;
        """
        vm.execute_prepared(vm.prepare(source))
        self.assertEqual(vm.variables["total"], Decimal(10))
        self.assertEqual(vm.variables["names"], "KeyKey")
