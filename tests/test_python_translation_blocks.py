"""Behavior retained from retired translation engines; only the direct backend runs.

Implementation-only registry, fusion emitter, instrumentation and inline-budget
checks belonged to deleted engines and are retired, not skipped or emulated.
Unsupported behavioral cases deliberately remain ordinary failing tests.
"""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError

class DirectBlocks(unittest.TestCase):
    def test_control_calls_and_collections(self):
        cases=[('Function F(x,Val y=2) x=x+y;Return x*2;EndFunction n=3;r=F(n);', 10), ('a=New Array;a.Add(1);a.Add(2);s=0;For Each x In a Do s=s+x;EndDo;r=s;', 3), ('s=0;For i=1 To 5 Do If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;s=s+i;EndDo;r=s;', 4), ('i=0;While i<3 Do i=i+1;EndDo;r=i;', 3), ('Try Raise "hello";Except r=1;EndTry;', 1), ('Goto ~done;r=0;~done:r=4;', 4), ('a=New Structure("n",1);a.n=4;r=a.n;', 4), ('a=New Array;a.Add(1);a[0]=4;r=a[0];', 4), ('Function F(Val x) If x=0 Then Return 1;EndIf;Return F(x-1)+1;EndFunction r=F(3);', 4)]
        for source,expected in cases:
            with self.subTest(source=source):
                vm=Interpreter();self.addCleanup(vm.close)
                vm.execute(source)
                self.assertEqual(vm.variables["r"],expected)
                self.assertIsNone(vm.locals)
                self.assertEqual(vm._handled_errors,[])
    def test_call_order_once(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
        vm.register_function('Arg',lambda:seen.append('arg') or Decimal(2))
        vm.register_function('Host',lambda x:seen.append(('host',x)) or x)
        vm.execute('r=Host(Arg());')
        self.assertEqual(seen,['arg',('host',Decimal(2))]);self.assertEqual(vm.variables['r'],2)
    def test_retained_defaults_and_live_import(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'helper.bsl').write_text('Function F(Val x=7) Export Return x;EndFunction')
            vm=Interpreter();self.addCleanup(vm.close)
            vm.execute('// #Import helper.bsl\nr=helper.F();',str(root/'main.bsl'))
            self.assertEqual(vm.variables['r'],7)
            vm.execute('x=99;r=helper.F();')
            self.assertEqual(vm.variables['r'],7)
