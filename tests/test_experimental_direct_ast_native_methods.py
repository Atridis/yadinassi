"""Native methods route runtime argument and receiver errors without preflight rejection."""
import unittest
from test_experimental_direct_ast_externals import DirectSourceAssertions

class NativeMethodsTests(DirectSourceAssertions,unittest.TestCase):
    def test_native_method_families(self):
        for source, checks in (
            ('A=New Array;A.Add(1);A.Add(2);R=A.UBound();F=A.Find(2);A.Delete(0);S=A[0];A=0;', {'expected': {'a': 0, 'f': 1, 'r': 1, 's': 2}}),
            ('A=New Array;A.Insert(0);R=A[0];A=0;', {'expected': {'a': 0, 'r': None}}),
            ('M=New Map;M.Insert("a",1);M.Delete("a");M.Delete("absent");R=M.Count();M=0;', {'expected': {'m': 0, 'r': 0}}),
            ('S=New Structure;S.Insert("a");R=S.a;S.Delete("a");S=0;', {'expected': {'r': None, 's': 0}}),
            ('A=New Array;A.Get(Touch(),Touch());', dict(error='Get ожидает', touches=2)),
            ('A=New Array;A.Add(Touch(),Touch());', dict(error='Add ожидает', touches=2)),
            ('A=New Array;A.UBound(Touch());', dict(error='UBound ожидает', touches=1)),
            ('A=New Array;A.Find();', dict(error='Find ожидает', touches=0)),
            ('A=New Array;A.Delete(Touch(),Touch());', dict(error='Delete ожидает', touches=2)),
            ('M=New Map;M.Get(Touch(),Touch());', dict(error='Get ожидает', touches=2)),
            ('M=New Map;M.Find(Touch());', dict(error='Метод соответствия не найден: Find', touches=0)),
            ('M=New Map;M.Add(Touch(),Touch());', dict(error='Метод соответствия не найден: Add', touches=0)),
            ('R=SearchDirection.Get();', dict(error='Метод или свойство не найдено: Get', touches=0)),
        ):
            with self.subTest(source=source):self.check_source(source,**checks)

    def test_invalid_arity_drops_arguments_before_handler(self):
        from yadinassi import Interpreter
        events=[];vm=Interpreter();self.addCleanup(vm.close)
        class Temporary:
            def __del__(self):events.append((vm.variables.get('x'),vm.variables.get('y')))
        vm.register_function('Make',Temporary)
        vm.execute('A=New Array;Try A.Count(Make());Except X=1;EndTry;Y=2;')
        self.assertEqual(events,[(None,None)])
        self.assertEqual((vm.variables['x'],vm.variables['y']),(1,2))

    def test_nested_invalid_arity_emission_is_linear(self):
        from unittest.mock import patch
        from yadinassi import Interpreter
        from yadinassi.execution.direct import python_direct
        from yadinassi.execution.codegen import experimental_direct_ast as direct
        for compiler in (direct.compile_module,direct.compile_module_whole_source):
            counts=[]
            for size in (4,8,12):
                expression='1'
                for _ in range(size):expression='A.Count('+expression+')'
                vm=Interpreter()
                try:
                    with patch.object(python_direct,'_compile',compiler):
                        plan=vm.prepare('A=New Array;R='+expression+';')
                    counts.append(plan._plan._research_lowering_counts)
                finally:vm.close()
            # Incremental Python node/BSL visit growth is constant per nested call.
            for column in (1,2):
                self.assertEqual(counts[2][column]-counts[1][column],counts[1][column]-counts[0][column])
