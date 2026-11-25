"""Binding a possible ByRef actual must not duplicate its expression tree."""
import unittest
from unittest.mock import patch

from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.codegen.direct_emitter import Emit, compile_owned
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

from test_configuration_source_runtime import source
from test_python_direct_source import common_module


class DirectEmitterArgumentScalingTests(unittest.TestCase):
    def test_nested_dynamic_actual_is_lowered_once_in_each_profile(self):
        original = Emit.expression
        for source_dispatch in (False, True):
            for wrapper in ('A.F({})', 'A.F(A[{}])', 'A.F(A[{}].Value)', 'A.F(,{})'):
                sizes = []
                for depth in (2, 4, 8, 16):
                    with self.subTest(source_dispatch=source_dispatch, wrapper=wrapper, depth=depth):
                        visits = []
                        def observed(emitter, node, want_value):
                            if (type(node) is ast.Call and type(node.callee) is ast.Name
                                    and node.callee.name == 'Leaf'):
                                visits.append(node)
                            return original(emitter, node, want_value)

                        expression = 'Leaf()'
                        for _ in range(depth):
                            expression = wrapper.format(expression)
                        text = 'R=' + expression + ';'
                        with patch.object(Emit, 'expression', observed):
                            plan = compile_owned(parse(text), source_text=text,
                                                 source_name='<scaling>',
                                                 source_dispatch=source_dispatch)
                        self.assertEqual(len(visits), 1)
                        sizes.append(len(plan.generated_source))
                self.assertLess(sizes[-1], sizes[0] * 10)

    def test_dynamic_actual_selects_value_or_reference_without_replaying_index(self):
        code = b'''
Procedure OnStart()
    A=New Array; A.Add(4);
    Helpers.Change(A[Index()]);
    Message(Helpers.Read(A[Index()]));
    Message(A[0]);
EndProcedure
Function Index()
    Message("index"); Return 0;
EndFunction
'''
        helper = b'''
Procedure Change(X) Export X=X+1; EndProcedure
Function Read(Val X) Export Return X; EndFunction
'''
        output = []
        app = SourceApplication(source(code, common_module(helper)), output=output.append)
        self.addCleanup(app.close)
        app.start()
        self.assertEqual(output, ['index', 'index', '5', '5'])
