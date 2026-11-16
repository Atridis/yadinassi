"""Bounded generated-Python factoring, never a semantic/interpreter fallback."""
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.compiled_inline import Emitter
from yadinassi import python_translation_blocks as blocks
from test_value_table_operations_checkpoint import source


class BudgetFactoringTests(unittest.TestCase):
    def test_existing_large_checkpoint_factors_without_legacy_codegen(self):
        vm = Interpreter(output=lambda value: None, execution_backend='compiled-strict')
        actual = blocks._prepare_blocks
        attempts = []
        def measured(*args, **kwargs):
            attempts.append((kwargs.get('_inline_depth', 10), kwargs['max_source_bytes']))
            return actual(*args, **kwargs)
        with patch.object(blocks, '_prepare_blocks', measured), \
                patch.object(Engine, '_lower_node', side_effect=AssertionError('legacy node')), \
                patch.object(Engine, '_lower_block', side_effect=AssertionError('legacy block')), \
                patch.object(Emitter, 'compile', side_effect=AssertionError('legacy IR')):
            vm.execute(source())
        self.assertEqual(attempts[:2], [(10, 1024 * 1024), (4, 1024 * 1024)])
        engine = vm._compiled()
        units = {id(unit): unit for _, unit in engine._python_units.values()}
        self.assertLessEqual(sum(unit.source_bytes for unit in units.values()), engine.MAX_PLAIN_SOURCE_BYTES)
        self.assertTrue(any(unit.sync_segments for unit in units.values()))
        self.assertEqual(engine.stats['interpreter_fallbacks'], 0)
        self.assertEqual(engine.stats.get('plain_adapter_blocks', 0), 0)
        self.assertEqual(engine.stats.get('python_compact_statement_calls', 0), 0)
        self.assertEqual(engine.active_frames, 0)

    def test_ordinary_unit_keeps_original_lowering_and_executes_once(self):
        effects = []
        vm = Interpreter(execution_backend='compiled-strict')
        vm.register_function('Effect', lambda: effects.append('once'))
        with patch.object(blocks, '_prepare_blocks', wraps=blocks._prepare_blocks) as prepare:
            vm.execute('Effect();')
        self.assertEqual(prepare.call_count, 1)
        self.assertNotIn('_inline_depth', prepare.call_args.kwargs)
        self.assertEqual(effects, ['once'])
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def test_exhausted_real_budget_rolls_back_before_any_effect(self):
        effects = []
        vm = Interpreter(output=effects.append, execution_backend='compiled-strict')
        vm.execute('Function Stable() Return 7; EndFunction')
        vm.register_function('Effect', lambda: effects.append('host'))
        engine = vm._compiled()
        def registries():
            maps = (engine._nodes, engine._blocks, engine._python_units,
                    engine._owned.memo, engine._owned.versions,
                    engine._origin_signatures, engine._origin_blocks)
            return [{key: id(value) for key, value in mapping.items()} for mapping in maps]
        before = registries()
        with patch.object(engine, 'MAX_PLAIN_SOURCE_BYTES', 50_000), \
                patch.object(blocks, '_prepare_blocks', wraps=blocks._prepare_blocks) as prepare:
            with self.assertRaisesRegex(CompiledUnsupported, 'generated unit source budget'):
                vm.execute('Effect();' + source())
        self.assertEqual(prepare.call_count, 2)
        self.assertEqual(registries(), before)
        self.assertEqual(effects, [])
        self.assertEqual(engine.active_frames, 0)
        self.assertIsNone(vm.locals)
        self.assertEqual(vm.execute('Stable()'), 7)
        self.assertEqual(engine.stats['interpreter_fallbacks'], 0)

    def test_retry_reuses_the_same_materialized_inputs(self):
        attempts = []
        sentinel = object()
        def prepare(blocks_arg, roots_arg, **options):
            attempts.append((tuple(blocks_arg), tuple(roots_arg), tuple(options['routines']), set(options['entry_keys'])))
            if len(attempts) == 1:
                raise blocks._GeneratedUnitBudget('generated unit source budget')
            return sentinel
        with patch.object(blocks, '_prepare_blocks', prepare):
            result = blocks.prepare_blocks(iter([1]), iter([2]), routines=iter([3]),
                                           entry_keys=iter([(4,)]), max_source_bytes=100, max_function_bytes=100)
        self.assertIs(result, sentinel)
        self.assertEqual(attempts, [((1,), (2,), (3,), {(4,)}), ((1,), (2,), (3,), {(4,)})])

    def test_other_failures_never_request_refactoring(self):
        for error in (blocks.UnsupportedTranslation('generated unit source budget'),
                      blocks.UnsupportedTranslation('generated function source budget'),
                      blocks.UnsupportedTranslation('generated operand binding budget'),
                      ValueError('integrity'), RuntimeError('unexpected')):
            with self.subTest(error=str(error)), patch.object(blocks, '_prepare_blocks', side_effect=error) as prepare:
                with self.assertRaises(type(error)) as caught:
                    blocks.prepare_blocks([], [], max_source_bytes=100, max_function_bytes=100)
                self.assertIs(caught.exception, error)
                self.assertEqual(prepare.call_count, 1)

    def test_compact_unit_exhaustion_has_no_retry_or_unbounded_attempts(self):
        for compact, count in ((False, 2), (True, 1)):
            with self.subTest(compact=compact), patch.object(blocks, '_prepare_blocks', side_effect=blocks._GeneratedUnitBudget('generated unit source budget')) as prepare:
                with self.assertRaises(blocks._GeneratedUnitBudget):
                    blocks.prepare_blocks([], [], max_source_bytes=100, max_function_bytes=100, compact_control=compact)
                self.assertEqual(prepare.call_count, count)
                self.assertTrue(all(call.kwargs['max_source_bytes'] == 100 and call.kwargs['max_function_bytes'] == 100 for call in prepare.call_args_list))

    def test_real_function_and_operand_limits_still_reject_before_effects(self):
        for limit in ('MAX_INLINE_FUNCTION_BYTES', 'MAX_REGISTRY_ENTRIES'):
            vm = Interpreter(output=lambda value: self.fail('output before admission'), execution_backend='compiled-strict')
            with self.subTest(limit=limit), patch.object(vm._compiled(), limit, 1), \
                    patch.object(blocks, '_prepare_blocks', wraps=blocks._prepare_blocks) as prepare:
                with self.assertRaises(CompiledUnsupported):
                    vm.execute('Message("not allowed");')
                self.assertLessEqual(prepare.call_count, 1)
            self.assertFalse(vm._compiled()._python_units)
            self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)
