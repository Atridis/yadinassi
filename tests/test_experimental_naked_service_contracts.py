import os,unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.values import HostFunction
from tests.retired_text_compiler import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation,UnsupportedHostSignature
class ServiceContracts(unittest.TestCase):
 def setUp(self):
  p=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});p.start();self.addCleanup(p.stop)
 def test_registration_change_keeps_bound_callee(self):
  for candidate in (False,True):
   events=[]
   old=lambda x:events.append('old') or 1
   new=lambda x:events.append('new') or 2
   if candidate:
    ctx=BoundaryContext(services={'host':old})
    def change():ctx._services['host']=new;return 0
    ctx._services['change']=change
    state=prepare('r=Host(Change());',repairs=('service_boundaries',)).run(context=ctx)
   else:
    vm=Interpreter(execution_backend='compiled-strict');vm.register_function('Host',old)
    def change():vm.register_function('Host',new);return 0
    vm.register_function('Change',change);vm.execute('r=Host(Change());');state=vm.variables
   self.assertEqual((state['r'],events),(1,['old']))
 def test_registered_service_outranks_variable(self):
  ctx=BoundaryContext(services={'host':lambda:1})
  self.assertEqual(prepare('Host=7;r=Host();',repairs=('service_boundaries',)).run(context=ctx)['r'],1)
 def test_canonical_dynamic_host_and_raw_rejection(self):
  for source in ('r=(Get())();','f=Get();r=f();'):
   for canonical in (False,True):
    for candidate in (False,True):
     events=[];function=lambda:events.append('called') or 7
     value=HostFunction('chosen',function) if canonical else function
     if candidate:
      p=prepare(source,repairs=('service_boundaries','error_boundaries'))
      execute=lambda:p.run(context=BoundaryContext(services={'get':lambda:value}))
     else:
      vm=Interpreter(execution_backend='compiled-strict');vm.register_function('Get',lambda:value)
      def execute():vm.execute(source);return vm.variables
     if canonical:self.assertEqual(execute()['r'],7);self.assertEqual(events,['called'])
     else:
      with self.assertRaisesRegex(Exception,'Значение не является функцией'):execute()
      self.assertEqual(events,[])
 def test_procedure_value_and_unsupported_dynamic_byref_before_args(self):
  for value,error in ((HostFunction('P',lambda x:None,returns_value=False),Exception),(HostFunction('P',lambda x:None,reference_parameters=frozenset({0})),UnsupportedHostSignature)):
   events=[];ctx=BoundaryContext(services={'get':lambda:value,'arg':lambda:events.append('arg')})
   with self.assertRaises(error):prepare('r=(Get())(Arg());',repairs=('service_boundaries',)).run(context=ctx)
   self.assertEqual(events,[])
 def test_policy_changed_by_argument_checked_after_binding(self):
  events=[];ctx=BoundaryContext(services={'host':lambda x:events.append('host')})
  def change():ctx.policy=lambda op,name:name!='host';return 0
  ctx._services['change']=change
  with self.assertRaises(BoundaryViolation):prepare('Host(Change());',repairs=('service_boundaries',)).run(context=ctx)
  self.assertEqual(events,[])
