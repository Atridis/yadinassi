"""Specialization uses identity, never user equality/hash hooks."""
import unittest
from yadinassi import Interpreter

class ServiceIdentityTests(unittest.TestCase):
    def test_unhashable_callable_is_not_classified_as_canonical_regex(self):
        class Callable:
            __hash__=None
            def __eq__(self,other):raise AssertionError('equality classification')
            def __call__(self,*args):return 'custom'
        vm=Interpreter();vm.register_function('StrFindByRegularExpression',Callable())
        self.assertEqual(vm.execute('StrFindByRegularExpression("a","a")'),'custom')
        with self.assertRaisesRegex(Exception,'Пропуск аргументов'):
            vm.execute('StrFindByRegularExpression("a","a",,)')
