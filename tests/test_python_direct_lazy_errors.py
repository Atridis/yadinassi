"""Scoped diagnostics are paid for only when observed or rethrown."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi import experimental_naked_errors as errors


class LazyErrorTests(unittest.TestCase):
    def test_silent_handler_never_formats(self):
        with patch.object(errors,'convert_error',side_effect=AssertionError('unused diagnostic')):
            vm=Interpreter();vm.execute('N=0;For I=1 To 100 Do Try X=1/0;Except N=N+1;EndTry;EndDo;')
        self.assertEqual(vm.variables['n'],100)

    def test_description_materializes_once_per_error(self):
        with patch.object(errors,'convert_error',wraps=errors.convert_error) as convert:
            vm=Interpreter();vm.execute('Try X=1/0;Except A=ErrorDescription();B=ErrorDescription();EndTry;','once.bsl')
        self.assertEqual(convert.call_count,1)
        self.assertEqual(vm.variables['a'],vm.variables['b'])
        self.assertIn('once.bsl:1:',vm.variables['a'])

    def test_cached_locations_equal_uncached_and_bounded(self):
        from types import SimpleNamespace
        context=SimpleNamespace()
        for line in (1,2,3,1):
            source='\n'*(line-1)+'1/0\n'
            code=compile(source,'locations.bsl','exec')
            try:exec(code,{})
            except ZeroDivisionError as error:
                expected=errors.convert_error(error,'locations.bsl',source)
                for _ in range(2):
                    actual=errors.convert_error(error,'locations.bsl',source,_context=context)
                    self.assertEqual((str(actual),actual.source_line),(str(expected),expected.source_line))
            locations=context._error_locations
            self.assertIs(locations.source,source)
            if hasattr(code,'co_positions'):self.assertIs(locations.code,code)
            self.assertEqual(set(locations.__slots__),{'code','positions','source','lines'})

    def test_position_table_built_once_for_repeated_description(self):
        calls=[];original=errors._ErrorLocations.for_code
        def count(locations,code):
            if locations.code is not code:calls.append(code)
            return original(locations,code)
        with patch.object(errors._ErrorLocations,'for_code',count):
            vm=Interpreter();vm.execute('For I=1 To 20 Do Try X=1/0;Except D=ErrorDescription();EndTry;EndDo;')
        import sys
        self.assertEqual(len(calls),1 if sys.version_info>=(3,11) else 0)

    def test_completed_handlers_release_tracebacks_without_gc(self):
        import gc,weakref
        contexts=[]
        from yadinassi.experimental_naked_boundaries import BoundaryContext
        original=BoundaryContext.__init__
        def capture(context,*args,**kwargs):
            original(context,*args,**kwargs);contexts.append(weakref.ref(context))
        enabled=gc.isenabled();gc.disable()
        try:
            with patch.object(BoundaryContext,'__init__',capture):
                vm=Interpreter();vm.execute('Try X=1/0;Except N=1;EndTry;')
                vm.execute('Try X=1/0;Except D=ErrorDescription();EndTry;')
            self.assertTrue(contexts)
            self.assertTrue(all(reference() is None for reference in contexts))
        finally:
            if enabled:gc.enable()

    def test_arithmetic_reraise_preserves_original_source(self):
        from yadinassi.errors import BSLRuntimeError
        vm=Interpreter()
        with self.assertRaises(BSLRuntimeError) as raised:
            vm.execute('Try\n X=1/0;\nExcept\n Raise;\nEndTry;','reraise.bsl')
        self.assertIn('reraise.bsl:2:',str(raised.exception))
        self.assertEqual(raised.exception.source_line,' X=1/0;')
        self.assertTrue(str(raised.exception).endswith('Деление на ноль'))
