import sys
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

class PublicationBoundaryTests(unittest.TestCase):
    def test_close_during_private_kernel_does_not_publish(self):
        vm=Interpreter();plan=vm.prepare('M=New Map;For I=0 To 50 Do M.Insert(I,I);EndDo;R=1;')
        code=plan._plan.function.__code__;seen=[]
        def trace(frame,event,arg):
            if frame.f_code is code and event=='line':
                seen.append(event)
                if len(seen)==8:vm.close()
            return trace
        old=sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        finally:sys.settrace(old);vm.close()
        self.assertGreaterEqual(len(seen),8)
        self.assertNotIn('m',vm.variables);self.assertNotIn('r',vm.variables);self.assertNotIn('i',vm.variables)
    def test_revocation_from_first_old_value_stops_later_publication(self):
        vm=Interpreter();events=[]
        class Old:
            def __del__(self):events.append('closed');vm.close()
        vm.variables['a']=Old();vm.variables['b']=Decimal(9)
        try:
            with self.assertRaises(BoundaryViolation):vm.execute('A=1;B=2;')
            self.assertEqual(events,['closed'])
            self.assertEqual(vm.variables['a'],Decimal(1));self.assertEqual(vm.variables['b'],Decimal(9))
        finally:vm.close()
