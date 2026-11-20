import unittest

from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported


class NonconstructibleDateDiagnostics(unittest.TestCase):
    def test_static_zero_argument_date_rejects_at_use(self):
        for expression, spelling in (('New Date', 'Date'), ('Новый Дата()', 'Дата')):
            for prepared in (False, True):
                with self.subTest(expression=expression, prepared=prepared):
                    out = []
                    vm = Interpreter(out.append)
                    source = 'Message("before");\n' + expression + ';\nMessage("after");'
                    with self.assertRaises(BSLRuntimeError) as failure:
                        if prepared:
                            vm.execute_prepared(vm.prepare(source, 'date.bsl'))
                        else:
                            vm.execute(source, 'date.bsl')
                    error = failure.exception
                    self.assertEqual((error.source, error.line, error.column), ('date.bsl', 2, 1))
                    self.assertEqual(error.message, 'Тип не определен: ' + spelling)
                    self.assertEqual(out, ['before'])

    def test_other_unknown_constructors_still_reject_before_execution(self):
        for expression in ('New UnlistedConstructor', 'New Date(2024, 2, 29)'):
            with self.subTest(expression=expression):
                out = []
                with self.assertRaises(PythonDirectUnsupported):
                    Interpreter(out.append).execute('Message("before"); ' + expression + ';')
                self.assertEqual(out, [])

    def test_extension_registration_is_not_constructor_admission(self):
        effects = []
        vm = Interpreter(allow_extensions=True)
        vm.register_type('Date', lambda: effects.append('unadmitted'), 'Дата')
        for source in ('New Date', 'Новый Дата'):
            with self.assertRaisesRegex(BSLRuntimeError, 'Тип не определен'):
                vm.execute(source)
            with self.assertRaisesRegex(BSLRuntimeError, 'Тип не определен'):
                vm.execute_prepared(vm.prepare(source))
        self.assertEqual(effects, [])

    def test_explicit_owned_constructor_profile_keeps_existing_resolution(self):
        from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
        from yadinassi.syntax.parser import parse
        source = 'New Date;'
        plan = compile_owned(parse(source, 'date.bsl'), source_text=source,
                             source_name='date.bsl', constructors=('Date',))
        self.assertIn('new:date', plan.required_services)
