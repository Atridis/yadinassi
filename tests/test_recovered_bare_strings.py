import unittest
from recovered_bare_fixture import Interpreter

class RecoveredBareStrings(unittest.TestCase):
    def test_slice_and_replace_both_routes(self):
        source='A=Сред("abcdef",2,3); B=Mid("abcdef",3); C=СтрЗаменить("aba","a","xx"); D=Mid("abc",0,2); E=Mid("abc",2,-1);'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual([vm.variables[k] for k in 'abcde'],['bcd','cdef','xxbxx','ab',''])
    def test_dynamic_arguments_evaluated_once_in_source_order(self):
        source='Function Text(C) C=C*10+1; Return "abcdef"; EndFunction; Function Start(C) C=C*10+2; Return 2; EndFunction; Function Count(C) C=C*10+3; Return 3; EndFunction; C=0; R=Mid(Text(C),Start(C),Count(C));'
        vm=Interpreter();vm.execute(source)
        self.assertEqual((vm.variables['c'],vm.variables['r']),(123,'bcd'))
    def test_direct_generated_code_and_unicode(self):
        p=Interpreter().prepare('R=Mid("a😀c",2,1); X=StrReplace("aba","a","x");')
        self.assertIn('[1:2]',p.generated_source);self.assertIn('str.replace(',p.generated_source)
        self.assertNotIn('resolve',p.generated_source)
        vm=Interpreter();vm.execute_prepared(p);self.assertEqual(vm.variables['r'],'😀')
    def test_no_string_coercion(self):
        for source in ('R=StrReplace(1,"a","b");','R=Mid(1,1,1);'):
            with self.assertRaises(TypeError):Interpreter().execute(source)
