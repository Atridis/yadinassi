"""Native methods route runtime argument and receiver errors without preflight rejection."""
from test_experimental_direct_ast_externals import DirectASTExternalTests

class NativeMethodsTests(DirectASTExternalTests):
    def test_native_method_families(self):
        for source in (
            'A=New Array;A.Add(1);A.Add(2);R=A.UBound();F=A.Find(2);A.Delete(0);S=A[0];A=0;',
            'A=New Array;A.Insert(0);R=A[0];A=0;',
            'M=New Map;M.Insert("a",1);M.Delete("a");M.Delete("absent");R=M.Count();M=0;',
            'S=New Structure;S.Insert("a");R=S.a;S.Delete("a");S=0;',
            'A=New Array;A.Get(Touch(),Touch());',
            'A=New Array;A.Add(Touch(),Touch());',
            'A=New Array;A.UBound(Touch());',
            'A=New Array;A.Find();',
            'A=New Array;A.Delete(Touch(),Touch());',
            'M=New Map;M.Get(Touch(),Touch());',
            'M=New Map;M.Find(Touch());',
            'M=New Map;M.Add(Touch(),Touch());',
            'R=SearchDirection.Get();',
        ):
            with self.subTest(source=source):self.paired(source)

    def test_invalid_arity_drops_arguments_before_handler(self):
        from unittest.mock import patch
        from yadinassi import Interpreter,python_direct
        from yadinassi import experimental_direct_ast as direct
        from direct_ast_text_oracle import compile_module as oracle
        outcomes=[]
        for compiler in (oracle,direct.compile_module,direct.compile_module_whole_source):
            events=[];vm=Interpreter()
            class Temporary:
                def __del__(self):events.append((vm.variables.get('x'),vm.variables.get('y')))
            vm.register_function('Make',Temporary)
            try:
                with patch.object(python_direct,'_compile',compiler):
                    vm.execute('A=New Array;Try A.Count(Make());Except X=1;EndTry;Y=2;')
                outcomes.append(list(events))
            finally:vm.close()
        self.assertEqual(outcomes,[[(None,None)]]*3)

    def test_nested_invalid_arity_emission_is_linear(self):
        from unittest.mock import patch
        from yadinassi import Interpreter,python_direct
        from yadinassi import experimental_direct_ast as direct
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
