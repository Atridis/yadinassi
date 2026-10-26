"""Explicit native targets are execution scoped, validated, and isolated."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
import os
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.native_targets import (
    LINUX_8_3_27_1508, WINDOWS_8_3_27_2342,
    current_native_target, target_context,
)
from yadinassi.syntax.parser import parse
from yadinassi.structures import BSLStructure, fill_property_values


class NativeTargetTests(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)

    def test_default_is_windows_even_inside_linux_context_or_environment(self):
        with patch.dict(os.environ, {'YADINASSI_NATIVE_TARGET': LINUX_8_3_27_1508,
                                     'NATIVE_TARGET': LINUX_8_3_27_1508}):
            self.assertEqual(Interpreter().native_target, WINDOWS_8_3_27_2342)
            with target_context(LINUX_8_3_27_1508):
                vm = Interpreter()
                vm.register_function('TargetName', current_native_target)
                self.assertEqual(vm.native_target, WINDOWS_8_3_27_2342)
                self.assertEqual(vm.execute('TargetName()'), WINDOWS_8_3_27_2342)
                self.assertEqual(current_native_target(), LINUX_8_3_27_1508)

    def test_known_targets_are_exact_and_read_only(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            vm = Interpreter(native_target=target)
            self.assertEqual(vm.native_target, target)
            with self.assertRaises(AttributeError):
                vm.native_target = WINDOWS_8_3_27_2342
            self.assertEqual(vm.native_target, target)

    def test_unknown_names_fail_without_normalization_or_fallback(self):
        for name in ('', 'linux', 'windows', 'LINUX-8.3.27.1508',
                     ' linux-8.3.27.1508', 'linux-8.3.27.1508 ',
                     'windows-8.3.27.1508', 'linux-8.3.27.2342', 'auto'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'Unsupported native_target'):
                    Interpreter(native_target=name)
                with target_context(LINUX_8_3_27_1508):
                    with self.assertRaisesRegex(ValueError, 'Unsupported native_target'):
                        with target_context(name):
                            self.fail('invalid context entered')
                    self.assertEqual(current_native_target(), LINUX_8_3_27_1508)

    def test_non_string_targets_are_rejected_without_host_hooks(self):
        class HostileString(str):
            def __eq__(self, other):
                raise AssertionError('unexpected equality hook')

            def __str__(self):
                raise AssertionError('unexpected string hook')

        for name in (None, False, 1, b'linux-8.3.27.1508', [], {},
                     HostileString(LINUX_8_3_27_1508)):
            with self.subTest(type=type(name)):
                with self.assertRaisesRegex(TypeError, 'native_target must be a string'):
                    Interpreter(native_target=name)
                with self.assertRaisesRegex(TypeError, 'native_target must be a string'):
                    with target_context(name):
                        self.fail('invalid context entered')

    def test_nested_contexts_restore_even_after_base_exception(self):
        with target_context(LINUX_8_3_27_1508):
            self.assertEqual(current_native_target(), LINUX_8_3_27_1508)
            with self.assertRaises(KeyboardInterrupt):
                with target_context(WINDOWS_8_3_27_2342):
                    self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
                    with target_context(LINUX_8_3_27_1508):
                        self.assertEqual(current_native_target(), LINUX_8_3_27_1508)
                    self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
                    raise KeyboardInterrupt
            self.assertEqual(current_native_target(), LINUX_8_3_27_1508)

    def test_execute_and_direct_ast_entry_points_restore_context(self):
        vm = Interpreter(native_target=LINUX_8_3_27_1508)
        vm.register_function('TargetName', current_native_target)
        for run in (lambda code: vm.execute(code),
                    lambda code: vm.execute_program(parse(code))):
            with self.subTest(run=run):
                self.assertEqual(run('TargetName()'), LINUX_8_3_27_1508)
                self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
                with self.assertRaises(BSLError):
                    run('Raise "failure";')
                self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
        with self.assertRaises(BSLError):
            vm.execute('If Then')

    def test_base_exception_during_execution_does_not_leak_target(self):
        vm = Interpreter(native_target=LINUX_8_3_27_1508)

        def interrupt():
            self.assertEqual(current_native_target(), LINUX_8_3_27_1508)
            raise KeyboardInterrupt

        vm.register_function('InterruptHost', interrupt)
        with self.assertRaises(KeyboardInterrupt):
            vm.execute('InterruptHost();')

    def test_reentrant_other_interpreter_and_error_restore_callers_target(self):
        outer = Interpreter(native_target=LINUX_8_3_27_1508)
        inner = Interpreter()
        seen = []
        for vm in (outer, inner):
            vm.register_function('TargetName', current_native_target)

        def reenter():
            seen.append(current_native_target())
            seen.append(inner.execute('TargetName()'))
            self.assertEqual(current_native_target(), LINUX_8_3_27_1508)
            with self.assertRaises(BSLError):
                inner.execute('Raise "inner failure";')
            seen.append(current_native_target())
            return outer.execute('TargetName()')

        outer.register_function('Reenter', reenter)
        self.assertEqual(outer.execute('Reenter()'), LINUX_8_3_27_1508)
        self.assertEqual(seen, [LINUX_8_3_27_1508, WINDOWS_8_3_27_2342,
                                LINUX_8_3_27_1508])
        self.assertEqual(inner.execute('TargetName()'), WINDOWS_8_3_27_2342)

    def test_eval_execute_fragments_and_caught_errors_keep_target(self):
        output = []
        vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
        vm.register_function('TargetName', current_native_target)
        vm.execute('''
            Function Nested() Return Eval("TargetName()"); EndFunction
            Message(Nested());
            Execute("Message(TargetName());");
            Try Raise "failure"; Except Message(TargetName()); EndTry;
        ''')
        self.assertEqual(output, [LINUX_8_3_27_1508] * 3)

    def test_concurrent_interpreters_do_not_share_dynamic_target(self):
        barrier = Barrier(2)

        def run(name):
            vm = Interpreter(native_target=name)

            def observe():
                barrier.wait(timeout=10)
                result = current_native_target()
                barrier.wait(timeout=10)
                return result

            vm.register_function('Observe', observe)
            result = vm.execute('Observe()')
            return result, current_native_target()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [WINDOWS_8_3_27_2342, LINUX_8_3_27_1508]))
        self.assertEqual(results, [(WINDOWS_8_3_27_2342, WINDOWS_8_3_27_2342),
                                   (LINUX_8_3_27_1508, WINDOWS_8_3_27_2342)])

    def test_async_contexts_remain_independent_across_yields(self):
        async def run(name):
            with target_context(name):
                await asyncio.sleep(0)
                self.assertEqual(current_native_target(), name)
                await asyncio.sleep(0)
                return current_native_target()

        async def both():
            return await asyncio.gather(run(WINDOWS_8_3_27_2342), run(LINUX_8_3_27_1508))

        self.assertEqual(asyncio.run(both()), [WINDOWS_8_3_27_2342, LINUX_8_3_27_1508])

    def test_copied_nested_context_falls_back_to_only_live_parent(self):
        with target_context(LINUX_8_3_27_1508):
            with target_context(WINDOWS_8_3_27_2342):
                copied = copy_context()
                self.assertEqual(copied.run(current_native_target), WINDOWS_8_3_27_2342)
            self.assertEqual(copied.run(current_native_target), LINUX_8_3_27_1508)
        self.assertEqual(copied.run(current_native_target), WINDOWS_8_3_27_2342)

    def test_detached_async_host_work_does_not_keep_completed_vm_target(self):
        async def run():
            tasks = []

            async def observe():
                target = BSLStructure('First,Last', 'old-first', 'old-last')
                source = BSLStructure('First,Last', 'new-first', 'new-last')
                with self.assertRaisesRegex(ValueError, 'Missing'):
                    fill_property_values(target, source, 'First,Missing,Last')
                return current_native_target(), target.get('First'), target.get('Last')

            def spawn():
                self.assertEqual(current_native_target(), LINUX_8_3_27_1508)
                tasks.append(asyncio.create_task(observe()))

            vm = Interpreter(native_target=LINUX_8_3_27_1508)
            vm.register_function('Spawn', spawn)
            vm.execute('Spawn();')
            with self.assertRaises(BSLError):
                vm.execute('Spawn(); Raise "failed execution";')
            return await asyncio.gather(*tasks)

        self.assertEqual(asyncio.run(run()),
                         [(WINDOWS_8_3_27_2342, 'new-first', 'old-last')] * 2)

    def test_python_helpers_after_linux_execution_keep_windows_default(self):
        vm = Interpreter(native_target=LINUX_8_3_27_1508)
        vm.execute('x = 1;')
        target = BSLStructure('First,Last', 'old-first', 'old-last')
        source = BSLStructure('First,Last', 'new-first', 'new-last')
        with self.assertRaisesRegex(ValueError, 'Missing'):
            fill_property_values(target, source, 'First,Missing,Last')
        self.assertEqual((target.get('First'), target.get('Last')), ('new-first', 'old-last'))


class NativeTargetImportTests(unittest.TestCase):
    def test_nested_import_initialization_exports_and_cached_modules_inherit_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Leaf.bsl').write_text('''
                Message(TargetName());
                Var initialized; initialized = Fill();
                Function Fill() Export
                    target = New Structure("ProbeName,ProbeNumber", "old", 5);
                    source = New Structure("ProbeName,ProbeNumber", "new", 9);
                    Try FillPropertyValues(target, source, "ProbeName,Missing,ProbeNumber");
                    Except EndTry;
                    Return target;
                EndFunction
                Function Initial() Export Return initialized; EndFunction
            ''', encoding='utf-8')
            (root / 'Middle.bsl').write_text('''// #Import Leaf.bsl
                Message(TargetName());
                Function Fill() Export Return Leaf.Fill(); EndFunction
                Function Initial() Export Return Leaf.Initial(); EndFunction
            ''', encoding='utf-8')
            main = root / 'Main.bsl'
            code = '// #Import Middle.bsl\nresult = Middle.Fill(); initial = Middle.Initial();'
            interpreters = []
            for name, expected in ((LINUX_8_3_27_1508, ('old', 9)),
                                   (WINDOWS_8_3_27_2342, ('new', 5))):
                output = []
                vm = Interpreter(output.append, native_target=name)
                vm.register_function('TargetName', current_native_target)
                vm.execute(code, str(main))
                interpreters.append((vm, expected))
                self.assertEqual(output, [name, name])
                self.assertEqual(len(vm._module_cache), 2)
                self.assertTrue(all(module.interpreter.native_target == name
                                    for module in vm._module_cache.values()))
                for key in ('result', 'initial'):
                    result = vm.variables[key]
                    self.assertEqual((result.get('ProbeName'), result.get('ProbeNumber')), expected)
                self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
            # Calling cached exports later must still use their owning VM's target.
            for vm, expected in interpreters:
                vm.execute('result = Middle.Fill();')
                result = vm.variables['result']
                self.assertEqual((result.get('ProbeName'), result.get('ProbeNumber')), expected)

    def test_failed_import_restores_target_and_loading_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Broken.bsl').write_text('Raise "failed import";', encoding='utf-8')
            vm = Interpreter(native_target=LINUX_8_3_27_1508)
            with self.assertRaisesRegex(BSLError, 'failed import'):
                vm.execute('// #Import Broken.bsl\n', str(root / 'Main.bsl'))
            self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)
            self.assertEqual(vm._loading, [])
            self.assertEqual(vm._module_cache, {})
            vm.register_function('TargetName', current_native_target)
            self.assertEqual(vm.execute('TargetName()'), LINUX_8_3_27_1508)
