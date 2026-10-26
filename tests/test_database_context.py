"""Lazy runtime wiring, using synthetic recognized headers, not valid 1C bases.

These files establish real read-only inspection and context propagation, not
authentication, native database validity or Windows return-value parity.
"""

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.database_context import FileDBContext, _normalize_directory
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342
from yadinassi.syntax.parser import parse
from yadinassi.storage import filedb


ALIASES = ("InfoBaseConnectionString", "СтрокаСоединенияИнформационнойБазы")
MISSING_CONTEXT = "db required for further code execution"


def make_header_file(directory, *, version=(8, 3, 8, 0), pages=3, magic=b"1CDBMSV8"):
    """Recognized header geometry only, intentionally not a native database."""
    directory.mkdir(parents=True, exist_ok=True)
    raw = (magic + bytes(version) + pages.to_bytes(4, "little") + b"\0" * 4
           + (4096).to_bytes(4, "little"))
    path = directory / "1Cv8.1CD"
    with path.open("wb") as stream:
        stream.write(raw)
        stream.truncate(pages * 4096)
    return path


class DatabaseContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Resolve only the owned fixture: macOS may spell /private/var as /var.
        self.root = Path(self.temporary.name).resolve()
        self.directory = self.root / "Моя база данных"
        self.path = make_header_file(self.directory)
        self.context = FileDBContext(self.directory)
        self.expected = f'File="{self.directory}";'

    def interpreter(self, context=None, **kwargs):
        interpreter = Interpreter(database_context=context, **kwargs)
        self.addCleanup(interpreter.close)
        return interpreter

    def test_construction_is_lexical_without_filesystem_inspection(self):
        expected = os.path.join(os.getcwd(), "База данных")
        with mock.patch("builtins.open", side_effect=AssertionError("unexpected open")), \
             mock.patch("io.open", side_effect=AssertionError("unexpected open")), \
             mock.patch.object(os, "open", side_effect=AssertionError("unexpected open")), \
             mock.patch.object(os, "stat", side_effect=AssertionError("unexpected stat")), \
             mock.patch.object(os, "lstat", side_effect=AssertionError("unexpected lstat")), \
             mock.patch.object(Path, "resolve", side_effect=AssertionError("unexpected resolve")):
            context = FileDBContext(os.path.join("unused", "..", "База данных", "."))
            self.assertEqual(context.directory, expected)
            interpreter = self.interpreter(context)
            self.assertIs(interpreter.database_context, context)
            self.assertEqual(interpreter.execute("20 + 22"), Decimal(42))

    def test_relative_directory_remains_anchored_after_cwd_change(self):
        later = self.root / "later"
        later.mkdir()
        before = os.getcwd()
        try:
            os.chdir(self.root)
            context = FileDBContext(Path("unused") / ".." / self.directory.name)
            os.chdir(later)
            self.assertEqual(context.directory, str(self.directory))
            self.assertEqual(context.connection_string(), self.expected)
        finally:
            os.chdir(before)

    @unittest.skipIf(os.name == "nt", "POSIX directory alias; no privileged Windows symlink required")
    def test_relative_directory_anchors_actual_cwd_without_runtime_resolution(self):
        physical = self.root / "physical"
        make_header_file(physical / "db")
        alias = self.root / "cwd-alias"
        alias.symlink_to(physical, target_is_directory=True)
        before = os.getcwd()
        try:
            os.chdir(alias)
            startup = os.getcwd()
            self.assertEqual(startup, str(physical))
            with mock.patch.object(Path, "resolve", side_effect=AssertionError("unexpected resolve")), \
                 mock.patch.object(os, "stat", side_effect=AssertionError("unexpected stat")), \
                 mock.patch.object(os, "lstat", side_effect=AssertionError("unexpected lstat")), \
                 mock.patch.object(os, "open", side_effect=AssertionError("unexpected open")):
                context = FileDBContext("db")
                self.assertEqual(context.directory, os.path.join(startup, "db"))
            os.chdir(self.root)
            self.assertEqual(context.connection_string(), f'File="{physical / "db"}";')
        finally:
            os.chdir(before)

    def test_immutable_context_keeps_no_session_or_descriptor(self):
        self.assertEqual({field.name for field in fields(self.context)},
                         {"directory", "_unsupported"})
        self.assertFalse(hasattr(self.context, "__dict__"))
        for name, value in (("directory", "replacement"), ("_unsupported", True)):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(self.context, name, value)
        interpreter = self.interpreter(self.context)
        with self.assertRaises(AttributeError):
            interpreter.database_context = None
        self.assertEqual(self.context.connection_string(), self.expected)
        self.assertEqual(self.context.connection_string(), self.expected)

    def test_bilingual_zero_argument_aliases_use_real_recognized_header(self):
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

    def test_invalid_or_missing_directory_is_not_used_by_unexecuted_code(self):
        source = """Function Uncalled()
Return InfoBaseConnectionString();
EndFunction
&AtServer
Function UncalledServer()
Return СтрокаСоединенияИнформационнойБазы();
EndFunction
If False Then Message(InfoBaseConnectionString()); EndIf;
Answer = 20 + 22;
"""
        for directory in (None, str(self.root / "missing"), 'private";Usr=secret',
                          "bad\0path", "bad\ud800path", r"\\server\share"):
            with self.subTest(directory=directory), \
                 mock.patch("yadinassi.database_context.inspect_header",
                            side_effect=AssertionError("unexpected inspection")) as inspect, \
                 mock.patch.object(os, "open", side_effect=AssertionError("unexpected open")):
                context = None if directory is None else FileDBContext(directory)
                program = parse(source, "lazy.bsl")
                interpreter = self.interpreter(context)
                interpreter.execute_program(program)
                self.assertEqual(interpreter.variables["answer"], Decimal(42))
                self.assertEqual(interpreter.execute("20 + 22"), Decimal(42))
                inspect.assert_not_called()

    def test_database_file_is_opened_readonly_and_closed_for_each_executed_call(self):
        interpreter = self.interpreter(self.context)
        with mock.patch.object(filedb.os, "open", wraps=os.open) as opened, \
             mock.patch.object(filedb.os, "read", wraps=os.read) as read, \
             mock.patch.object(filedb.os, "close", wraps=os.close) as closed:
            interpreter.execute("Function Never() Return InfoBaseConnectionString(); EndFunction\n"
                                "If False Then Never(); EndIf; 1 + 2")
            opened.assert_not_called()
            for alias in ALIASES:
                self.assertEqual(interpreter.execute(alias + "()"), self.expected)
            self.assertEqual(opened.call_count, 2)
            self.assertEqual(closed.call_count, 2)
            self.assertEqual(read.call_count, 2)
            for call in opened.call_args_list:
                self.assertEqual(os.fspath(call.args[0]), str(self.path))
                self.assertEqual(call.args[1] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), 0)
            self.assertTrue(all(call.args[1] == 24 for call in read.call_args_list))

    def test_failed_and_successful_inspections_are_not_cached(self):
        interpreter = self.interpreter(self.context)
        self.path.unlink()
        with self.assertRaisesRegex(BSLRuntimeError, "inspection failed: io_error"):
            interpreter.execute("InfoBaseConnectionString()")
        make_header_file(self.directory)
        self.assertEqual(interpreter.execute("InfoBaseConnectionString()"), self.expected)
        make_header_file(self.directory, magic=b"BADMAGIC")
        with self.assertRaisesRegex(BSLRuntimeError, "invalid_layout: bad_magic"):
            interpreter.execute("InfoBaseConnectionString()")
        make_header_file(self.directory)
        self.assertEqual(interpreter.execute("InfoBaseConnectionString()"), self.expected)

    def test_header_errors_are_catchable_and_do_not_echo_database_path(self):
        cases = (({"magic": b"BADMAGIC"}, "invalid_layout: bad_magic"),
                 ({"version": (8, 3, 9, 0)}, "unsupported_format: unknown_version"),
                 ({"pages": 2}, "policy_limit: minimum_pages"))
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                make_header_file(self.directory, **arguments)
                output = []
                interpreter = self.interpreter(self.context, output=output.append)
                interpreter.execute("Try InfoBaseConnectionString(); Except "
                                    "Message(ErrorDescription()); EndTry; Message(42);")
                self.assertIn(expected, output[0])
                self.assertNotIn(str(self.directory), output[0])
                self.assertEqual(output[1], "42")
        self.path.write_bytes(b"1C")
        with self.assertRaisesRegex(BSLRuntimeError, "invalid_layout: truncated_header"):
            self.interpreter(self.context).execute("InfoBaseConnectionString()")

    def test_unsupported_spelling_fails_lazily_without_echo_or_open(self):
        directories = ('private"path', "private;path", "private\npath", "private\x7fpath",
                       "private\x85path", "private\ud800path", r"\\server\share",
                       "//server/share", r"\\?\C:\private", r"\\.\C:\private")
        for directory in directories:
            with self.subTest(directory=directory), \
                 mock.patch.object(os, "open", side_effect=AssertionError("unexpected open")):
                context = FileDBContext(directory)
                interpreter = self.interpreter(context)
                self.assertEqual(interpreter.execute("21 * 2"), Decimal(42))
                with self.assertRaises(BSLRuntimeError) as caught:
                    interpreter.execute("InfoBaseConnectionString()")
                self.assertEqual(caught.exception.message, "unsupported file database directory")

    def test_windows_path_parsing_uses_native_semantics_and_rejects_drive_relative(self):
        # Pure ntpath rules are checked independently of this test machine.
        directory, unsupported = _normalize_directory(
            r"C:\Работа\temporary\..\Моя база\.", r"D:\Startup", windows=True)
        self.assertEqual(directory, "C:\\Работа\\Моя база")
        self.assertFalse(unsupported)
        directory, unsupported = _normalize_directory(
            r"temporary\..\Моя база", r"D:\Startup", windows=True)
        self.assertEqual(directory, "D:\\Startup\\Моя база")
        self.assertFalse(unsupported)
        for path in ("C:db", "D:db", "C:"):
            with self.subTest(path=path):
                self.assertTrue(_normalize_directory(path, r"D:\Startup", windows=True)[1])
        # Do not globally ban native POSIX paths merely because Windows paths
        # cannot be opened here. A colon is an ordinary POSIX filename character.
        self.assertEqual(_normalize_directory("C:db", "/startup", windows=False),
                         ("/startup/C:db", False))
        windows_path = r"C:\Работа\Моя база"
        if os.name != "nt":
            with mock.patch.object(os, "open", side_effect=AssertionError("unexpected open")):
                context = FileDBContext(windows_path)
                interpreter = self.interpreter(context)
                self.assertEqual(interpreter.execute("20 + 22"), Decimal(42))
                with self.assertRaises(BSLRuntimeError) as caught:
                    interpreter.execute("InfoBaseConnectionString()")
                self.assertEqual(caught.exception.message, "unsupported file database directory")
        else:
            for path in ("C:db", "C:"):
                with self.subTest(path=path), mock.patch.object(
                        os, "open", side_effect=AssertionError("unexpected open")):
                    context = FileDBContext(path)
                    with self.assertRaisesRegex(ValueError, "^unsupported file database directory$"):
                        context.connection_string()

    def test_nonzero_argument_calls_fail_before_header_inspection(self):
        for context in (None, self.context):
            interpreter = self.interpreter(context)
            for alias in ALIASES:
                with self.subTest(context=context, alias=alias), \
                     mock.patch("yadinassi.database_context.inspect_header") as inspect:
                    with self.assertRaises(BSLRuntimeError):
                        interpreter.execute(alias + "(1)")
                    inspect.assert_not_called()

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
        make_header_file(second_directory)
        second_context = FileDBContext(second_directory)
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
                                      (second, f'File="{second_directory}";'),
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


if __name__ == "__main__":
    unittest.main()
