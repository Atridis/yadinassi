"""Core structured exceptions; native checkpoint establishes platform defaults."""
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.syntax import ast
from yadinassi.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse


class ExtendedExceptionTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_full_russian_and_english_path(self):
        self.vm.execute('''
            Попытка
                ВызватьИсключение ("ошибка", КатегорияОшибки.ОшибкаКонфигурации,
                                   "E.1", "подробности");
            Исключение
                инфо = ИнформацияОбОшибке();
                Сообщить(инфо.Описание); Сообщить(инфо.Код);
                Сообщить(инфо.ДополнительнаяИнформация);
                Сообщить(инфо.ЯвляетсяОшибкойКатегории(КатегорияОшибки.ОшибкаКонфигурации));
                Сообщить(ТипЗнч(инфо) = Тип("ИнформацияОбОшибке"));
            КонецПопытки;
            Try Raise ("failure", ErrorCategory.ConfigurationError, "E.2", "details");
            Except
                info = ErrorInfo(); Message(info.Description); Message(info.Code);
                Message(info.AdditionalInformation);
                Message(info.IsErrorOfCategory(ErrorCategory.ExceptionRaisedFromScript));
                Message(TypeOf(info) = Type("ErrorInfo"));
            EndTry;
        ''')
        self.assertEqual(self.output, ['ошибка', 'E.1', 'подробности', 'Да', 'Да',
                                       'failure', 'E.2', 'details', 'Да', 'Да'])

    def test_optional_slots_and_legacy_parenthesized_expression(self):
        self.vm.execute('''
            Try Raise ("code-only",, "E.3");
            Except e=ErrorInfo(); Message(e.Code); Message(e.Description); EndTry;
            Try Raise ("left") + "-right";
            Except e=ErrorInfo(); Message(e.Description); EndTry;
            Try Raise (("nested"));
            Except e=ErrorInfo(); Message(e.Description); EndTry;
        ''')
        self.assertEqual(self.output, ['E.3', 'code-only', 'left-right', 'nested'])

    def test_saved_cause_survives_handlers_and_wrapper_does_not_modify_it(self):
        self.vm.execute('''
            Try Raise ("original",, "INNER", "inner-details");
            Except original=ErrorInfo(); EndTry;
            Try Raise ("wrapper", ErrorCategory.ConfigurationError, "OUTER", "outer-details", original);
            Except
                outer=ErrorInfo(); Message(outer.Description); Message(outer.Code);
                Message(outer.Cause.Description); Message(outer.Cause.Code);
                Message(outer.Cause.AdditionalInformation);
            EndTry;
            Message(original.Code);
        ''')
        self.assertEqual(self.output, ['wrapper', 'OUTER', 'original', 'INNER',
                                       'inner-details', 'INNER'])

    def test_rethrow_and_routine_propagation_preserve_snapshot(self):
        self.vm.execute('''
            Procedure Fail()
                Raise ("routine", ErrorCategory.ConfigurationError, "PROC", "details");
            EndProcedure
            Function ReadInfo() Return ErrorInfo(); EndFunction
            Try
                Try Fail(); Except first=ReadInfo(); Raise; EndTry;
            Except
                second=ErrorInfo(); Message(second.Code); Message(second.AdditionalInformation);
                Message(second.Description); Message(second.LineNumber=first.LineNumber);
            EndTry;
        ''', 'routines.bsl')
        self.assertEqual(self.output, ['PROC', 'details', 'routine', 'Да'])
        self.assertIs(self.vm.variables['first'], self.vm.variables['second'])

    def test_category_query_includes_immediate_cause(self):
        self.vm.execute('''
            Try
                Try Raise ("inner", ErrorCategory.ConfigurationError, "INNER");
                Except Raise ("outer",, "OUTER",, ErrorInfo()); EndTry;
            Except
                saved=ErrorInfo();
                Message(saved.IsErrorOfCategory(ErrorCategory.ConfigurationError));
                Message(saved.Cause.Code);
            EndTry;
        ''')
        self.assertEqual(self.output, ['Да', 'INNER'])

    def test_imported_routine_exposes_same_dynamic_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'worker.bsl').write_text('''
                Procedure Fail() Export
                    Raise ("imported",, "MODULE", "details");
                EndProcedure
                Function ReadInfo() Export Return ErrorInfo(); EndFunction
            ''', encoding='utf-8')
            self.vm.execute('''
                // #Import worker.bsl
                Try worker.Fail(); Except e=worker.ReadInfo(); Message(e.Code); EndTry;
            ''', str(path/'main.bsl'))
        self.assertEqual(self.output, ['MODULE'])

    def test_fields_are_read_only_and_python_attributes_are_hidden(self):
        self.vm.execute('Try Raise ("x",, "C"); Except saved=ErrorInfo(); EndTry;')
        for statement in ['saved.Code="changed";', 'saved.Description="changed";',
                          'saved.Cause=Undefined;', 'saved.categories;', 'saved.__dict__;']:
            with self.subTest(statement=statement), self.assertRaises(BSLRuntimeError):
                self.vm.execute(statement)
        self.assertEqual(self.vm.execute('saved.Code'), 'C')

    def test_argument_expressions_are_evaluated_once_in_order(self):
        self.vm.execute('''
            Var order; order="";
            Function Part(value) order=order+value; Return value; EndFunction
            Try Raise (Part("D"),, Part("C"), Part("A")); Except e=ErrorInfo(); EndTry;
            Message(order); Message(e.Description); Message(e.Code); Message(e.AdditionalInformation);
        ''')
        self.assertEqual(self.output, ['DCA', 'D', 'C', 'A'])

    def test_documented_forbidden_raise_categories(self):
        for category in ['AllErrors', 'OtherError', 'ScriptCompileError',
                         'ScriptRuntimeError', 'ExceptionRaisedFromScript']:
            with self.subTest(category=category), self.assertRaises(BSLRuntimeError):
                self.vm.execute(f'Raise ("bad", ErrorCategory.{category});')
        self.vm.execute('''
            Try Raise ("not-raised", ErrorCategory.AllErrors);
            Except
                rejected=ErrorInfo();
                Message(rejected.Cause=Undefined);
                Message(rejected.IsErrorOfCategory(ErrorCategory.ScriptRuntimeError));
                Message(rejected.IsErrorOfCategory(ErrorCategory.ExceptionRaisedFromScript));
                Message(rejected.Cause.IsErrorOfCategory(ErrorCategory.ConfigurationError));
            EndTry;
        ''')
        self.assertEqual(self.output, ['Нет', 'Да', 'Нет', 'Нет'])

    def test_structured_runtime_error_has_source_diagnostics(self):
        self.vm.execute('''Try
    x = 1 / 0;
Except saved=ErrorInfo(); EndTry;''', 'division.bsl')
        self.assertEqual(self.vm.execute('saved.Description'), 'Деление на ноль')
        self.assertEqual(self.vm.execute('saved.ModuleName'), 'division.bsl')
        self.assertEqual(self.vm.execute('saved.InitialString'), '    x = 1 / 0;')
        self.assertTrue(self.vm.execute('saved.IsErrorOfCategory(ErrorCategory.ScriptRuntimeError)'))
        self.assertFalse(self.vm.execute('saved.IsErrorOfCategory(ErrorCategory.ExceptionRaisedFromScript)'))

    def test_source_line_snapshot_survives_reusing_source_label(self):
        from yadinassi.syntax.lexer import Lexer
        tokens = Lexer('a = 1; b = 2;\r\n').tokens()
        self.assertEqual(tokens[0].source_line, 'a = 1; b = 2;')
        self.assertTrue(all(token.source_line is tokens[0].source_line
                            for token in tokens if token.kind != 'EOF'))
        self.vm.execute('Procedure Fail() Raise ("old",, "C"); EndProcedure', 'reused.bsl')
        self.vm.execute('Try Fail(); Except saved=ErrorInfo(); EndTry;', 'reused.bsl')
        self.assertEqual(self.vm.execute('saved.InitialString'),
                         'Procedure Fail() Raise ("old",, "C"); EndProcedure')

    def test_error_codec_policy_explicitly_rejects_values_and_type_records(self):
        from yadinassi import serialization
        from yadinassi.values import BSLType
        self.assertEqual(serialization._UNSUPPORTED_CODEC_TYPES,
                         {BSLType.XML_READER,BSLType.XML_WRITER,BSLType.XML_READER_SETTINGS,BSLType.XML_WRITER_SETTINGS,BSLType.XML_NODE_TYPE,BSLType.XML_SPACE,BSLType.XML_VALIDATION_TYPE,BSLType.XML_NAMESPACE_CONTEXT,
                          BSLType.ERROR_INFO, BSLType.ERROR_CATEGORY, BSLType.PROMISE,
                          BSLType.TEXT_DOCUMENT, BSLType.JSON_READER, BSLType.JSON_WRITER,
                          BSLType.JSON_WRITER_SETTINGS, BSLType.JSON_VALUE_TYPE, BSLType.JSON_LINE_BREAK,
                          BSLType.CATALOGS_MANAGER,
                          BSLType.FILE, BSLType.TEXT_READER, BSLType.TEXT_WRITER,
                          BSLType.BINARY_DATA, BSLType.TEXT_ENCODING}
                         | serialization._TREE_CODEC_TYPES)
        self.vm.execute('Try Raise "x"; Except saved=ErrorInfo(); EndTry;')
        for expression in ['saved', 'ErrorCategory.ConfigurationError',
                           'Type("ErrorInfo")', 'Type("ErrorCategory")']:
            with self.subTest(expression=expression), self.assertRaisesRegex(BSLRuntimeError, 'пока не поддерживается'):
                self.vm.execute('ValueToStringInternal(' + expression + ');')

    def test_parser_retains_omissions_and_rejects_missing_description(self):
        node=parse('Raise ("x",, "C",,);')[0]
        self.assertEqual(len(node.optional_arguments), 4)
        self.assertIsInstance(node.optional_arguments[0], ast.OmittedArgument)
        self.assertIsInstance(node.optional_arguments[3], ast.OmittedArgument)
        for source in ['Raise ();', 'Raise (, "x");', 'Raise ("x", 1, 2, 3, 4, 5);']:
            with self.subTest(source=source), self.assertRaises(BSLError):
                parse(source)


if __name__ == '__main__':
    unittest.main()
