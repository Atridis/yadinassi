"""XML writer workflows; local structural evidence, not native parity."""
import codecs
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET
from yadinassi.xml_writer import BSLXMLWriter as Writer, BSLXMLWriterSettings as Settings
from yadinassi import xml_writer as module


class XMLWriterTests(unittest.TestCase):
    def writer(self, settings=None):
        w=Writer();w.set_string(settings if settings is not None else Settings('',None,False));return w
    def test_document_roundtrip_escape_and_declaration(self):
        w=self.writer();w.write_xml_declaration();w.write_start_element('root')
        w.write_attribute('name','<&"\n\t\r');w.write_text('Привет <&> 😀')
        w.write_end_element();text=w.close();root=ET.fromstring(text)
        self.assertEqual(root.text,'Привет <&> 😀');self.assertEqual(root.attrib['name'],'<&"\n\t\r')
        self.assertTrue(text.startswith('<?xml version="1.0"?>'))
    def test_nested_empty_and_mixed_content(self):
        w=self.writer(Settings('',None,True));w.write_start_element('root')
        w.write_text('a');w.write_start_element('child');w.write_end_element();w.write_text('b');w.write_end_element()
        self.assertEqual(w.close(),'<root>a<child/>b</root>')
    def test_pretty_settings_and_readonly(self):
        settings=Settings('UTF-8','1.0',True,True,'  ')
        self.assertEqual(settings.get_member('СимволыОтступа'),'  ')
        with self.assertRaises(ValueError): settings.set_member('Indent',False)
        w=self.writer(settings);w.write_start_element('root');w.write_attribute('x','1')
        w.write_start_element('child');w.write_end_element();w.write_end_element();text=w.close()
        self.assertEqual(text,'<root\n  x="1">\n  <child/>\n</root>');ET.fromstring(text)
    def test_namespaces_scope_and_expanded_attributes(self):
        w=self.writer();w.write_start_element('root','urn:r');w.write_namespace_mapping('p','urn:r')
        w.write_namespace_mapping('a','urn:a');w.write_attribute('id','urn:a','1')
        self.assertEqual(w.lookup_prefix('urn:r'),'p')
        w.write_start_element('child','urn:r');w.write_namespace_mapping('a','urn:b')
        self.assertEqual(w.lookup_prefix('urn:a'),None)
        w.write_end_element();self.assertEqual(w.lookup_prefix('urn:a'),'a');w.write_end_element()
        root=ET.fromstring(w.close());self.assertEqual(root.tag,'{urn:r}root');self.assertEqual(root.attrib,{'{urn:a}id':'1'})
    def test_default_namespace_and_unqualified_attribute(self):
        w=self.writer();w.write_start_element('root','urn:r');w.write_namespace_mapping('','urn:r')
        w.write_attribute('id','1');w.write_end_element();r=ET.fromstring(w.close())
        self.assertEqual(r.tag,'{urn:r}root');self.assertEqual(r.attrib,{'id':'1'})
    def test_streamed_attribute_and_duplicate_rejection(self):
        w=self.writer();w.write_start_element('root');w.write_start_attribute('x');w.write_text('a&');w.write_text('"b');w.write_end_attribute()
        with self.assertRaises(ValueError): w.write_attribute('x','again')
        w.write_end_element();self.assertEqual(ET.fromstring(w.close()).attrib['x'],'a&"b')
    def test_comment_cdata_and_pi(self):
        w=self.writer();w.write_processing_instruction('style','a="b"');w.write_comment('outside');w.write_start_element('root')
        w.write_cdata_section('<&>');w.write_comment('inside');w.write_end_element()
        text=w.close();self.assertIn('<?style a="b"?>',text);self.assertIn('<![CDATA[<&>]]>',text)
        self.assertEqual(ET.fromstring(text).text,'<&>')
    def test_invalid_xml_rejected_before_state_change(self):
        w=self.writer();w.write_start_element('root')
        for method,args in [(w.write_comment,('a--b',)),(w.write_cdata_section,(']]>',)),
                            (w.write_processing_instruction,('xml','x')),(w.write_text,('\0',)),
                            (w.write_attribute,('bad name','x'))]:
            with self.subTest(method=method),self.assertRaises(ValueError):method(*args)
        w.write_attribute('ok','1');w.write_end_element();self.assertEqual(w.close(),'<root ok="1"/>')
    def test_lifecycle_and_reinitialization(self):
        w=Writer()
        for fn in (w.close,w.write_end_element,lambda:w.write_text('x'),lambda:w.lookup_prefix('x')):
            with self.assertRaises(ValueError):fn()
        w.set_string();w.write_start_element('a')
        with self.assertRaises(ValueError):w.close()
        w.write_end_element();self.assertEqual(w.close(),'<a/>')
        w.set_string();w.write_start_element('b');w.write_end_element();self.assertEqual(w.close(),'<b/>')
    def test_file_encoding_bom_and_reopen_owned_paths(self):
        with tempfile.TemporaryDirectory(prefix='xml-writer-test-') as tmp:
            path=Path(tmp)/'a.xml'
            for enc,bom,mark in [('UTF-8',True,codecs.BOM_UTF8),('UTF-16',True,codecs.BOM_UTF16_LE),('windows-1251',False,b'')]:
                w=Writer();w.open_file(str(path),enc,bom);w.write_xml_declaration();w.write_start_element('root');w.write_text('Привет');w.write_end_element()
                self.assertEqual(w.close(),'');data=path.read_bytes();self.assertTrue(data.startswith(mark))
                encoding={'UTF-8':'utf-8-sig','UTF-16':'utf-16','windows-1251':'cp1251'}[enc]
                self.assertEqual(ET.fromstring(data.decode(encoding)).text,'Привет')
            before=path.read_bytes()
            with self.assertRaises(ValueError):w.open_file(str(path),'bad-codec')
            self.assertEqual(path.read_bytes(),before)
    def test_nonregular_file_error(self):
        with tempfile.TemporaryDirectory(prefix='xml-writer-test-') as tmp:
            with self.assertRaises(ValueError):Writer().open_file(tmp)
    def test_depth_node_and_escaping_budgets(self):
        w=self.writer()
        with patch.object(module,'MAX_DEPTH',2):
            w.write_start_element('r');w.write_start_element('c')
            with self.assertRaises(ValueError):w.write_start_element('x')
        w.write_end_element();w.write_end_element();ET.fromstring(w.close())
        w=self.writer();w.write_start_element('r')
        with patch.object(module,'MAX_TEXT',32):
            with self.assertRaises(ValueError):w.write_text('&'*10)
        w.write_text('ok');w.write_end_element();self.assertEqual(ET.fromstring(w.close()).text,'ok')
        w=self.writer()
        with patch.object(module,'MAX_NODES',1):
            w.write_start_element('r')
            with self.assertRaises(ValueError):w.write_comment('x')
    def test_namespace_rejections_and_no_external_entity_api(self):
        w=self.writer();w.write_start_element('root')
        for prefix,uri in [('xml','urn:bad'),('p','http://www.w3.org/XML/1998/namespace'),('xmlns','urn:x'),('p','')]:
            with self.assertRaises(ValueError):w.write_namespace_mapping(prefix,uri)
        with self.assertRaises(ValueError):w.write_attribute('xmlns:p','urn:x')
        for method in ['WriteDocumentType','WriteEntityReference','OpenStream']:
            with self.assertRaises(ValueError):w.get_method(method)
    def test_indent_property_applies_at_next_initialization(self):
        w=Writer();self.assertTrue(w.get_member('Indent'));w.set_string()
        w.set_member('Отступ',False);w.write_start_element('r');w.write_start_element('c');w.write_end_element();w.write_end_element()
        self.assertIn('\n',w.close())
        w.set_string();w.write_start_element('r');w.write_start_element('c');w.write_end_element();w.write_end_element()
        self.assertEqual(w.close(),'<r><c/></r>')
        self.assertFalse(w.get_member('Settings').get_member('Indent'))
    def test_writer_namespace_context_is_snapshot(self):
        w=self.writer();w.write_start_element('root');w.write_namespace_mapping('p','urn:a')
        context=w.get_member('NamespaceContext');w.write_start_element('child');w.write_namespace_mapping('p','urn:b')
        self.assertEqual(context.lookup_namespace_uri('p'),'urn:a')
        self.assertEqual(w.get_member('NamespaceContext').lookup_namespace_uri('p'),'urn:b')
    def test_file_close_failure_releases_descriptor(self):
        with tempfile.TemporaryDirectory(prefix='xml-writer-test-') as tmp:
            path=Path(tmp)/'a.xml'
            w=Writer();w.open_file(str(path),'windows-1251');stream=w._stream
            w.write_start_element('r');w.write_text('😀');w.write_end_element()
            with self.assertRaises(UnicodeError):w.close()
            self.assertTrue(stream.closed);self.assertIsNone(w._stream)
            w.open_file(str(path));stream=w._stream;w.write_start_element('r')
            with self.assertRaises(ValueError):w.close()
            self.assertTrue(stream.closed)
            w.open_file(str(path));stream=w._stream;w.write_start_element('r');w.write_end_element()
            wrapper=Mock(wraps=stream);wrapper.write.side_effect=OSError('owned injected failure');w._stream=wrapper
            with self.assertRaises(ValueError):w.close()
            self.assertTrue(stream.closed);self.assertIsNone(w._stream)
    def test_reset_inherited_default_namespace(self):
        w=self.writer();w.write_start_element('root','urn:r');w.write_namespace_mapping('','urn:r')
        w.write_start_element('child','');w.write_end_element();w.write_end_element()
        root=ET.fromstring(w.close());self.assertEqual(root.tag,'{urn:r}root');self.assertEqual(root[0].tag,'child')
    def test_reader_whitespace_setting_changes_during_iteration(self):
        from yadinassi.xml_io import BSLXMLReader, BSLXMLNodeType
        reader=BSLXMLReader();reader.set_string('<r>  <x/> </r>');reader.read()
        reader.set_member('IgnoreWhitespace',False);reader.read()
        self.assertEqual(reader.get_member('Value'),'  ')
        reader.set_member('IgnoreWhitespace',True);reader.read()
        self.assertEqual(reader.get_member('NodeType'),BSLXMLNodeType.START)
    def test_write_current_does_not_advance_reader(self):
        from yadinassi.xml_io import BSLXMLReader
        reader=BSLXMLReader();reader.set_string('<p:r xmlns:p="urn:r" a="1"><x>Привет</x><![CDATA[<&>]]><!--c--></p:r>')
        w=self.writer();count=0
        while reader.read():
            position=reader._position; current=dict(reader._current)
            w.write_current(reader);count+=1
            self.assertEqual(reader._position,position);self.assertEqual(reader._current,current)
        self.assertGreater(count,5)
        root=ET.fromstring(w.close());self.assertEqual(root.tag,'{urn:r}r');self.assertEqual(root.attrib,{'a':'1'})
        self.assertEqual(root[0].text,'Привет');self.assertEqual(root[0].tail,'<&>')
    def test_bounded_raw_fragment_and_no_entity_resolution(self):
        w=self.writer();w.write_start_element('r');w.write_raw('<a>ok</a>')
        for raw in ('<a>', '<!DOCTYPE x [<!ENTITY boom SYSTEM "file:///never-read">]><x>&boom;</x>', '<x>&missing;</x>'):
            with self.assertRaises(ValueError):w.write_raw(raw)
        w.write_end_element();self.assertEqual(w.close(),'<r><a>ok</a></r>')
    def test_bilingual_host_methods(self):
        w=Writer();w.get_method('УстановитьСтроку')();w.get_method('ЗаписатьНачалоЭлемента')('r')
        w.get_method('ЗаписатьАтрибут')('a','1');w.get_method('ЗаписатьКонецЭлемента')()
        self.assertEqual(w.get_method('Закрыть')(),'<r a="1"/>')

if __name__=='__main__':unittest.main()
