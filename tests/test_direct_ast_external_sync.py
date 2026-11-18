"""Synchronization belongs to external callbacks, not native expressions."""
import sys
import unittest
from decimal import Decimal as D
from unittest.mock import patch
from yadinassi import Interpreter, python_direct
from yadinassi.experimental_naked_boundaries import HostMembers, BoundaryViolation, BoundaryContext

class ExternalSyncTests(unittest.TestCase):
    def test_native_table_sync_count_does_not_scale_with_operations(self):
        counts=[]
        for n in (4,32):
            vm=Interpreter();self.addCleanup(vm.close)
            plan=vm.prepare(f'T=New ValueTable;T.Columns.Add("N");For I=0 To {n-1} Do Row=T.Add();Row.N=I;EndDo;R=0;For I=0 To {n-1} Do R=R+T.Get(I).N;EndDo;')
            seen=[]
            def profile(frame,event,arg):
                if event=='call' and frame.f_code.co_name=='_publish_module':seen.append(1)
            prior=sys.getprofile()
            try:sys.setprofile(profile);vm.execute_prepared(plan)
            finally:sys.setprofile(prior)
            self.assertEqual(vm.variables['r'],D(n*(n-1)//2));counts.append(len(seen))
        self.assertEqual(counts,[1,1]) # fresh native constructor; final publication only
    def test_external_get_set_call_see_latest_locals_and_reload(self):
        vm=Interpreter();self.addCleanup(vm.close);seen=[]
        class Host:
            @property
            def value(self):seen.append(('get',vm.variables['x']));vm.variables['x']=D(5);return D(2)
            @value.setter
            def value(self,v):seen.append(('set',vm.variables['x'],v));vm.variables['x']=D(8)
            def touch(self,v):seen.append(('call',vm.variables['x'],v));vm.variables['x']=D(11);return v
        host=Host();vm.variables['h']=host
        original=python_direct.make_boundary
        def boundary(*args,**kwargs):
            context=original(*args,**kwargs)
            context.expose(HostMembers(host,readable=('value',),writable=('value',),callable=('touch',)))
            # Explicit trusted test bridge. Product standalone does not grant
            # arbitrary Python receiver access merely because it is returned.
            for method in ('get_member','resolve_set_member','resolve_member'):
                original_method=getattr(context,method)
                base=getattr(BoundaryContext,method)
                setattr(context,method,lambda value,*a,_base=base,_old=original_method,**kw: _base(context,value,*a,**kw) if value is host else _old(value,*a,**kw))
            return context
        with patch.object(python_direct,'make_boundary',boundary):
            vm.execute('X=3;Y=H.Value;R=X+Y;H.Value=7;S=X;Z=H.Touch(9);Final=X;')
        self.assertEqual(seen,[('get',D(3)),('set',D(5),D(7)),('call',D(8),D(9))])
        self.assertEqual((vm.variables['r'],vm.variables['s'],vm.variables['final']),(D(7),D(8),D(11)))
    def test_host_getter_exception_reloads_and_close_cannot_be_caught(self):
        for close in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            class Host:
                @property
                def value(self):
                    vm.variables['x']=D(9)
                    if close:vm.close()
                    raise ValueError('host failure')
            host=Host();vm.variables['h']=host;original=python_direct.make_boundary
            def boundary(*args,**kwargs):
                context=original(*args,**kwargs);context.expose(HostMembers(host,readable=('value',)))
                context.get_member=lambda value,name:BoundaryContext.get_member(context,value,name)
                return context
            with patch.object(python_direct,'make_boundary',boundary):
                if close:
                    with self.assertRaises(BoundaryViolation):vm.execute('X=3;Try Y=H.Value;Except Caught=True;EndTry;After=1;')
                    self.assertNotIn('caught',vm.variables);self.assertNotIn('after',vm.variables)
                else:
                    vm.execute('X=3;Try Y=H.Value;Except R=X;EndTry;')
                    self.assertEqual(vm.variables['r'],D(9))
    def test_opaque_arithmetic_close_prevents_public_native_alias_mutation(self):
        from yadinassi.python_direct_plain_array import PlainArray
        for operation in ('A.Add(7);','A[0]=7;'):
            vm=Interpreter();self.addCleanup(vm.close);array=PlainArray([D(3)])
            class Opaque:
                def __add__(self,value):vm.close();return D(1)
            vm.variables.update(a=array,x=Opaque())
            with self.assertRaises(BoundaryViolation):vm.execute('R=X+1;'+operation+'After=1;')
            self.assertEqual(list(array),[D(3)]);self.assertNotIn('after',vm.variables)
    def test_generated_sync_implementation_is_not_copied_per_expression(self):
        vm=Interpreter();self.addCleanup(vm.close);vm.register_function('Touch',lambda:D(1))
        def build(n):
            source=';'.join(f'X{i}={i}' for i in range(n))+';'+''.join('Touch();' for _ in range(n))
            text=vm.prepare(source)._plan.generated_source
            self.assertEqual(text.count('def _publish_module'),1)
            self.assertEqual(text.count('_initial.__setitem__'),n)
            return len(text)
        small,large=build(8),build(32)
        self.assertLess(large,small*5)
