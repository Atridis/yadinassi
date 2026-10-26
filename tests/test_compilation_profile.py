"""Explicit compilation contracts; these unit tests are not native evidence.

Every source fixture belongs to this test's resolved TemporaryDirectory. No
native installation, database fixture, capture, or external artifact is used.
"""

from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi import BSLError, BSLRuntimeError, Interpreter
from yadinassi.syntax import ast
from yadinassi.database_context import FileDBContext
from yadinassi.syntax import lexer as lexer_module
from yadinassi.syntax import parser as parser_module
from yadinassi import runtime as runtime_module
from yadinassi.syntax.lexer import Lexer
from yadinassi.native_targets import (
    LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, target_context,
)
from yadinassi.syntax.parser import parse, parse_expression, parse_fragment
from yadinassi.syntax.preprocessor import COMPILATION_PROFILES, ConditionalCompilation


SITES = ("client", "server", "server_nocontext", "dual_client", "dual_server")
OLD_ALIASES = (
    ("Client", "Клиент"), ("Server", "Сервер"),
    ("AtClient", "НаКлиенте"), ("AtServer", "НаСервере"),
)
FALSE_ALIASES = (
    ("ThinClient", "ТонкийКлиент"), ("WebClient", "ВебКлиент"),
    ("ThickClientOrdinaryApplication", "ТолстыйКлиентОбычноеПриложение"),
    ("ThickClientManagedApplication", "ТолстыйКлиентУправляемоеПриложение"),
    ("ExternalConnection", "ВнешнееСоединение"),
)
OLD_VALUES = {
    "client": (True, False, True, False),
    "server": (False, True, False, True),
    "server_nocontext": (False, True, False, False),
    "dual_client": (True, False, False, False),
    "dual_server": (False, True, False, False),
}


def weighted_body(language):
    lines = ["Result = 0;"]
    for position, aliases in enumerate(OLD_ALIASES + FALSE_ALIASES):
        lines.extend((f"#If {aliases[language]} Then",
                      f"Result = Result + {1 << position};", "#EndIf"))
    return "\n".join([*lines, "Return Result;"])


def weighted_program():
    declarations = []
    for name, annotation in (("Client", "&AtClient"), ("Server", "&AtServer"),
                             ("NoContext", "&AtServerNoContext"),
                             ("Dual", "&AtClientAtServerNoContext")):
        for language, suffix in enumerate(("En", "Ru")):
            declarations.append(f"{annotation}\nFunction {name}{suffix}()\n"
                                f"{weighted_body(language)}\nEndFunction")
    for suffix in ("En", "Ru"):
        declarations.append("&AtServer\nFunction ServerDual" + suffix + "()\n"
                            "Return Dual" + suffix + "();\nEndFunction")
    calls = [f"Message({name}{suffix}());" for name in
             ("Client", "Server", "NoContext", "Dual", "ServerDual")
             for suffix in ("En", "Ru")]
    return "\n".join(declarations + calls)


class CompilationProfileTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.vm = Interpreter(self.messages.append, compilation_profile="standalone")
        self.addCleanup(self.vm.close)

    def test_default_is_exact_standalone_and_public_property_is_read_only(self):
        default = Interpreter()
        self.addCleanup(default.close)
        self.assertEqual(default.compilation_profile, "standalone")
        self.assertEqual(default.execution_context, "client")
        self.assertEqual(default.native_target, WINDOWS_8_3_27_2342)
        for value in ("standalone", "native", {"Client": True}):
            with self.subTest(value=value), self.assertRaises(AttributeError):
                self.vm.compilation_profile = value
        with self.assertRaises(AttributeError):
            del self.vm.compilation_profile
        self.assertEqual(self.vm.compilation_profile, "standalone")
        lexer = Lexer("42", compilation_profile="standalone")
        with self.assertRaises(AttributeError):
            lexer.compilation_profile = "native"

    def test_only_exact_identifier_is_supported_at_every_public_entry(self):
        factories = (
            lambda value: Interpreter(compilation_profile=value),
            lambda value: parse("42", compilation_profile=value),
            lambda value: Lexer("42", compilation_profile=value).tokens(),
            lambda value: ConditionalCompilation("profile.bsl", compilation_profile=value),
        )
        for value in ("", "Standalone", "STANDALONE", " standalone", "standalone ",
                      "standalone\n", "auto", "client", "server", "thin-client", "native"):
            for factory in factories:
                with self.subTest(value=value, factory=factory), self.assertRaises(ValueError):
                    factory(value)
        for value in (None, True, 1, b"standalone", {}, {"Client": True},
                      {"compilation_profile": "standalone"}, ["standalone"]):
            for factory in factories:
                with self.subTest(value=value, factory=factory), self.assertRaises(TypeError):
                    factory(value)

    def test_profile_validation_does_not_call_custom_coercion_or_equality(self):
        class HostileString(str):
            def __str__(self):
                raise AssertionError("profile coercion")

            def __eq__(self, other):
                raise AssertionError("profile equality")

            __hash__ = str.__hash__

        for factory in (lambda value: Interpreter(compilation_profile=value),
                        lambda value: parse("42", compilation_profile=value),
                        lambda value: Lexer("42", compilation_profile=value).tokens(),
                        lambda value: ConditionalCompilation("p", compilation_profile=value)):
            with self.subTest(factory=factory), self.assertRaises(TypeError):
                factory(HostileString("standalone"))

    def test_all_aliases_and_case_variants_follow_exact_five_site_truth_table(self):
        for site in SITES:
            expected_values = OLD_VALUES[site] + (False,) * len(FALSE_ALIASES)
            for aliases, expected in zip(OLD_ALIASES + FALSE_ALIASES, expected_values):
                for alias in aliases:
                    for spelling in (alias, alias.lower(), alias.upper(), alias.swapcase()):
                        with self.subTest(site=site, symbol=spelling):
                            compilation = ConditionalCompilation(
                                "flags.bsl", site, compilation_profile="standalone")
                            self.assertIs(compilation.symbols[alias.casefold()], expected)
                            compilation.process(f"#If {spelling} Then", 1, 1)
                            self.assertIs(compilation.active, expected)
                            compilation.process("#Else", 2, 1)
                            self.assertIs(compilation.active, not expected)
                            compilation.process("#EndIf", 3, 1)
                            compilation.finish(4, 1)

    def test_profile_truth_maps_are_read_only_and_do_not_cross_contaminate(self):
        for site in SITES:
            compilation = ConditionalCompilation("flags", site, compilation_profile="standalone")
            with self.subTest(site=site), self.assertRaises(TypeError):
                compilation.symbols["thinclient"] = True
            with self.assertRaises(TypeError):
                del compilation.symbols["client"]
            with self.assertRaises(AttributeError):
                compilation.symbols = {"thinclient": True}
            with self.assertRaises(AttributeError):
                compilation.compilation_profile = "native"
            fresh = ConditionalCompilation("fresh", site, compilation_profile="standalone")
            self.assertFalse(fresh.symbols["thinclient"])
            self.assertEqual(fresh.symbols["client"], OLD_VALUES[site][0])

    def test_weighted_bilingual_signature_covers_all_runtime_variants(self):
        self.vm.execute(weighted_program(), "synthetic-profile.bsl")
        signature = "pp.v1:" + "".join(f"{int(value):03d}" for value in self.messages)
        self.assertEqual(signature, "pp.v1:005005010010002002001001002002")
        self.assertEqual(self.vm.execution_context, "client")
        self.assertEqual(self.vm.compilation_profile, "standalone")

    def test_default_and_explicit_profile_select_identical_ast(self):
        source = weighted_program()
        self.assertEqual(parse(source), parse(source, compilation_profile="standalone"))

    def test_known_false_aliases_exclude_invalid_bsl_and_missing_imports(self):
        for aliases in FALSE_ALIASES:
            for alias in aliases:
                with self.subTest(alias=alias):
                    source = (f"#If {alias} Then\ninvalid !!! syntax \"\n"
                              "// #Import Missing.bsl\n#If Client Then\ninvalid ???\n#EndIf\n"
                              f"#ElsIf Not {alias} Then\n"
                              "#If ThinClient Or WebClient Then\n'not a date\n"
                              "#Else\n42\n#EndIf\n#Else\ninvalid !!!\n#EndIf")
                    self.assertEqual(self.vm.execute(source), Decimal(42))
        self.assertEqual(self.vm.imports, {})

    def test_false_symbols_exclude_invalid_bodies_in_server_nocontext_and_dual(self):
        for annotation in ("&AtClient", "&AtServer", "&AtServerNoContext",
                           "&AtClientAtServerNoContext"):
            condition = " Or ".join(aliases[0] for aliases in FALSE_ALIASES)
            source = (f"{annotation}\nFunction Chosen()\n#If {condition} Then\n"
                      "invalid !!! syntax \"\nFunction Unfinished(\n"
                      "// #Import Missing.bsl\n#Else\nReturn 42;\n#EndIf\nEndFunction")
            with self.subTest(annotation=annotation):
                routines = [node for node in parse(source, compilation_profile="standalone")
                            if isinstance(node, ast.Routine)]
                self.assertEqual(len(routines), 2 if "ClientAtServer" in annotation else 1)
                self.assertTrue(all(node.body[0].value.value == Decimal(42) for node in routines))

    def test_unknown_symbols_are_validated_even_when_excluded_or_not_short_circuited(self):
        unknowns = ("UnknownProfileFlag", "MobileClient", "МобильныйКлиент",
                    "MobileServer", "МобильныйСервер", "MobileAppClient", "MobileAppServer",
                    "AtClientAtServer", "НаКлиентеНаСервере", "AtServerNoContext",
                    "AtClientAtServerNoContext", "dual_client", "dual_server")
        for unknown in unknowns:
            for condition in (unknown, f"Client Or {unknown}", f"ThinClient And {unknown}"):
                for wrapper in ("{body}", "#If ThinClient Then\n{body}\n#EndIf",
                                "#If Client Then\n42\n#ElsIf {condition} Then\n#EndIf"):
                    body = f"#If {condition} Then\n42\n#EndIf"
                    source = 'Message("must-not-run");\n' + wrapper.format(
                        body=body, condition=condition)
                    with self.subTest(symbol=unknown, condition=condition, wrapper=wrapper), \
                            self.assertRaisesRegex(BSLError, "Неподдерживаемый символ"):
                        self.vm.execute(source, "unknown-profile.bsl")
        self.assertEqual(self.messages, [])

    def test_unknown_in_each_execution_body_precedes_root_effects(self):
        for annotation in ("&AtClient", "&AtServer", "&AtServerNoContext",
                           "&AtClientAtServerNoContext"):
            source = ('Message("must-not-run");\n' + annotation + "\nFunction F()\n"
                      "#If ThinClient Then\n#If UnknownProfileFlag Then\n"
                      "Return 1;\n#EndIf\n#EndIf\nReturn 42;\nEndFunction")
            with self.subTest(annotation=annotation), self.assertRaises(BSLError):
                self.vm.execute(source)
        self.assertEqual(self.messages, [])

    def test_parse_explicitly_passes_profile_to_all_five_lexers(self):
        with mock.patch.object(parser_module, "Lexer", wraps=Lexer) as constructor:
            parse(weighted_program(), compilation_profile="standalone")
        self.assertEqual(len(constructor.call_args_list), 5)
        self.assertEqual([call.kwargs.get("execution_context", "client")
                          for call in constructor.call_args_list], list(SITES))
        for call in constructor.call_args_list:
            self.assertEqual(call.kwargs.get("compilation_profile"), "standalone")

    def test_lexers_explicitly_pass_profile_to_root_and_skipped_compilations(self):
        with mock.patch.object(lexer_module, "ConditionalCompilation",
                               wraps=ConditionalCompilation) as constructor:
            parse(weighted_program(), compilation_profile="standalone")
        self.assertGreater(len(constructor.call_args_list), 10)
        observed = set()
        for call in constructor.call_args_list:
            self.assertEqual(call.kwargs.get("compilation_profile"), "standalone")
            observed.add(call.args[1] if len(call.args) > 1 else call.kwargs["execution_context"])
        self.assertEqual(observed, set(SITES))

    def test_interpreter_execute_explicitly_passes_profile_to_parse(self):
        with mock.patch.object(runtime_module, "parse", wraps=parse) as parser:
            self.assertEqual(self.vm.execute("6 * 7"), Decimal(42))
        self.assertEqual(parser.call_count, 1)
        self.assertEqual(parser.call_args.kwargs.get("compilation_profile"), "standalone")

    def test_execute_program_consumes_already_compiled_ast_without_recompiling(self):
        program = parse("#If ThinClient Then\n0\n#Else\n42\n#EndIf",
                        compilation_profile="standalone")
        with mock.patch.object(runtime_module, "parse",
                               side_effect=AssertionError("unexpected recompile")) as parser:
            self.assertEqual(self.vm.execute_program(program), Decimal(42))
        parser.assert_not_called()

    def test_imports_and_new_server_activations_explicitly_inherit_profile(self):
        with tempfile.TemporaryDirectory(prefix="compilation-profile-") as temporary:
            root = Path(temporary).resolve()
            leaf = root / "Leaf.bsl"
            leaf.write_text("&AtServer\nFunction ServerValue() Export\n"
                            + weighted_body(0) + "\nEndFunction\n"
                            "&AtServerNoContext\nFunction NoContextValue() Export\n"
                            + weighted_body(1) + "\nEndFunction\n"
                            "#If ExternalConnection Then\ninvalid !!!\n#EndIf\n",
                            encoding="utf-8")
            (root / "Middle.bsl").write_text(
                "// #Import Leaf.bsl\nFunction Value() Export\n"
                "Return Leaf.ServerValue() + Leaf.NoContextValue();\nEndFunction\n",
                encoding="utf-8")
            original_init = Interpreter.__init__
            with mock.patch.object(Interpreter, "__init__", autospec=True,
                                   side_effect=original_init) as constructor:
                self.vm.execute("// #Import Middle.bsl\nMessage(Middle.Value());",
                                str(root / "Main.bsl"))
                for has_context in (True, False):
                    server = self.vm._new_server_activation(module_context=has_context)
                    self.assertEqual(server.compilation_profile, "standalone")
            self.assertGreaterEqual(constructor.call_count, 6)
            for call in constructor.call_args_list:
                self.assertEqual(call.kwargs.get("compilation_profile"), "standalone")
            middle = self.vm.imports["middle"].interpreter
            self.assertEqual(middle.compilation_profile, "standalone")
            self.assertEqual(middle.imports["leaf"].interpreter.compilation_profile, "standalone")
            self.assertEqual(self.messages, ["12"])

    def test_invalid_imported_condition_does_not_execute_module_or_root_effects(self):
        with tempfile.TemporaryDirectory(prefix="compilation-profile-") as temporary:
            root = Path(temporary).resolve()
            leaf = root / "Leaf.bsl"
            leaf.write_text('Message("must-not-run-leaf");\n#If ThinClient Then\n'
                            "#If MobileClient Then\n#EndIf\n#EndIf\n", encoding="utf-8")
            with self.assertRaises(BSLError) as caught:
                self.vm.execute('// #Import Leaf.bsl\nMessage("must-not-run-root");',
                                str(root / "Main.bsl"))
            self.assertEqual((caught.exception.source, caught.exception.line), (str(leaf), 3))
        self.assertEqual(self.messages, [])

    def test_native_target_environment_and_host_os_cannot_select_platform_flags(self):
        environment = {"YADINASSI_PREPROCESSOR_PROFILE": "native",
                       "YADINASSI_COMPILATION_PROFILE": "native", "COMPILATION_PROFILE": "native"}
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            for host in ("win32", "linux", "darwin"):
                with self.subTest(target=target, host=host), \
                        mock.patch.dict(os.environ, environment), \
                        mock.patch("sys.platform", host), \
                        mock.patch("platform.system", return_value=host), target_context(target):
                    messages = []
                    interpreter = Interpreter(messages.append, native_target=target)
                    self.addCleanup(interpreter.close)
                    interpreter.execute(weighted_program())
                    self.assertEqual(interpreter.compilation_profile, "standalone")
                    self.assertEqual(interpreter.native_target, target)
                    self.assertEqual(messages, ["5", "5", "10", "10", "2", "2",
                                                "1", "1", "2", "2"])

    def test_dynamic_eval_execute_still_reject_preprocessor_directives_before_effects(self):
        for symbol in ("Client", "ThinClient", "ВнешнееСоединение", "UnknownProfileFlag"):
            text = f"#If {symbol} Then\n42\n#Else\n0\n#EndIf"
            for parser in (parse_expression, parse_fragment):
                with self.subTest(symbol=symbol, parser=parser.__name__), self.assertRaises(BSLError):
                    parser(text)
            self.vm.variables["code"] = text
            with self.subTest(symbol=symbol, dynamic="Eval"), self.assertRaises(BSLError):
                self.vm.execute("Eval(code)")
            self.vm.variables["code"] = 'Message("must-not-run");\n' + text
            with self.subTest(symbol=symbol, dynamic="Execute"), self.assertRaises(BSLError):
                self.vm.execute("Execute(code);")
        self.assertEqual(self.messages, [])


