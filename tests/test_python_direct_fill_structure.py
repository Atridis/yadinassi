"""Finite direct property transfer: native traversal and hostile boundaries."""
from decimal import Decimal
from itertools import product
from unittest import TestCase
from unittest.mock import patch

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_structure import new_structure, _DirectStructure
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342
from yadinassi.execution.direct.python_direct_fill import fill


class DirectFillStructureTests(TestCase):
    def vm(self, target=WINDOWS_8_3_27_2342, *, allow_extensions=False):
        return Interpreter(allow_extensions=allow_extensions, native_target=target)

    def test_selection_matrix_preserves_errors_partial_writes_and_key_order(self):
        missing = 'Свойство структуры не найдено: Missing'
        whitespace = 'Пустые имена или пробелы в списках свойств пока не поддерживаются'
        invalid = 'Недопустимое имя свойства структуры: bad-name'
        excluded_missing = 'Отсутствующие исключаемые свойства пока не поддерживаются'
        copied = (None, 10, 20)
        unchanged = (None, 1, 2)
        # Each outcome is (error, A, B). Verified against the pre-removal
        # compiled executor at 14e1e729; native observations are tested separately.
        cases = (
            # Selection       Windows include        Linux include          Either exclude
            (None,            copied,                copied,                copied),
            ('A,B',           copied,                copied,                unchanged),
            ('A,Missing,B',   (missing, 10, 2),      (missing, 1, 20),      (excluded_missing, 1, 2)),
            ('Missing,A,B',   (missing, 1, 2),       (missing, 10, 20),     (excluded_missing, 1, 2)),
            ('A,B,Missing',   (missing, 10, 20),     (missing, 1, 2),       (excluded_missing, 1, 2)),
            ('A,,B',          (whitespace, 10, 2),   copied,               (whitespace, 1, 2)),
            ('A, ,B',         (whitespace, 10, 2),   (whitespace, 1, 20),   (whitespace, 1, 2)),
            ('A, B',          (whitespace, 10, 2),   copied,               (whitespace, 1, 2)),
            ('A,bad-name,B',  (invalid, 10, 2),      (invalid, 1, 20),      (invalid, 1, 2)),
            ('B,A,A',         copied,                copied,                unchanged),
            ('',              (whitespace, 1, 2),    unchanged,             (whitespace, 1, 2)),
        )
        for target, fixed, reverse, exclude, case in product(
                (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508),
                (False, True), (False, True), (False, True), cases):
            selection, windows, linux, excluded = case
            expected = excluded if exclude else (linux if target == LINUX_8_3_27_1508 else windows)
            with self.subTest(target=target, fixed=fixed, reverse=reverse, exclude=exclude, selection=selection):
                vm = self.vm(target)
                self.addCleanup(vm.close)
                source = '"B,A,Extra",20,10,30' if reverse else '"A,B,Extra",10,20,30'
                vm.execute(f'T=New Structure("A,B,Keep",1,2,3); S=New Structure({source});')
                if fixed:
                    vm.execute('S=New FixedStructure(S);')
                vm.variables['selection'] = selection
                error = None
                lists = 'Undefined,selection' if exclude else 'selection'
                try:
                    vm.execute(f'FillPropertyValues(T,S,{lists});')
                except BSLRuntimeError as exc:
                    error = exc.message
                vm.execute('Keys="";For Each P In T Do Keys=Keys+P.Key+",";EndDo;')
                actual = (error, vm.execute('T.A'), vm.execute('T.B'),
                          vm.execute('T.Keep'), vm.variables['keys'])
                self.assertEqual(actual, (*expected, 3, 'A,B,Keep,'))

    def test_payload_alias_self_copy_and_iteration_version(self):
        vm=self.vm();vm.execute('A=New Array();S=New Structure("a,b",A,Undefined);T=New Structure("A,B",1,2);Alias=T;'
            'For Each P In T Do FillPropertyValues(T,S);EndDo;FillPropertyValues(T,T);T.A.Add(7);')
        self.assertIs(vm.variables['t'],vm.variables['alias'])
        self.assertIs(vm.variables['t'].get('A'),vm.variables['a'])
        self.assertIsNone(vm.variables['t'].get('B'))
        self.assertEqual(vm.execute('S.a[0]'),Decimal(7))

    def test_custom_registration_is_not_intercepted(self):
        vm=self.vm(allow_extensions=True);calls=[]
        vm.register_function('FillPropertyValues',lambda *args:calls.append(args))
        vm.execute('FillPropertyValues(1,2);')
        self.assertEqual(calls,[(Decimal(1),Decimal(2))])

    def test_hostile_receivers_and_payloads_never_run_protocols(self):
        calls=[]
        class Evil:
            def __getattribute__(self,name):calls.append(name);raise AssertionError(name)
            def __hash__(self):calls.append('hash');raise AssertionError
            def __eq__(self,other):calls.append('eq');raise AssertionError
        class Sub(BSLStructure):
            def __getattribute__(self,name):calls.append(name);raise AssertionError
        good=new_structure('A',1)
        for bad in (Evil(),Sub(),{},[],object()):
            for left,right in ((bad,good),(good,bad)):
                with self.assertRaises(TypeError):fill(left,right)
        payload=Evil();source=new_structure('a',payload)
        fill(good,source)
        self.assertIs(good.get('a'),payload)
        self.assertEqual(calls,[])

    def test_raw_canonical_storage_avoids_receiver_hooks(self):
        for factory in (BSLStructure,BSLFixedStructure):
            source=factory('A',9);target=new_structure('A',1)
            with patch.object(factory,'__getattribute__',side_effect=AssertionError('attribute')):
                fill(target,source)
            self.assertEqual(target.get('a'),9)

    def test_corrupt_storage_fails_before_mutation_without_hooks(self):
        target=new_structure('A',1)
        for corrupt in ({'a':('A',2),'b':['B',3]}, {'a':('Other',2)}, {'a':('A',2,3)}):
            source=new_structure();dict.update(source,corrupt)
            with self.assertRaises(BoundaryViolation):fill(target,source)
            self.assertEqual(target.get('a'),1)
        source=BSLStructure('A',2);source._items=[]
        with self.assertRaises(BoundaryViolation):fill(target,source)

    def test_implementation_change_during_arguments_is_rejected(self):
        vm=self.vm(allow_extensions=True);vm.execute('T=New Structure("A",1);S=New Structure("A",2);')
        calls=[]
        def mutate():
            vm.functions['fillpropertyvalues'].function=lambda *a:calls.append(a)
            return vm.variables['s']
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('FillPropertyValues(T,Mutate());')
        self.assertEqual(vm.variables['t'].get('a'),Decimal(1));self.assertEqual(calls,[])

    def test_no_database_or_extended_adapter_fallback(self):
        from yadinassi.collections.value_tables import BSLValueTable
        vm=self.vm();vm.variables.update(t=BSLValueTable(),s=new_structure('A',1))
        with patch('yadinassi.collections.property_transfer.fill_property_values',side_effect=AssertionError('fallback')):
            with self.assertRaisesRegex(BSLRuntimeError,'приемник должен быть структурой'):
                vm.execute('FillPropertyValues(T,S);')

    def test_lifetime_before_and_after_policy_boundary(self):
        from yadinassi.execution.direct.python_direct_fill import resolve_fill
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        from yadinassi.collections.structures import fill_property_values
        from yadinassi.types.values import HostFunction
        function=HostFunction('FillPropertyValues',fill_property_values,returns_value=False)
        context=BoundaryContext();context.start()
        bound=resolve_fill(context,function)
        context.revoke()
        with self.assertRaises(BoundaryViolation):bound(new_structure('A',1),new_structure('A',2))

    def test_policy_revocation_and_rebinding_precede_writes(self):
        from yadinassi.execution.direct.python_direct_fill import resolve_fill
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        from yadinassi.collections.structures import fill_property_values
        from yadinassi.types.values import HostFunction
        for mode in ('revoke','rebind','deny'):
            function=HostFunction('FillPropertyValues',fill_property_values,returns_value=False)
            context=BoundaryContext();context.start()
            target=new_structure('A',1);source=new_structure('A',2)
            calls=[]
            def policy(operation,name):
                calls.append((operation,name))
                if mode=='revoke':context.revoke()
                elif mode=='rebind':function.function=lambda *args:calls.append('unexpected')
                else:return False
            context.policy=policy
            bound=resolve_fill(context,function)
            with self.assertRaises(BoundaryViolation):bound(target,source)
            self.assertEqual(target.get('a'),1)
            self.assertEqual(calls,[('call_value','fillpropertyvalues')])

    def test_captured_function_optional_omissions_and_fixed_target(self):
        vm=self.vm()
        # Explicit host capture is the supported callable seam, not BSL function
        # introspection. It must use the same identity-bound direct adapter.
        vm.variables['captured']=vm.functions['fillpropertyvalues']
        vm.execute('T=New Structure("A,B",1,2); S=New Structure("A,B",10,20);Captured(T,S,,"A");')
        self.assertEqual(vm.execute('T.A'),Decimal(1));self.assertEqual(vm.execute('T.B'),Decimal(20))
        vm.execute('F=New FixedStructure(T);Captured(F,S);')
        self.assertEqual(vm.execute('F.A'),Decimal(1))
        with self.assertRaisesRegex(BSLRuntimeError,'фиксированного приемника'):
            vm.execute('Captured(F,S,"A");')

    def test_existing_canonical_host_lane_remains_unchanged(self):
        from yadinassi.collections.value_tables import BSLValueTable
        vm=self.vm();table=BSLValueTable();table.columns.add('A');row=table.add()
        row.set_member('A',Decimal(1))
        vm.variables.update(t=row,s=BSLStructure('A',Decimal(2)))
        vm.execute('FillPropertyValues(T,S);')
        self.assertEqual(row.get_member('A'),Decimal(2))

    def test_native_include_and_exclude_checkpoint_observations(self):
        import hashlib
        import json
        from pathlib import Path
        from tests.test_fill_include_checkpoint import CASES
        from tests.test_fill_include_runtime import NATIVE, NATIVE_SUFFIX_SHA256
        from tests.test_fill_exclude_checkpoint import CASES as EXCLUDE_CASES
        root=Path(__file__).resolve().parents[1]
        # Pinned native INCLUDE bytes/expectations, not a new native run.
        lines=[f'fill.include-normalization.{label}: [{status};{{"N",{first}}};{{"N",{last}}}]'
               for (label,_),(status,first,last) in zip(CASES,NATIVE)]
        self.assertEqual(hashlib.sha256(('\n'.join(lines)+'\n').encode()).hexdigest(),NATIVE_SUFFIX_SHA256)
        for (_,selection),expected in zip(CASES,NATIVE):
            vm=self.vm(target=LINUX_8_3_27_1508)
            vm.execute('T=New Structure("First,Last",1,2);S=New Structure("First,Last",10,20);')
            vm.variables['selection']=selection;status='ok'
            try:vm.execute('FillPropertyValues(T,S,selection);')
            except BSLRuntimeError:status='error'
            self.assertEqual((status,vm.execute('T.First'),vm.execute('T.Last')),expected)
        observed=json.loads((root/'integrational_tests/fill_exclude_native/observations.json').read_text())
        raw=(root/'integrational_tests/fill_exclude_native/collections.out').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),observed['output_sha256'])
        cases=[(variant,excluded,'last') for _,variant,excluded in EXCLUDE_CASES]
        cases += [('source-only','Missing',position) for position in ('first','between')]
        for (variant,excluded,position),record in zip(cases,observed['records']):
            vm=self.vm(target=LINUX_8_3_27_1508)
            target=new_structure('First,Last,Copy',1,2,3)
            if variant=='target-only':target.insert('Missing',4)
            items=[('First',10),('Last',20),('Copy',30)]
            if variant=='source-only':items.insert({'first':0,'between':1,'last':3}[position],('Missing',40))
            source=new_structure()
            for name,value in items:source.insert(name,value)
            vm.variables.update(t=target,s=source,excluded=excluded);status='ok'
            try:vm.execute('FillPropertyValues(T,S,Undefined,excluded);')
            except BSLRuntimeError:status='error'
            self.assertEqual(dict(status=status,first=target.get('First'),last=target.get('Last'),copy=target.get('Copy'),
                target_count=len(target),target_missing=target.property('Missing'),target_missing_value=target.get('Missing')),record['state'])

    def test_preserved_host_lane_permission_error_remains_fail_closed(self):
        from yadinassi.collections.value_tables import BSLValueTable
        vm=self.vm();table=BSLValueTable();table.columns.add('A');row=table.add()
        vm.variables.update(t=row,s=BSLStructure('A',2))
        with patch('yadinassi.collections.property_transfer.fill_property_values',side_effect=PermissionError('denied')):
            with self.assertRaises(BoundaryViolation):
                vm.execute('Try FillPropertyValues(T,S);Except Swallowed=True;EndTry;')
        self.assertNotIn('swallowed',vm.variables)
