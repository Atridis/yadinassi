"""FixedMap canonical snapshots without losing direct keys or mutable aliases."""
import unittest
import gc
import weakref
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.execution.direct.python_direct_plain_map import PlainFixedMap, PlainMap
from yadinassi.types.unique_identifiers import BSLUUID
from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct_services import ServicesBoundary

class DirectFixedMapTests(unittest.TestCase):
    def test_routes_typed_keys_snapshot_and_missing_index(self):
        source='M=New Map;M.Insert(True,"bool");M.Insert(1,"number");M.Insert("1",Undefined);F=New ФиксированноеСоответствие(M);M.Insert(1,"changed");'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            if route=='source':vm.execute(source)
            elif route=='ast':vm.execute_program(parse(source))
            else:vm.execute_prepared(vm.prepare(source))
            self.assertIs(type(vm.variables['f']),PlainFixedMap)
            self.assertEqual(vm.execute('F.Count()'),3)
            self.assertEqual(vm.execute('F[True]'),'bool');self.assertEqual(vm.execute('F[1]'),'number')
            self.assertEqual(vm.execute('F.Get(True)'),'bool');self.assertEqual(vm.execute('F.Get(1.00)'),'number')
            self.assertEqual(vm.execute('M[1]'),'changed')
            self.assertIsNone(vm.execute('F["1"]'));self.assertIsNone(vm.execute('F.Get("absent")'))
            with self.assertRaises(BSLError):vm.execute('F["absent"]')

    def test_scalar_key_shallow_values_and_unsupported_host_key(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('V=New Array;M=New Map;M.Insert("child",V);F=New FixedMap(M);V.Add(2);M.Clear();R=F.Get("child");')
        self.assertIs(vm.variables['r'],vm.variables['v']);self.assertEqual(vm.execute('R[0]'),2)
        class HostKey(list):
            def __hash__(self):raise AssertionError('hash')
            def __eq__(self, other):raise AssertionError('eq')
        vm.variables['k']=HostKey()
        vm.execute('After=False;')
        with self.assertRaisesRegex(BSLError, 'scalar Python value'):
            vm.execute('M.Insert(K,V);After=True;')
        self.assertIs(vm.variables['after'],False)
        self.assertEqual(vm.execute('M.Count()'),0)
        self.assertIs(vm.variables['f'].get('child'),vm.variables['v'])

    def test_collection_keys_have_the_same_identity_across_writes_and_snapshots(self):
        script = """
            M=New Map; A=New Array; S=New Structure("X", 1); Other=New Map;
            FA=New FixedArray(A); FS=New FixedStructure(S); FM=New FixedMap(Other);
            M.Insert(A, "array"); M[S]="structure"; M[Other]=Undefined;
            M[FA]="fixed-array"; M.Insert(FS,"fixed-structure"); M.Insert(FM,"fixed-map");
            M[M]="self"; M[True]="bool"; M[1]="number";
            A.Add(7); S.X=2; Other[1]=2;
            F=New FixedMap(M); Copy=New Map(F); M.Delete(A); M.Clear();
        """
        for route in ('source','ast','prepared'):
            with self.subTest(route=route):
                vm=Interpreter(); self.addCleanup(vm.close)
                if route=='source': vm.execute(script)
                elif route=='ast': vm.execute_program(parse(script))
                else: vm.execute_prepared(vm.prepare(script))
                for name, expected in (
                    ('A','array'),('S','structure'),('Other',None),('FA','fixed-array'),
                    ('FS','fixed-structure'),('FM','fixed-map'),('M','self'),
                    ('True','bool'),('1.00','number'),
                ):
                    self.assertEqual(vm.execute(f'F[{name}]'),expected)
                    self.assertEqual(vm.execute(f'Copy.Get({name})'),expected)
                self.assertEqual(vm.execute('F.Count()'),9)
                self.assertEqual(vm.execute('String(Copy)'), 'Соответствие')
                self.assertEqual(vm.execute_prepared(vm.prepare('String(F)')),
                                 'ФиксированноеСоответствие')
                self.assertEqual(vm.execute('M.Count()'),0)
                self.assertIsNone(vm.execute('F.Get(New FixedArray(A))'))
                with self.assertRaisesRegex(BSLError,'Ключ фиксированного соответствия не найден'):
                    vm.execute('F[New FixedArray(A)]')
                self.assertIsNone(vm.execute('Copy[New Array]'))
                self.assertEqual(vm.execute("""
                    Found=False;
                    For Each Pair In F Do
                        If Pair.Value="array" Then Pair.Key.Add(8); Found=True; EndIf;
                    EndDo;
                    Found
                """),True)
                self.assertEqual(vm.execute('A[1]'),8)
                vm.execute('Copy.Delete(A);')
                self.assertEqual(vm.execute('F[A]'),'array')
                self.assertEqual(vm.execute('Copy.Count()'),8)

    def test_identity_keys_stay_live_only_while_an_entry_is_retained(self):
        class Payload: pass
        marker=Payload(); ref=weakref.ref(marker); key=[marker]
        data=PlainMap(); data.setdefault(key,'item')
        self.assertIs(next(iter(data)),key)
        self.assertIs(next(iter(data.copy().items()))[0],key)
        self.assertIs(next(iter(PlainMap(data).keys())),key)
        fixed=PlainFixedMap(data)
        taken, value = data.popitem()
        self.assertIs(taken,key)
        self.assertEqual(value,'item')
        del taken, key, marker
        gc.collect()
        self.assertIsNotNone(ref())
        del fixed
        gc.collect()
        self.assertIsNone(ref())

    def test_identity_key_codecs_still_reject_unserializable_keys(self):
        vm=Interpreter(); self.addCleanup(vm.close)
        from yadinassi.formats.storage.value_storage import capture, SnapshotError
        vm.execute('M=New Map; K=New Array; M[K]=7; F=New FixedMap(M); W=New JSONWriter; W.SetString();')
        for name in ('M','F'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(BSLError,'недопустимый ключ соответствия'):
                    vm.execute(f'ValueToStringInternal({name})')
        with self.assertRaisesRegex(SnapshotError, 'invalid native map key'):
            capture(vm.variables['m'], _source_direct=True)
        with self.assertRaisesRegex(BSLError, 'JSON: ожидается Строка'):
            vm.execute('WriteJSON(W,F);')
        self.assertEqual(vm.execute('WriteJSON(W,7); W.Close()'),'7')

    def test_canonical_host_map_retains_object_identity_keys(self):
        key=[];child=[];mapping=BSLMap();mapping.insert(key,child)
        fixed=BSLFixedMap(mapping);mapping.clear();child.append(2)
        self.assertIs(fixed.get(key),child)
        self.assertIsNone(fixed.get([]))

    def test_equal_canonical_keys_cannot_silently_drop_direct_entries(self):
        vm=Interpreter();a=BSLUUID('11111111-1111-1111-1111-111111111111');b=BSLUUID(str(a))
        mapping=_TypedMap();mapping[a]=1;mapping[b]=2;vm.variables.update(m=mapping,saved=7)
        with self.assertRaises(BSLError):vm.execute('Saved=New FixedMap(M);')
        self.assertEqual(vm.variables['saved'],7);self.assertEqual(len(mapping),2)
        del mapping[b];vm.execute('F=New FixedMap(M);')
        self.assertEqual(vm.variables['f'].get(b),1)

    def test_hostile_object_keys_do_not_call_hash_or_equality(self):
        class Key:
            def __hash__(self):raise AssertionError('hash')
            def __eq__(self,other):raise AssertionError('equality')
        a=Key();b=Key();source=_TypedMap();source[a]=1;source[b]=2
        vm=Interpreter();vm.variables['m']=source;vm.execute('F=New FixedMap(M);')
        self.assertEqual(vm.variables['f'].get(a),1);self.assertEqual(vm.variables['f'].get(b),2)

    def test_canonical_source_and_noncanonical_roots(self):
        vm=Interpreter();mapping=BSLMap();mapping.insert('x',1);vm.variables['m']=mapping
        vm.execute('F=New FixedMap(M);');mapping.insert('x',2);self.assertEqual(vm.execute('F.Get("x")'),1)
        class Child(_TypedMap):pass
        for bad in ({},Child(),vm.variables['f']):
            vm.variables['bad']=bad
            with self.assertRaises(BSLError):vm.execute('New FixedMap(Bad)')

    def test_readonly_iteration_and_private_fields(self):
        vm=Interpreter();vm.execute('M=New Map;M.Insert("x",1);F=New FixedMap(M);S=0;For Each P In F Do S=S+P.Value;EndDo;')
        self.assertEqual(vm.variables['s'],1)
        for text in ('F["x"]=3','F.Insert("x",3)','F.Clear()','F._items','P.Value=2'):
            with self.assertRaises(BSLError):vm.execute(text)
        self.assertEqual(vm.execute('F["x"]'),1)

    def test_constructor_binding_and_policy_are_live(self):
        vm=Interpreter(allow_extensions=True);factory=vm.types['fixedmap'];seen=[]
        def change():factory.function=lambda *a:seen.append(1);return _TypedMap()
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('New FixedMap(Change())')
        self.assertEqual(seen,[])
        class Boundary(ServicesBoundary,BoundaryContext):pass
        vm=Interpreter(allow_extensions=True);events=[]
        context=Boundary(policy=lambda op,name:events.append((op,name)) or False);context.vm=vm;context.start()
        with self.assertRaises(BoundaryViolation):context.resolve_service('new:fixedmap')(_TypedMap())
        self.assertEqual(events,[('call_value',vm.types['fixedmap'].name.casefold())])
