"""Finite dynamic constructors preserve timing, identities and live admission."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.types.values import BSLArray, BSLType
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
from yadinassi.execution.direct.python_direct_plain_map import PlainMap as _TypedMap


class DirectDynamicNewTests(unittest.TestCase):
    def vm(self, *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions);self.addCleanup(vm.close);return vm

    def test_three_routes_use_exact_native_values_without_vm(self):
        code='Args=New Array;Args.Add(2);A=New(Type("Array"),Args);S=New("Structure");M=New("Map");'
        for route in ('source','ast','prepared'):
            with self.subTest(route=route):
                vm=self.vm()
                with ExitStack() as stack:
                    if route=='source':vm.execute(code)
                    elif route=='ast':vm.execute_program(parse(code))
                    else:vm.execute_prepared(vm.prepare(code))
                self.assertIs(type(vm.variables['a']),list);self.assertEqual(vm.variables['a'],[None,None])
                self.assertIs(type(vm.variables['s']),_DirectStructure)
                self.assertIs(type(vm.variables['m']),_TypedMap)

    def test_type_and_string_aliases(self):
        vm=self.vm()
        for target in ('"aRrAy"','"мАсСиВ"','Type("Array")','Type("Массив")'):
            self.assertIs(type(vm.execute('New('+target+')')),list)
        for target in ('Type("String")','" Array "','"Unknown"','Undefined','1','True'):
            with self.subTest(target=target),self.assertRaises(BSLError):vm.execute('New('+target+')')

    def test_order_and_invalid_target_validation_after_parameters(self):
        vm=self.vm(allow_extensions=True);events=[]
        vm.register_function('Kind',lambda:events.append('type') or 'Missing')
        vm.register_function('Params',lambda:events.append('parameters') or False)
        with self.assertRaises(BSLError):vm.execute('New(Kind(),Params())')
        self.assertEqual(events,['type','parameters'])
        events.clear()
        with self.assertRaises(BSLError):vm.execute('New(1/0,Params())')
        self.assertEqual(events,[])
        vm.execute('New("Array",Params())');self.assertEqual(events,['parameters'])

    def test_nonarray_ignored_without_user_coercion_or_iteration(self):
        class Hostile:
            def __str__(self):raise AssertionError('str')
            def __iter__(self):raise AssertionError('iter')
        vm=self.vm();vm.variables['hostile']=Hostile()
        self.assertEqual(vm.execute('New("Array",hostile)'),[])
        with self.assertRaises(BSLError):vm.execute('New(hostile)')
        self.assertEqual(vm.execute('New("Array",New FixedArray(New Array(3)))'),[])
        with self.assertRaises(BSLError):vm.execute('New("FixedArray",hostile)')

    def test_exact_argument_array_storage_and_budget_before_factory(self):
        from yadinassi.execution.direct import python_direct_dynamic_new as dynamic
        class Hostile:
            def __iter__(self):raise AssertionError('storage iterator')
        vm=self.vm();args=BSLArray();args.items=Hostile();vm.variables['args']=args
        with self.assertRaises(BoundaryViolation):vm.execute('New("Array",args)')
        args.items=[];self.assertEqual(vm.execute('New("Array",args)'),[])
        vm.variables['args']=[1,2]
        with patch.object(dynamic,'_MAX_ARGUMENTS',1):
            with self.assertRaisesRegex(BSLError,'предел аргументов'):vm.execute('New("Array",args)')
        class Child(list):
            def __iter__(self):raise AssertionError('subclass iterator')
        vm.variables['args']=Child([1]);self.assertEqual(vm.execute('New("Array",args)'),[])

    def test_parameter_snapshot_is_shallow_and_identity_preserved(self):
        vm=self.vm();vm.execute('Args=New Array;Args.Add("Self");Args.Add(Args);S=New("Structure",Args);')
        self.assertIs(vm.execute('S.Self'),vm.variables['args'])
        vm.execute('Args[0]="Other";');self.assertIs(vm.execute('S.Self'),vm.variables['args'])

    def test_finite_service_constructors_and_fixed_native_snapshots(self):
        vm=self.vm()
        for name in ('JSONReader','JSONWriter','ValueTable','NumberQualifiers','UUID'):
            with self.subTest(name=name):
                self.assertEqual(vm.execute('TypeOf(New("'+name+'"))'),vm.execute('Type("'+name+'")'))
        vm.execute('A=New("Array");A.Add(7);Args=New Array;Args.Add(A);F=New("FixedArray",Args);Args[0]=F;B=New("Array",Args);B[0]=9;')
        self.assertEqual(vm.execute('F[0]'),7);self.assertEqual(vm.execute('B[0]'),9)
        self.assertIs(type(vm.variables['b']),list)

    def test_plain_value_list_reports_canonical_type(self):
        for prepared in (False,True):
            vm=self.vm()
            code='L=New("ValueList"); Reported=TypeOf(L); After=True;'
            if prepared:vm.execute_prepared(vm.prepare(code))
            else:vm.execute(code)
            self.assertIs(vm.variables['reported'],BSLType.VALUE_LIST)
            self.assertIs(vm.variables['after'],True)

    def test_unknown_registered_factories_and_replacements_are_not_grants(self):
        vm=self.vm(allow_extensions=True);effects=[]
        factory=lambda *args:effects.append('factory')
        vm.register_type('Arbitrary',factory)
        for name in ('Arbitrary','JSONReader','Array','UUID','Query'):
            with self.subTest(name=name):
                vm.register_type(name,factory)
                with self.assertRaises((BSLError,BoundaryViolation)):vm.execute('New("'+name+'")')
                self.assertEqual(effects,[])

    def test_parameter_effect_updates_live_registry_before_admission(self):
        vm=self.vm(allow_extensions=True);effects=[]
        def replace():
            effects.append('params');vm.register_type('Array',lambda:effects.append('bad'));return None
        vm.register_function('Replace',replace)
        with self.assertRaises(BoundaryViolation):vm.execute('New("Array",Replace())')
        self.assertEqual(effects,['params'])

    def test_owner_revocation_and_constructor_failure_preserve_target(self):
        vm=self.vm(allow_extensions=True);vm.execute('Saved=7;')
        def close():vm.close();return None
        vm.register_function('CloseOwner',close)
        with self.assertRaises(BoundaryViolation):vm.execute('Saved=New("Array",CloseOwner())')
        self.assertEqual(vm.variables['saved'],7)
        other=self.vm();other.execute('Saved=7;')
        with self.assertRaises(BSLError):other.execute('Saved=New("Unknown")')
        self.assertEqual(other.variables['saved'],7)

    def test_eval_execute_and_imported_factory(self):
        vm=self.vm();vm.execute('B=Undefined;Kind=Type("Array");A=Eval("New(Kind)");Execute("B=New(Kind);");')
        self.assertIs(type(vm.variables['a']),list);self.assertIs(type(vm.variables['b']),list)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'Factory.bsl').write_text('Function Make(Val Kind) Export Return New(Kind);EndFunction',encoding='utf-8')
            value=vm.execute('// #Import Factory.bsl\nFactory.Make("Array")',str(root/'Main.bsl'))
            self.assertIs(type(value),list)


    def test_runtime_source_coordinates_and_prepared_live_admission(self):
        vm=self.vm(allow_extensions=True);plan=vm.prepare('Saved=New("JSONReader");','dynamic.bsl')
        vm.execute_prepared(plan)
        vm.register_type('JSONReader',lambda:None)
        with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        with self.assertRaises(BSLError) as caught:vm.execute('X=1;\nNew("Missing")','dynamic.bsl')
        self.assertEqual((caught.exception.source,caught.exception.line,caught.exception.column),('dynamic.bsl',2,1))

    def test_argument_items_descriptor_is_rejected_without_getter_effect(self):
        vm=self.vm();vm.variables['args']=BSLArray();effects=[]
        def getter(value):effects.append('getter');return []
        with patch.object(BSLArray,'items',property(getter),create=True):
            with self.assertRaises(BoundaryViolation):vm.execute('New("Array",args)')
        self.assertEqual(effects,[])

    def test_type_descriptor_is_not_authority_or_executed(self):
        vm=self.vm();vm.variables['kind']=BSLType.ARRAY;effects=[]
        def getter(value):effects.append('getter');return 'Arbitrary'
        with patch.object(BSLType,'value',property(getter),create=True):
            self.assertEqual(vm.execute('New(kind)'),[])
        self.assertEqual(effects,[])

    def test_pre_lazy_argument_descriptor_patch_is_rejected(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            from yadinassi import Interpreter
            from yadinassi.types.values import BSLArray
            from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
            from unittest.mock import patch
            vm=Interpreter();vm.variables['args']=BSLArray();effects=[]
            def getter(value):effects.append('getter');return []
            with patch.object(BSLArray,'items',property(getter),create=True):
                try:vm.execute('New("Array",args)')
                except BoundaryViolation:pass
                else:raise RuntimeError('admitted hostile descriptor')
            if effects:raise RuntimeError('getter executed')
        ''')
        result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-c',script],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class DirectDynamicCopyOrderTests(unittest.TestCase):
    def test_copy_does_not_mutate_definition_time_collection_classes(self):
        from copy import copy, deepcopy
        from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI
        for cls,mro,fields in _DIRECT_COLLECTION_CLASS_ABI:
            self.assertTrue(all('__slots__' not in vars(base) for base in mro))
            value=BSLArray() if cls is BSLArray else object.__new__(cls)
            for copier in (copy,deepcopy):
                copier(value)
                self.assertEqual(len(vars(cls)),len(fields))
                self.assertTrue(all(vars(cls).get(k) is v for k,v in fields))

    def test_copied_argument_arrays_work_before_and_after_lazy_import(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            from copy import copy,deepcopy
            from decimal import Decimal
            from yadinassi import Interpreter
            from yadinassi.types.values import BSLArray
            vm=Interpreter()
            for copier in (copy,deepcopy):
                args=BSLArray();args.items=[Decimal(2)]
                vm.variables['args']=copier(args)
                if vm.execute('New("Array",args)') != [None,None]:raise RuntimeError('shape')
            vm.close()
        ''')
        result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-c',script],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_mutated_or_replaced_copy_cache_is_not_accepted(self):
        from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI
        for cls,mro,fields in _DIRECT_COLLECTION_CLASS_ABI:
            for change in ('replace','append','delete','foreign'):
                with self.subTest(cls=cls.__name__,change=change):
                    vm=Interpreter();vm.variables['args']=BSLArray()
                    slots=vars(cls)['__slotnames__']
                    try:
                        if change=='replace':cls.__slotnames__=[]
                        elif change=='append':slots.append('items')
                        elif change=='delete':del cls.__slotnames__
                        else:cls._foreign_dynamic_test=True
                        with self.assertRaises(BoundaryViolation):vm.execute('New("Array",args)')
                    finally:
                        if change=='append':slots.clear()
                        elif change=='foreign':del cls._foreign_dynamic_test
                        else:cls.__slotnames__=slots
                        vm.close()

    def test_legacy_slotted_subclass_keeps_its_own_copy_cache(self):
        from copy import copy, deepcopy
        from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI
        class Slotted(BSLArray):
            __slots__=('extra',)
        source=Slotted();source.items=['items'];source.extra=['extra']
        for copier in (copy,deepcopy):
            result=copier(source)
            self.assertEqual(result.items,source.items)
            self.assertEqual(result.extra,source.extra)
            for cls,mro,fields in _DIRECT_COLLECTION_CLASS_ABI:
                self.assertEqual(len(vars(cls)),len(fields))
                self.assertTrue(all(vars(cls).get(k) is v for k,v in fields))
