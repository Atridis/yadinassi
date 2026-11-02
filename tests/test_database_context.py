"""SQLite host identity and existing logical BSL context propagation."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342
from sqlite_catalog_fixture import configuration_files

ALIASES = ("InfoBaseConnectionString", "СтрокаСоединенияИнформационнойБазы")
MISSING_CONTEXT = "db required for further code execution"


def make_sqlite_file(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'application.sqlite'
    with SQLiteDBContext.create(path, import_configuration(configuration_files())):
        pass
    return path


class DatabaseContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Resolve only the owned fixture: macOS may spell /private/var as /var.
        self.root = Path(self.temporary.name).resolve()
        self.directory = self.root / "Моя база данных"
        self.path = make_sqlite_file(self.directory)
        self.context = SQLiteDBContext(self.path)
        self.addCleanup(self.context.close)
        self.expected = "SQLite=" + str(self.path)

    def interpreter(self, context=None, **kwargs):
        interpreter = Interpreter(database_context=context, **kwargs)
        self.addCleanup(interpreter.close)
        return interpreter

    def test_bilingual_zero_argument_aliases_use_owned_sqlite(self):
        before = self.path.read_bytes()
        interpreter = self.interpreter(self.context)
        self.assertIs(interpreter.functions[ALIASES[0].casefold()],
                      interpreter.functions[ALIASES[1].casefold()])
        for alias in ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(interpreter.execute(alias + "()"), self.expected)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_context_uses_catchable_runtime_error_not_bare_bsl_error(self):
        for alias in ALIASES:
            with self.subTest(alias=alias):
                output = []
                interpreter = self.interpreter(output=output.append)
                with self.assertRaises(BSLRuntimeError) as caught:
                    interpreter.execute(alias + "()", "without-db.bsl")
                self.assertIs(type(caught.exception), BSLRuntimeError)
                self.assertEqual(caught.exception.message, MISSING_CONTEXT)
                self.assertEqual(caught.exception.source, "without-db.bsl")
                interpreter.execute("Try " + alias + "(); Except "
                                    "Message(ErrorDescription()); EndTry; Message(42);")
                self.assertIn(MISSING_CONTEXT, output[0])
                self.assertEqual(output[1], "42")

    def test_missing_context_callback_does_not_bind_interpreter(self):
        interpreter = self.interpreter()
        for alias in ALIASES:
            callback = interpreter.functions[alias.casefold()].function
            self.assertIsNone(getattr(callback, "__self__", None))
            with self.assertRaisesRegex(ValueError, "^" + MISSING_CONTEXT + "$"):
                callback()

    def test_context_is_not_a_bsl_module_variable_or_transferable_value(self):
        interpreter = self.interpreter(self.context)
        self.assertEqual(interpreter.variables, {})
        for expression in ("database_context", "ThisObject.database_context"):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                interpreter.execute(expression)
        with self.assertRaises(TypeError):
            Interpreter._copy_context_packet([self.context])

    def test_server_activations_share_context_without_client_frame_binding(self):
        interpreter = self.interpreter(self.context)
        interpreter.variables["private_client_value"] = "must not cross"
        for module_context in (True, False):
            with self.subTest(module_context=module_context):
                first = interpreter._new_server_activation(module_context=module_context)
                second = interpreter._new_server_activation(module_context=module_context)
                self.assertIsNot(first, second)
                for server in (first, second):
                    self.assertIs(server.database_context, self.context)
                    self.assertNotIn("private_client_value", server.variables)
                    for alias in ALIASES:
                        callback = server.functions[alias.casefold()].function
                        self.assertIs(callback.__self__, self.context)
                        self.assertEqual(callback(), self.expected)

    def test_server_nocontext_and_dual_execution_receive_same_database(self):
        interpreter = self.interpreter(self.context)
        interpreter.execute("""&AtClientAtServerNoContext
Function Dual() Return InfoBaseConnectionString(); EndFunction
&AtServerNoContext
Function Detached() Return СтрокаСоединенияИнформационнойБазы(); EndFunction
&AtServer
Function ContextServer() Return InfoBaseConnectionString(); EndFunction
&AtServer
Function ServerDual() Return Dual(); EndFunction
&AtServerNoContext
Function DetachedDual() Return Dual(); EndFunction
""")
        for call in ("Dual()", "Detached()", "ContextServer()", "ServerDual()", "DetachedDual()"):
            with self.subTest(call=call):
                self.assertEqual(interpreter.execute(call), self.expected)
                self.assertEqual(interpreter.execution_context, "client")
                self.assertTrue(interpreter._has_module_context)

    def test_missing_database_in_every_execution_lane_is_catchable(self):
        for directive in ("", "&AtServer\n", "&AtServerNoContext\n",
                          "&AtClientAtServerNoContext\n"):
            with self.subTest(directive=directive):
                output = []
                interpreter = self.interpreter(output=output.append)
                interpreter.execute(directive + "Function ReadDB() Return InfoBaseConnectionString(); "
                                    "EndFunction\nTry ReadDB(); Except Message(ErrorDescription()); EndTry;")
                self.assertIn(MISSING_CONTEXT, output[0])
                self.assertEqual(interpreter.execution_context, "client")

    def test_imports_explicitly_share_context_for_client_server_and_dual_wrappers(self):
        module = self.root / "Side.bsl"
        module.write_text("""&AtClientAtServerNoContext
