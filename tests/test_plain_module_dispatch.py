import unittest
from decimal import Decimal
from yadinassi import Interpreter
from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class ModuleDispatchTests(unittest.TestCase):
 def test_actual_module_route_and_partial_error_state(self):
  for source in ('x=1;y=2;r=x+y;','x=1;y=1/0;',
                 's=0;For i=1 To 5 Do s=s+i;r=10/(3-i);EndDo;'):
   outcomes=[]
   for enabled in (False,True):
    vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled);error=None
    try:result=vm.execute(source)
    except Exception as e:error=(type(e).__name__,str(e));result=None
    outcomes.append((result,error,[(k,vm.variables[k]) for k in ('x','y','s','i','r') if k in vm.variables]))
    self.assertIsNone(vm.locals);self.assertEqual(vm._compiled().active_frames,0)
    self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
    if enabled:self.assertEqual(vm.compiled_backend_stats.get('plain_module_entries'),1)
   self.assertEqual(*outcomes)
 def test_opaque_program_does_not_run_prefix(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True);seen=[]
  def host():seen.append(vm.variables['x']);return Decimal(2)
  vm.register_function('Host',host);vm.execute('x=1;y=Host();')
  self.assertEqual(seen,[Decimal(1)]);self.assertEqual(vm.compiled_backend_stats.get('plain_module_entries',0),0)
 def test_repl_sees_existing_storage(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
  vm.execute('x=1;');vm.execute('x=x+2;');self.assertEqual(vm.variables['x'],3)
  self.assertEqual(vm.compiled_backend_stats.get('plain_module_entries'),2)
 def test_module_budget_exhaustion_keeps_adapter_before_effects(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
  vm._compiled().MAX_PLAIN_SOURCE_BYTES=0;vm.execute('x=1;')
  self.assertEqual(vm.variables['x'],1);self.assertEqual(vm.compiled_backend_stats.get('plain_module_entries',0),0)

@legacy_compiler_fixture
class SharedModuleBudgetTests(unittest.TestCase):
 def test_retained_routine_and_new_module_share_cap(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
  vm.execute('Function F(Val x) Return x+1;EndFunction')
  engine=vm._compiled();used=engine._plain_source_bytes();self.assertGreater(used,0)
  entries=engine.stats.get('plain_module_entries',0);self.assertGreater(entries,0)
  engine.MAX_PLAIN_SOURCE_BYTES=used+1;vm.execute('r=1;')
  self.assertEqual(vm.variables['r'],1);self.assertEqual(engine.stats.get('plain_module_entries',0),entries)
  self.assertLessEqual(engine._plain_source_bytes(),engine.MAX_PLAIN_SOURCE_BYTES)
 def test_module_and_new_routine_share_cap(self):
  from yadinassi.syntax.parser import parse
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True);engine=vm._compiled()
  engine.prepare(parse('x=1;'),module_entry=True);used=engine._plain_source_bytes();self.assertGreater(used,0)
  engine.MAX_PLAIN_SOURCE_BYTES=used+1;engine.prepare(parse('Function F(Val x) Return x+1;EndFunction'))
  self.assertLessEqual(engine._plain_source_bytes(),engine.MAX_PLAIN_SOURCE_BYTES)
  self.assertFalse(any(plan is not None for _,plan in engine._plain_routines.values()))
 def test_ineligible_modules_do_not_retain_synthetic_blocks(self):
  from yadinassi.syntax.parser import parse
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True);engine=vm._compiled()
  program=parse('Host();');engine.prepare(program)
  before=(len(engine._owned.memo),len(engine._owned.versions))
  for _ in range(10):engine.prepare(program,allow_reprepare=False,module_entry=True)
  self.assertEqual(before,(len(engine._owned.memo),len(engine._owned.versions)));self.assertEqual(engine._plain_modules,{})

if __name__=='__main__':unittest.main()
