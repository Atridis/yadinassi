"""Code-only caching must not cache authority, bindings or admission decisions."""
import concurrent.futures
import gc
import weakref
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.compiled_inline import _CodeCache, _CODE_CACHE


class CompiledCodeCacheTests(unittest.TestCase):
    def setUp(self):
        _CODE_CACHE.reset()

    def test_hits_skip_actual_parse_and_compile(self):
        import builtins
        cache = _CodeCache()
        with patch('builtins.compile', wraps=builtins.compile) as compiler:
            one = cache.get('def generated(): return 1')
            calls = compiler.call_count
            self.assertGreater(calls, 0)
            two = cache.get('def generated(): return 1')
            self.assertIs(one, two)
            self.assertEqual(compiler.call_count, calls)
        self.assertEqual(cache.info()['hits'], 1)

    def test_fresh_vm_values_callbacks_and_no_host_retention(self):
        class Host:
            def __init__(self, value): self.value = value
            def __call__(self): return self.value
        refs=[]
        for expected in (11, 37):
            vm=Interpreter(execution_backend='compiled-strict')
            callback=Host(expected);refs.extend((weakref.ref(vm), weakref.ref(callback)))
            vm.register_function('Callback', callback)
            vm.execute('r=Callback();')
            self.assertEqual(vm.variables['r'], expected)
            self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)
            del vm, callback
        gc.collect()
        self.assertTrue(all(ref() is None for ref in refs))
        self.assertGreater(_CODE_CACHE.info()['hits'], 0)

    def test_cached_code_keeps_fresh_source_diagnostics(self):
        from yadinassi.errors import BSLRuntimeError
        for source_name, text, expected_line in (
                ('first.bsl', 'r=1/0;', 1), ('second.bsl', '\n\nr=1/0;', 3)):
            vm = Interpreter(execution_backend='compiled-strict')
            with self.assertRaises(BSLRuntimeError) as failure:
                vm.execute(text, source_name)
            self.assertEqual(failure.exception.source, source_name)
            self.assertEqual(failure.exception.line, expected_line)
            self.assertEqual(failure.exception.source_line, 'r=1/0;')
        self.assertGreater(_CODE_CACHE.info()['hits'], 0)

    def test_source_budgets_reject_even_after_cache_warmup(self):
        Interpreter(execution_backend='compiled-strict').execute('r=1+2;')
        for field in ('MAX_INLINE_UNIT_BYTES', 'MAX_INLINE_FUNCTION_BYTES'):
            vm=Interpreter(execution_backend='compiled-strict')
            with patch.object(Engine, field, 1):
                with self.assertRaises(CompiledUnsupported): vm.execute('r=1+2;')
            self.assertNotIn('r', vm.variables)

    def test_eviction_weight_and_oversize_bypass(self):
        cache=_CodeCache(max_entries=2, max_bytes=100000)
        first=cache.get('x=1');cache.get('x=2');cache.get('x=3')
        self.assertEqual(cache.info()['entries'], 2)
        self.assertIsNot(first, cache.get('x=1'))
        self.assertLessEqual(cache.info()['bytes'], cache.max_bytes)
        small=_CodeCache(max_entries=2, max_bytes=1)
        self.assertIsNot(small.get('x=1'), small.get('x=1'))
        self.assertEqual(small.info()['entries'], 0)
        cache.reset();self.assertEqual(cache.info()['bytes'], 0)

    def test_compilation_flags_and_optimization_are_keyed(self):
        import __future__
        cache=_CodeCache()
        source='assert False\nx: int = 1'
        plain=cache.get(source, optimize=0)
        optimized=cache.get(source, optimize=1)
        future=cache.get(source, optimize=1, flags=__future__.annotations.compiler_flag)
        self.assertIsNot(plain, optimized);self.assertIsNot(optimized, future)
        with self.assertRaises(AssertionError): exec(plain, {})
        namespace={};exec(future, namespace)
        self.assertEqual(namespace['__annotations__']['x'], 'int')
        import ast
        with self.assertRaises(ValueError): cache.get('x=1', flags=ast.PyCF_ONLY_AST)

    def test_concurrent_callers_share_code_not_namespaces(self):
        cache=_CodeCache(max_entries=4)
        def run(value):
            code=cache.get('result=callback()')
            namespace={'callback':lambda:value}
            exec(code, namespace)
            return namespace['result']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(run, range(16))), list(range(16)))
        self.assertEqual(cache.info()['entries'], 1)
