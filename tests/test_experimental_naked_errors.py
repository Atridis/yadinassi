"""Experiment source mapping restores diagnostics without hot node wrappers."""
import unittest
import os
from unittest.mock import patch
from decimal import Decimal
from types import CodeType
from yadinassi.syntax.parser import parse
from yadinassi.errors import BSLRuntimeError
from yadinassi.experimental_naked_errors import SourceMap,convert_error

class NakedErrorMappingTests(unittest.TestCase):
    def test_python_instruction_maps_to_original_binary_token(self):
        source='result=1/0;';node=parse(source,'original.bsl')[0]
        mapping=SourceMap();mapping.enter(node)
        mapping.expression('_constants[0]',node.value.left)
        mapping.expression('_constants[1]',node.value.right)
        mapping.expression('(_constants[0] / _constants[1])',node.value)
        mapping.line(1);mapping.leave()
        code=mapping.compile('def run(_constants):\n    result=(_constants[0] / _constants[1])\n','original.bsl',1)
        namespace={};exec(code,namespace)
        try:namespace['run']((Decimal(1),Decimal(0)))
        except Exception as error:converted=convert_error(error,'original.bsl',source)
        self.assertIsInstance(converted,BSLRuntimeError)
        self.assertEqual(converted.message,'Деление на ноль')
        self.assertEqual(converted.line,node.value.token.line)
        self.assertEqual(converted.column,node.value.token.column if hasattr(CodeType,'co_positions') else 1)
        self.assertEqual(converted.source_line,source)
    def test_normalization_is_once_per_text_and_compile(self):
        import yadinassi.experimental_naked_errors as errors
        node=parse('x=1+2;','repeat.bsl')[0]
        mapping=SourceMap();mapping.enter(node)
        for _ in range(4):mapping.expression('(1 + 2)',node.value)
        mapping.line(1);mapping.line(2);mapping.leave()
        for _ in range(2):
            with patch.object(errors,'_normalized',wraps=errors._normalized) as normalize:
                mapping.compile('x=1+2\ny=1+2\n','repeat.bsl',0)
                normalize.assert_called_once_with('(1 + 2)')

    def test_mapping_does_not_serialize_subtrees(self):
        import ast
        import yadinassi.experimental_naked_errors as errors
        node=parse('x=1+2;','filter.bsl')[0]
        mapping=SourceMap();mapping.enter(node)
        mapping.expression('(1 + 2)',node.value);mapping.line(1);mapping.leave()
        with patch.object(errors.ast,'dump',wraps=ast.dump) as dump:
            mapping.compile('x=1+2\n','filter.bsl',0)
            dump.assert_not_called()

    def test_duplicate_expressions_retain_distinct_source_locations(self):
        source='x=1/0; y=1/0;'
        first,second=parse(source,'duplicate.bsl')
        mapping=SourceMap()
        for row,node in enumerate((first,second),1):
            mapping.enter(node);mapping.expression('(1 / 0)',node.value)
            mapping.line(row);mapping.leave()
        code=mapping.compile('x=1/0\ny=1/0\n','duplicate.bsl',0)
        if hasattr(code,'co_positions'):
            positions=set(code.co_positions())
            for node in (first,second):
                self.assertIn((1,1,node.value.token.column-1,node.value.token.column),positions)
        else:
            self.assertEqual({line for _,_,line in code.co_lines() if line is not None},{1})

    def test_authority_and_control_failures_remain_outside_conversion(self):
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        for error in (BoundaryViolation('denied'),KeyboardInterrupt(),SystemExit(),PermissionError('denied')):
            self.assertIs(convert_error(error,'original.bsl',''),error)
    def test_existing_bsl_error_identity_preserved(self):
        error=BSLRuntimeError('original','x',2,3)
        self.assertIs(convert_error(error,'original.bsl',''),error)

class NakedErrorIntegrationTests(unittest.TestCase):
    def test_exact_source_errors_and_partial_effects(self):
        from yadinassi import Interpreter
        from yadinassi.experimental_naked_collections import prepare
        for source in ('result=1/0;','a=New Array;a.Add(1);result=a[2];',
                       'Function F() Return 1/0;EndFunction result=F();'):
            outcomes=[]
            for naked in (False,True):
                with patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'}):
                    try:
                        if naked:prepare(source,source_name='errors.bsl',repairs=('error_boundaries','array_index_contract')).run()
                        else:Interpreter().execute(source,'errors.bsl')
                    except Exception as error:outcomes.append((type(error),str(error)))
            self.assertEqual(len(outcomes),2);self.assertEqual(*outcomes)
    def test_permission_error_is_not_swallowed_by_bsl_try(self):
        from yadinassi.experimental_naked_collections import prepare
        def denied():raise PermissionError('denied')
        with patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'}):
            program=prepare('caught=False;Try Host();Except caught=True;EndTry;',repairs=('error_boundaries',))
            with self.assertRaises(PermissionError):program.run({'host':denied})
            self.assertIs(program.last_state['caught'],False)


class DirectPortableDiagnosticsTests(unittest.TestCase):
    def test_prepared_nested_error_preserves_bsl_line_and_effects(self):
        from yadinassi import Interpreter
        source='Function Fail()\n  x=1;\n  Return 1/0;\nEndFunction\nbefore=7; result=Fail();'
        vm=Interpreter();plan=vm.prepare(source,'portable.bsl')
        with patch.object(vm,'_compiled',side_effect=AssertionError('legacy')):
            with self.assertRaises(BSLRuntimeError) as caught:vm.execute_prepared(plan)
        error=caught.exception
        self.assertEqual(error.line,3)
        self.assertEqual(error.source_line,'  Return 1/0;')
        self.assertEqual(error.column,11 if hasattr(CodeType,'co_positions') else 1)
        self.assertEqual(error.message,'Деление на ноль')
        self.assertEqual(vm.variables['before'],7)
        self.assertNotIn('result',vm.variables)
        self.assertEqual(vm.execution_backend_stats['fallback'],0)

    def test_host_error_uses_bsl_call_line(self):
        from yadinassi import Interpreter
        vm=Interpreter()
        def fail():raise ValueError('host failure')
        vm.register_function('Fail',fail)
        source='before=1;\n\nFail();'
        with self.assertRaises(BSLRuntimeError) as caught:vm.execute(source,'host.bsl')
        self.assertEqual(caught.exception.line,3)
        self.assertEqual(caught.exception.source_line,'Fail();')
        self.assertEqual(caught.exception.column,1)
        self.assertEqual(vm.variables['before'],1)

    def test_try_handles_runtime_error_without_masking_authority(self):
        from yadinassi import Interpreter
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        vm=Interpreter()
        vm.execute('caught=False; Try x=1/0; Except caught=True; EndTry;')
        self.assertTrue(vm.variables['caught'])
        def deny():raise BoundaryViolation('closed')
        vm.register_function('Deny',deny)
        with self.assertRaises(BoundaryViolation):
            vm.execute('caught=False; Try Deny(); Except caught=True; EndTry;')
        self.assertFalse(vm.variables['caught'])
