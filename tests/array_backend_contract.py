"""Assertions for the public BSL array contract on the direct backend."""
from yadinassi import Interpreter
from yadinassi.types.values import BSLArray, BSLFixedArray
from yadinassi.formats.storage.serialization import value_to_string_internal

class ArrayBackendContract:
    def interpreter(self, **kwargs):
        vm = Interpreter(**kwargs)
        self.addCleanup(vm.close)
        self.assertEqual(vm.execution_backend, 'python-direct')
        return vm

    def array_items(self, value):
        self.assertIs(type(value), list)
        return value

    def fixed_items(self, value):
        self.assertIs(type(value), BSLFixedArray)
        return value.items

    def serialize_array(self, name):
        value = self.vm.execute(name)
        items = self.array_items(value)
        result = self.vm.execute('ValueToStringInternal(' + name + ')')
        # Compare with an independently populated canonical host array.
        canonical = BSLArray()
        for item in items:
            canonical.add(item)
        self.assertEqual(result, value_to_string_internal(canonical))
        return result
