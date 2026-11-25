"""Native Python operators reuse measured Date tick algorithms, not VM dispatch."""
from decimal import Decimal, localcontext, Rounded, Inexact
import unittest
from unittest.mock import patch
from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.execution.codegen.direct_scalar_semantics import UnsupportedScalarSemantics
from yadinassi.syntax.parser import parse
from yadinassi.temporal.dates import BSLDate, MAX_TICKS, UnsupportedDateRange, shift_date, date_difference

class DirectDateArithmeticTests(unittest.TestCase):
    def test_python_ticks_match_existing_algorithms(self):
        value=BSLDate(123456789)
        for seconds in ('1','-1','0.00005','-0.00005','0.12345','123.45678'):
            delta=Decimal(seconds)
            self.assertEqual(value+delta,shift_date(value,delta))
            self.assertEqual(value-delta,shift_date(value,delta.copy_negate()))
        self.assertEqual(value-BSLDate(123450000),date_difference(value,BSLDate(123450000)))
    def test_direct_program_matches_fixed_tick_offsets(self):
        source = 'a=Date(2024,1,1);b=a+0.12345;c=b-0.00005;elapsed=c-a;'
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter()
                try:
                    if prepared:
                        vm.execute_prepared(vm.prepare(source))
                    else:
                        vm.execute(source)
                    values = vm.variables
                    start = values['a'].ticks
                    # A tick is 0.0001 s. Each half tick rounds away from zero.
                    self.assertEqual(values['b'].ticks - start, 1235)
                    self.assertEqual(values['c'].ticks - start, 1234)
                    self.assertEqual(values['elapsed'], Decimal('0.1234'))
                finally:
                    vm.close()

    def test_direct_date_operands_keep_left_to_right_effect_order(self):
        vm = Interpreter(allow_extensions=True)
        seen = []
        vm.register_function('Left', lambda: seen.append('left') or BSLDate(10000))
        vm.register_function('Right', lambda: seen.append('right') or Decimal(1))
        try:
            vm.execute('result=Left()+Right();')
            self.assertEqual(seen, ['left', 'right'])
            self.assertEqual(vm.variables['result'].ticks, 20000)
        finally:
            vm.close()

    def test_wrong_types_do_not_invoke_reflected_host_callbacks(self):
        class Foreign:
            def __radd__(self,other):raise AssertionError('host callback')
            def __rsub__(self,other):raise AssertionError('host callback')
        for operand in (True,1,'1',Foreign()):
            with self.assertRaisesRegex(TypeError,'число секунд'):BSLDate(10000)+operand
            with self.assertRaisesRegex(TypeError,'число секунд'):BSLDate(10000)-operand
    def test_range_markers_and_decimal_context_remain_exact(self):
        for value,delta in ((BSLDate(0),Decimal(-1)),(BSLDate(MAX_TICKS),Decimal(1))):
            marked=value+delta
            self.assertTrue(marked.boundary)
            with self.assertRaises(UnsupportedDateRange):marked+Decimal(0)
        with self.assertRaises(UnsupportedDateRange):BSLDate(0)-Decimal('0.0001')
        with localcontext() as context:
            context.prec=1;context.traps[Rounded]=True;context.traps[Inexact]=True
            self.assertEqual((BSLDate(123456789)-Decimal('0.1234')).ticks,123455555)

    def test_date_order_all_operators_use_ticks_in_source_ast_and_prepared(self):
        source = ('Early=Date("20240229123456"); Late=Early+0.0001; '
                  'LT=Early<Late; LE=Early<=Early; GT=Late>Early; GE=Late>=Late; '
                  'SameTick=Late>Late; Opposite=Late<Early;')
        for route in ('source', 'ast', 'prepared'):
            with self.subTest(route=route):
                vm = Interpreter()
                self.addCleanup(vm.close)
                if route == 'source': vm.execute(source)
                elif route == 'ast': vm.execute_program(parse(source))
                else: vm.execute_prepared(vm.prepare(source))
                for name in ('lt', 'le', 'gt', 'ge'):
                    self.assertIs(vm.variables[name], True)
                self.assertIs(vm.variables['sametick'], False)
                self.assertIs(vm.variables['opposite'], False)

    def test_date_order_rejects_unproven_range_and_mixed_types(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Low=Date(1,1,1); High=Date(9999,12,31,23,59,59); '
                   'Before=Low+(-1); After=High+1;')
        self.assertIs(vm.execute('Low<High'), True)
        self.assertIs(vm.execute('High>=High'), True)
        for comparison in ('Before<Low', 'Low<=Before', 'After>High', 'High>=After'):
            with self.subTest(comparison=comparison):
                with self.assertRaisesRegex(BSLRuntimeError, 'выхода за диапазон'):
                    vm.execute(comparison)
        for comparison in ('Low<1', '1<=High', 'Low>"date"', 'True>=High'):
            with self.subTest(comparison=comparison):
                with self.assertRaisesRegex(BSLRuntimeError, 'несовместимы'):
                    vm.execute(comparison)
