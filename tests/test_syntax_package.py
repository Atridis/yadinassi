"""Canonical frontend imports and the intentionally narrow legacy shims."""

import ast
import importlib
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
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)], cwd=ROOT,
            env=environment, capture_output=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_legacy_exports_are_the_same_objects(self):
        for name, exports in EXPORTS.items():
            legacy = importlib.import_module(f"yadinassi.{name}")
            canonical = importlib.import_module(f"yadinassi.syntax.{name}")
            with self.subTest(module=name):
                self.assertIsNot(legacy, canonical)
                self.assertEqual(set(legacy.__all__), set(exports))
            for symbol in exports:
                with self.subTest(module=name, symbol=symbol):
                    self.assertIs(getattr(legacy, symbol), getattr(canonical, symbol))

    def test_every_public_frontend_definition_has_a_legacy_export(self):
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

    def test_fresh_process_import_orders_preserve_symbol_identity(self):
        for name in MODULES:
            for legacy_first in (False, True):
                names = [f"yadinassi.syntax.{name}", f"yadinassi.{name}"]
                if legacy_first:
                    names.reverse()
                with self.subTest(module=name, legacy_first=legacy_first):
                    self.run_python(f"""
                        import importlib
                        first = importlib.import_module({names[0]!r})
                        second = importlib.import_module({names[1]!r})
                        assert first is not second
                        for symbol in {EXPORTS[name]!r}:
                            assert getattr(first, symbol) is getattr(second, symbol), symbol
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

    def test_legacy_symbol_imports_produce_canonical_nodes_and_tokens(self):
        self.run_python("""
            from yadinassi import ast
            from yadinassi.lexer import Lexer, Token
            from yadinassi.parser import Parser, parse, parse_expression, parse_fragment
            from yadinassi.preprocessor import ConditionalCompilation, SourceRegions
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
