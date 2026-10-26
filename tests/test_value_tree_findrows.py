"""Generic model and local safety policy; not additional native observations."""
from decimal import Decimal as D, localcontext, InvalidOperation
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi import value_trees as trees
from yadinassi.dates import BSLDate
from yadinassi.structures import BSLStructure, BSLFixedStructure
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.values import BSLArray, NULL


def setup():
    tree = trees.BSLValueTree()
    tree.columns.add('Key')
    tree.columns.add('Other')
    a = tree.rows.add()
    b = tree.rows.add()
    b1 = b.rows.add()
    a1 = a.rows.add()
    a2 = a.rows.add()
    a11 = a1.rows.add()
    nodes = (a, b, b1, a1, a2, a11)
    for node in nodes:
        node.set_member('Key', 'yes')
        node.set_member('Other', D(7))
    return tree, nodes


class FindRowsGenericModel(unittest.TestCase):
    def setUp(self):
        self.tree, self.nodes = setup()
        self.a, self.b, self.b1, self.a1, self.a2, self.a11 = self.nodes
        self.query = BSLStructure('Key', 'yes')

    def test_hierarchy_not_registry_order_and_local_receiver(self):
        self.assertEqual(self.tree.rows.find_rows(self.query, True).items,
                         [self.a, self.a1, self.a11, self.a2, self.b, self.b1])
        self.assertEqual(self.a.rows.find_rows(self.query, True).items,
                         [self.a1, self.a11, self.a2])
        self.assertEqual(self.a.rows.find_rows(self.query).items, [self.a1, self.a2])
        first = self.tree.rows.insert(D(0))
        first.set_member('Key', 'yes')
        self.assertIs(self.tree.rows.find_rows(self.query, True).items[0], first)
        self.assertIs(list(self.tree._all_rows)[-1], first)

    def test_recursion_does_not_prune_nonmatching_parents(self):
        self.a.set_member('Key', 'no')
        self.a1.set_member('Key', 'no')
        self.b.set_member('Key', 'no')
        self.assertEqual(self.tree.rows.find_rows(self.query, True).items,
                         [self.a11, self.a2, self.b1])

    def test_filter_names_case_and_order_do_not_change_conjunction(self):
        self.a2.set_member('Other', D(9))
        for fields, values in [('Key,Other', ('yes', D(9))),
                               ('oThEr,kEy', (D(9), 'yes'))]:
            self.assertEqual(self.tree.rows.find_rows(BSLStructure(fields, *values), True).items,
                             [self.a2])

    def test_reference_array_is_new_list_with_same_row_objects(self):
        old = self.tree.rows.find_rows(self.query, True)
        self.assertIs(type(old), BSLArray)
        self.assertIsNot(old.items, self.tree.rows.items)
        self.assertIs(old.items[1], self.a1)
        old.items[1].set_member('Other', D(31))
        self.assertEqual(self.a1.get_member('Other'), D(31))
        self.a1.set_member('Other', D(32))
        self.assertEqual(old.items[1].get_member('Other'), D(32))
        removed = old.items.pop(0)
        self.assertIs(removed, self.a)
        self.assertIs(self.tree.rows.items[0], self.a)
        added = self.a.rows.add()
        added.set_member('Key', 'yes')
        self.assertNotIn(added, old.items)
        self.assertIn(added, self.tree.rows.find_rows(self.query, True).items)
        self.query.set('Key', 'gone')
        self.assertEqual(len(old.items), 5)
        self.assertEqual(self.tree.rows.find_rows(self.query, True).items, [])

    def test_generic_typed_scalars_not_witness_value_lookup(self):
        samples = [D('7.25'), True, '7.25', 'Mixed ', None, NULL]
        for node, value in zip(self.nodes, samples):
            node.set_member('Key', value)
        for node, value in zip(self.nodes, samples):
            result = self.tree.rows.find_rows(BSLStructure('Key', value), True)
            self.assertEqual(len(result.items), 1)
            self.assertIs(result.items[0], node)
        self.assertEqual(self.tree.rows.find_rows(BSLStructure('Key', 'mixed '), True).items, [])
        self.assertEqual(self.tree.rows.find_rows(BSLStructure('Key', 'Mixed'), True).items, [])

    def test_unknown_schema_is_checked_before_empty_receiver_or_short_circuit(self):
        for rows in (self.tree.rows, self.a11.rows):
            for query in (BSLStructure('Missing', D(7)),
                          BSLStructure('Key,Missing', 'no', D(7))):
                with self.assertRaises(ValueError): rows.find_rows(query, True)
            self.assertEqual(rows.find_rows(BSLStructure(), True).items, [])


