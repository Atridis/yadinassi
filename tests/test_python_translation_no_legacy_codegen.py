import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.compiled_inline import Emitter
from yadinassi.syntax.parser import parse

class NoLegacyCodegen(unittest.TestCase):
    def test_force_compiles_only_selected_executables(self):
        vm=Interpreter(execution_backend='compiled-strict')
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True), patch.object(Engine,'_lower_node',side_effect=AssertionError('legacy node')), patch.object(Engine,'_lower_block',side_effect=AssertionError('legacy block')), patch.object(Emitter,'compile',side_effect=AssertionError('legacy IR')):
            vm.execute('Function F(x) Return x+1;EndFunction a=New Array;For i=1 To 3 Do a.Add(F(i));EndDo;r=a[2];')
        self.assertEqual(vm.variables['r'],4)
        e=vm._compiled()
        self.assertEqual(e.stats['compiled_node_functions'],0)
        self.assertEqual(e.stats['compiled_block_functions'],0)
        self.assertFalse(e._inline_ir)
        self.assertEqual(e.stats['interpreter_fallbacks'],0)

    def test_old_mode_still_compiles(self):
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',False):
            vm=Interpreter(execution_backend='compiled-strict');vm.execute('r=1+2;')
        self.assertEqual(vm.variables['r'],3)
        self.assertGreater(vm._compiled().stats['compiled_node_functions'],0)

    def test_missing_semantic_service_rejected_before_effects(self):
        vm=Interpreter(execution_backend='compiled-strict');vm.semantic_raise=None
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            with self.assertRaises(CompiledUnsupported):vm.execute('r=1;Raise "bad";')
        self.assertNotIn('r',vm.variables)

    def test_actual_source_and_node_limits_remain(self):
        for limit in ('MAX_INLINE_FUNCTION_BYTES','MAX_INLINE_UNIT_BYTES','MAX_PLAIN_SOURCE_BYTES','MAX_NODES','MAX_REGISTRY_ENTRIES'):
            with self.subTest(limit=limit),patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True),patch.object(Engine,limit,1):
                vm=Interpreter(execution_backend='compiled-strict')
                with self.assertRaises(CompiledUnsupported):vm.execute('r=1+2;')
                self.assertNotIn('r',vm.variables)

    def test_cycles_rejected(self):
        program=parse('r=1;');program[0].value=program[0]
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm=Interpreter(execution_backend='compiled-strict')
            with self.assertRaises(CompiledUnsupported):vm._compiled().prepare(program)
