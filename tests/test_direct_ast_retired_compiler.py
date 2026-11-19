"""Production compiler isolation without retaining an executable old oracle."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest
from yadinassi import experimental_naked_collections as runtime

class RetiredCompilerTests(unittest.TestCase):
    def test_runtime_has_no_old_generator_entrypoints(self):
        for name in ('prepare','compile_source','execute'):
            self.assertNotIn(name,vars(runtime))

    def test_production_imports_no_test_oracle(self):
        root=Path(runtime.__file__).parent
        for path in root.rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('tests','retired_text_compiler')),str(path))
                elif isinstance(node,ast.Import):
                    self.assertFalse(any(item.name.startswith(('tests','retired_text_compiler')) for item in node.names),str(path))

    def test_default_without_test_modules(self):
        code='''
import sys
from yadinassi import Interpreter
vm=Interpreter()
try:
    vm.execute('Function F(Val X) Return X+1;EndFunction R=F(41);')
    if vm.variables['r'] != 42: raise AssertionError('result')
finally: vm.close()
if any(n.startswith('tests.') or n == 'tests' for n in sys.modules):
    raise AssertionError('production imported tests')
'''
        subprocess.run([sys.executable,*(['-O'] if not __debug__ else []),'-c',code],check=True)
