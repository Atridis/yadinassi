"""Deterministic launch accounting for the reduced frozen success matrices.

These mocks count transports, not interpreter correctness. Independent semantic
suites and the real frozen smoke remain required.
"""
import ast
import inspect
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import smoke_test as smoke

# Complete bounded programs, not selected assertions or shortened checkpoints.
FAMILIES = {
    'eval': ('EVAL_PROGRAM', 'EVAL_OUTPUT'),
    'string_parity': ('STRING_PARITY_PROGRAM', 'STRING_PARITY_OUTPUT'),
    'array_gap': ('ARRAY_GAP_PROGRAM', 'ARRAY_GAP_OUTPUT'),
    'array_defaults': ('ARRAY_DEFAULT_PROGRAM', 'ARRAY_DEFAULT_OUTPUT'),
    'value_filled': ('VALUE_FILLED_PROGRAM', 'VALUE_FILLED_OUTPUT'),
    'string_lines': ('STRING_LINES_PROGRAM', 'STRING_LINES_OUTPUT'),
    'string_template': ('STRING_TEMPLATE_PROGRAM', 'STRING_TEMPLATE_OUTPUT'),
    'string_boundaries': ('STRING_BOUNDARY_PROGRAM', 'STRING_BOUNDARY_OUTPUT'),
    'characters': ('CHARACTER_PROGRAM', 'CHARACTER_OUTPUT'),
    'numeric_helpers': ('NUMERIC_HELPERS_PROGRAM', 'NUMERIC_HELPERS_OUTPUT'),
    'numeric_boolean_comparisons': ('COMPARISON_PROGRAM', 'COMPARISON_OUTPUT'),
    'goto': ('GOTO_PROGRAM', 'GOTO_OUTPUT'),
    'rounding': ('ROUNDING_PROGRAM', 'ROUNDING_OUTPUT'),
    'text_document': None,
    'tree_findrows': None,
}


class LaterFailureMatrix(Exception):
    """Stop before existing negative cases, which this inventory does not mock."""


class SmokeLaunchInventoryTests(unittest.TestCase):
    def test_all_fifteen_success_matrices_keep_exact_bom_file_and_stateful_console(self):
        count = 0
        for name, constants in FAMILIES.items():
            with self.subTest(family=name), tempfile.TemporaryDirectory() as temporary:
                if constants:
                    program, expected = (getattr(smoke, key) for key in constants)
                else:
                    program, expected = getattr(smoke, name + '_smoke_program')()
                # Count the actual first success matrix, not merely the first
                # two calls before a sentinel. A third success route must fail.
                definition = ast.parse(inspect.getsource(getattr(smoke, 'check_' + name))).body[0]
                matrix = next(node.value for node in definition.body
                              if isinstance(node, ast.Assign)
                              and any(isinstance(t, ast.Name) and t.id == 'cases'
                                      for t in node.targets))
                self.assertIsInstance(matrix, ast.List)
                self.assertEqual(len(matrix.elts), 2)
                calls = []

                def launch(arguments, **kwargs):
                    if len(calls) == 2:
                        self.assertIn(name, {'array_gap', 'value_filled', 'string_lines',
                                            'string_template', 'string_boundaries',
                                            'characters', 'goto', 'rounding'})
                        if len(arguments) > 1 and arguments[1] in ('-c', '-с', '--command'):
                            later_program = arguments[2]
                        elif len(arguments) == 2 and arguments[1] != '-':
                            later_program = Path(arguments[1]).read_text(encoding='utf-8-sig')
                        else:
                            later_program = kwargs['input']
                        self.assertNotIn(later_program, (program, program + '/exit\n'),
                                         'unexpected repeated successful launch')
                        raise LaterFailureMatrix
                    if not calls:
                        self.assertEqual(len(arguments), 2)
                        source = Path(arguments[1])
                        self.assertTrue(source.read_bytes().startswith(b'\xef\xbb\xbf'))
                        self.assertEqual(source.read_text(encoding='utf-8-sig'), program)
                        self.assertIsNone(kwargs.get('input'))
                    else:
                        self.assertEqual(arguments, ['frozen-binary'])
                        self.assertEqual(kwargs['input'], program + '/exit\n')
                    self.assertEqual(kwargs['encoding'], 'utf-8')
                    self.assertTrue(kwargs['capture_output'])
                    self.assertEqual(kwargs['env'], {'PATH': 'sanitized'})
                    calls.append(arguments)
                    return subprocess.CompletedProcess(arguments, 0, expected, '')

                with mock.patch.object(smoke.subprocess, 'run', side_effect=launch), contextlib.redirect_stdout(io.StringIO()):
                    try:
                        getattr(smoke, 'check_' + name)(
                            'frozen-binary', directory=Path(temporary) / name,
                            env={'PATH': 'sanitized'})
                    except LaterFailureMatrix:
                        pass
                self.assertEqual(len(calls), 2)
                count += len(calls)
        self.assertEqual(len(FAMILIES), 15)
        self.assertEqual(count, 30)
        self.assertEqual(len(FAMILIES) * 6 - count, 60)
