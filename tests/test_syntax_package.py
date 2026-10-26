"""Canonical frontend identities and retired root-module imports."""

import ast
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULES = ("ast", "lexer", "parser", "preprocessor")
EXPORTS = {
    "ast": (
        "Node", "Literal", "OmittedArgument", "Name", "Group", "Unary", "Await",
        "Binary", "Conditional", "Attribute", "Index", "Call", "New", "DynamicNew",
        "Assign", "ExpressionStatement", "If", "For", "ForEach", "While", "Break",
        "Continue", "Var", "ServerInitializer", "Parameter", "Routine", "Return",
        "Import", "Try", "Raise", "Label", "Goto", "Execute", "Token",
    ),
    "lexer": ("KEYWORDS", "EXECUTION_DIRECTIVES", "Token", "Lexer"),
    "parser": (
        "PRECEDENCE", "Parser", "validate_async", "validate_labels", "parse",
        "parse_expression", "parse_fragment",
    ),
    "preprocessor": (
        "DIRECTIVES", "COMPILATION_PROFILES", "validate_compilation_profile",
        "OPERATORS", "REGION_DIRECTIVES", "ConditionalCompilation", "SourceRegions",
    ),
}


class SyntaxPackageTests(unittest.TestCase):
    def run_python(self, source):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(ROOT), environment.get("PYTHONPATH")]))
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-B", "-c", textwrap.dedent(source)], cwd=ROOT,
            env=environment, capture_output=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_canonical_package_and_symbol_imports_are_the_same_objects(self):
        package = importlib.import_module("yadinassi.syntax")
        for name, exports in EXPORTS.items():
            canonical = importlib.import_module(f"yadinassi.syntax.{name}")
            namespace = {}
            exec(f"from yadinassi.syntax.{name} import " + ", ".join(exports), namespace)
            with self.subTest(module=name):
                self.assertIs(getattr(package, name), canonical)
            for symbol in exports:
                with self.subTest(module=name, symbol=symbol):
                    self.assertIs(namespace[symbol], getattr(canonical, symbol))

    def test_retired_module_specs_and_imports_are_absent(self):
        for name in EXPORTS:
            with self.subTest(module=name):
                self.run_python(f"""
                    import importlib
                    import importlib.util
                    import sys
                    retired = "yadinassi." + {name!r}
                    assert importlib.util.find_spec(retired) is None, retired
                    try:
                        importlib.import_module(retired)
                    except ModuleNotFoundError as error:
                        assert error.name == retired, error.name
                    else:
                        raise AssertionError("Retired module imported: " + retired)
                    assert retired not in sys.modules
                """)

    def test_retired_root_attribute_imports_are_absent(self):
        for name in EXPORTS:
            with self.subTest(module=name):
                self.run_python(f"""
                    import yadinassi
                    name = {name!r}
                    assert not hasattr(yadinassi, name), name
                    try:
                        exec("from yadinassi import " + name, {{}})
                    except ImportError as error:
                        assert type(error) is ImportError, type(error)
                        assert error.name == "yadinassi", error.name
                    else:
                        raise AssertionError("Retired root import succeeded: " + name)
                    assert not hasattr(yadinassi, name), name
                """)

    def test_every_public_frontend_definition_is_covered(self):
        for name, exports in EXPORTS.items():
            source = ROOT / "yadinassi" / "syntax" / f"{name}.py"
            definitions = set()
            for node in ast.parse(source.read_text(encoding="utf-8")).body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    definitions.add(node.name)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    definitions.update(target.id for target in targets
                                       if isinstance(target, ast.Name))
            with self.subTest(module=name):
                self.assertLessEqual({name for name in definitions if not name.startswith("_")},
                                     set(exports))

    def test_package_marker_is_nonempty_and_has_no_eager_imports(self):
        source = (ROOT / "yadinassi" / "syntax" / "__init__.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        self.assertTrue(ast.get_docstring(module))
        self.assertEqual(len(module.body), 1)

    def test_live_python_sources_have_no_retired_imports(self):
        retired_names = set(MODULES) | {
            "math_conversion", "binary_exp", "powers", "elementary",
            "bits", "numbers", "round_modes",
        }
        retired_modules = {"yadinassi." + name for name in retired_names}
        paths = sorted((ROOT / "yadinassi").rglob("*.py"))
        paths += sorted((ROOT / "scripts").rglob("*.py"))
        paths += sorted((ROOT / "tests").glob("test*.py"))
        violations = []
        for path in paths:
            relative = path.relative_to(ROOT)
            package = ".".join(relative.with_suffix("").parts[:-1])
            if path.name == "__init__.py":
                package = ".".join(relative.parent.parts)
            pending = [ast.parse(path.read_text(encoding="utf-8-sig"))]
            snippets = set()
            while pending:
                for node in ast.walk(pending.pop()):
                    imported = []
                    if isinstance(node, ast.Import):
                        imported = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if node.level:
                            module = importlib.util.resolve_name("." * node.level + module,
                                                                 package)
                        imported = [module] + [module + "." + alias.name
                                               for alias in node.names]
                    elif isinstance(node, ast.Call) and node.args:
                        function = node.func
                        name = (function.attr if isinstance(function, ast.Attribute) else
                                function.id if isinstance(function, ast.Name) else None)
                        if name in ("import_module", "__import__"):
                            argument = node.args[0]
                            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                                imported = [argument.value]
                    for module in imported:
                        if any(module == retired or module.startswith(retired + ".")
                               for retired in retired_modules):
                            violations.append((relative.as_posix(), node.lineno, module))

                    # Also inspect literal subprocess/exec programs. Negative
                    # import tests construct names deliberately at runtime; no
                    # entire test file, production path, or fixture is exempted.
                    source = None
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        source = node.value
                    elif isinstance(node, ast.JoinedStr):
                        source = "".join(value.value if isinstance(value, ast.Constant)
                                         else "__dynamic_value__" for value in node.values)
                    if source and "import" in source and source not in snippets:
                        snippets.add(source)
                        try:
                            pending.append(ast.parse(textwrap.dedent(source)))
                        except SyntaxError:
                            pass
        self.assertEqual(violations, [])

    def test_fresh_process_import_orders_preserve_symbol_identity(self):
        # The root initializer is eager: these are requested-import orders,
        # not claims that leaf modules initialize before the root package.
        for name, exports in EXPORTS.items():
            for consumer_first in (False, True):
                names = [f"yadinassi.syntax.{name}", "yadinassi.runtime"]
                if consumer_first:
                    names.reverse()
                with self.subTest(module=name, consumer_first=consumer_first):
                    self.run_python(f"""
                        import importlib
                        importlib.import_module({names[0]!r})
                        importlib.import_module({names[1]!r})
                        canonical = importlib.import_module("yadinassi.syntax." + {name!r})
                        package = importlib.import_module("yadinassi.syntax")
                        assert getattr(package, {name!r}) is canonical
                        namespace = {{}}
                        exec("from yadinassi.syntax." + {name!r} + " import " +
                             ", ".join({exports!r}), namespace)
                        for symbol in {exports!r}:
                            assert namespace[symbol] is getattr(canonical, symbol), symbol
                    """)

    def test_public_embedding_import_does_not_load_legacy_shims(self):
        self.run_python("""
            import sys
            import yadinassi
            from yadinassi.errors import BSLError, BSLRuntimeError
            from yadinassi.runtime import Interpreter
            assert yadinassi.__all__ == ["BSLError", "BSLRuntimeError", "Interpreter"]
            assert yadinassi.Interpreter is Interpreter
            assert yadinassi.BSLError is BSLError
            assert yadinassi.BSLRuntimeError is BSLRuntimeError
            assert isinstance(yadinassi.__version__, str) and yadinassi.__version__
            assert Interpreter().execute("6 * 7") == 42
            for name in ("ast", "lexer", "parser", "preprocessor"):
                assert "yadinassi.syntax." + name in sys.modules
                assert "yadinassi." + name not in sys.modules
        """)

    def test_canonical_symbol_imports_produce_canonical_nodes_and_tokens(self):
        self.run_python("""
            from yadinassi.syntax import ast
            from yadinassi.syntax.lexer import Lexer, Token
            from yadinassi.syntax.parser import Parser, parse, parse_expression, parse_fragment
            from yadinassi.syntax.preprocessor import ConditionalCompilation, SourceRegions
            from yadinassi.syntax import ast as canonical_ast
            from yadinassi.syntax import lexer, parser, preprocessor
            assert Parser is parser.Parser
            assert Lexer is lexer.Lexer and Token is lexer.Token
            assert ConditionalCompilation is preprocessor.ConditionalCompilation
            assert SourceRegions is preprocessor.SourceRegions
            assert ast.Token is Token
            expression = parse_expression("6 * 7")
            assert type(expression) is canonical_ast.Binary
            assert isinstance(expression, ast.Binary)
            assert type(expression.token) is Token
            for parse_source in (parse, parse_fragment):
                node, = parse_source("answer = 42;")
                assert type(node) is canonical_ast.Assign
                assert isinstance(node, ast.Assign)
        """)

    def test_production_consumers_use_canonical_frontend(self):
        from yadinassi import cli, runtime
        from yadinassi.syntax import ast, lexer, parser, preprocessor

        self.assertIs(runtime.ast, ast)
        for name in ("parse", "parse_expression", "parse_fragment", "validate_async",
                     "validate_labels"):
            self.assertIs(getattr(runtime, name), getattr(parser, name))
        self.assertIs(runtime.KEYWORDS, lexer.KEYWORDS)
        self.assertIs(runtime.validate_compilation_profile,
                      preprocessor.validate_compilation_profile)
        self.assertIs(cli.parse, parser.parse)
        self.assertIs(cli.COMPILATION_PROFILES, preprocessor.COMPILATION_PROFILES)


if __name__ == "__main__":
    unittest.main()
