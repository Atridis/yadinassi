"""Documented Delete773 no-op above UBound, not generated native evidence."""
from decimal import Decimal, Inexact, Rounded, localcontext
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.values import BSLArray


class ArrayDeleteBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda text: None)

    def test_bilingual_empty_and_above_upper_bound(self):
        for method in ('Delete', 'Удалить', 'dElEtE', 'уДаЛиТь'):
            for size in range(4):
                for offset in (0, 1, 100):
                    with self.subTest(method=method, size=size, offset=offset):
                        self.vm.execute(f'a = New Array({size}); alias = a; a.{method}({size + offset});')
                        self.assertIs(self.vm.variables['a'], self.vm.variables['alias'])
                        self.assertEqual(self.vm.variables['a'].items, [None] * size)
                        self.assertEqual(self.vm.execute('a.Count()'), size)
                        self.assertEqual(self.vm.execute('a.UBound()'), size - 1)

    def test_every_valid_index_and_retained_identity(self):
        for index in range(5):
            a = BSLArray()
            values = [object() for _ in range(5)]
            for value in values:
                a.add(value)
            a.delete(Decimal(index))
            self.assertEqual(a.items, values[:index] + values[index + 1:])
            for actual, expected in zip(a.items, values[:index] + values[index + 1:]):
                self.assertIs(actual, expected)

    def test_repeated_deletion_last_then_empty(self):
        self.vm.execute('a = New Array; a.Add("first"); a.Add("last"); '
                        'a.Delete(a.UBound()); a.Delete(0); a.Delete(0); a.Delete(1);')
        self.assertEqual(self.vm.variables['a'].items, [])

    def test_huge_positive_indices_never_expand_to_host_integer(self):
        a = BSLArray(); a.add('kept')
        # int(1e1000000000) would be prohibitively expensive. Only metadata is needed.
        for value in ('1e1000000000', '1e999999999999999999', '4294967296'):
            a.delete(Decimal(value))
            self.assertEqual(a.items, ['kept'])
        empty = BSLArray()
        empty.delete(Decimal('1e1000000000'))
        self.assertEqual(empty.items, [])

    def test_scaled_integer_and_negative_zero(self):
        self.vm.execute('a = New Array; a.Add("first"); a.Add("last"); '
                        'a.Delete(2.000); a.Delete(-0.000); a.Delete(0.000); a.Delete(-0.000);')
        self.assertEqual(self.vm.variables['a'].items, [])

    def test_existing_unsupported_index_contract_is_atomic(self):
        for expression in ('-1', '-0.5', '0.5', '1.5', '100.5',
                           'Number("1e-1000000")', 'Number("-1e1000000")',
                           'True', '"10"', 'Undefined', 'New Array', 'Type("Number")'):
            with self.subTest(expression=expression):
                self.vm.execute('a = New Array; a.Add("kept");')
                with self.assertRaises(BSLError):
                    self.vm.execute(f'a.Delete({expression});')
                self.assertEqual(self.vm.variables['a'].items, ['kept'])

    def test_host_invalid_values_are_atomic(self):
        a = BSLArray(); a.add('kept')
        for value in (Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'),
                      Decimal('-Infinity'), 0, 0.0, True, None, '0'):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                a.delete(value)
            self.assertEqual(a.items, ['kept'])

    def test_arity_and_missing_argument(self):
        self.vm.execute('a = New Array; a.Add("kept");')
        for arguments in ('', ', 1', '0, 1', '0,'):
            with self.subTest(arguments=arguments), self.assertRaises(BSLError):
                self.vm.execute(f'a.Delete({arguments})')
            self.assertEqual(self.vm.variables['a'].items, ['kept'])

    def test_noop_preserves_serialization_aliases_and_snapshot(self):
        self.vm.execute('a = New Array; nested = New Structure("Text", "Я😀"); '
                        'a.Add(nested); a.Add(nested); snapshot = New FixedArray(a); '
                        'before = ValueToStringInternal(a); '
                        'a.Delete(2); a.Delete(100); after = ValueToStringInternal(a); '
                        'restored = ValueFromStringInternal(after);')
        self.assertEqual(self.vm.variables['before'], self.vm.variables['after'])
        a = self.vm.variables['a']
        self.assertIs(a.items[0], a.items[1])
        restored = self.vm.variables['restored']
        # Existing native codec serializes repeated references by value.
        self.assertIsNot(restored.items[0], restored.items[1])
        self.assertEqual(self.vm.execute('restored[0].Text'), 'Я😀')
        self.assertEqual(self.vm.execute('ValueToStringInternal(restored)'), self.vm.variables['before'])
        self.assertEqual(len(self.vm.variables['snapshot'].items), 2)
        self.assertTrue(self.vm.execute('(TypeOf(restored) = Type("Array"))'))

    def test_noop_retains_self_reference_without_traversal(self):
        a = BSLArray(); a.add(a)
        a.delete(Decimal(1)); a.delete(Decimal('1e1000000000'))
        self.assertIs(a.items[0], a)

    def test_fixed_arrays_still_reject_deletion_including_above_bound(self):
        self.vm.execute('a = New Array; fixed = New FixedArray(a);')
        for expression in ('fixed.Delete(0)', 'fixed.Удалить(100)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.variables['fixed'].items, ())

    def test_reads_and_writes_remain_strict_after_noop(self):
        self.vm.execute('a = New Array; a.Add("kept"); a.Delete(1);')
        for expression in ('a.Get(1)', 'a[1]', 'a.Set(1, 2)', 'a[1] = 2'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.variables['a'].items, ['kept'])

    def test_live_reference_survives_noop_and_can_write(self):
        # Local integration of the existing reference mechanism; no structural mutation.
        self.vm.execute('''Procedure Change(slot, owner)
            owner.Delete(owner.Count()); owner.Delete(100);
            slot = slot + "!";
        EndProcedure
        a = New Array; a.Add("Я😀"); Change((a[0]), a);''')
        self.assertEqual(self.vm.variables['a'].items, ['Я😀!'])

    def test_noop_during_iteration_and_eval_execute_routines(self):
        self.vm.execute('''Function Index() calls = calls + 1; Return 100; EndFunction
        Перем calls; calls = 0;
        a = New Array; a.Add(1); a.Add(2); seen = New Array;
        For Each item In a Do a.Delete(Index()); seen.Add(item); EndDo;
        Execute("a.Delete(2);"); Eval("a.Delete(2)");''')
        self.assertEqual(self.vm.variables['calls'], 2)
        self.assertEqual(self.vm.variables['seen'].items, [Decimal(1), Decimal(2)])
        self.assertEqual(self.vm.variables['a'].items, [Decimal(1), Decimal(2)])

    def test_error_recovery_and_noop_does_not_enter_except(self):
        self.vm.execute('''a = New Array; a.Add("kept"); caught = False;
        Try a.Delete(1); Except caught = True; EndTry;
        failed = False; Try a.Delete(-1); Except failed = True; EndTry;
        a.Delete(0); a.Delete(0); a.Add("recovered");''')
        self.assertIs(self.vm.variables['caught'], False)
        self.assertIs(self.vm.variables['failed'], True)
        self.assertEqual(self.vm.variables['a'].items, ['recovered'])

    def test_decimal_context_does_not_affect_deletion_or_noop(self):
        a = BSLArray(); a.add('first'); a.add('last')
        with localcontext() as context:
            context.prec = 1; context.Emax = 1; context.Emin = -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            a.delete(Decimal('1e1000000000'))
            a.delete(Decimal('2.000'))
            a.delete(Decimal('0.000'))
            self.assertFalse(any(context.flags.values()))
        self.assertEqual(a.items, ['last'])
