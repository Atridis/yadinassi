"""Product contracts retained when the obsolete compiled cache tests were removed."""
import gc
import unittest
import weakref
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError


class DirectRuntimeIsolationDiagnosticsTests(unittest.TestCase):
    def test_fresh_vm_callbacks_and_no_host_retention(self):
        class Host:
            def __init__(self, value): self.value = value
            def __call__(self): return self.value
        refs = []
        for expected in (11, 37):
            vm = Interpreter()
            self.assertEqual(vm.execution_backend, 'python-direct')
            callback = Host(expected)
            refs.extend((weakref.ref(vm), weakref.ref(callback)))
            vm.register_function('Callback', callback)
            vm.execute('r=Callback();')
            self.assertEqual(vm.variables['r'], expected)
            del vm, callback
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))

    def test_fresh_source_diagnostics(self):
        for source_name, text, expected_line in (
                ('first.bsl', 'r=1/0;', 1), ('second.bsl', '\n\nr=1/0;', 3)):
            vm = Interpreter()
            self.addCleanup(vm.close)
            with self.assertRaises(BSLRuntimeError) as failure:
                vm.execute(text, source_name)
            self.assertEqual(failure.exception.source, source_name)
            self.assertEqual(failure.exception.line, expected_line)
            self.assertEqual(failure.exception.source_line, 'r=1/0;')
