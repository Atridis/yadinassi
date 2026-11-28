import unittest
from decimal import Decimal
from yadinassi import Interpreter


class DefiniteReadsTests(unittest.TestCase):
    def paired(self, source, install=None):
        results=[]
        for prepared in (False,True):
            vm=Interpreter(allow_extensions=install is not None)
            self.addCleanup(vm.close)
            if install:install(vm)
            error=None
            try:
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
            except Exception as exc:error=(type(exc).__name__,str(exc))
            results.append((vm.variables,error))
        self.assertEqual(*results)
        return results[0]

    def test_callback_delete_after_assignment(self):
        values,error=self.paired('x=1;Drop();y=x;',lambda vm:vm.register_function('Drop',lambda:vm.variables.pop('x')))
        self.assertNotIn('y',values); self.assertIn('не определена',error[1])

    def test_callback_clear_update_same_dict(self):
        def install(vm):
            def reset():vm.variables.clear();vm.variables['x']=Decimal(9)
            vm.register_function('Reset',reset)
        values,_=self.paired('x=1;Reset();y=x+1;',install)
        self.assertEqual(values['y'],10)

    def test_loop_callback_counter_mutation(self):
        def install(vm):vm.register_function('Change',lambda:vm.variables.__setitem__('i',Decimal(5)))
        values,_=self.paired('s=0;For i=1 To 5 Do s=s+1;Change();EndDo;',install)
        self.assertEqual(values['s'],1);self.assertEqual(values['i'],6)

    def test_loop_callback_deletion(self):
        def install(vm):vm.register_function('Drop',lambda:vm.variables.pop('s',None))
        values,error=self.paired('s=0;For i=1 To 2 Do s=s+1;Drop();EndDo;',install)
        self.assertIsNotNone(error)
        self.assertNotIn('s',values)

    def test_error_publishes_partial_state(self):
        values,error=self.paired('s=0;For i=1 To 4 Do s=s+i;x=1/(3-i);EndDo;')
        self.assertEqual(values['s'],6);self.assertEqual(values['i'],3);self.assertIsNotNone(error)

    def test_branch_intersection_and_missing_branch(self):
        values,error=self.paired('x=1;If x=1 Then y=2;Else y=3;EndIf;r=y;')
        self.assertIsNone(error)
        self.assertEqual(values['r'],2)
        values,error=self.paired('x=0;If x=1 Then y=2;EndIf;r=y;')
        self.assertIsNotNone(error)
        self.assertNotIn('r',values)

    def test_byref_invalidates(self):
        values,_=self.paired('Procedure F(x) x=9;EndProcedure x=1;F(x);y=x;')
        self.assertEqual(values['y'],9)

    def test_unknown_operator_can_delete_state(self):
        def install(vm):
            class Host:
                def __add__(self,other):vm.variables.pop('x',None);return Decimal(1)
            vm.variables['host']=Host()
        vm=Interpreter()
        self.addCleanup(vm.close)
        install(vm)
        with self.assertRaisesRegex(Exception,'не определена'):
            vm.execute('x=1;y=host+1;z=x;')
        self.assertNotIn('x',vm.variables);self.assertNotIn('z',vm.variables)

    def test_zero_iterations_do_not_define_body_names(self):
        values,error=self.paired('For i=2 To 1 Do y=1;EndDo;r=y;')
        self.assertIsNotNone(error)
        self.assertFalse({'y','r'} & values.keys())

if __name__=='__main__':unittest.main()
