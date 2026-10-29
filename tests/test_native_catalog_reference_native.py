"""Pure source/sidecar checks; no native run or fixture evidence is fabricated."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/native_1c_db_oracle"))
import catalog_reference_native as native


class NativeReferenceTests(unittest.TestCase):
    def setUp(self):
        self.binding = dict(nonce="a" * 32, token="b" * 32,
                            case="distinct_a", operation="create")
        self.data = dict(schema=1, status="ok", **self.binding,
                         before_present=False, after_present=True,
                         before="TFE" * 3 + "NNN", after="ETF" * 4,
                         actual_uuid=native.CASES["distinct_a"])

    def decode(self, data=None):
        return native.validate_witness(json.dumps(self.data if data is None else data).encode(),
                                       **self.binding)

    def test_observations_not_prescribed(self):
        for code in "TFE":
            self.data["before"] = code * 9 + "NNN"
            self.data["after"] = code * 12
            self.assertEqual(self.decode().after, code * 12)

    def test_absent_and_retained_deleted_reference(self):
        self.binding["operation"] = "observe"
        self.data.update(operation="observe", after_present=False,
                         after="E" * 9 + "NNN", actual_uuid="")
        self.assertFalse(self.decode().after_present)
        self.binding["operation"] = "delete"
        self.data.update(operation="delete", before_present=True, after_present=True,
                         before="F" * 12, after="F" * 12,
                         actual_uuid=native.CASES["distinct_a"])
        self.assertTrue(self.decode().after_present)

    def test_reject_malformed_structure_and_binding(self):
        for key, value in (("schema", True), ("nonce", "c" * 32),
                           ("token", "c" * 32), ("case", "distinct_b"),
                           ("operation", "update"), ("status", "unknown"),
                           ("before_present", 0), ("before", "T" * 12),
                           ("after", "N" * 12), ("actual_uuid", native.CASES["distinct_b"]),
                           ("extra", 0)):
            with self.subTest(key=key):
                data = {**self.data, key: value}
                with self.assertRaisesRegex(ValueError, "^reference_witness_invalid$"):
                    self.decode(data)
        for key in self.data:
            data = dict(self.data)
            del data[key]
            with self.assertRaises(ValueError):
                self.decode(data)

    def test_wire_bounds_duplicate_keys_and_encoding(self):
        for raw in (b"", b" " * 1025, b"\xff", b"[]", b"null", b'{"x":NaN}',
                    b'{"schema":1,"schema":1}', b"[" * 1500):
            with self.assertRaises(ValueError):
                native.validate_witness(raw, **self.binding)
        self.assertEqual(native.validate_witness(b"\xef\xbb\xbf" + json.dumps(self.data).encode(),
                                                **self.binding).status, "ok")

    def test_failure_categories_and_immutable_result(self):
        data = dict(schema=1, status="error", **self.binding,
                    phase="set_reference", code="native_api_error")
        result = self.decode(data)
        self.assertEqual(result.phase, "set_reference")
        with self.assertRaises(AttributeError):
            result.phase = "other"
        for key, value in (("phase", "raw native details"), ("phase", []),
                           ("code", "exception text"), ("actual_uuid", "")):
            with self.assertRaises(ValueError):
                self.decode({**data, key: value})
        self.binding["operation"] = "observe"
        data["operation"] = "observe"
        with self.assertRaises(ValueError):
            self.decode(data)

    def test_template_is_pinned_and_legacy_unchanged(self):
        path = ROOT / "scripts/native_1c_db_oracle/modules/NativeOracleServer.bsl"
        original = path.read_bytes()
        source = original.decode("utf-8-sig")
        for case in native.CASES:
            result = native.render_template(source, case)
            self.assertIn(native.CASES[case], result)
            self.assertNotIn("@@CASE", result)
            self.assertIn("@@NONCE@@", result)
            self.assertEqual(result.count("NativeReferenceInstall(Объект, Корень, ТокенЗапуска, Операция);"), 1)
            self.assertIn('Контекст.phase = "reference_uuid";\n            NativeReferenceInstall', result)
            self.assertIn('NativeReferenceFinish(Корень, ТокенЗапуска, Операция, НаблюдениеДо);', result)
            self.assertEqual(native.render_template(source.replace("\n", "\r\n"), case), result)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(hashlib.sha256(original).hexdigest(), native._TEMPLATE_SHA256)
        for altered in (source + "\n", source.replace('"K1"', '"K2"'), source.replace("Количество() <> 1", "Количество() <> 3")):
            with self.assertRaisesRegex(ValueError, "^reference_template_invalid$"):
                native.render_template(altered, "distinct_a")
        for case in ("free-form", "", None, []):
            with self.assertRaises(ValueError):
                native.render_template(source, case)

    def test_probe_template_has_no_dynamic_evaluation_or_expected_constants(self):
        source = (ROOT / "scripts/native_1c_db_oracle/modules/CatalogReferenceObservation.bsl").read_text()
        self.assertNotIn("Вычислить(", source)
        self.assertEqual(source.count('Коды = Коды + "E";'), 12)
        self.assertEqual(source.count("Коды = Коды + NativeReferenceCode("), 12)
        self.assertIn("Объект.УстановитьСсылкуНового(Ссылка);", source)
        self.assertIn("UUID = Строка(Сохраненная.УникальныйИдентификатор());", source)
        self.assertNotIn("Контекст.phase", source)


if __name__ == "__main__":
    unittest.main()
