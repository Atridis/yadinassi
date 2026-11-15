import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.compiled_backend import Engine

class FullBlocksTests(unittest.TestCase):
 def test_bulk_control_calls_and_collections_without_adapter(self):
  cases=[
   'Function F(x,Val y=2) x=x+y;Return x*2;EndFunction n=3;r=F(n);',
   'a=New Array;a.Add(1);a.Add(2);s=0;For Each x In a Do s=s+x;EndDo;r=s;',
   's=0;For i=1 To 5 Do If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;s=s+i;EndDo;r=s;',
   'i=0;While i<3 Do i=i+1;EndDo;r=i;',
   'Try Raise "hello";Except r=1;EndTry;',
   'Goto ~done;r=0;~done:r=4;',
   'a=New Structure("n",1);a.n=4;r=a.n;',
   'a=New Array;a.Add(1);a[0]=4;r=a[0];',
   'Function F(Val x) If x=0 Then Return 1;EndIf;Return F(x-1)+1;EndFunction r=F(3);']
  for src in cases:
   with self.subTest(src=src):
    outcomes=[]
    for backend in ('interpreter','compiled-strict'):
     vm=Interpreter(execution_backend=backend,compiled_plain_routines=True)
     try:
      with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):vm.execute(src)
      outcomes.append({k:vm.variables[k] for k in ('r','n','s','i') if k in vm.variables})
      if backend=='compiled-strict':
       stats=vm.compiled_backend_stats
       self.assertGreater(stats.get('python_translated_blocks',0),0)
       self.assertEqual(stats.get('plain_adapter_blocks',0),0)
       self.assertEqual(stats['inline_fragments'],0)
       self.assertEqual(stats['interpreter_fallbacks'],0)
      self.assertIsNone(vm.locals);self.assertEqual(vm._handled_errors,[])
     finally:vm.close()
    self.assertEqual(*outcomes)
 def test_call_effect_order_and_live_security_boundary(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True);seen=[]
  vm.register_function('Arg',lambda:(seen.append('arg') or 2))
  vm.register_function('Host',lambda x:(seen.append(('host',x)) or x))
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):vm.execute('r=Host(Arg());')
  self.assertEqual(seen,['arg',('host',2)]);self.assertEqual(vm.variables['r'],2)

class TranslatedImportTests(unittest.TestCase):
 def test_sync_import_service_and_retained_child_routine(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as directory,patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   root=Path(directory);(root/'helper.bsl').write_text('Function F(Val x=7) Export Return x;EndFunction')
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
   vm.execute('// #Import helper.bsl\nr=helper.F();',str(root/'main.bsl'))
   self.assertEqual(vm.variables['r'],7)
   self.assertGreater(vm.imports['helper'].interpreter.compiled_backend_stats['python_translated_blocks'],0)
   self.assertEqual(vm.compiled_backend_stats.get('plain_adapter_blocks',0),0)
