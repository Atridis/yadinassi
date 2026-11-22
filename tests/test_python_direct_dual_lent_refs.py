"""Same-side dual calls receive explicit addresses, never module authority."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


DUAL = '&AtClientAtServerNoContext\n'
EXPORTED = 'Var Secret Export; Secret=7;\n'


class DualLentReferencesTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        return vm

    def restored(self,vm):
        self.assertEqual(vm._context_stack,['client'])
        self.assertEqual(vm._module_context_stack,[True])
        self.assertIsNone(vm.locals)

    def capture(self,vm,observe):
        vm.register_function('Capture',observe,returns_value=False)
        vm.functions['capture'].reference_parameters=frozenset({0})

    def test_lexical_alias_is_live_only_inside_same_side_call(self):
        vm=self.vm()
        kept=[]
        def observe(ref):
            self.assertEqual((vm.execution_context,vm._has_module_context),('client',False))
            self.assertEqual(ref.get(),Decimal(3))
            ref.set(6)
            kept.append(ref)
        self.capture(vm,observe)
        vm.execute(DUAL+'''
            Procedure D(A,B)
                A=3; Capture(B); B=B+1;
            EndProcedure
            Function Caller()
                X=1; D(X,X); Return X;
            EndFunction
        ''')
        self.assertEqual(vm.execute('Caller()'),Decimal(7))
        self.assertEqual(len(kept),1)
        for expired in (kept[0].get, lambda:kept[0].set(100)):
            with self.assertRaises(BoundaryViolation):expired()
        self.restored(vm)

    def test_public_field_lease_detects_storage_and_generation_replacement(self):
        for change in ('storage','generation'):
            with self.subTest(change=change):
                vm=self.vm()
                original=vm.variables
                calls=[]
                def revoke():
                    calls.append((vm.execution_context,vm._has_module_context))
                    if change=='storage':vm.variables=dict(original)
                    else:vm._family_generation+=1
                vm.register_function('Revoke',revoke,returns_value=False)
                vm.execute(EXPORTED+DUAL+'''
                    Procedure D(X)
                        X=X+1; Revoke(); X=99;
                    EndProcedure
                ''')
                with self.assertRaisesRegex(BoundaryViolation,'dual reference lend expired or changed'):
                    vm.execute('D(ThisObject.Secret);')
                self.assertEqual(calls,[('client',False)])
                self.assertEqual(original['secret'],Decimal(8))
                self.assertEqual(vm.variables['secret'],Decimal(8))
                self.restored(vm)

    def test_mutated_public_address_rejects_foreign_key_before_lookup(self):
        vm=self.vm()
        seen=[]
        class Key:
            def __hash__(self):return hash('secret')
            def __eq__(self,_other):seen.append('comparison');raise AssertionError
        def corrupt():
            del vm.variables['secret']
            vm.variables[Key()]=7
        vm.register_function('Corrupt',corrupt,returns_value=False)
        vm.execute(EXPORTED+DUAL+'''
            Procedure D(X)
                Corrupt(); X=99;
            EndProcedure
        ''')
        with self.assertRaisesRegex(BoundaryViolation,'module field storage changed'):
            vm.execute('D(ThisObject.Secret);')
        self.assertEqual(seen,[])
        self.assertEqual(list(vm.variables.values()),[7])
        self.restored(vm)

    def test_parent_revocation_blocks_write_through_lent_address(self):
        from yadinassi.execution.direct.python_direct_server import ServerBoundary
        vm=self.vm()
        parent=[]
        original=ServerBoundary.__init__
        def capture(boundary,owner,**options):
            original(boundary,owner,**options)
            parent.append(owner)
        vm.register_function('Revoke',lambda:parent[0].revoke(),returns_value=False)
        vm.execute(EXPORTED+DUAL+'''
            Procedure D(X)
                X=8; Revoke(); X=99;
            EndProcedure
        ''')
        with patch.object(ServerBoundary,'__init__',capture):
            with self.assertRaisesRegex(BoundaryViolation,'execution authority revoked'):
                vm.execute('D(ThisObject.Secret);')
        self.assertEqual(vm.variables['secret'],8)
        self.restored(vm)

    def test_light_client_lends_only_its_own_exact_address(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute(EXPORTED+DUAL+'''
            Procedure D(X) X=X+1; EndProcedure
            Function Caller()
                X=3; D(X); Return X;
            EndFunction
        ''')
        self.assertEqual(vm.execute('Caller()'),4)
        vm.execute('D(ThisObject.Secret);')
        self.assertEqual(vm.variables['secret'],8)
        self.restored(vm)

    def test_imported_field_is_not_an_own_lent_address(self):
        vm=self.vm()
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'M.bsl').write_text('Var Shared Export; Shared=7;',encoding='utf-8')
            vm.execute('// #Import M.bsl\n'+DUAL+'Procedure D(X) X=99; EndProcedure',
                       str(root/'Root.bsl'))
            with self.assertRaises(BoundaryViolation):
                vm.execute('D(M.Shared);')
            self.assertEqual(vm.execute('M.Shared'),7)
        self.restored(vm)

    def test_explicit_lend_does_not_arm_ambient_module_receiver(self):
        vm=self.vm()
        touched=[]
        vm.register_function('Effect',lambda:touched.append('opaque') or 99)
        vm.execute('Var Secret Export, Other Export; Secret=7; Other=31;\n'+DUAL+'''
            Procedure D(X,Val Owner)
                X=8; Owner.Other=Effect();
            EndProcedure
        ''')
        with self.assertRaisesRegex(BoundaryViolation,'unregistered or foreign database receiver'):
            vm.execute('D(ThisObject.Secret,ThisObject);')
        self.assertEqual((vm.variables['secret'],vm.variables['other']),(8,31))
        self.assertEqual(touched,[])
        self.restored(vm)

    def test_actual_client_server_passage_still_requires_name_and_copies(self):
        vm=self.vm()
        seen=[]
        vm.register_function('Observe',lambda:seen.append((vm.execution_context,vm._has_module_context)),
                             returns_value=False)
        vm.execute(EXPORTED+'''
            &AtServerNoContext
            Procedure S(X,Val A)
                Observe(); X=12; A[0]=11;
            EndProcedure
        ''')
        with self.assertRaisesRegex(BSLError,'требуют имя переменной'):
            vm.execute('S(ThisObject.Secret,New Array);')
        self.assertEqual(seen,[])
        self.assertEqual(vm.variables['secret'],7)
        vm.execute('N=3; A=New Array; A.Add(5); S(N,A);')
        self.assertEqual((vm.variables['n'],vm.variables['a'][0]),(12,5))
        self.assertEqual(seen,[('server',False)])
        self.restored(vm)

    def test_ordinary_public_reference_accepts_no_override_for_its_check(self):
        vm=self.vm()
        seen=[]
        def attempt(ref):
            def replacement():
                seen.append('bypassed')
            with self.assertRaises(TypeError):ref.get(replacement)
            with self.assertRaises(TypeError):ref.set(9,replacement)
            self.assertEqual(ref.get(),7)
        self.capture(vm,attempt)
        vm.execute(EXPORTED)
        vm.execute('Capture(ThisObject.Secret);')
        self.assertEqual(vm.variables['secret'],7)
        self.assertEqual(seen,[])
        self.restored(vm)

    def test_ordinary_client_byref_and_side_still_use_original_lease(self):
        vm=self.vm()
        kept=[]
        def observe(ref):
            self.assertEqual((vm.execution_context,vm._has_module_context),('client',True))
            self.assertEqual(ref.get(),4)
            ref.set(6)
            kept.append(ref)
        self.capture(vm,observe)
        vm.execute('Function Caller() X=4; Capture(X); Return X; EndFunction')
        self.assertEqual(vm.execute('Caller()'),6)
        self.assertEqual(len(kept),1)
        with self.assertRaises(BoundaryViolation):kept[0].get()
        self.restored(vm)
