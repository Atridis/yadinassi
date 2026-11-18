import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from tests.retired_text_compiler import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation,HostMembers

class NakedBoundaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});self.env.start();self.addCleanup(self.env.stop)
    def run_program(self,source,ctx,initial=None,**kwargs):
        return prepare(source,repairs=('service_boundaries','authority_checkpoints','error_boundaries','byref_routines'),**kwargs).run(initial,context=ctx)
    def test_registered_service_exactly_once(self):
        events=[];ctx=BoundaryContext(services={'Host':lambda x:events.append(x) or x+1})
        result=self.run_program('r=Host(2);',ctx)
        self.assertEqual((result['r'],events),(3,[2]))
    def test_denied_private_method_before_argument_effect(self):
        events=[];ctx=BoundaryContext(services={'Host':lambda:events.append(1)})
        with self.assertRaises(BoundaryViolation):self.run_program('obj.secret(Host());',ctx,{'obj':SimpleNamespace(secret=lambda x:None)})
        self.assertEqual(events,[])
    def test_denied_private_write_before_rhs_effect(self):
        events=[];obj=SimpleNamespace(secret=0);ctx=BoundaryContext(services={'Host':lambda:events.append(1)})
        with self.assertRaises(BoundaryViolation):self.run_program('obj.secret=Host();',ctx,{'obj':obj})
        self.assertEqual((obj.secret,events),(0,[]))
    def test_permission_denial_not_catchable_by_bsl_try(self):
        def denied():raise PermissionError('no')
        ctx=BoundaryContext(services={'Host':denied})
        with self.assertRaises(BoundaryViolation):self.run_program('Try Host();Except r=1;EndTry;',ctx)
    def test_revocation_after_service_no_replay(self):
        events=[];ctx=BoundaryContext()
        def host():events.append(1);ctx.revoke();return 4
        ctx._services['host']=host
        p=prepare('a=New Array;a.Add(1);r=Host();s=8;',repairs=('service_boundaries','authority_checkpoints'))
        with self.assertRaises(BoundaryViolation):p.run(context=ctx)
        self.assertEqual(events,[1]);self.assertEqual(p.last_state['a'],[1]);self.assertNotIn('s',p.last_state)
    def test_loop_budget_has_explicit_header_units(self):
        ctx=BoundaryContext(loop_budget=3)
        p=prepare('r=0;While True Do r=r+1;EndDo;',repairs=('authority_checkpoints',))
        with self.assertRaises(BoundaryViolation):p.run(context=ctx)
        self.assertEqual(p.last_state['r'],3);self.assertEqual(ctx.loop_backedges,3)
    def test_service_reference_signature(self):
        ctx=BoundaryContext(services={'Host':lambda ref:ref.set(Decimal(7))})
        result=self.run_program('a=1;Host(a);r=a;',ctx,service_references={'Host':(0,)})
        self.assertEqual(result['r'],7)
    def test_readonly_host_reference_can_be_read_not_written(self):
        obj=SimpleNamespace(value=Decimal(7));ctx=BoundaryContext(members=(HostMembers(obj,readable=('value',)),))
        self.assertEqual(self.run_program('Function F(x) Return x;EndFunction r=F(obj.value);',ctx,{'obj':obj})['r'],7)
        ctx=BoundaryContext(members=(HostMembers(obj,readable=('value',)),))
        with self.assertRaises(BoundaryViolation):self.run_program('Procedure F(x) x=9;EndProcedure F(obj.value);',ctx,{'obj':obj})
        self.assertEqual(obj.value,7)
    def test_explicit_constructor_and_members_execute(self):
        class Box:
            def __init__(self,value):self.value=value
            def count(self):return self.value
        events=[];ctx=BoundaryContext()
        def constructor(value):
            events.append(value);box=Box(value);ctx.expose(HostMembers(box,callable=('count',)));return box
        ctx._services['new:box']=constructor
        self.assertEqual(self.run_program('b=New Box(7);r=b.Count();',ctx,constructors=('Box',))['r'],7)
        self.assertEqual(events,[7])
    def test_constructor_declaration_is_not_permission(self):
        with self.assertRaises(BoundaryViolation):self.run_program('b=New Box;',BoundaryContext(),constructors=('Box',))
    def test_thread_created_after_entry_revokes_at_next_loop_header(self):
        import threading
        loop_entered=threading.Event();revoked=threading.Event();threads=[]
        class CoordinatedContext(BoundaryContext):
            def checkpoint(self):
                loop_entered.set()
                if not revoked.wait(2):raise AssertionError('revocation worker stalled')
                super().checkpoint()
        ctx=CoordinatedContext()
        def start_worker():
            def worker():
                if loop_entered.wait(2):ctx.revoke();revoked.set()
            thread=threading.Thread(target=worker);threads.append(thread);thread.start()
        ctx._services['startworker']=start_worker
        p=prepare('StartWorker();r=0;While True Do r=r+1;EndDo;',repairs=('service_boundaries','authority_checkpoints'))
        try:
            with self.assertRaises(BoundaryViolation):p.run(context=ctx)
            self.assertEqual(p.last_state['r'],0)
        finally:
            for thread in threads:thread.join(3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
    def test_hostile_metaclass_cannot_impersonate_native_receiver(self):
        events=[]
        class Meta(type):
            def __eq__(cls,other):events.append('metaclass equality');return True
        class Host(metaclass=Meta):
            def append(self,value):events.append('unauthorized append')
            def __len__(self):events.append('unauthorized len');return 0
            def __getitem__(self,key):events.append('unauthorized get');return 0
            def __setitem__(self,key,value):events.append('unauthorized set')
            def __iter__(self):events.append('unauthorized iterator');return iter(())
        for source in ('obj.Add(7);','r=obj.Count();','r=obj[0];','obj[0]=7;','For Each p In obj Do EndDo;'):
            with self.assertRaises(BoundaryViolation):
                prepare(source,repairs=('service_boundaries',)).run({'obj':Host()},context=BoundaryContext())
            self.assertEqual(events,[],source)
    def test_decimal_subclass_cannot_invoke_numeric_hooks(self):
        events=[]
        class HostDecimal(Decimal):
            def to_integral_value(self,*args,**kwargs):events.append('integral');return Decimal(0)
            def __int__(self):events.append('int');return 0
        for source in ('a=New Array;a.Add(7);r=a[x];','a=New Array(x);','a=New Array;a.Insert(x,7);'):
            with self.assertRaisesRegex(TypeError,'Ожидается число'):
                prepare(source,repairs=('service_boundaries','array_index_contract','array_insert_shape','constructor_bounds')).run({'x':HostDecimal(0)},context=BoundaryContext())
            self.assertEqual(events,[])
