"""Direct BSL collection access and operand order, without an executor oracle."""

from decimal import Decimal
from unittest import TestCase

from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class TranslatedAccessTests(TestCase):
    def vm(self, *, allow_extensions=False):
        vm = Interpreter(allow_extensions=allow_extensions)
        self.addCleanup(vm.close)
        return vm

    def test_collection_index_read_write(self):
        cases = (
            ("a=New Array();a.Add(2);", "a[0]"),
            ("a=New Map();a.Insert(0,2);", "a[0]"),
            ('a=New Structure("x",2);', 'a["x"]'),
        )
        for source, access in cases:
            with self.subTest(access=access, source=source):
                vm = self.vm()
                vm.execute(source)
                self.assertEqual(vm.execute(access), Decimal(2))
                vm.execute(f"{access}=7;")
                self.assertEqual(vm.execute(access), Decimal(7))

    def test_value_list_index_returns_live_item(self):
        vm = self.vm()
        vm.execute("a=New ValueList();a.Add(2);item=a[0];")
        self.assertEqual(vm.execute("item.Value"), Decimal(2))
        vm.execute("item.Value=7;")
        self.assertEqual(vm.execute("a[0].Value"), Decimal(7))

    def test_structure_attribute_read_and_write_share_the_indexed_value(self):
        vm = self.vm()
        vm.execute('a=New Structure("x",2);')
        self.assertEqual(vm.execute("a.x"), Decimal(2))
        vm.execute("a.x=11;")
        self.assertEqual(vm.execute('a["x"]'), Decimal(11))

    def test_index_read_observes_mutation_during_index_evaluation(self):
        vm = self.vm(allow_extensions=True)
        vm.execute("a=New Array();a.Add(2);")
        array = vm.variables["a"]
        events = []

        def index():
            events.append("index")
            array[0] = Decimal(9)
            return Decimal(0)

        vm.register_function("Index", index)
        self.assertEqual(vm.execute("a[Index()]"), Decimal(9))
        self.assertEqual(events, ["index"])

    def test_indexed_write_evaluates_index_before_rhs_and_keeps_receiver(self):
        vm = self.vm(allow_extensions=True)
        vm.execute("a=New Array();a.Add(2);replacement=New Array();replacement.Add(99);")
        array, replacement = vm.variables["a"], vm.variables["replacement"]
        events = []

        def index():
            events.append("index")
            return Decimal(0)

        def rhs():
            events.append("rhs")
            vm.variables["a"] = replacement
            return Decimal(7)

        vm.register_function("Index", index)
        vm.register_function("Rhs", rhs)
        vm.execute("a[Index()]=Rhs();")
        self.assertEqual(events, ["index", "rhs"])
        self.assertEqual(array[0], Decimal(7))
        self.assertEqual(replacement[0], Decimal(99))
        self.assertIs(vm.variables["a"], replacement)

    def test_attribute_write_keeps_receiver_when_rhs_rebinds_name(self):
        vm = self.vm(allow_extensions=True)
        vm.execute('a=New Structure("x",2);alias=a;replacement=New Structure("x",99);')

        def rhs():
            vm.variables["a"] = vm.variables["replacement"]
            return Decimal(7)

        vm.register_function("Rhs", rhs)
        vm.execute("a.x=Rhs();")
        self.assertEqual(vm.execute("alias.x"), Decimal(7))
        self.assertEqual(vm.execute("a.x"), Decimal(99))

    def test_invalid_receiver_precedes_index_and_rhs(self):
        for statement in ("a[Index()]", "a.x=Rhs();", "a[Index()]=Rhs();"):
            with self.subTest(statement=statement):
                vm = self.vm(allow_extensions=True)
                vm.variables["a"] = Decimal(3)
                index = lambda: self.fail("index evaluated for invalid receiver")
                rhs = lambda: self.fail("right-hand side evaluated for invalid receiver")
                vm.register_function("Index", index)
                vm.register_function("Rhs", rhs)
                with self.assertRaises(BoundaryViolation):
                    vm.execute(statement)
