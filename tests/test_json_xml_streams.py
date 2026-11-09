"""Borrowed-stream JSON/XML composition; local profile, not native captures."""
import codecs
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from yadinassi import Interpreter
from yadinassi.binary_streams import (BSLMemoryStream as Memory, BSLBinaryDataBuffer as Buffer,
    BSLFileStream as FileStream, BSLFileOpenMode as Mode, BSLFileAccess as Access,
    BSLPositionInStream as Origin)
from yadinassi.file_io import BSLBinaryData, BSLTextEncoding
from yadinassi.json_processing import (BSLJSONReader as JSONReader, BSLJSONWriter as JSONWriter,
    BSLJSONWriterSettings as JSONSettings, read_json)
from yadinassi.xml_io import BSLXMLReader as XMLReader, BSLXMLReaderSettings
from yadinassi.xml_writer import BSLXMLWriter as XMLWriter, BSLXMLWriterSettings as XMLSettings


def memory(data=b''):
    stream = Memory(); stream._write_bytes(data); stream.seek(0, Origin.BEGIN)
    return stream


def content(stream):
    position = stream.current_position(); stream.seek(0, Origin.BEGIN)
    data = stream._read_bytes(stream._size()); stream.seek(position, Origin.BEGIN)
    return data


def xml_value(writer, text='Привет <&> 😀'):
    writer.write_start_element('root'); writer.write_attribute('name', 'value')
    writer.write_text(text); writer.write_end_element()


