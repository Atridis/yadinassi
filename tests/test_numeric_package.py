"""Canonical numeric imports and the intentionally narrow legacy shims."""

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
    "bits": (
        "bitwise_and", "bitwise_or", "bitwise_xor", "bitwise_not", "bitwise_and_not",
        "check_bit", "check_by_bit_mask", "set_bit", "bitwise_shift_right",
        "bitwise_shift_left", "BUILTINS",
    ),
    "numbers": (
        "integer_part", "round_number", "minimum", "maximum",
        "number_from_binary_string", "number_from_hex_string", "BUILTINS",
    ),
    "round_modes": ("BSLRoundMode", "BSLRoundModes", "ROUND_MODES"),
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

    def test_every_public_numeric_definition_has_a_legacy_export(self):
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

    def test_public_embedding_import_does_not_load_legacy_numeric_shims(self):
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
            for name in ("math_conversion", "binary_exp", "powers", "elementary",
                         "bits", "numbers", "round_modes"):
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

    def test_canonical_numeric_globals_and_runtime_builtins(self):
        from yadinassi import collation, runtime, type_descriptions, values
        from yadinassi.numeric import bits, numbers, round_modes

        self.assertIs(runtime.bits, bits)
        self.assertIs(runtime.numbers, numbers)
        self.assertIs(runtime.BSLRoundModes, round_modes.BSLRoundModes)
        self.assertIs(runtime.ROUND_MODES, round_modes.ROUND_MODES)
        self.assertIs(type_descriptions.round_number, numbers.round_number)
        self.assertIs(numbers.number, values.number)
        self.assertIs(numbers.string_key, collation.string_key)
        self.assertIs(numbers.BSLRoundMode, round_modes.BSLRoundMode)
        self.assertEqual(round_modes.BSLRoundModes.__bases__, (values.BSLObject,))
        self.assertIs(numbers.round_number.__defaults__[1],
                      round_modes.BSLRoundMode.ROUND15_AS20)
        vm = runtime.Interpreter()
        for module in (bits, numbers):
            for name, function, alias in module.BUILTINS:
                with self.subTest(module=module.__name__, function=function.__name__):
                    self.assertIs(function.__globals__, vars(module))
                    self.assertIs(vm.functions[name.casefold()].function, function)
                    self.assertIs(vm.functions[alias.casefold()].function, function)
        for name in ("RoundMode", "РежимОкругления"):
            self.assertIs(vm.execute(name), round_modes.ROUND_MODES)
        vm.execute("modes = New Array; For Each mode In RoundMode Do modes.Add(mode); EndDo;")
        self.assertIs(vm.variables["modes"].items[0], round_modes.BSLRoundMode.ROUND15_AS10)
        self.assertIs(vm.variables["modes"].items[1], round_modes.BSLRoundMode.ROUND15_AS20)

    def test_fresh_consumer_first_imports_preserve_round_mode_registries_and_codec(self):
        # Importing any submodule runs the eager package initializer first. These
        # are requested-import orders, not claims about class creation order.
        for consumer in ("runtime", "serialization", "type_values", "value_checks",
                         "type_descriptions"):
            with self.subTest(consumer=consumer):
                self.run_python(f"""
                    import importlib
                    importlib.import_module("yadinassi." + {consumer!r})
                    from yadinassi import round_modes as legacy
                    from yadinassi import serialization, type_values, value_checks
                    from yadinassi.numeric import numbers, round_modes as canonical
                    from yadinassi.values import BSLType

                    assert legacy.BSLRoundMode is canonical.BSLRoundMode
                    assert legacy.BSLRoundModes is canonical.BSLRoundModes
                    assert legacy.ROUND_MODES is canonical.ROUND_MODES
                    assert numbers.round_number.__defaults__[1] is canonical.BSLRoundMode.ROUND15_AS20
                    assert serialization.BSLRoundMode is canonical.BSLRoundMode
                    assert serialization._ENUM_TYPES[BSLType.ROUND_MODE] is canonical.BSLRoundMode
                    for module in (type_values, value_checks):
                        assert module.BSLRoundMode is canonical.BSLRoundMode
                        assert module.BSLRoundModes is canonical.BSLRoundModes
                    assert value_checks.ROUND_MODES is canonical.ROUND_MODES
                    for cls, kind in ((canonical.BSLRoundMode, BSLType.ROUND_MODE),
                                      (canonical.BSLRoundModes, BSLType.ROUND_MODES)):
                        entries = [entry for entry in type_values._VALUE_TYPES if entry[0] is cls]
                        assert len(entries) == 1 and entries[0][1] is kind

                    write = serialization.value_to_string_internal
                    read = serialization.value_from_string_internal
                    mode_id = "32c82ccd-fef3-4070-beb5-b9c52afc781d"
                    namespace_id = "a47c4665-311c-405a-828e-0c5a3ca3bdda"
                    members = serialization._ENUM_MEMBERS[BSLType.ROUND_MODE]
                    assert set(members) == {{"0", "1"}}
                    for index, member in enumerate((canonical.BSLRoundMode.ROUND15_AS10,
                                                    canonical.BSLRoundMode.ROUND15_AS20)):
                        assert member.value == index
                        assert members[str(index)] is member
                        payload = '{{"#",' + mode_id + ',' + str(index) + '}}'
                        assert write(member) == payload and read(payload) is member
                        assert type_values.type_of(member) is BSLType.ROUND_MODE
                        assert value_checks.value_is_filled(member) is True
                    namespace = canonical.ROUND_MODES
                    assert type(namespace) is canonical.BSLRoundModes
                    assert type_values.type_of(namespace) is BSLType.ROUND_MODES
                    assert value_checks.value_is_filled(namespace) is True
                    payload = '{{"#",' + namespace_id + '}}'
                    assert write(namespace) == payload and read(payload) is None
                    assert type_values.type_of(read(payload)) is BSLType.UNDEFINED
                    for kind, identifier in ((BSLType.ROUND_MODE, mode_id),
                                             (BSLType.ROUND_MODES, namespace_id)):
                        payload = '{{"T",' + identifier + '}}'
                        assert write(kind) == payload and read(payload) is kind
                """)


if __name__ == "__main__":
    unittest.main()
