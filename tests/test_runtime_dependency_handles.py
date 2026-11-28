"""Module handles must never become cached values, callable bindings or rights."""
import gc
import types
import unittest
import weakref
from unittest.mock import Mock, patch
from decimal import Decimal

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution import runtime_dependencies as dependencies
from yadinassi.types.values import InterpreterCall, BSLArray


class DependencyHandleTests(unittest.TestCase):
    def setUp(self):
        dependencies._load_module.cache_clear()
        self.addCleanup(dependencies._load_module.cache_clear)

    def test_lazy_failure_retries_and_closed_cache_is_bounded(self):
        original = dependencies.import_module
        calls = []
        def load(name):
            calls.append(name)
            if len(calls) == 1:
                raise ImportError('unavailable')
            return original(name)
        with patch.object(dependencies, 'import_module', side_effect=load):
            with self.assertRaises(ImportError):
                dependencies.runtime_module('runtime')
            self.assertEqual(dependencies._load_module.cache_info().currsize, 0)
            first = dependencies.runtime_module('runtime')
            self.assertIs(first, dependencies.runtime_module('runtime'))
        self.assertEqual(calls, ['yadinassi.runtime', 'yadinassi.runtime'])
        for name in dependencies._MODULE_NAMES:
            self.assertIs(type(dependencies.runtime_module(name)), types.ModuleType)
        info = dependencies._load_module.cache_info()
        self.assertEqual(info.currsize, len(dependencies._MODULE_NAMES))
        self.assertEqual(info.maxsize, len(dependencies._MODULE_NAMES))

    def test_unknown_input_cannot_invoke_hash_equality_or_import(self):
        class Host:
            def __hash__(self): raise AssertionError('hash')
            def __eq__(self, other): raise AssertionError('equality')
        class StringHost(str):
            def __hash__(self): raise AssertionError('string subclass hash')
        with patch.object(dependencies, 'import_module', side_effect=AssertionError('import')):
            for value in (Host(), StringHost('runtime'), [], None, 'os', '../runtime', 'runtime.extra'):
                with self.assertRaises(ValueError): dependencies.runtime_module(value)
        self.assertEqual(dependencies._load_module.cache_info().currsize, 0)

    def test_partially_initialized_module_is_returned_but_not_cached(self):
        partial = types.ModuleType('partial')
        partial.__spec__ = types.SimpleNamespace(_initializing=True)
        complete = types.ModuleType('complete')
        complete.__spec__ = types.SimpleNamespace(_initializing=False)
        with patch.object(dependencies, 'import_module', side_effect=[partial, ImportError('outer failed'), complete]):
            self.assertIs(dependencies.runtime_module('runtime'), partial)
            self.assertEqual(dependencies._load_module.cache_info().currsize, 0)
            with self.assertRaises(ImportError): dependencies.runtime_module('runtime')
            self.assertIs(dependencies.runtime_module('runtime'), complete)
            self.assertIs(dependencies.runtime_module('runtime'), complete)


    def test_warm_cache_retains_no_vm_or_call_argument(self):
        vm = Interpreter(allow_extensions=True); argument = BSLArray(); seen = []
        vm.register_function('Host', lambda value: seen.append(weakref.ref(value)))
        vm.variables['value'] = argument
        vm.execute('Host(value);')
        vm_ref, argument_ref = weakref.ref(vm), weakref.ref(argument)
        vm.close(); del vm, argument
        gc.collect()
        self.assertIsNone(vm_ref()); self.assertIsNone(argument_ref()); self.assertIsNone(seen[0]())

    def test_direct_unsupported_descriptor_has_no_authorization_effect_or_lazy_work(self):
        forbidden=('reusable_values','common_templates','temporary_storage')
        for warm in (False,True):
            with self.subTest(warm=warm):
                dependencies._load_module.cache_clear()
                if warm:
                    for name in forbidden:dependencies.runtime_module(name)
                vm=Interpreter(execution_backend='python-direct', allow_extensions=True);self.addCleanup(vm.close)
                authorize=Mock(side_effect=AssertionError('authorization must not run'))
                dispatch=Mock(side_effect=AssertionError('dispatch must not run'))
                effect=Mock(side_effect=AssertionError('argument must not run'))
                vm.register_function('Denied',InterpreterCall(1,1,authorize,dispatch))
                vm.register_function('Effect',effect)
                original=dependencies.runtime_module;reached=[]
                def dependency(name):
                    reached.append(name)
                    if name in forbidden:self.fail('dependency reached before unsupported refusal')
                    return original(name)
                with patch.object(dependencies,'runtime_module',dependency):
                    with self.assertRaisesRegex(BSLRuntimeError,'explicit interpreter dispatch') as caught:
                        vm.execute('Denied(Effect());')
                self.assertIs(type(caught.exception),BSLRuntimeError)
                authorize.assert_not_called();dispatch.assert_not_called();effect.assert_not_called()
                self.assertFalse(set(forbidden).intersection(reached))