class JSONXMLStreamTests(unittest.TestCase):
    def test_json_encoding_bom_roundtrip(self):
        for encoding, codec in [('UTF-8', 'utf-8'), ('UTF-16', 'utf-16-le'), ('UTF-16BE', 'utf-16-be')]:
            for bom in (False, True):
                with self.subTest(encoding=encoding, bom=bom):
                    s = Memory(); w = JSONWriter(); w.open_stream(s, encoding, bom)
                    w.write_start_object(); w.write_property_name('текст'); w.write_value('Я😀'); w.write_end_object()
                    self.assertEqual(w.close(), ''); self.assertGreater(s.size(), 0)
                    s.seek(0, Origin.BEGIN); r = JSONReader(); r.open_stream(s, encoding)
                    self.assertEqual(read_json(r).get_member('текст'), 'Я😀'); r.close()
                    self.assertEqual(s.current_position(), s.size())
                    s.close()

    def test_json_default_no_bom_and_whole_document_deferred_write(self):
        s = Memory(); w = JSONWriter(); w.open_stream(s); w.write_value('ok')
        self.assertEqual(s.size(), 0); self.assertEqual(w.close(), '')
        self.assertEqual(content(s), b'"ok"'); s.close()

    def test_json_source_current_position_and_binarydata_view(self):
        source = BSLBinaryData.from_bytes(b'prefix[1,2]').open_stream_for_read()
        source.seek(6, Origin.BEGIN); r = JSONReader(); r.open_stream(source)
        self.assertEqual(read_json(r).items, [D(1), D(2)]); r.close()
        self.assertEqual(source.current_position(), source.size()); source.close()

    def test_json_stream_open_replaces_unread_string_document(self):
        r = JSONReader(); r.set_string('[1,2]'); self.assertTrue(r.read())
        s = memory(b'[3]'); r.open_stream(s)
        self.assertEqual(read_json(r).items, [D(3)]); r.close(); s.close()

    def test_json_decode_error_restores_source_and_previous_reader(self):
        r = JSONReader(); r.set_string('7'); s = memory(b'\xff')
        with self.assertRaises(UnicodeError): r.open_stream(s, 'UTF-8')
        self.assertEqual(s.current_position(), 0); self.assertEqual(read_json(r), 7)
        s.close()

    def test_json_invalid_encoding_and_byte_budget_do_not_consume(self):
        s = memory(b'"abc"'); r = JSONReader()
        for encoding in ('unknown-encoding', D(1), True):
            with self.subTest(encoding=encoding), self.assertRaises((TypeError, ValueError)):
                r.open_stream(s, encoding)
            self.assertEqual(s.current_position(), 0)
        with patch('yadinassi.json_processing.MAX_TEXT', 3), self.assertRaises(ValueError):
            r.open_stream(s)
        self.assertEqual(s.current_position(), 0); s.close()

    def test_json_reader_admits_text_encoding_enum(self):
        s = memory('"Я"'.encode('utf-16-le')); r = JSONReader()
        r.open_stream(s, BSLTextEncoding.UTF16); self.assertEqual(read_json(r), 'Я')
        r.close(); s.close()

    def test_json_closed_source_is_rejected_before_reader_replacement(self):
        s = memory(b'1'); s.close(); r = JSONReader(); r.set_string('2')
        with self.assertRaises(ValueError): r.open_stream(s)
        self.assertEqual(read_json(r), 2)

    def test_json_invalid_target_preserves_active_string_writer(self):
        w = JSONWriter(); w.set_string(); w.write_value('previous')
        s = BSLBinaryData.from_bytes(b'123').open_stream_for_read()
        with self.assertRaises(ValueError): w.open_stream(s)
        self.assertEqual(w.close(), '"previous"'); s.close()

    def test_json_readonly_memory_view_cannot_write_despite_capability_property(self):
        s = Memory(); view = s.get_readonly_stream(); w = JSONWriter()
        self.assertTrue(view.get_member('CanWrite'))
        with self.assertRaises(ValueError): w.open_stream(view)
        self.assertEqual(s.size(), 0); view.close(); s.close()

    def test_json_fixed_capacity_failure_has_no_partial_bytes_and_keeps_stream_open(self):
        s = Memory(Buffer(D(3))); before = content(s); w = JSONWriter(); w.open_stream(s)
        w.write_value('long')
        with self.assertRaises(ValueError): w.close()
        self.assertEqual(content(s), before); self.assertEqual(s.current_position(), 0)
        with self.assertRaises(ValueError): w.close()
        s.close()

    def test_json_encoding_failure_does_not_write_or_close_borrowed_stream(self):
        s = Memory(); w = JSONWriter(); w.open_stream(s, 'ascii'); w.write_value('Я')
        with self.assertRaises(UnicodeError): w.close()
        self.assertEqual(s.size(), 0); self.assertEqual(s.current_position(), 0); s.close()

    def test_json_incomplete_close_is_repairable_without_consuming_destination(self):
        s = Memory(); w = JSONWriter(); w.open_stream(s); w.write_start_array(); w.write_value(D(3))
        with self.assertRaises(ValueError): w.close()
        self.assertEqual(s.size(), 0); w.write_end_array(); w.close()
        self.assertEqual(json.loads(content(s)), [3]); s.close()

    def test_json_target_close_by_owner_is_detected_at_publication(self):
        s = Memory(); w = JSONWriter(); w.open_stream(s); w.write_value(True); s.close()
        with self.assertRaises(ValueError): w.close()

    def test_json_replacing_stream_writer_does_not_close_or_publish_old_target(self):
        a, b = Memory(), Memory(); w = JSONWriter(); w.open_stream(a); w.write_value('old')
        w.open_stream(b); w.write_value('new'); w.close()
        self.assertEqual(a.size(), 0); self.assertEqual(content(b), b'"new"')
        a.close(); b.close()

    def test_json_parameter_validation_is_before_writer_replacement(self):
        s = Memory(); w = JSONWriter(); w.set_string(); w.write_value('keep')
        for args in [(s, BSLTextEncoding.UTF8), (s, 'UTF-8', D(1)), (s, 'UTF-8', False, 'bad')]:
            with self.subTest(args=args), self.assertRaises((TypeError, ValueError)): w.open_stream(*args)
        self.assertEqual(w.close(), '"keep"'); self.assertEqual(s.size(), 0); s.close()

    def test_json_bsl_handlers_dates_and_stream_roundtrip(self):
        vm = Interpreter(lambda _: None)
        try:
            vm.execute('''
Var Calls;
Function Convert(Property, Value, Extra, Cancel) Export
 Calls=Calls+1; Return String(Value);
EndFunction
Calls=0; S=New MemoryStream; W=New JSONWriter; W.OpenStream(S);
V=New Structure("ID,When",New UUID("12345678-1234-1234-1234-123456789abc"),Date(2024,1,2));
WriteJSON(W,V,,"Convert",ThisObject); W.Close(); S.Seek(0,PositionInStream.Begin);
R=New JSONReader; R.OpenStream(S); V2=ReadJSON(R,False,"When"); R.Close();
''')
            self.assertEqual(vm.execute('Calls'), 1)
            self.assertEqual(str(vm.execute('V2.ID')), '12345678-1234-1234-1234-123456789abc')
            self.assertEqual(vm.execute('V2.When=Date(2024,1,2)'), True)
            self.assertEqual(vm.execute('S.CurrentPosition()=S.Size()'), True)
        finally: vm.close()

    def test_xml_roundtrip_all_unicode_encodings_and_bom(self):
        for encoding in ('UTF-8', 'UTF-16', 'UTF-16BE'):
            for bom in (False, True):
                with self.subTest(encoding=encoding, bom=bom):
                    s = Memory(); w = XMLWriter(); w.open_stream(s, XMLSettings(encoding, indent=False), bom)
                    w.write_xml_declaration(); xml_value(w); self.assertEqual(w.close(), '')
                    self.assertEqual(ET.fromstring(content(s)).text, 'Привет <&> 😀')
                    s.seek(0, Origin.BEGIN); r = XMLReader(); r.open_stream(s)
                    tokens = []
                    while r.read(): tokens.append(r.get_member('Value'))
                    self.assertIn('Привет <&> 😀', tokens); r.close(); s.close()

    def test_xml_default_bom_and_no_encoding_declaration_attribute(self):
        s = Memory(); w = XMLWriter(); w.open_stream(s); w.write_xml_declaration(); xml_value(w)
        self.assertEqual(s.size(), 0); w.close(); raw = content(s)
        self.assertTrue(raw.startswith(codecs.BOM_UTF8)); self.assertNotIn(b'encoding=', raw)
        s.close()

    def test_xml_source_nonzero_position_and_explicit_text_encoding(self):
        s = memory(b'prefix' + '<r>Я</r>'.encode('utf-16-le')); s.seek(6, Origin.BEGIN)
        r = XMLReader(); r.open_stream(s, encoding=BSLTextEncoding.UTF16)
        values = []
        while r.read(): values.append(r.get_member('Value'))
        self.assertIn('Я', values); self.assertEqual(s.current_position(), s.size()); r.close(); s.close()

    def test_xml_invalid_settings_schema_and_encoding_preserve_source(self):
        s = memory(b'<r/>'); r = XMLReader(); r.set_string('<old/>')
        for kwargs in ({'settings':'bad'}, {'schemas':'bad'}, {'encoding':D(4)}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                r.open_stream(s, **kwargs)
            self.assertEqual(s.current_position(), 0)
        self.assertTrue(r.read()); self.assertEqual(r.get_member('Name'), 'old'); s.close()

    def test_xml_decode_and_size_errors_restore_source_cursor(self):
        s = memory(b'\xff'); r = XMLReader()
        with self.assertRaises(UnicodeError): r.open_stream(s, encoding='UTF-8')
        self.assertEqual(s.current_position(), 0); s.close()
        s = memory(b'<r/>')
        with patch('yadinassi.xml_io.MAX_XML_BYTES', 3), self.assertRaises(ValueError): r.open_stream(s)
        self.assertEqual(s.current_position(), 0); s.close()

    def test_xml_reader_close_releases_snapshot_not_stream(self):
        s = memory(b'<r/>'); r = XMLReader(); r.open_stream(s); r.close(); r.close()
        with self.assertRaises(ValueError): r.read()
        self.assertEqual(s.size(), 4); s.seek(0, Origin.BEGIN); r.open_stream(s); self.assertTrue(r.read()); s.close()

    def test_xml_forbidden_dtd_uses_existing_safe_parser(self):
        s = memory(b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///no-such-file">]><r>&x;</r>')
        r = XMLReader(); r.open_stream(s)
        with self.assertRaises(ValueError): r.read()
        self.assertEqual(s.current_position(), s.size()); r.close(); s.close()

    def test_xml_invalid_target_preserves_string_writer(self):
        s = BSLBinaryData.from_bytes(b'').open_stream_for_read(); w = XMLWriter(); w.set_string(); xml_value(w, 'ok')
        with self.assertRaises(ValueError): w.open_stream(s)
        self.assertEqual(ET.fromstring(w.close()).text, 'ok'); s.close()

    def test_xml_incomplete_close_is_terminal_but_stream_remains_open(self):
        s = Memory(); w = XMLWriter(); w.open_stream(s); w.write_start_element('r')
        with self.assertRaises(ValueError): w.close()
        self.assertEqual(s.size(), 0)
        with self.assertRaises(ValueError): w.close()
        s.close()

    def test_xml_capacity_and_encoding_failure_are_before_publication(self):
        for s, encoding in [(Memory(Buffer(D(3))), 'UTF-8'), (Memory(), 'ascii')]:
            with self.subTest(encoding=encoding):
                before = content(s); w = XMLWriter(); w.open_stream(s, encoding, False); xml_value(w, 'Я')
                with self.assertRaises((ValueError, UnicodeError)): w.close()
                self.assertEqual(content(s), before); self.assertEqual(s.current_position(), 0); s.close()

    def test_xml_settings_are_copied_before_write(self):
        settings = XMLSettings('UTF-8', indent=False); s = Memory(); w = XMLWriter()
        w.open_stream(s, settings, False); settings.encoding = 'ascii'; settings.indent = True
        xml_value(w, 'Я'); w.close(); self.assertEqual(ET.fromstring(content(s)).text, 'Я'); s.close()

    def test_file_stream_roundtrip_keeps_borrowed_file_usable(self):
        with tempfile.TemporaryDirectory() as d:
            for writer_class, reader_class in [(JSONWriter, JSONReader), (XMLWriter, XMLReader)]:
                with self.subTest(writer=writer_class.__name__):
                    p = Path(d) / (writer_class.__name__+'.dat')
                    s = FileStream(str(p), Mode.CREATE, Access.READ_WRITE)
                    try:
                        w = writer_class(); w.open_stream(s)
                        if writer_class is JSONWriter: w.write_value('value')
                        else: xml_value(w, 'value')
                        w.close(); s.seek(0, Origin.BEGIN); r = reader_class(); r.open_stream(s)
                        self.assertTrue(r.read()); r.close(); s.flush(); self.assertTrue(p.read_bytes())
                    finally: s.close()

    def test_cross_family_data_header_then_json_payload(self):
        vm = Interpreter(lambda _: None)
        try:
            vm.execute('''S=New MemoryStream; D=New DataWriter(S); D.WriteInt32(42); D.Close();
W=New JSONWriter; W.OpenStream(S); WriteJSON(W,New Structure("Code",7)); W.Close();
S.Seek(0,PositionInStream.Begin); D=New DataReader(S); Header=D.ReadInt32(); D.Close();
R=New JSONReader; R.OpenStream(S); Body=ReadJSON(R); R.Close();''')
            self.assertEqual(vm.execute('Header'), 42); self.assertEqual(vm.execute('Body.Code'), 7)
        finally: vm.close()

    def test_russian_xml_bsl_stream_and_repeated_chains(self):
        vm = Interpreter(lambda _: None)
        try:
            vm.execute('''П=Новый ПотокВПамяти; З=Новый ЗаписьXML; З.ОткрытьПоток(П,,Ложь);
З.ЗаписатьНачалоЭлемента("Корень"); З.ЗаписатьТекст("данные"); З.ЗаписатьКонецЭлемента(); З.Закрыть();
П.Перейти(0,ПозицияВПотоке.Начало); Ч=Новый ЧтениеXML; Ч.ОткрытьПоток(П); Ч.Прочитать(); Имя=Ч.Имя;
Ч.Закрыть(); П.Перейти(0,ПозицияВПотоке.Начало); Ч.ОткрытьПоток(П); Ч.Прочитать(); Ч.Прочитать(); Значение=Ч.Значение;''')
            self.assertEqual(vm.execute('Имя'), 'Корень'); self.assertEqual(vm.execute('Значение'), 'данные')
        finally: vm.close()

    def test_foreign_host_objects_are_not_stream_adapters(self):
        import io
        for target in (io.BytesIO(b'1'), b'1', BSLBinaryData.from_bytes(b'1'), 'filename'):
            for cls in (JSONReader, JSONWriter, XMLReader, XMLWriter):
                with self.subTest(cls=cls.__name__, target=type(target).__name__), self.assertRaises(TypeError):
                    cls().open_stream(target)
