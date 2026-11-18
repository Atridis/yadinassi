"""Production has one compiler; the old generator is only a test oracle."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest
from yadinassi import experimental_naked_collections as runtime
from tests import retired_text_compiler as oracle

class RetiredCompilerTests(unittest.TestCase):
    def test_runtime_has_no_old_generator_entrypoints(self):
        for name in ('prepare','compile_source','execute'):
            self.assertNotIn(name,vars(runtime))
        for name in ('Program','_Cell','_Reference','_IndexRef','_AttributeRef','UnsupportedNakedSyntax'):
            self.assertIs(getattr(runtime,name),getattr(oracle,name))

    def test_production_imports_no_test_oracle(self):
        root=Path(runtime.__file__).parent
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('tests','retired_text_compiler')),str(path))
                elif isinstance(node,ast.Import):
                    self.assertFalse(any(item.name.startswith(('tests','retired_text_compiler')) for item in node.names),str(path))

    def test_default_and_legacy_interpreter_without_test_modules(self):
        code='''
import sys
from yadinassi import Interpreter
for backend in ('python-direct','interpreter'):
    vm=Interpreter(execution_backend=backend)
    try:
        vm.execute('Function F(Val X) Return X+1;EndFunction R=F(41);')
        if vm.variables['r'] != 42: raise AssertionError('result')
    finally: vm.close()
if any(n.startswith('tests.') or n == 'tests' for n in sys.modules):
    raise AssertionError('production imported tests')
'''
        subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),'-c',code],check=True)
