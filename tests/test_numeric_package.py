"""Canonical math imports and the intentionally narrow legacy shims."""

import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = {
    "math_conversion": ("UnsupportedConversionRange", "decimal_to_binary64"),
    "binary_exp": ("binary_exp",),
    "powers": ("integral_power",),
    "elementary": (
        "sqrt", "log", "log10", "exp", "sin", "cos", "tan", "asin", "acos",
        "atan", "power", "BUILTINS",
    ),
}


class NumericPackageTests(unittest.TestCase):
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

    def test_legacy_exports_are_the_same_objects(self):
        for name, exports in EXPORTS.items():
            legacy = importlib.import_module(f"yadinassi.{name}")
            canonical = importlib.import_module(f"yadinassi.numeric.{name}")
            with self.subTest(module=name):
                self.assertIsNot(legacy, canonical)
                self.assertEqual(tuple(legacy.__all__), exports)
                self.assertEqual({name for name in vars(legacy) if not name.startswith("_")},
                                 set(exports))
            for symbol in exports:
                with self.subTest(module=name, symbol=symbol):
                    self.assertIs(getattr(legacy, symbol), getattr(canonical, symbol))

    def test_every_public_math_definition_has_a_legacy_export(self):
        for name, exports in EXPORTS.items():
            source = ROOT / "yadinassi" / "numeric" / f"{name}.py"
            definitions = set()
            for node in ast.parse(source.read_text(encoding="utf-8")).body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    definitions.add(node.name)
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    definitions.update(target.id for target in targets
                                       if isinstance(target, ast.Name))
            with self.subTest(module=name):
                self.assertEqual({name for name in definitions if not name.startswith("_")},
                                 set(exports))

    def test_package_marker_is_nonempty_and_has_no_eager_imports(self):
        source = (ROOT / "yadinassi" / "numeric" / "__init__.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        self.assertTrue(ast.get_docstring(module))
        self.assertEqual(len(module.body), 1)

    def test_fresh_process_import_orders_preserve_symbol_identity(self):
        for name, exports in EXPORTS.items():
            for legacy_first in (False, True):
                names = [f"yadinassi.numeric.{name}", f"yadinassi.{name}"]
                if legacy_first:
                    names.reverse()
                with self.subTest(module=name, legacy_first=legacy_first):
                    self.run_python(f"""
                        import importlib
                        first = importlib.import_module({names[0]!r})
                        second = importlib.import_module({names[1]!r})
                        assert first is not second
                        for symbol in {exports!r}:
                            assert getattr(first, symbol) is getattr(second, symbol), symbol
                    """)

    def test_public_embedding_import_does_not_load_legacy_math_shims(self):
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
            assert Interpreter().execute("Pow(6, 2) + Sqrt(36)") == 42
            for name in ("math_conversion", "binary_exp", "powers", "elementary"):
                assert "yadinassi.numeric." + name in sys.modules
                assert "yadinassi." + name not in sys.modules
        """)

    def test_legacy_exception_catches_canonical_errors(self):
        from decimal import Decimal
        from yadinassi.math_conversion import UnsupportedConversionRange
        from yadinassi.numeric.math_conversion import decimal_to_binary64

        with self.assertRaises(UnsupportedConversionRange):
            decimal_to_binary64(Decimal("1E+1000000"))

    def test_canonical_consumers_and_binary_exp_module_namespace(self):
        from types import ModuleType
        from yadinassi import runtime
        from yadinassi.numeric import binary_exp, elementary, math_conversion, powers
        from yadinassi.values import divide, number

        self.assertIsInstance(binary_exp, ModuleType)
        self.assertIs(runtime.elementary, elementary)
        self.assertIs(elementary.binary_exp, binary_exp.binary_exp)
        self.assertIs(elementary.integral_power, powers.integral_power)
        self.assertIs(elementary.number, number)
        self.assertIs(powers.divide, divide)
        self.assertIs(elementary.decimal_to_binary64, math_conversion.decimal_to_binary64)
        self.assertIs(elementary.UnsupportedConversionRange,
                      math_conversion.UnsupportedConversionRange)
        self.assertIs(binary_exp.UnsupportedConversionRange,
                      math_conversion.UnsupportedConversionRange)
        self.assertIs(binary_exp.binary_exp.__globals__, vars(binary_exp))


if __name__ == "__main__":
    unittest.main()
