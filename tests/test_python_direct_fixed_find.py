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

    def test_date_needles_match_exact_ticks_for_named_and_captured_find(self):
        from yadinassi.temporal.dates import BSLDate, date
        vm = self.vm()
        vm.execute('''
            Point = Date(2024, 2, 29, 12, 34, 56);
            A = New Array;
            A.Add(Point + 0.0001); A.Add(Point); A.Add(Point);
            F = New FixedArray(A);
            AF = A.Find; FF = F.Найти;
        ''')
        vm.variables['needle'] = date('20240229123456')
        vm.variables['missing_date'] = date('20240229123457')
        with patch.object(BSLDate, '__eq__', side_effect=AssertionError('date equality hook')):
            for find in ('A.Find', 'AF', 'F.Find', 'FF'):
                with self.subTest(find=find):
                    self.assertEqual(vm.execute(f'{find}(Needle)'), Decimal(1))
                    self.assertIsNone(vm.execute(f'{find}(Missing_Date)'))

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

    def test_published_plain_array_named_and_captured_find_use_storage_not_hooks(self):
        from yadinassi.execution.direct.python_direct_plain_array import PlainArray
        vm=self.vm()
        # A closed module publishes the actual optimized Array representation.
        vm.execute('A=New Array;For I=1 To 4 Do A.Add(I);EndDo;')
        self.assertIs(type(vm.variables['a']),PlainArray)
        plan=vm.prepare('Named=A.Find(2); Saved=A.Найти; Captured=Saved(2);')
        def hostile(*args): raise AssertionError('PlainArray payload hook')
        with patch.object(PlainArray,'__iter__',hostile),patch.object(PlainArray,'__eq__',hostile):
            vm.execute_prepared(plan)
            self.assertIsNone(vm.execute('A.Find(True)'))
            self.assertEqual(vm.execute('Saved(4)'),Decimal(3))
        self.assertEqual(vm.variables['named'],Decimal(1))
        self.assertEqual(vm.variables['captured'],Decimal(1))
        # Native stored numerics in this lane are Decimal, not private integers.
        self.assertTrue(all(type(i) is Decimal for i in list.__iter__(vm.variables['a'])))
        with self.assertRaisesRegex(Exception,'Ожидается массив'):
            vm.execute('Other=A.Add;')

    def test_direct_collection_needles_are_identity_only_on_both_receivers(self):
        from yadinassi.execution.direct.python_direct_plain_array import PlainArray
        from yadinassi.execution.direct.python_direct_plain_map import PlainMap, PlainFixedMap
        vm=self.vm()
        vm.execute('A=New Array;A.Add(1);')
        self.assertIs(type(vm.variables['a']),PlainArray)
        vm.execute("""
            M=New Map; M[1]=7; Copy=New Map; Copy[1]=7;
            FM=New FixedMap(M); FC=New FixedMap(Copy); D=New Array;
            D.Add(M); D.Add(FM); D.Add(A); F=New FixedArray(D);
            DF=D.Find; FF=F.Find; M[1]=8;
            FrozenA=F[2]; SeparateSnapshot=New FixedArray(A); A[0]=9;
        """)
        # Native nested.freeze / nested.is-fixed-array / nested.after-source-write:
        # array cells are independently frozen; maps stay the original objects.
        self.assertIs(vm.execute('(TypeOf(F[2]) = Type("FixedArray"))'),True)
        self.assertEqual(vm.execute('F[2][0]'),Decimal(1))
        self.assertEqual(vm.execute('D[2][0]'),Decimal(9))
        self.assertIs(vm.execute('F[0]'),vm.variables['m'])
        self.assertIs(vm.execute('F[1]'),vm.variables['fm'])
        vm.variables['other_a']=PlainArray([Decimal(1)])
        def hostile(*args): raise AssertionError('needle equality')
        with patch.object(PlainMap,'__eq__',hostile),patch.object(PlainFixedMap,'__eq__',hostile,create=True),patch.object(PlainArray,'__eq__',hostile):
            for receiver in ('D.Find','DF','F.Find','FF'):
                fixed=receiver in ('F.Find','FF')
                for i,needle in enumerate(('M','FM','FrozenA' if fixed else 'A')):
                    with self.subTest(receiver=receiver, needle=needle):
                        self.assertEqual(vm.execute(f'{receiver}({needle})'),Decimal(i))
                opposite=('A','SeparateSnapshot') if fixed else ('FrozenA',)
                for other in ('Copy','FC','Other_A',*opposite):
                    with self.subTest(receiver=receiver, needle=other):
                        self.assertIsNone(vm.execute(f'{receiver}({other})'))

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
