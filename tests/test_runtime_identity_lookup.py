"""Exact type/owned identity lookups must not introduce host hooks or forgery."""
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.types.type_values import type_of
from yadinassi.types.values import BSLType, BSLArray
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.collections.value_trees import BSLValueTree


class RuntimeIdentityLookupTests(unittest.TestCase):
    def test_static_and_dynamic_type_results_remain_exact(self):
        cases = [(None, BSLType.UNDEFINED), (True, BSLType.BOOLEAN),
                 (Decimal(1), BSLType.NUMBER), ('x', BSLType.STRING),
                 (BSLArray(), BSLType.ARRAY), (BSLValueTable(), BSLType.VALUE_TABLE),
                 (BSLValueTree(), BSLType.VALUE_TREE)]
        for value, expected in cases:
            with self.subTest(expected=expected): self.assertIs(type_of(value), expected)

    def test_every_static_type_matches_original_first_identity_scan(self):
        from yadinassi.types.type_values import _VALUE_TYPES
        for cls, _, _ in _VALUE_TYPES:
            with self.subTest(cls=cls.__name__):
                # Uninitialized instances are enough: static type reflection must
                # not read payloads or invoke constructor/descriptor effects.
                try:
                    allocate = list.__new__ if issubclass(cls, list) else object.__new__
                    value = allocate(cls)
                except TypeError:
                    value = cls()
                expected = next(kind for exact, kind, _ in _VALUE_TYPES if type(value) is exact)
                self.assertIs(type_of(value), expected)

    def test_public_typeof_matches_host_identity_for_table_and_tree_rows(self):
        source = ("T=New ValueTable; T.Columns.Add(\"X\"); TableRow=T.Add(); TableRow.X=7; "
                  "Tree=New ValueTree; Tree.Columns.Add(\"X\"); TreeRow=Tree.Rows.Add(); TreeRow.X=7; "
                  "TableKind=TypeOf(TableRow); TreeKind=ТипЗнч(TreeRow);")
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter()
                self.addCleanup(vm.close)
                if prepared:
                    vm.execute_prepared(vm.prepare(source))
                else:
                    vm.execute(source)
                for row, kind, expected in (
                    ('tablerow', 'tablekind', BSLType.VALUE_TABLE_ROW),
                    ('treerow', 'treekind', BSLType.VALUE_TREE_ROW),
                ):
                    self.assertIs(vm.variables[kind], expected)
                    self.assertIs(type_of(vm.variables[row]), expected)

    def test_foreign_type_and_subclass_reject_without_metaclass_hooks(self):
        class Meta(type):
            def __hash__(cls): raise AssertionError('metaclass hash')
            def __eq__(cls, other): raise AssertionError('metaclass equality')
        class Foreign(metaclass=Meta): pass
        class SubArray(BSLArray, metaclass=Meta): pass
        for value in (Foreign(), SubArray()):
            with self.assertRaises(TypeError): type_of(value)
