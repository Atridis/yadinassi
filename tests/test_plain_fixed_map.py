import unittest
from decimal import Decimal as D
from types import MappingProxyType
from yadinassi import Interpreter, BSLError
from yadinassi.execution.direct.python_direct_plain_map import PlainMap,PlainFixedMap,plain_map
from yadinassi.execution.direct.python_direct_fixed import construct
from yadinassi.collections.maps import BSLMap,BSLFixedMap
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class PlainFixedMapTests(unittest.TestCase):
    def test_shallow_native_snapshot_and_reverse_copy(self):
        child=[];source=PlainMap();source[True]=child;source[D(1)]=child
        fixed=construct(BSLFixedMap,(source,))
        self.assertIs(type(fixed._items),MappingProxyType)
        self.assertEqual(len(fixed._items),1)
        source[True]='changed';source['new']=2
        self.assertIs(fixed.get(D(1)),child);self.assertIsNone(fixed.get('new'))
        child.append(3);self.assertEqual(fixed.get(True),[3])
        with self.assertRaises(TypeError):fixed._items[True]=4
        copied=plain_map(fixed);self.assertIs(copied[True],child)
        copied[True]=5;self.assertIs(fixed.get(True),child)
    def test_default_execute_and_prepared(self):
        source='''M=New Map;A=New Array;A.Add(1);M.Insert("K",A);
F=New FixedMap(M);M.Insert("K",7);A.Add(2);
C=F.Get("K").Count();N=F.Count();R=New Map(F);N2=R.Count();
S=String(F);T=TypeOf(F);I=0;For Each Pair In F Do I=I+1;EndDo;'''
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual((vm.variables['c'],vm.variables['n'],vm.variables['n2'],vm.variables['i']),(2,1,1,1))
            self.assertEqual(vm.variables['s'],'ФиксированноеСоответствие')
            with self.assertRaises((BSLError,BoundaryViolation)):vm.execute('F["K"]=9;')
            with self.assertRaises(BSLError):vm.execute('Missing=F["absent"];')
            with self.assertRaises(BSLError):vm.execute('F.Known=9;')
    def test_legacy_typed_key_contract_unchanged(self):
        source=BSLMap();source.insert(True,'bool');source.insert(D(1),'number')
        fixed=construct(BSLFixedMap,(source,))
        self.assertIs(type(fixed),BSLFixedMap)
        self.assertEqual((fixed.get(True),fixed.get(D(1))),('bool','number'))
    def test_scalar_key_boundary_and_unknown_snapshot(self):
        class Key:
            def __hash__(self):raise AssertionError('hash')
        fixed=PlainFixedMap(PlainMap())
        with self.assertRaises(TypeError):fixed.get(Key())
        from yadinassi.formats.storage import value_storage
        with self.assertRaises(value_storage.SnapshotError):value_storage.capture(fixed)
