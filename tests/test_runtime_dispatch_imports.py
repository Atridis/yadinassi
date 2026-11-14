"""The lazy dispatch cache holds type identities, never invocation authority."""
import builtins
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi import runtime


class DispatchImportTests(unittest.TestCase):
    def setUp(self):
        runtime._source_call_dispatch_types.cache_clear()
        self.addCleanup(runtime._source_call_dispatch_types.cache_clear)

    def test_cold_and_warm_calls_preserve_output_and_types(self):
        outputs=[]
        for _ in range(2):
            out=[]; vm=Interpreter(output=out.append)
            vm.execute('For i = 1 To 20 Do Message(String(i)); EndDo;')
            outputs.append(out)
        self.assertEqual(outputs[0], [str(i) for i in range(1,21)])
        self.assertEqual(outputs[0], outputs[1])
        info=runtime._source_call_dispatch_types.cache_info()
        self.assertEqual(info.misses,1); self.assertGreater(info.hits,1)
        from yadinassi.source_constant_managers import ValueManagerCall, write_values
        value=runtime._source_call_dispatch_types()
        self.assertIs(type(value),tuple)
        self.assertEqual(value[-2:],(ValueManagerCall,write_values))

    def test_preargument_procedure_refusal_does_not_load(self):
        vm=Interpreter()
        from yadinassi.values import HostFunction
        vm.functions['procedureonly']=HostFunction('ProcedureOnly',lambda value: None,returns_value=False)
        with patch.object(runtime,'_source_call_dispatch_types',side_effect=AssertionError('too early')) as load:
            with self.assertRaises(BSLError):vm.execute('x = ProcedureOnly(1);')
            load.assert_not_called()

    def test_failed_argument_does_not_load(self):
        vm=Interpreter()
        with patch.object(runtime,'_source_call_dispatch_types',side_effect=AssertionError('too early')) as load:
            with self.assertRaises(BSLError):vm.execute('Message(1 / 0);')
            load.assert_not_called()

    def test_import_failure_is_not_cached(self):
        original=builtins.__import__
        def importing(name,*args,**kwargs):
            if name=='source_constant_queries':raise ImportError('synthetic unavailable dependency')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=importing):
            with self.assertRaises(ImportError):runtime._source_call_dispatch_types()
        self.assertEqual(runtime._source_call_dispatch_types.cache_info().currsize,0)
        self.assertEqual(len(runtime._source_call_dispatch_types()),12)
        self.assertEqual(runtime._source_call_dispatch_types.cache_info().currsize,1)


if __name__=='__main__':unittest.main()
