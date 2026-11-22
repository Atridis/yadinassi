import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_plain_map import PlainMap

class StaticMapTests(unittest.TestCase):
    def test_map_loops_use_local_native_storage(self):
        vm=Interpreter()
        try:
            source='M=New Map;For I=0 To 7 Do M.Insert(I,I);EndDo;R=0;For I=0 To 7 Do R=R+M.Get(I);EndDo;'
            plan=vm.prepare(source);text=plan._plan.generated_source
            self.assertNotIn('resolve_member_call',text)
            self.assertIn('_native_dict_get(',text)
            self.assertIn('_native_dict_setitem(',text)
            vm.execute_prepared(plan)
            self.assertIs(type(vm.variables['m']),PlainMap);self.assertEqual(vm.variables['r'],Decimal(28))
            # A Number inserted by the direct operation remains distinct
            # from a Boolean added later through the public generic route.
            vm.execute('M.Insert(True,99); Bool=M.Get(True); Num=M[1];')
            self.assertEqual((vm.variables['bool'],vm.variables['num']), (99,1))
            self.assertEqual(vm.execute('M.Count()'),9)
        finally:vm.close()
    def test_missing_map_value_is_not_a_host_callback(self):
        vm=Interpreter()
        try:
            with self.assertRaises(Exception):vm.execute('M=New Map;M.Insert(1,2);R=0;R=R+M.Get(3);')
            self.assertEqual(vm.variables['r'],Decimal(0));self.assertEqual(vm.variables['m'].get(1),Decimal(2))
        finally:vm.close()
