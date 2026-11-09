"""Local file contract, not native evidence; every path is owned by this test."""
import codecs
from decimal import Decimal as D
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi import file_io
from yadinassi.text_documents import BSLTextDocument


class TextDocumentFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="yadinassi-text-document-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "текст.txt"
        self.doc = BSLTextDocument()
        self.doc.set_text("old\r\nstate")
        self.vm = Interpreter(lambda _: None)
        self.vm.variables["d"] = self.doc
        self.vm.variables["p"] = str(self.path)

    def snapshot(self):
        return (self.doc.get_text(), self.doc.line_count(),
                [self.doc.get_line(D(i)) for i in range(1, int(self.doc.line_count()) + 1)])

    def test_bilingual_read_edit_write_workflow(self):
        for read, write, constructor in (("Read", "Write", "TextDocument"),
                                         ("пРоЧиТаТь", "зАпИсАтЬ", "ТекстовыйДокумент")):
            with self.subTest(read=read):
                self.path.write_bytes("Первая\r\nВторая".encode("cp1251"))
                self.vm.execute(f'd=New {constructor}; d.{read}(p,"windows-1251");'
                                f'd.AddLine("Третья"); d.{write}(p,"UTF-8");'
                                f'd.Clear(); d.{read}(p);')
                self.assertEqual(self.vm.execute("d.GetText()"), "Первая\nВторая\nТретья\n")
                self.assertEqual(self.vm.execute("d.LineCount()"), D(3))
                self.assertEqual(self.path.read_bytes(),
                                 codecs.BOM_UTF8 + "Первая\r\nВторая\r\nТретья\r\n".encode())

    def test_default_read_without_bom_is_utf8_not_textreader_ansi(self):
        self.path.write_bytes("Ж😀\r\nlast\rbare\n".encode())
        self.doc.read(str(self.path))
        self.assertEqual(self.snapshot(), ("Ж😀\nlast\rbare\n", D(3), ["Ж😀", "last", "bare"]))

    def test_read_autodetects_supported_boms(self):
        for mark, encoding in ((codecs.BOM_UTF8, "utf-8"),
                               (codecs.BOM_UTF16_LE, "utf-16-le"),
                               (codecs.BOM_UTF16_BE, "utf-16-be")):
            with self.subTest(encoding=encoding):
                self.path.write_bytes(mark + "Ж😀\r\nlast".encode(encoding))
                self.doc.read(str(self.path))
                self.assertEqual(self.doc.get_text(), "Ж😀\nlast")

    def test_explicit_encodings_and_enum_roundtrip(self):
        self.doc.set_text("Привет\nмир")
        for encoding in ("utf-8", "utf-16", "utf-16be", "windows-1251", "cp866", "koi8-r",
                         file_io.BSLTextEncoding.UTF8, file_io.BSLTextEncoding.UTF16,
                         file_io.BSLTextEncoding.ANSI, file_io.BSLTextEncoding.OEM):
            with self.subTest(encoding=encoding):
                self.doc.write(str(self.path), encoding, "")
                other = BSLTextDocument()
                other.read(str(self.path), encoding, "")
                self.assertEqual(other.get_text(), "Привет\nмир")
        for locale, bom in (("UTF-8", codecs.BOM_UTF8), ("UTF-16LE", codecs.BOM_UTF16_LE),
                            ("UTF-16BE", codecs.BOM_UTF16_BE), ("windows-1251", b"")):
            with self.subTest(system_locale=locale), patch.object(
                    file_io.locale, "getpreferredencoding", return_value=locale):
                self.doc.write(str(self.path), file_io.BSLTextEncoding.SYSTEM, "")
                self.assertTrue(self.path.read_bytes().startswith(bom))
                other = BSLTextDocument()
                other.read(str(self.path), file_io.BSLTextEncoding.SYSTEM, "")
                self.assertEqual(other.get_text(), "Привет\nмир")

    def test_read_separator_selection_and_empty_preservation(self):
        raw = "A\r\nB\rC\n\n"
        self.path.write_bytes(raw.encode())
        for separator in ("", "\r", "\n", "\r\n"):
            with self.subTest(separator=repr(separator)):
                self.doc.read(str(self.path), "UTF-8", separator)
                self.assertEqual(self.doc.get_text(), raw.replace(separator, "\n") if separator else raw)

    def test_write_separator_selection_preserves_document_state(self):
        raw = "A\r\nB\rC\n\n"
        self.doc.set_text(raw)
        before = self.snapshot()
        for separator in ("", "\r", "\n", "\r\n"):
            with self.subTest(separator=repr(separator)):
                self.doc.write(str(self.path), "UTF-8", separator)
                expected = raw.replace("\r\n", "\n").replace("\n", separator) if separator else raw
                self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8 + expected.encode())
                self.assertEqual(self.snapshot(), before)

    def test_empty_and_unterminated_documents_do_not_gain_a_line(self):
        for text in ("", "one", "one\n", "\n\n"):
            with self.subTest(text=repr(text)):
                self.doc.set_text(text)
                expected = self.snapshot()
                self.doc.write(str(self.path))
                self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8 + text.replace("\n", "\r\n").encode())
                self.doc.read(str(self.path))
                self.assertEqual(self.snapshot(), expected)

    def test_write_replaces_existing_contents_without_appending(self):
        self.path.write_bytes(b"existing longer contents")
        self.doc.set_text("x")
        self.doc.write(str(self.path))
        self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8 + b"x")
        self.doc.clear()
        self.doc.write(str(self.path), "ascii")
        self.assertEqual(self.path.read_bytes(), b"")

    def test_completed_operations_release_file_handles(self):
        self.doc.write(str(self.path))
        self.doc.read(str(self.path))
        moved = self.root / "moved.txt"
        self.path.rename(moved)
        moved.unlink()
        self.assertFalse(self.path.exists())
        self.assertFalse(moved.exists())

    def test_missing_malformed_and_surrogate_reads_preserve_full_state(self):
        before = self.snapshot()
        with self.assertRaises(ValueError): self.doc.read(str(self.path))
        for raw, encoding in ((b"\xff", "UTF-8"), (b"\x00\xd8", "UTF-16")):
            self.path.write_bytes(raw)
            with self.assertRaises(UnicodeError): self.doc.read(str(self.path), encoding)
            self.assertEqual(self.snapshot(), before)

    def test_read_text_budget_is_utf16_and_atomic(self):
        before = self.snapshot()
        self.path.write_bytes("😀😀x".encode())
        with patch("yadinassi.text_documents._MAX_TEXT_UNITS", 4):
            with self.assertRaises(ValueError): self.doc.read(str(self.path))
            self.assertEqual(self.snapshot(), before)
            self.path.write_bytes("😀😀".encode())
            self.doc.read(str(self.path))
            self.assertEqual(self.doc.get_text(), "😀😀")

    def test_read_line_budget_is_checked_after_separator_conversion(self):
        before = self.snapshot()
        self.path.write_bytes(b"a\rb\rc")
        with patch("yadinassi.text_documents._MAX_LINES", 2):
            with self.assertRaises(ValueError): self.doc.read(str(self.path), None, "\r")
        self.assertEqual(self.snapshot(), before)

    def test_invalid_options_are_rejected_before_file_access(self):
        before = self.snapshot()
        options = (("not-an-encoding", None), (D(8), None), (True, None),
                   (None, "|"), (None, True), (None, D(1)), (None, "\n\r"))
        for method, helper in ((self.doc.read, "_read_bytes"), (self.doc.write, "_write_bytes")):
            for encoding, separator in options:
                with self.subTest(method=method.__name__, encoding=encoding, separator=separator):
                    with patch.object(file_io, helper) as operation:
                        with self.assertRaises((ValueError, TypeError)):
                            method(str(self.path), encoding, separator)
                        operation.assert_not_called()
                    self.assertEqual(self.snapshot(), before)
                    self.assertFalse(self.path.exists())

    def test_encoding_failure_neither_truncates_nor_creates_destination(self):
        self.doc.set_text("😀")
        self.path.write_bytes(b"keep")
        other = self.root / "absent.txt"
        for path in (self.path, other):
            with self.assertRaises(UnicodeError): self.doc.write(str(path), "cp1251")
        self.assertEqual(self.path.read_bytes(), b"keep")
        self.assertFalse(other.exists())
        self.assertEqual(self.doc.get_text(), "😀")

    def test_write_byte_budget_includes_bom_and_precedes_truncation(self):
        self.doc.set_text("xx")
        self.path.write_bytes(b"keep")
        with patch.object(file_io, "MAX_BYTES", 4):
            with self.assertRaises(ValueError): self.doc.write(str(self.path))
            self.assertEqual(self.path.read_bytes(), b"keep")
            self.doc.set_text("x")
            self.doc.write(str(self.path))
            self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8 + b"x")

    def test_read_byte_budget_preserves_state(self):
        self.path.write_bytes(b"12345")
        before = self.snapshot()
        with patch.object(file_io, "MAX_BYTES", 4):
            with self.assertRaises(ValueError): self.doc.read(str(self.path))
        self.assertEqual(self.snapshot(), before)

    def test_invalid_paths_and_directories_are_catchable(self):
        before = self.snapshot()
        for path in ("", "https://example.invalid/file", "bad\0path", str(self.root), None, D(1)):
            for name in ("Read", "Write"):
                self.vm.variables["badpath"] = path
                with self.subTest(path=path, name=name):
                    self.vm.execute(f'caught=False; Try d.{name}(badpath); Except caught=True; EndTry;')
                    self.assertTrue(self.vm.execute("caught"))
                    self.assertEqual(self.snapshot(), before)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO boundary")
    def test_nonregular_fifo_is_rejected_without_waiting_for_a_writer(self):
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError): self.doc.read(str(fifo))
        with self.assertRaises(ValueError): self.doc.write(str(fifo))

    def test_permission_failure_is_an_ordinary_bsl_error(self):
        before = self.snapshot()
        with patch.object(file_io.os, "open", side_effect=PermissionError("denied")):
            for method in ("Read", "Write"):
                self.vm.execute(f'caught=False; Try d.{method}(p); Except caught=True; EndTry;')
                self.assertTrue(self.vm.execute("caught"))
                self.assertEqual(self.snapshot(), before)

    def test_procedure_expression_rejected_before_argument_side_effects(self):
        calls = []
        self.vm.register_function("PathEffect", lambda: calls.append(True) or str(self.path))
        for method in ("Read", "Прочитать", "Write", "Записать"):
            with self.assertRaises(BSLError): self.vm.execute(f"result=d.{method}(PathEffect());")
        self.assertEqual(calls, [])
        self.assertFalse(self.path.exists())

    def test_optional_holes_and_explicit_undefined_use_defaults(self):
        self.doc.set_text("x\ny")
        for write, read in (("Write", "Read"), ("Записать", "Прочитать")):
            self.vm.execute(f'd.{write}(p,,""); d.Clear(); d.{read}(p,,"");')
            self.assertEqual(self.doc.get_text(), "x\ny")
            self.vm.execute(f'd.{write}(p,Undefined,Undefined); d.Clear(); d.{read}(p,,);')
            self.assertEqual(self.doc.get_text(), "x\ny")
            self.assertEqual(self.path.read_bytes(), codecs.BOM_UTF8 + b"x\r\ny")

    def test_required_holes_arity_and_computed_receivers_stay_guarded(self):
        calls = []
        self.vm.register_function("Factory", lambda: calls.append(True) or self.doc)
        for code in ('d.Read()', 'd.Write()', 'd.Read(,)', 'd.Write(,)',
                     'd.Read(p,,,,)', 'd.Write(p,Undefined,Undefined,1)',
                     'Factory().Write(p,,"")', 'Factory().Read(p,,"")',
                     'd.SetText(,)', 'd.Clear(,)'):
            with self.subTest(code=code), self.assertRaises(BSLError): self.vm.execute(code)
        self.assertEqual(calls, [])
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
