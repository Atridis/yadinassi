"""Module handles must never become cached values, callable bindings or rights."""
import gc
import types
import unittest
import weakref
from unittest.mock import patch
from decimal import Decimal

from yadinassi import Interpreter
from yadinassi import runtime_dependencies as dependencies
from yadinassi.values import InterpreterCall, BSLArray
from yadinassi import translated_access


class DependencyHandleTests(unittest.TestCase):
    def setUp(self):
        dependencies._load_module.cache_clear()
        self.addCleanup(dependencies._load_module.cache_clear)

    def test_lazy_failure_retries_and_closed_cache_is_bounded(self):
        original = dependencies.import_module
        calls = []
        def load(name, package):
            calls.append(name)
            if len(calls) == 1:
                raise ImportError('unavailable')
            return original(name, package)
        with patch.object(dependencies, 'import_module', side_effect=load):
            with self.assertRaises(ImportError):
                dependencies.runtime_module('runtime')
            self.assertEqual(dependencies._load_module.cache_info().currsize, 0)
            first = dependencies.runtime_module('runtime')
            self.assertIs(first, dependencies.runtime_module('runtime'))
        self.assertEqual(calls, ['.runtime', '.runtime'])
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

    def test_symbols_rebind_after_receiver_but_not_after_actual_arguments(self):
        from yadinassi.values import HostFunction
        module = dependencies.runtime_module('source_catalog_runtime')
        for backend in ('interpreter', 'compiled-strict'):
            events = []; vm = Interpreter(execution_backend=backend)
            def target(label):
                return lambda caller, receiver, name: HostFunction(name, lambda x: events.append(label) or x)
            def receiver():
                events.append('receiver'); module.reference_call = target('new'); return BSLArray()
            def argument():
                events.append('argument'); module.reference_call = target('later'); return Decimal(4)
            vm.register_function('Receiver', receiver); vm.register_function('Argument', argument)
            vm.variables['stored'] = BSLArray()
            try:
                with patch.object(module, 'reference_call', target('old')):
                    vm.execute('x=Receiver().Probe(Argument());y=stored.Probe(5);')
                self.assertEqual(events, ['receiver', 'argument', 'new', 'later'])
                self.assertEqual((vm.variables['x'],vm.variables['y']), (4,5))
            finally: vm.close()

    def test_warm_module_attributes_remain_live_at_access_boundary(self):
        module = dependencies.runtime_module('source_document_runtime')
        vm = Interpreter(execution_backend='compiled-strict')
        self.addCleanup(vm.close)
        value = object()
        for result in (Decimal(7), Decimal(9)):
            with patch.object(module, 'is_source_reference', lambda v: v is value), \
                 patch.object(module, 'reference_member', lambda caller, v, name: result):
                call = translated_access.read_attribute(vm, value, 'Name')
                with self.assertRaises(StopIteration) as end: next(call)
                self.assertEqual(end.exception.value, result)
        with self.assertRaises(TypeError): next(translated_access.read_attribute(vm, value, 'Name'))

    def test_warm_cache_retains_no_vm_or_call_argument(self):
        vm = Interpreter(); argument = BSLArray(); seen = []
        vm.register_function('Host', lambda value: seen.append(weakref.ref(value)))
        vm.variables['value'] = argument
        vm.execute('Host(value);')
        vm_ref, argument_ref = weakref.ref(vm), weakref.ref(argument)
        vm.close(); del vm, argument
        gc.collect()
        self.assertIsNone(vm_ref()); self.assertIsNone(argument_ref()); self.assertIsNone(seen[0]())

    def test_cold_and_warm_caches_do_not_bypass_reauthorization(self):
        for warm in (False, True):
            for backend in ('interpreter', 'compiled-strict'):
                with self.subTest(warm=warm, backend=backend):
                    dependencies._load_module.cache_clear()
                    if warm:
                        for name in dependencies._MODULE_NAMES: dependencies.runtime_module(name)
                    active = [True]; events = []
                    vm = Interpreter(execution_backend=backend)
                    def authorize(caller):
                        events.append(('authorize', active[0]))
                        if not active[0]: raise PermissionError('revoked')
                    def dispatch(caller, values):
                        events.append('dispatch')
                        if False: yield
                        return values[0]
                    def revoke():
                        events.append('argument'); active[0] = False; return Decimal(1)
                    vm.register_function('Host', InterpreterCall(1, 1, authorize, dispatch))
                    vm.register_function('Revoke', revoke)
                    try:
                        with self.assertRaisesRegex(PermissionError, 'revoked'):
                            vm.execute('Try Host(Revoke()); Except Message("caught"); EndTry;')
                        self.assertEqual(events, [('authorize', True), 'argument', ('authorize', False)])
                    finally: vm.close()

    def test_preargument_denial_precedes_later_lazy_dependencies(self):
        from yadinassi import runtime
        vm = Interpreter(); self.addCleanup(vm.close)
        def deny(caller): raise PermissionError('denied')
        def dispatch(caller, values):
            if False: yield
        vm.register_function('Denied', InterpreterCall(1, 1, deny, dispatch))
        vm.register_function('Effect', lambda: self.fail('argument executed'))
        original = runtime._runtime_module
        def dependency(name):
            if name in ('reusable_values', 'common_templates', 'temporary_storage'):
                self.fail('dependency reached before denial')
            return original(name)
        with patch.object(runtime, '_runtime_module', dependency):
            with self.assertRaisesRegex(PermissionError, 'denied'):
                vm.execute('Denied(Effect());')
