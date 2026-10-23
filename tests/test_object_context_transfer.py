"""Measured object copy semantics and explicitly local fail-closed guards."""
import unittest
from decimal import Decimal
from yadinassi import Interpreter, BSLError
from yadinassi.values import BSLArray
from yadinassi.structures import BSLStructure

class ObjectContextTransferTests(unittest.TestCase):
    def setUp(self):
        self.messages=[]; self.vm=Interpreter(self.messages.append)

    def test_per_occurrence_copy_and_independent_packet_roots(self):
        child=BSLArray();child.add(Decimal(1));root=BSLStructure('Left,Right',child,child)
        a,b=self.vm._copy_context_packet([root,root])
        self.assertIsNot(a,b);self.assertIsNot(a,root)
        self.assertIsNot(a.get('Left'),a.get('Right'))
        a.get('Left').set(Decimal(0),Decimal(9))
        self.assertEqual(a.get('Right').items,[Decimal(1)])
        self.assertEqual(b.get('Left').items,[Decimal(1)])
        self.assertEqual(child.items,[Decimal(1)])

    def test_client_state_unchanged_during_server_body(self):
        seen=[]
        self.vm.register_function('Observe',lambda:seen.append(self.vm.variables['x'].get('N')))
        self.vm.execute('''
&AtServer
Procedure Change(P) P.N = 2; Observe(); EndProcedure
x = New Structure("N",1); old = x; Change(x);
''')
        self.assertEqual(seen,[Decimal(1)])
        self.assertEqual(self.vm.variables['x'].get('N'),Decimal(2))
        self.assertEqual(self.vm.variables['old'].get('N'),Decimal(1))

    def test_same_side_retains_existing_shared_reference_behavior(self):
        self.vm.execute('''
Procedure Change(Val P) P.N = 2; EndProcedure
x = New Structure("N",1); old = x; Change(x);
''')
        self.assertIs(self.vm.variables['x'],self.vm.variables['old'])
        self.assertEqual(self.vm.variables['x'].get('N'),Decimal(2))

    def test_scalar_named_val_late_expression_early_and_effect_once(self):
        self.vm.execute('''
&AtServer
Function Capture(Val Named, Val Expression, Val Token) Return Named*100+Expression; EndFunction
Function Identity(Val X) Return X; EndFunction
Function Effect(X, Calls) Calls=Calls+1; X=9; Return 0; EndFunction
x=1; calls=0; result=Capture(x,Identity(x),Effect(x,calls));
''')
        self.assertEqual(self.vm.variables['result'],Decimal(901))
        self.assertEqual(self.vm.variables['calls'],Decimal(1))

    def test_named_forwarding_copies_objects_without_aliasing_client(self):
        self.vm.execute('''
&AtServer
Procedure Server(P) P.N=2; EndProcedure
Procedure Forward(P) Server(P); EndProcedure
x=New Structure("N",1); old=x; Forward(x);
''')
        self.assertEqual(self.vm.variables['x'].get('N'),Decimal(2))
        self.assertEqual(self.vm.variables['old'].get('N'),Decimal(1))

    def test_forwarded_property_val_is_explicitly_outside_named_storage_slice(self):
        self.vm.execute('''
&AtServer
Function Server(Val P) Message("entered"); Return P; EndFunction
Procedure Forward(P) Message(Server(P)); EndProcedure
x=New Structure("N",1);
''')
        with self.assertRaisesRegex(BSLError, 'ссылок на свойства'):
            self.vm.execute('Forward(x.N);')
        self.assertEqual(self.messages, [])
        self.assertEqual(self.vm.variables['x'].get('N'), Decimal(1))
        self.assertEqual(self.vm.execution_context, 'client')
        # A direct Val property expression is already a value, not forwarded storage.
        self.assertEqual(self.vm.execute('Server(x.N)'), Decimal(1))

    def test_cycle_rejects_before_body_without_replacing_caller(self):
        self.vm.execute('''
&AtServer
Procedure Server(P) Message("entered"); EndProcedure
x=New Array; x.Add(x);
''')
        old=self.vm.variables['x']
        with self.assertRaisesRegex(BSLError,'циклических'):self.vm.execute('Server(x);')
        self.assertIs(self.vm.variables['x'],old);self.assertEqual(self.messages,[])
        self.assertEqual(self.vm.execution_context,'client')

    def test_unsupported_nested_leaf_rejects_before_body(self):
        for leaf in ('New Map','New FixedArray(New Array)','New FixedStructure','Date(2026,1,1)'):
            self.vm.execute(f'&AtServer\nProcedure Server(P) Message("entered"); EndProcedure\nx=New Structure("Leaf",{leaf});')
            old=self.vm.variables['x']
            with self.assertRaisesRegex(BSLError,'Межконтекстная передача'):self.vm.execute('Server(x);')
            self.assertIs(self.vm.variables['x'],old);self.assertEqual(self.messages,[])

    def test_all_outgoing_graphs_validate_before_any_caller_write(self):
        for bad in ('B=New Structure("Bad",New Map);','B=New Array; B.Add(B);','B=New Array(10001);'):
            self.vm.execute(f'&AtServer\nProcedure Server(A,B) A=New Structure("N",43); {bad} EndProcedure\nx=New Structure("N",1); y=New Structure("N",2);')
            x,y=self.vm.variables['x'],self.vm.variables['y']
            with self.assertRaises(BSLError):self.vm.execute('Server(x,y);')
            self.assertIs(self.vm.variables['x'],x);self.assertIs(self.vm.variables['y'],y)
            self.assertEqual(x.get('N'),Decimal(1));self.assertEqual(y.get('N'),Decimal(2))
            self.assertEqual(self.vm.execution_context,'client')

    def test_bad_result_prevents_valid_output_even_when_result_discarded(self):
        self.vm.execute('&AtServer\nFunction Server(P) P.N=2; Return New Structure("Bad",New Map); EndFunction\nx=New Structure("N",1);')
        old=self.vm.variables['x']
        with self.assertRaises(BSLError):self.vm.execute('Server(x);')
        self.assertIs(self.vm.variables['x'],old);self.assertEqual(old.get('N'),Decimal(1))

    def test_subclasses_are_not_serialized_through_host_hooks(self):
        class Trap(BSLArray):
            def __iter__(self):raise AssertionError('host hook')
        with self.assertRaises(TypeError):self.vm._copy_context_packet([Trap()])

    def test_resource_guards_bound_depth_and_shared_expansion(self):
        deep=BSLArray()
        for _ in range(65):p=BSLArray();p.add(deep);deep=p
        with self.assertRaisesRegex(ValueError,'предел'):self.vm._copy_context_packet([deep])
        shared=BSLArray();shared.add(Decimal(1))
        for _ in range(14):p=BSLArray();p.add(shared);p.add(shared);shared=p
        with self.assertRaisesRegex(ValueError,'предел'):self.vm._copy_context_packet([shared])
        self.assertEqual(self.vm._copy_context_packet([Decimal(1)]),[Decimal(1)])
