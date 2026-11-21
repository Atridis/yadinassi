"""Exact fixed-collection identity lookup does not grant host equality authority."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_scalar_semantics import typed_find, UnsupportedScalarSemantics
from yadinassi.types.values import BSLFixedArray, BSLArray
from yadinassi.collections.structures import BSLFixedStructure
from yadinassi.collections.maps import BSLFixedMap, BSLMap
from yadinassi.syntax.parser import parse


class DirectFixedFindTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter();self.addCleanup(vm.close);return vm

    def test_source_ast_prepared_match_recorded_native_find_labels(self):
        native=(Path(__file__).resolve().parents[1]/'integrational_tests/fill_exclude_native/collections.out').read_text(encoding='utf-8')
        expected={line.split(': ',1)[0]:line.split(': ',1)[1] for line in native.splitlines() if '.find-' in line}
        for kind,source in (('array','New FixedArray(New Array)'),('structure','New FixedStructure("X",1)'),('map','New FixedMap(New Map)')):
            for route in ('source','ast','prepared'):
                with self.subTest(kind=kind,route=route):
                    text=f'A={source};B={source};Bag=New Array;Bag.Add(A);Bag.Add(A);Alias=A;R=Bag.Find(Alias);S=Bag.Найти(B);'
                    vm=self.vm()
                    with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                        if route=='source':vm.execute(text)
                        elif route=='ast':vm.execute_program(parse(text))
                        else:vm.execute_prepared(vm.prepare(text))
                    self.assertEqual('['+str(vm.variables['r'])+']',expected['fixed-'+kind+'.find-alias'])
                    self.assertIsNone(vm.variables['s']);self.assertEqual(expected['fixed-'+kind+'.find-copy'],'[]')
                    self.assertIs(type(vm.variables['r']),Decimal)

    def test_exact_fixed_values_ignore_payload_and_equality_hooks(self):
        events=[]
        class Evil:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        values=(BSLFixedArray(BSLArray()),BSLFixedStructure('X',Evil()),BSLFixedMap(BSLMap()))
        def hook(self,*args):events.append('hook');raise AssertionError('hook')
        for value in values:
            kind=type(value)
            with patch.object(kind,'__eq__',hook,create=True),patch.object(kind,'__getattribute__',hook):
                self.assertEqual(typed_find([Evil(),value,value],value),Decimal(1))
                self.assertIsNone(typed_find([Evil()],value))
        self.assertEqual(events,[])

    def test_fixed_subclass_keys_are_identity_only_foreign_and_receivers_rejected(self):
        events=[]
        class Meta(type):
            def __eq__(self,other):events.append('class eq');raise AssertionError('class eq')
            def __hash__(self):events.append('class hash');raise AssertionError('class hash')
        class Foreign(metaclass=Meta):
            def __eq__(self,other):events.append('eq');raise AssertionError('eq')
        class Child(BSLFixedStructure):pass
        class ListChild(list):pass
        value=Foreign()
        with self.assertRaises(UnsupportedScalarSemantics):typed_find([value],value)
        child=Child('X',1)
        self.assertEqual(typed_find([child],child),Decimal(0))
        self.assertIsNone(typed_find([child],Child('X',1)))
        fixed=BSLFixedStructure('X',1)
        with self.assertRaises(UnsupportedScalarSemantics):typed_find(ListChild([fixed]),fixed)
        self.assertIsNone(typed_find([Foreign(),Child('X',1)],fixed));self.assertEqual(events,[])

    def test_first_index_different_fixed_types_and_strict_scalar_keys(self):
        a=BSLFixedArray(BSLArray());b=BSLFixedStructure();c=BSLFixedMap(BSLMap())
        bag=[True,Decimal(1),'1',None,b,c,a,a]
        for value,index in ((a,6),(b,4),(c,5),(True,0),(Decimal(1),1),('1',2),(None,3)):
            self.assertEqual(typed_find(bag,value),Decimal(index))
        self.assertIsNone(typed_find(bag,BSLFixedArray(BSLArray())))

    def test_pre_lazy_class_rebinding_never_admits_fake(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            from unittest.mock import patch
            from yadinassi.types import values
            from yadinassi.collections import structures, maps
            originals=(values.BSLFixedArray(values.BSLArray()),structures.BSLFixedStructure(),maps.BSLFixedMap(maps.BSLMap()))
            class Fake:pass
            with patch.object(values,'BSLFixedArray',Fake),patch.object(structures,'BSLFixedStructure',Fake),patch.object(maps,'BSLFixedMap',Fake):
                from yadinassi.execution.codegen.experimental_naked_scalar_semantics import typed_find,UnsupportedScalarSemantics
                for value in originals:
                    if typed_find([value],value)!=0:raise AssertionError('lost canonical identity')
                fake=Fake()
                try:typed_find([fake],fake)
                except UnsupportedScalarSemantics:pass
                else:raise AssertionError('counterfeit admitted')
        ''')
        result=subprocess.run([sys.executable]+(['-O'] if not __debug__ else [])+['-c',script],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