MANAGED_PROFILE = "managed-thick-file"
MANAGED_VALUES = {
    "client": (True, True, True, False),
    "server": (True, True, False, True),
    "server_nocontext": (True, True, False, False),
    "dual_client": (True, True, False, False),
    "dual_server": (True, True, False, False),
}


class ManagedCompilationProfileTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.vm = Interpreter(self.messages.append, compilation_profile=MANAGED_PROFILE)
        self.addCleanup(self.vm.close)

    def test_exact_public_identifier_and_read_only_properties(self):
        self.assertEqual(COMPILATION_PROFILES, ("standalone", MANAGED_PROFILE))
        for factory in (lambda name: Interpreter(compilation_profile=name),
                        lambda name: Lexer("42", compilation_profile=name),
                        lambda name: ConditionalCompilation("profile", compilation_profile=name)):
            obj = factory(MANAGED_PROFILE)
            if isinstance(obj, Interpreter):
                self.addCleanup(obj.close)
            self.assertEqual(obj.compilation_profile, MANAGED_PROFILE)
            with self.assertRaises(AttributeError):
                obj.compilation_profile = "standalone"
            with self.assertRaises(AttributeError):
                del obj.compilation_profile
            for invalid in ("Managed-Thick-File", "MANAGED-THICK-FILE", "managed_thick_file",
                            "managed-thick", "managed-thick-file ", " managed-thick-file"):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    factory(invalid)
        self.assertEqual(parse("42", compilation_profile=MANAGED_PROFILE), parse("42"))

    def test_bilingual_case_insensitive_truth_table_and_immutable_isolation(self):
        for site in SITES:
            expected_values = MANAGED_VALUES[site] + (False, False, False, True, False)
            for aliases, expected in zip(OLD_ALIASES + FALSE_ALIASES, expected_values):
                for alias in aliases:
                    for spelling in (alias, alias.lower(), alias.upper(), alias.swapcase()):
                        with self.subTest(site=site, symbol=spelling):
                            compilation = ConditionalCompilation(
                                "flags", site, compilation_profile=MANAGED_PROFILE)
                            self.assertIs(compilation.symbols[alias.casefold()], expected)
                            compilation.process(f"#If {spelling} Then", 1, 1)
                            self.assertIs(compilation.active, expected)
                            compilation.process("#Else", 2, 1)
                            self.assertIs(compilation.active, not expected)
                            compilation.process("#EndIf", 3, 1)
                            compilation.finish(4, 1)
            with self.assertRaises(TypeError):
                compilation.symbols["server"] = False
            with self.assertRaises(TypeError):
                del compilation.symbols["client"]
            with self.assertRaises(AttributeError):
                compilation.symbols = {}
            standalone = ConditionalCompilation("old", site)
            self.assertEqual(tuple(standalone.symbols[aliases[0].casefold()]
                                   for aliases in OLD_ALIASES), OLD_VALUES[site])
            self.assertTrue(all(not standalone.symbols[alias.casefold()]
                                for aliases in FALSE_ALIASES for alias in aliases))

    def test_ordinary_mixed_client_server_conditions_use_profile_at_every_site(self):
        conditions = (
            ("Client And Server", True), ("Client Or Server", True),
            ("Not Client Or Not Server", False), ("Client And Not Server", False),
            ("Not Client And Server", False), ("Not (Client And Server)", False),
            ("ThinClient Or Client And Server", True),
            ("(ThinClient Or Client) And Not WebClient And Server", True),
            ("Клиент И Сервер И Не ВнешнееСоединение", True),
            ("Не Клиент Или Не Сервер", False),
        )
        for condition, expected in conditions:
            for annotation in ("&AtClient", "&AtServer", "&AtServerNoContext",
                               "&AtClientAtServerNoContext"):
                source = (f"{annotation}\nFunction Chosen()\n#If {condition} Then\n"
                          "Return 42;\n#Else\nReturn 0;\n#EndIf\nEndFunction")
                with self.subTest(condition=condition, annotation=annotation):
                    routines = [node for node in parse(source, compilation_profile=MANAGED_PROFILE)
                                if isinstance(node, ast.Routine)]
                    self.assertEqual(len(routines), 2 if "ClientAtServer" in annotation else 1)
                    self.assertTrue(all(node.body[0].value.value == Decimal(42 if expected else 0)
                                        for node in routines))
        self.assertEqual(self.vm.execute("#If Server Then\n#If Client Then\n42\n"
                                         "#Else\ninvalid !!!\n#EndIf\n#Else\ninvalid !!!\n#EndIf"),
                         Decimal(42))

    def test_first_true_branch_wins_when_client_and_server_are_both_true(self):
        for first, second in (("Client", "Server"), ("Server", "Client")):
            with self.subTest(first=first):
                self.assertEqual(self.vm.execute(f"#If {first} Then\n42\n#ElsIf {second} Then\n"
                                                  "invalid !!!\n#Else\ninvalid !!!\n#EndIf"),
                                 Decimal(42))

    def test_profile_reaches_all_passes_and_skipped_routine_compilations(self):
        with mock.patch.object(parser_module, "Lexer", wraps=Lexer) as lexers, \
                mock.patch.object(lexer_module, "ConditionalCompilation",
                                  wraps=ConditionalCompilation) as compilations:
            parse(weighted_program(), compilation_profile=MANAGED_PROFILE)
        self.assertEqual([call.kwargs.get("execution_context", "client")
                          for call in lexers.call_args_list], list(SITES))
        self.assertGreater(compilations.call_count, 10)
        observed = set()
        for call in lexers.call_args_list + compilations.call_args_list:
            self.assertEqual(call.kwargs.get("compilation_profile"), MANAGED_PROFILE)
        for call in compilations.call_args_list:
            observed.add(call.args[1] if len(call.args) > 1 else call.kwargs["execution_context"])
        self.assertEqual(observed, set(SITES))
        for annotation in ("&AtClient", "&AtServer", "&AtServerNoContext",
                           "&AtClientAtServerNoContext"):
            source = (f"{annotation}\nFunction Chosen()\n#If Not (Client And Server) Then\n"
                      "invalid !!! syntax \"\nFunction Unfinished(\n// #Import Missing.bsl\n"
                      "#ElsIf ThickClientManagedApplication Then\nReturn 42;\n"
                      "#Else\ninvalid !!!\n#EndIf\nEndFunction")
            with self.subTest(annotation=annotation):
                routines = [node for node in parse(source, compilation_profile=MANAGED_PROFILE)
                            if isinstance(node, ast.Routine)]
                self.assertEqual(len(routines), 2 if "ClientAtServer" in annotation else 1)
                self.assertTrue(all(node.body[0].value.value == Decimal(42) for node in routines))

    def test_weighted_runtime_signature_and_unchanged_measurement_core(self):
        self.vm.execute(weighted_program())
        self.assertEqual(self.messages, ["135", "135", "139", "139", "131", "131",
                                        "131", "131", "131", "131"])
        self.messages.clear()
        core = Path(__file__).resolve().parents[1] / (
            "integrational_tests/directive_probes/preprocessor_profiles_core.bsl")
        # Execute the immutable original source, then an ordinary caller. There
        # is no source rewrite or replacement implementation of its routines.
        self.vm.execute(core.read_text(encoding="utf-8"), str(core))
        self.vm.execute("Records = New Array; PPAppend(Records); Message(Records[0]);")
        self.assertEqual(self.messages, ["pp.v1:135135139139131131131131131131"])
        self.assertEqual(self.vm.execution_context, "client")

    def test_nested_imports_and_context_and_nocontext_activations_inherit_profile(self):
        with tempfile.TemporaryDirectory(prefix="managed-compilation-profile-") as temporary:
            root = Path(temporary).resolve()
            (root / "Leaf.bsl").write_text(
                "#If Not (Client And Server And ThickClientManagedApplication) Then\n"
                "invalid !!!\n#EndIf\n&AtServer\nFunction ServerValue() Export\n"
                + weighted_body(0) + "\nEndFunction\n"
                "&AtServerNoContext\nFunction NoContextValue() Export\n"
                + weighted_body(1) + "\nEndFunction\n", encoding="utf-8")
            (root / "Middle.bsl").write_text(
                "// #Import Leaf.bsl\nFunction Value() Export\n"
                "Return Leaf.ServerValue() + Leaf.NoContextValue();\nEndFunction\n",
                encoding="utf-8")
            original_init = Interpreter.__init__
            with mock.patch.object(Interpreter, "__init__", autospec=True,
                                   side_effect=original_init) as constructor:
                self.vm.execute("// #Import Middle.bsl\nMessage(Middle.Value());",
                                str(root / "Main.bsl"))
                for has_context in (True, False):
                    server = self.vm._new_server_activation(module_context=has_context)
                    self.assertEqual(server.compilation_profile, MANAGED_PROFILE)
            self.assertGreaterEqual(constructor.call_count, 6)
            for call in constructor.call_args_list:
                self.assertEqual(call.kwargs.get("compilation_profile"), MANAGED_PROFILE)
            middle = self.vm.imports["middle"].interpreter
            self.assertEqual(middle.compilation_profile, MANAGED_PROFILE)
            self.assertEqual(middle.imports["leaf"].interpreter.compilation_profile, MANAGED_PROFILE)
            self.assertEqual(self.messages, ["270"])

    def test_explicit_profile_and_native_target_are_independent_of_host_and_environment(self):
        environment = {"YADINASSI_PREPROCESSOR_PROFILE": MANAGED_PROFILE,
                       "YADINASSI_COMPILATION_PROFILE": MANAGED_PROFILE,
                       "COMPILATION_PROFILE": MANAGED_PROFILE}
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            for host in ("win32", "linux", "darwin"):
                with self.subTest(target=target, host=host), \
                        mock.patch.dict(os.environ, environment), \
                        mock.patch("sys.platform", host), target_context(target):
                    default = Interpreter(native_target=target)
                    managed = Interpreter(native_target=target, compilation_profile=MANAGED_PROFILE)
                    self.addCleanup(default.close)
                    self.addCleanup(managed.close)
                    self.assertEqual(default.compilation_profile, "standalone")
                    for vm in (default, managed):
                        self.assertEqual(vm.native_target, target)
                        self.assertEqual(vm.execution_context, "client")
                    source = "#If Client And Server Then\n42\n#Else\n5\n#EndIf"
                    self.assertEqual(default.execute(source), Decimal(5))
                    self.assertEqual(managed.execute(source), Decimal(42))
        self.assertEqual(self.vm.native_target, WINDOWS_8_3_27_2342)

    def test_profile_never_changes_dispatch_or_turns_server_symbol_into_runtime_side(self):
        seen = []
        self.vm.register_function("Observe", lambda: seen.append(
            (self.vm.execution_context, self.vm._has_module_context)))
        self.vm.execute('''
#If Server Then
Function Ordinary() Return 42; EndFunction
Observe();
#EndIf
&AtClientAtServerNoContext
Function Dual()
Observe();
#If Client And Server Then
Return "both";
#Else
Return "wrong";
#EndIf
EndFunction
&AtServer
Function ServerCall() R = Dual(); Observe(); Return R; EndFunction
&AtServerNoContext
Function Detached() R = Dual(); Observe(); Return R; EndFunction
Message(Dual()); Message(ServerCall()); Message(Detached());
''')
        self.assertEqual(self.messages, ["both", "both", "both"])
        self.assertEqual(seen, [("client", True), ("client", False), ("server", False),
                               ("server", True), ("server", False), ("server", False)])
        self.assertEqual(self.vm.routines["ordinary"].execution_context, "client")
        self.assertNotIn("ordinary", self.vm.server_routines)
        self.assertEqual(self.vm._context_stack, ["client"])
        self.assertEqual(self.vm._module_context_stack, [True])
        self.vm.execute("&AtServer\nFunction Denied() Return Ordinary(); EndFunction")
        with self.assertRaisesRegex(BSLError, "клиентской подпрограммы с сервера"):
            self.vm.execute("Denied()")

    def test_database_context_and_builtin_availability_are_not_selected_by_profile(self):
        with tempfile.TemporaryDirectory(prefix="managed-profile-db-") as temporary:
            context = FileDBContext(Path(temporary) / "missing-unused-base")
            for db in (None, context):
                standalone = Interpreter(database_context=db)
                managed = Interpreter(database_context=db, compilation_profile=MANAGED_PROFILE)
                self.addCleanup(standalone.close)
                self.addCleanup(managed.close)
                self.assertIs(managed.database_context, db)
                self.assertEqual(set(managed.functions), set(standalone.functions))
                self.assertEqual(set(managed.types), set(standalone.types))
                with self.assertRaises(AttributeError):
                    managed.database_context = None
                for has_context in (True, False):
                    server = managed._new_server_activation(module_context=has_context)
                    self.assertIs(server.database_context, db)
                    self.assertEqual(server.native_target, managed.native_target)
                self.assertEqual(managed.execute("42"), Decimal(42))
        self.assertIsNone(self.vm.database_context)
        with self.assertRaisesRegex(BSLRuntimeError, "db required for further code execution"):
            self.vm.execute("InfoBaseConnectionString()")
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute("New Form")

    def test_unknown_and_combined_side_symbols_still_fail_before_effects(self):
        for unknown in ("UnknownProfileFlag", "MobileClient", "AtClientAtServer",
                        "ClientAtServer", "НаКлиентеНаСервере", "КлиентНаСервере"):
            for condition in (unknown, f"Client Or {unknown}", f"ThinClient And {unknown}"):
                for annotation in ("&AtClient", "&AtServer", "&AtServerNoContext",
                                   "&AtClientAtServerNoContext"):
                    source = (f'Message("must-not-run");\n{annotation}\nFunction F()\n'
                              f"#If ThinClient Then\n#If {condition} Then\n"
                              "Return 0;\n#EndIf\n#EndIf\nReturn 42;\nEndFunction")
                    with self.subTest(condition=condition, annotation=annotation), \
                            self.assertRaisesRegex(BSLError, "Неподдерживаемый символ"):
                        self.vm.execute(source)
        self.assertEqual(self.messages, [])

    def test_execute_program_keeps_parse_time_profile_and_dynamic_directives_stay_forbidden(self):
        source = "#If Client And Server Then\n42\n#Else\n5\n#EndIf"
        for compilation_profile, expected in (("standalone", 5), (MANAGED_PROFILE, 42)):
            program = parse(source, compilation_profile=compilation_profile)
            with mock.patch.object(runtime_module, "parse",
                                   side_effect=AssertionError("unexpected recompile")):
                self.assertEqual(self.vm.execute_program(program), Decimal(expected))
        self.vm.variables["code"] = source
        for call in ("Eval(code)", "Execute(code);"):
            with self.subTest(call=call), self.assertRaises(BSLError):
                self.vm.execute(call)


if __name__ == "__main__":
    unittest.main()
