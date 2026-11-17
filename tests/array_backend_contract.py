"""Exact host representations for the same public BSL array contract."""
from yadinassi import Interpreter
from yadinassi.values import BSLArray, BSLFixedArray
from yadinassi.serialization import value_to_string_internal

class ArrayBackendContract:
    backend = None

    def interpreter(self, **kwargs):
        if self.backend is not None:
            kwargs['execution_backend'] = self.backend
        vm = Interpreter(**kwargs)
        self.addCleanup(vm.close)
        self.assertEqual(vm.execution_backend, self.backend or 'python-direct')
        return vm

    def array_items(self, value):
        expected = list if self.backend is None else BSLArray
        self.assertIs(type(value), expected)
        return value if expected is list else value.items

    def fixed_items(self, value):
        self.assertIs(type(value), BSLFixedArray)
        return value.items

    def serialize_array(self, name):
        value = self.vm.execute(name)
        items = self.array_items(value)
        result = self.vm.execute('ValueToStringInternal(' + name + ')')
        # Retain the legacy public host-codec assertion, and require the direct
        # stream to match a canonical host array with exactly the same contents.
        if self.backend is not None:
            self.assertEqual(result, value_to_string_internal(value))
        else:
            canonical = BSLArray()
            for item in items:
                canonical.add(item)
            self.assertEqual(result, value_to_string_internal(canonical))
        return result
