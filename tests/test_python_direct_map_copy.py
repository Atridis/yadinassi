"""Bounded FixedMap thaw: never silently downgrade canonical value-key equality."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.experimental_naked_collections import _TypedMap
from yadinassi.maps import BSLMap, BSLFixedMap
from yadinassi.syntax.parser import parse
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.dates import BSLDate
from yadinassi.values import BSLType, BSLNull
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.catalog_types import BSLCatalogReference, BSLCatalogType
from uuid import UUID


class DirectMapCopyTests(unittest.TestCase):
    def vm(self,backend='python-direct'):
        vm=Interpreter(execution_backend=backend);self.addCleanup(vm.close);return vm

    def test_routes_typed_keys_fresh_storage_shallow_aliases(self):
        source='''Key=New Array;Child=New Array;M=New Map;
M.Insert(True,"bool");M.Insert(1,"number");M.Insert("1",Undefined);M.Insert(Key,Child);
F=New FixedMap(M);T=New Map(F);U=New Соответствие(F);M.Clear();
T.Insert(1,"changed");T[Key].Add(7);T.Delete("1");
R=F.Get(1);B=T.Get(True);N=U.Count();C=U.Get(Key).Count();Missing=T.Get("absent");'''
        for route in ('source','ast','prepared'):
            with self.subTest(route=route):
                vm=self.vm()
                with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                    if route=='source':vm.execute(source)
                    elif route=='ast':vm.execute_program(parse(source))
                    else:vm.execute_prepared(vm.prepare(source))
                self.assertEqual(tuple(vm.variables[k] for k in ('r','b','n','c','missing')),('number','bool',4,1,None))
                self.assertIs(type(vm.variables['t']),_TypedMap)
                self.assertIs(vm.variables['u'].get(vm.variables['key']),vm.variables['child'])
                self.assertIsNot(vm.variables['t'],vm.variables['u'])
                self.assertEqual(vm.variables['f'].get(Decimal(1)),'number')

    def test_dynamic_copy_and_legacy_comparison(self):
        source='''M=New Map;M.Insert("K",1);F=New FixedMap(M);
Args=New Array;Args.Add(F);T=New("Map",Args);T.Insert("K",2);R=F.Get("K");V=T.Get("K");'''
        for backend in ('python-direct','compiled-strict'):
            vm=self.vm(backend);vm.execute(source)
            self.assertEqual((vm.variables['r'],vm.variables['v']),(1,2))

    def test_invalid_arity_source_runs_arguments_then_preserves_target(self):
        for source in ('T=New Map(Effect(),Effect());','T=New Map(Effect());'):
            vm=self.vm();events=[];vm.variables['t']=7
            vm.register_function('Effect',lambda:events.append('argument') or {})
            with self.assertRaises(BSLError):vm.execute(source)
            self.assertEqual(len(events),source.count('Effect()'));self.assertEqual(vm.variables['t'],7)

    def test_identity_keys_never_hash_compare_or_inspect_payloads(self):
        events=[]
        class Evil:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
            def __hash__(self):events.append('hash');raise AssertionError('hash')
            def __eq__(self,other):events.append('eq');raise AssertionError('eq')
        key=Evil();value=Evil();other=Evil();source=BSLMap();source.insert(key,value)
        fixed=BSLFixedMap(source);copy=_TypedMap(fixed)
        self.assertIs(copy.get(key),value);self.assertIsNone(copy.get(other));self.assertEqual(events,[])
        del copy[key];self.assertIs(fixed.get(key),value)

    def test_value_key_domains_explicitly_reject_atomically(self):
        keys=(BSLUUID('11111111-1111-1111-1111-111111111111'),BSLDate(123456789),BSLTypeDescription('String'),
            BSLCatalogReference(BSLCatalogType(UUID(int=1),'Catalog',object()),UUID(int=2)))
        for key in keys:
            with self.subTest(kind=type(key)):
                source=BSLMap();source.insert('first',1);source.insert(key,2)
                fixed=BSLFixedMap(source);vm=self.vm();vm.variables.update(f=fixed,saved=7)
                with self.assertRaisesRegex(BSLError,'canonical value-key semantics'):vm.execute('Saved=New Map(F);')
                self.assertEqual(vm.variables['saved'],7);self.assertEqual(len(fixed._items),2)
                self.assertEqual(fixed.get(key),2)

    def test_foreign_subclass_rebound_and_malformed_storage_do_not_call_hooks(self):
        events=[]
        class Foreign:
            def __iter__(self):events.append('iter');raise AssertionError('iter')
        class Child(BSLFixedMap):
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        class EvilDict(dict):
            def items(self):events.append('items');raise AssertionError('items')
        for value in (Foreign(),object.__new__(Child),{},[],None,BSLMap()):
            with self.assertRaises(TypeError):_TypedMap(value)
        for storage in (EvilDict(),{('bad',1):('x',1)},{(str,'x'):['x',1]},{(str,'wrong'):('x',1)}):
            fixed=BSLFixedMap(BSLMap());fixed._items=storage
            with self.assertRaises(TypeError):_TypedMap(fixed)
        source=BSLMap();source.insert('x',1);fixed=BSLFixedMap(source)
        def hook(self,name):events.append(name);raise AssertionError(name)
        with patch.object(BSLFixedMap,'__getattribute__',hook):copy=_TypedMap(fixed)
        self.assertEqual(copy.get('x'),1);self.assertEqual(events,[])

    def test_self_cycle_and_iteration_retains_original_keys(self):
        source=BSLMap();source.insert('self',source);source.insert(None,None)
        fixed=BSLFixedMap(source);copy=_TypedMap(fixed)
        self.assertIs(copy.get('self'),source);self.assertEqual(list(copy.items()),[('self',source),(None,None)])
        copy.clear();self.assertEqual(len(fixed._items),2)

    def test_forged_identity_token_cannot_bypass_value_key_rejection(self):
        key=BSLUUID('11111111-1111-1111-1111-111111111111')
        fixed=BSLFixedMap(BSLMap());fixed._items={(object,id(key)):(key,1)}
        with self.assertRaisesRegex(TypeError,'canonical value-key semantics'):_TypedMap(fixed)

    def test_definition_identity_survives_pre_lazy_rebinding(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            from unittest.mock import patch
            from yadinassi import maps
            m=maps.BSLMap();m.insert('x',1);source=maps.BSLFixedMap(m)
            class Fake:pass
            with patch.object(maps,'BSLFixedMap',Fake):
                from yadinassi.experimental_naked_collections import _TypedMap
                if _TypedMap(source).get('x')!=1:raise AssertionError('lost canonical snapshot')
                try:_TypedMap(Fake())
                except TypeError:pass
                else:raise AssertionError('counterfeit admitted')
        ''')
        result=subprocess.run([sys.executable]+(['-O'] if not __debug__ else [])+['-c',script],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_type_and_null_singletons_keep_lookup_semantics(self):
        source=BSLMap();source.insert(BSLType.STRING,'type');source.insert(BSLNull.VALUE,'null')
        source.insert(None,'undefined');fixed=BSLFixedMap(source);copy=_TypedMap(fixed)
        self.assertEqual(copy.get(BSLType.STRING),'type');self.assertEqual(copy.get(BSLNull.VALUE),'null')
        self.assertEqual(copy.get(None),'undefined');self.assertEqual(len(copy),3)
        copy[BSLNull.VALUE]='new';self.assertEqual(fixed.get(BSLNull.VALUE),'null')