Function Dual() Return InfoBaseConnectionString(); EndFunction
Function ClientRead() Export Return Dual(); EndFunction
&AtServer
Function ServerRead() Export Return Dual(); EndFunction
&AtServerNoContext
Function DetachedRead() Export Return СтрокаСоединенияИнформационнойБазы(); EndFunction
""", encoding="utf-8")
        interpreter = self.interpreter(self.context)
        interpreter.execute("// #Import Side.bsl\n", str(self.root / "Root.bsl"))
        child = interpreter.imports["side"].interpreter
        self.assertIs(child.database_context, self.context)
        for alias in ALIASES:
            self.assertIs(child.functions[alias.casefold()].function.__self__, self.context)
        for method in ("ClientRead", "ServerRead", "DetachedRead"):
            with self.subTest(method=method):
                self.assertEqual(interpreter.execute("Side." + method + "()"), self.expected)

    def test_import_without_database_remains_usable_until_database_call(self):
        (self.root / "Side.bsl").write_text(
            "Function ReadDB() Export Return InfoBaseConnectionString(); EndFunction\n"
            "Function Arithmetic() Export Return 20 + 22; EndFunction", encoding="utf-8")
        output = []
        interpreter = self.interpreter(output=output.append)
        interpreter.execute("// #Import Side.bsl\nMessage(Side.Arithmetic());\n"
                            "Try Side.ReadDB(); Except Message(ErrorDescription()); EndTry;",
                            str(self.root / "Root.bsl"))
        self.assertEqual(output[0], "42")
        self.assertIn(MISSING_CONTEXT, output[1])
        self.assertIsNone(interpreter.imports["side"].interpreter.database_context)

    def test_interleaved_interpreters_and_import_caches_are_isolated(self):
        second_directory = self.root / "Second DB"
        second_path = make_sqlite_file(second_directory)
        second_context = SQLiteDBContext(second_path)
        self.addCleanup(second_context.close)
        (self.root / "Side.bsl").write_text(
            "Function ReadDB() Export Return InfoBaseConnectionString(); EndFunction\n"
            "&AtServerNoContext\nFunction ServerDB() Export Return InfoBaseConnectionString(); EndFunction",
            encoding="utf-8")
        first = self.interpreter(self.context)
        second = self.interpreter(second_context)
        absent = self.interpreter()
        for interpreter in (first, second, absent):
            interpreter.execute("// #Import Side.bsl\n", str(self.root / "Root.bsl"))
        self.assertIsNot(first.imports["side"], second.imports["side"])
        for interpreter, expected in ((first, self.expected),
                                      (second, "SQLite=" + str(second_path)),
                                      (first, self.expected)):
            for call in ("InfoBaseConnectionString()", "Side.ReadDB()", "Side.ServerDB()"):
                with self.subTest(expected=expected, call=call):
                    self.assertEqual(interpreter.execute(call), expected)
        with self.assertRaisesRegex(BSLRuntimeError, MISSING_CONTEXT):
            absent.execute("Side.ServerDB()")

    def test_database_does_not_change_default_client_or_native_target(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                interpreter = self.interpreter(self.context, native_target=target)
                self.assertEqual(interpreter.native_target, target)
                self.assertEqual(interpreter.execution_context, "client")
                self.assertEqual(interpreter.execute("InfoBaseConnectionString()"), self.expected)
                self.assertEqual(interpreter._new_server_activation().native_target, target)
        self.assertEqual(self.interpreter(self.context).native_target, WINDOWS_8_3_27_2342)


    def test_invalid_storage_fails_at_context_admission_without_creating_file(self):
        missing = self.root / 'missing.sqlite'
        with self.assertRaises(BackendError):
            SQLiteDBContext(missing)
        self.assertFalse(missing.exists())
        invalid = self.root / 'invalid.sqlite'
        invalid.write_bytes(b'not a database')
        with self.assertRaises(BackendError):
            SQLiteDBContext(invalid)
        self.assertEqual(invalid.read_bytes(), b'not a database')

    def test_nonzero_arity_does_not_invoke_context(self):
        interpreter = self.interpreter(self.context)
        for alias in ALIASES:
            with self.subTest(alias=alias), self.assertRaises(BSLRuntimeError):
                interpreter.execute(alias + '(1)')
        self.assertEqual(interpreter.execute(ALIASES[0] + '()'), self.expected)

if __name__ == '__main__':
    unittest.main()