class FindRowsLocalPolicy(unittest.TestCase):
    def setUp(self):
        self.tree, self.nodes = setup()
        self.query = BSLStructure('Key', 'yes')

    def test_decimal_flag_extension_is_separately_evidenced_conversion_policy(self):
        for flag, count in [(D(0), 2), (D('-0'), 2), (D(2), 6),
                            (D('-3.5'), 6), (D('1E+999999'), 6), (D('1E-999999'), 6)]:
            self.assertEqual(len(self.tree.rows.find_rows(self.query, flag).items), count)
        with localcontext() as context:
            context.traps[InvalidOperation] = True
            before = dict(context.flags)
            for flag in (D('NaN'), D('sNaN'), D('Infinity'), D('9' * 4097)):
                with self.assertRaises(ValueError): self.tree.rows.find_rows(self.query, flag)
            self.assertEqual(dict(context.flags), before)

    def test_flag_validation_preserves_both_clear_and_already_set_ambient_flags(self):
        for initial in (False, True):
            with localcontext() as context:
                context.flags[InvalidOperation] = initial
                context.traps[InvalidOperation] = True
                before = dict(context.flags)
                for value in (D('NaN'), D('sNaN'), D('Infinity'), D('9' * 4097)):
                    with self.assertRaises(ValueError):
                        self.tree.rows.find_rows(self.query, value)
                self.assertEqual(dict(context.flags), before)

    def test_number_reservation_precedes_converter_and_tuple_extraction(self):
        for work in (0, 1, 3 * trees._MAX_NUMBER_DIGITS - 1):
            with patch.object(trees, '_MAX_SEARCH_WORK', work), \
                    patch.object(trees, '_number_value', side_effect=AssertionError('unreserved number')), \
                    patch.object(trees, '_boolean_value', side_effect=AssertionError('unreserved flag')):
                with self.assertRaises(ValueError):
                    self.tree.rows.find_rows(self.query, D(1))
        # Oversized coefficients are rejected before the old tuple-based helper,
        # including zero padding that numeric-value equality would not detect.
        for value in (D('9' * 100_000), D('1' + '0' * 100_000)):
            with patch.object(trees, '_number_value', side_effect=AssertionError('unbounded tuple')):
                with self.assertRaises(ValueError):
                    self.tree.rows.find_rows(BSLStructure('Key', value))

    def test_number_guard_preserves_extreme_exponents_and_ambient_context(self):
        from decimal import MAX_EMAX, MIN_ETINY
        for value in (D((0, (1,), MAX_EMAX)), D((0, (1,), MIN_ETINY)),
                      D((0, (0,), MIN_ETINY)), D('9' * 4096)):
            self.nodes[0].set_member('Key', value)
            with localcontext() as context:
                context.prec = 2
                for signal in context.traps: context.traps[signal] = True
                context.clear_flags()
                found = self.tree.rows.find_rows(BSLStructure('Key', value))
                self.assertEqual(found.items, [self.nodes[0]])
                self.assertFalse(any(context.flags.values()))

    def test_flag_rejection_precedes_converter_and_empty_filter_shortcut(self):
        for flag in (None, NULL, [], {}, object(), 1, 'true', 'False', 'Истина', 'True '):
            with patch.object(trees, '_boolean_value', side_effect=AssertionError('converter called')):
                for query in (self.query, BSLStructure()):
                    with self.assertRaises((TypeError, ValueError)):
                        self.tree.rows.find_rows(query, flag)

    def test_exact_structure_required_and_no_optional_holes(self):
        for query in (None, NULL, D(1), {}, BSLFixedStructure(self.query)):
            with self.assertRaises(TypeError): self.tree.rows.find_rows(query)
        vm = Interpreter(lambda _: None)
        vm.execute('t=New ValueTree; t.Columns.Add("K"); q=New Structure("K", 1);')
        for call in ('t.Rows.FindRows(q,)', 't.Rows.FindRows(,True)',
                     't.Rows.FindRows(q,True,False)'):
            with self.assertRaises(BSLError): vm.execute(call)

    def test_deferred_scalar_types_are_not_silent_identity_comparisons(self):
        for value in (BSLDate(0), BSLUUID('00000000-0000-0000-0000-000000000000'),
                      BSLArray(), BSLStructure(), object(), 7):
            with self.assertRaises(TypeError):
                self.tree.rows.find_rows(BSLStructure('Key', value), True)

    def test_every_selected_cell_validated_before_false_conjunction(self):
        row = self.nodes[0]
        row.set_member('Key', 'no')
        row.set_member('Other', object())
        for query in (BSLStructure('Key,Other', 'yes', D(7)),
                      BSLStructure('Other,Key', D(7), 'yes')):
            with self.assertRaises(TypeError): self.tree.rows.find_rows(query, True)
        # Unselected cells remain irrelevant, including unsupported object values.
        self.assertEqual(len(self.tree.rows.find_rows(self.query, True).items), 5)

    def test_deleted_receiver_and_result_row_remain_invalid(self):
        row = self.nodes[0]
        held = self.tree.rows.find_rows(self.query)
        self.tree.rows.delete(row)
        self.assertIs(held.items[0], row)
        with self.assertRaises(ValueError): held.items[0].get_member('Key')
        for query in (self.query, BSLStructure()):
            with self.assertRaises(ValueError): row.rows.find_rows(query, True)

    def test_hostile_types_and_primitive_subclasses_never_call_hooks(self):
        calls = []
        class Meta(type):
            def __eq__(cls, other): calls.append('meta-eq'); return True
            def __hash__(cls): calls.append('meta-hash'); raise AssertionError()
        class Hostile(metaclass=Meta):
            def __eq__(self, other): calls.append('eq'); return True
            def __bool__(self): calls.append('bool'); return True
            def __str__(self): calls.append('str'); return 'True'
        class Text(str, metaclass=Meta):
            def casefold(self): calls.append('casefold'); return 'key'
            def __eq__(self, other): calls.append('text-eq'); return True
        class Number(D, metaclass=Meta):
            def is_finite(self): calls.append('finite'); return True
            def as_tuple(self): calls.append('tuple'); raise AssertionError()
        class Structure(BSLStructure, metaclass=Meta): pass
        for value in (Hostile(), Hostile, Text('True'), Number(1), Structure('Key', 'yes')):
            with self.assertRaises(TypeError): self.tree.rows.find_rows(value)
            with self.assertRaises(TypeError): self.tree.rows.find_rows(self.query, value)
            with self.assertRaises(TypeError): self.tree.rows.find_rows(BSLStructure('Key', value))
            self.nodes[0].cells[self.tree.columns.items[0]] = value
            with self.assertRaises(TypeError): self.tree.rows.find_rows(self.query)
        self.assertEqual(calls, [])

    def test_hostile_filter_name_has_no_casefold_hook(self):
        calls = []
        class Name(str):
            def casefold(self): calls.append('casefold'); return 'key'
        self.query._items['key'] = (Name('Key'), 'yes')
        with self.assertRaises(TypeError): self.tree.rows.find_rows(self.query)
        self.assertEqual(calls, [])

    def test_deep_iterative_search_and_no_registry_traversal(self):
        tree = trees.BSLValueTree()
        tree.columns.add('K')
        row = tree.rows.add()
        row.set_member('K', True)
        for _ in range(trees._MAX_DEPTH):
            row = row.rows.add()
            row.set_member('K', True)
        class Registry(dict):
            def __iter__(self): raise AssertionError('registry traversal')
        tree._all_rows = Registry(tree._all_rows)
        self.assertEqual(len(tree.rows.find_rows(BSLStructure('K', True), True).items), 257)

    def test_row_cell_depth_limits_fail_without_mutation(self):
        old = self.tree.rows.find_rows(self.query, True)
        before = [dict(row.cells) for row in self.nodes]
        for limit, value in (('_MAX_ROWS', 5), ('_MAX_CELLS', 5),
                             ('_MAX_DEPTH', 1), ('_MAX_COLUMNS', 1)):
            with patch.object(trees, limit, value), self.assertRaises(ValueError):
                self.tree.rows.find_rows(self.query, True)
        self.assertEqual(before, [row.cells for row in self.nodes])
        self.assertEqual(len(old.items), 6)

    def test_text_and_work_limits_charge_before_equality(self):
        with patch.object(trees, '_MAX_SEARCH_TEXT', 2), self.assertRaises(ValueError):
            self.tree.rows.find_rows(self.query)
        # Determine exact work from the public deterministic model, not timing.
        charges = []
        original = trees._SearchBudget.charge
        def charged(budget, units):
            charges.append(units)
            return original(budget, units)
        with patch.object(trees._SearchBudget, 'charge', charged):
            self.tree.rows.find_rows(self.query, True)
        exact = sum(charges)
        with patch.object(trees, '_MAX_SEARCH_WORK', exact):
            self.assertEqual(len(self.tree.rows.find_rows(self.query, True).items), 6)
        with patch.object(trees, '_MAX_SEARCH_WORK', exact - 1), self.assertRaises(ValueError):
            self.tree.rows.find_rows(self.query, True)
        # Budget enough for preparation, but not the first row's complete pair.
        first_row_cost = 1 + len('yes') * 2
        preparation = exact - 6 * first_row_cost
        with patch.object(trees, '_MAX_SEARCH_WORK', preparation + first_row_cost - 1), \
                patch.object(trees, 'equal', side_effect=AssertionError('unreserved equality')):
            with self.assertRaises(ValueError): self.tree.rows.find_rows(self.query, True)

    def test_aggregate_names_and_repeated_content_spend_budget(self):
        tree = trees.BSLValueTree()
        for name in ('LongNameA', 'LongNameB', 'LongNameC'): tree.columns.add(name)
        with patch.object(trees, '_MAX_SEARCH_WORK', 30), self.assertRaises(ValueError):
            tree.rows.find_rows(BSLStructure('LongNameA', 'x'))
        tree = trees.BSLValueTree()
        tree.columns.add('K')
        for _ in range(3): tree.rows.add().set_member('K', 'x' * 100)
        query = BSLStructure('K', 'x' * 100)
        with patch.object(trees, '_MAX_SEARCH_WORK', 500), self.assertRaises(ValueError):
            tree.rows.find_rows(query)

    def test_corrupted_cycle_or_foreign_row_fails_boundedly(self):
        self.nodes[-1].rows.items.append(self.nodes[0])
        with self.assertRaises(ValueError): self.tree.rows.find_rows(self.query, True)
        self.nodes[-1].rows.items.clear()
        self.tree.rows.items.append(trees.BSLValueTree().rows.add())
        with self.assertRaises(ValueError): self.tree.rows.find_rows(self.query, True)


if __name__ == '__main__':
    unittest.main()
