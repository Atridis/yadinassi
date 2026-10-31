"""Ordinary XML reading plus bounded parser security, only owned temp paths."""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi import xml_io as x


class XMLReaderTests(unittest.TestCase):
    def reader(self, text, settings=None):
        r = x.BSLXMLReader(); r.set_string(text, settings); return r

    def test_document_tokens_attributes_namespaces(self):
        r=self.reader('<r xmlns="urn:r" xmlns:p="urn:p" a="1" p:b="2"><p:c>Я&amp;&lt;</p:c><e/></r>')
        self.assertTrue(r.read()); self.assertEqual(r.get_member('NodeType'),x.T.START)
        self.assertEqual(r.get_member('NamespaceURI'),'urn:r')
        self.assertEqual(r.attribute_count(),D(2))
        self.assertEqual(r.get_attribute('b','urn:p'),'2')
        self.assertIsNone(r.get_attribute('missing'))
        self.assertEqual(r.attribute_name(D(1)),'p:b')
        context=r.get_member('NamespaceContext')
        self.assertEqual(context.lookup_prefix('urn:p'),'p')
        self.assertEqual(context.lookup_namespace_uri(''),'urn:r')
        self.assertEqual(context.prefixes('urn:p').items,['p'])
        self.assertIn('urn:r',context.namespace_uris().items)
        self.assertEqual(context.namespace_mappings().get('p'),'urn:p')
        self.assertTrue(r.first_attribute()); self.assertEqual(r.get_member('Name'),'a')
        self.assertTrue(r.read_attribute()); self.assertEqual(r.get_member('Prefix'),'p')
        self.assertFalse(r.read_attribute()); self.assertTrue(r.read())
        self.assertEqual(r.get_member('Name'),'p:c')
        self.assertTrue(r.read()); self.assertEqual(r.get_member('Value'),'Я&<')
        self.assertTrue(r.read()); self.assertEqual(r.get_member('NodeType'),x.T.END)
        self.assertTrue(r.read()); self.assertEqual(r.get_member('Name'),'e')
        self.assertTrue(r.read()); self.assertEqual(r.get_member('NodeType'),x.T.END)
        self.assertTrue(r.read()); self.assertFalse(r.read()); self.assertFalse(r.read())
        self.assertEqual(r.get_member('NodeType'),x.T.NONE)
        self.assertEqual(context.lookup_prefix('urn:p'),'p')

    def test_skip_content_and_attribute_cursor(self):
        r=self.reader('<!--a--><?p v?><r><skip a="1"><deep/></skip><keep/></r>')
        self.assertEqual(r.move_to_content(),x.T.START)
        self.assertEqual(r.get_member('Name'),'r')
        r.read(); r.first_attribute(); self.assertIsNone(r.skip())
        self.assertEqual(r.get_member('Name'),'skip')
        self.assertEqual(r.get_member('NodeType'),x.T.END)
        r.read(); self.assertEqual(r.get_member('Name'),'keep')
        r.skip(); r.read(); self.assertEqual(r.get_member('Name'),'r')
        self.assertEqual(r.get_member('NodeType'),x.T.END)

    def test_settings_declaration_cdata_whitespace(self):
        settings=x.BSLXMLReaderSettings(ignore_declaration=False,ignore_whitespace=False,use_whitespace=True)
        r=self.reader('<?xml version="1.0" encoding="UTF-8"?><a> <![CDATA[x<y]]><!--c--><?p v?></a>',settings)
        types=[]; values=[]
        while r.read(): types.append(r.get_member('NodeType')); values.append(r.get_member('Value'))
        self.assertEqual(types,[x.T.DECLARATION,x.T.START,x.T.WHITESPACE,x.T.CDATA,x.T.COMMENT,x.T.PI,x.T.END])
        self.assertEqual(values[3],'x<y')
        self.assertEqual(r.get_member('XMLVersion'),'1.0')
        settings=x.BSLXMLReaderSettings(cdata_as_text=True,ignore_comments=True,ignore_pi=True)
        r=self.reader('<a><![CDATA[x]]><!--c--><?p v?></a>',settings)
        self.assertTrue(r.read()); self.assertTrue(r.read()); self.assertEqual(r.get_member('NodeType'),x.T.TEXT)
        self.assertTrue(r.read()); self.assertEqual(r.get_member('NodeType'),x.T.END)

    def test_preserved_space_language_and_scopes(self):
        r=self.reader('<r xml:space="preserve" xml:lang="ru" xmlns:p="one"> <a xmlns:p="two"/> </r>')
        r.read(); root=r.get_member('NamespaceContext')
        r.read(); self.assertEqual(r.get_member('Value'),' '); self.assertEqual(r.get_member('Lang'),'ru')
        r.read(); self.assertEqual(r.get_member('NamespaceContext').lookup_namespace_uri('p'),'two')
        r.read(); r.read(); self.assertEqual(r.get_member('NamespaceContext').lookup_namespace_uri('p'),'one')
        self.assertEqual(root.lookup_namespace_uri('p'),'one')

    def test_owned_files_encoding_and_descriptor_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='yadinassi-xml-reader-') as temp:
            path=Path(temp)/'doc.xml'; r=x.BSLXMLReader()
            for enc in ('utf-8-sig','utf-16','cp1251'):
                declaration='windows-1251' if enc=='cp1251' else ('UTF-16' if enc=='utf-16' else 'UTF-8')
                path.write_bytes(('<?xml version="1.0" encoding="'+declaration+'"?><a>Я</a>').encode(enc))
                r.open_file(str(path)); path.unlink() # snapshot owns no descriptor
                r.read(); r.read(); self.assertEqual(r.get_member('Value'),'Я'); r.close()
            with self.assertRaises(ValueError): r.open_file(temp)
            with self.assertRaises(ValueError): r.open_file(str(path))

    def test_lifecycle_replace_and_closed(self):
        r=x.BSLXMLReader()
        with self.assertRaises(ValueError): r.read()
        r.set_string('<old><x/></old>'); r.read(); r.set_string('<new/>')
        r.read(); self.assertEqual(r.get_member('Name'),'new')
        r.close(); r.close(); self.assertEqual(r.get_member('NodeType'),x.T.NONE)
        with self.assertRaises(ValueError): r.read()

    def test_entities_dtd_and_namespace_fail_closed(self):
        for text in ('<!DOCTYPE a><a/>', '<!DOCTYPE a SYSTEM "file:///not-read"><a/>',
                     '<!DOCTYPE a [<!ENTITY x "hello">]><a>&x;</a>',
                     '<!DOCTYPE a [<!ENTITY x SYSTEM "https://not-contacted">]><a>&x;</a>',
                     '<a>&unknown;</a>', '<p:a/>', '<a p:b="1"/>', '<a><b></a>',
                     '<?xml version="1.1"?><a/>'):
            with self.subTest(text=text),self.assertRaises(ValueError): self.reader(text).read()
        for enc in ('utf-16','utf-8-sig'):
            r=x.BSLXMLReader(); r._set_source('<!DOCTYPE a><a/>'.encode(enc),None,None)
            with self.assertRaises(ValueError): r.read()

    def test_resource_budgets(self):
        with patch.object(x,'MAX_XML_DEPTH',3):
            with self.assertRaises(ValueError): self.reader('<a><a><a><a/></a></a></a>').read()
        with patch.object(x,'MAX_XML_NODES',3):
            with self.assertRaises(ValueError): self.reader('<a><b/><c/></a>').read()
        with patch.object(x,'MAX_XML_BYTES',4):
            with self.assertRaises(ValueError): self.reader('<abc/>')
        with patch.object(x,'MAX_NAMESPACE_BINDINGS',2):
            with self.assertRaises(ValueError): self.reader('<a xmlns:p="p"><b/></a>').read()

    def test_bilingual_interpreter_optional_types_errors(self):
        vm=Interpreter()
        vm.execute('r=Новый ЧтениеXML; s=Новый ПараметрыЧтенияXML(,,,,Ложь); '
                   'r.УстановитьСтроку("<a b=""1""/>",s,); r.Прочитать(); '
                   'name=r.Имя; n=r.КоличествоАтрибутов();')
        self.assertEqual(vm.execute('name'),'a'); self.assertEqual(vm.execute('n'),D(1))
        self.assertTrue(vm.execute('(TypeOf(r)=Type("XMLReader"))'))
        self.assertTrue(vm.execute('(r.ТипУзла=ТипУзлаXML.НачалоЭлемента)'))
        self.assertTrue(vm.execute('(TypeOf(r.NamespaceContext)=Type("XMLNamespaceContext"))'))
        for source in ('r._source', 'r.Name="x"', 'New XMLReaderSettings("1.1")',
                       'r.SetString("<a/>",,New Array)'):
            with self.assertRaises(BSLError): vm.execute(source)
        vm.execute('r.ИгнорироватьПробелы=Ложь;')
        self.assertFalse(vm.execute('r.IgnoreWhitespace'))

    def test_attribute_and_whitespace_global_budgets_and_settings_copy(self):
        settings=x.BSLXMLReaderSettings()
        r=self.reader('<a> <b/> </a>',settings)
        r.read(); r.set_member('IgnoreWhitespace',False)
        self.assertTrue(settings.ignore_whitespace)
        self.assertTrue(r.read()); self.assertEqual(r.get_member('Value'),' ')
        r.set_member('IgnoreWhitespace',True); r.read(); r.read(); r.read()
        self.assertEqual(r.get_member('NodeType'),x.T.END)
        with patch.object(x,'MAX_XML_NODES',6):
            with self.assertRaises(ValueError): self.reader('<a x="1" y="2" z="3"><b x="1" y="2" z="3" q="4"/></a>').read()
        r=self.reader('<a x="1"/>'); r.read()
        for index in (D('NaN'),D('Infinity'),D('-1'),D('0.5')):
            with self.assertRaises((TypeError,ValueError)): r.get_attribute(index)
        self.assertEqual(r.attribute_value('x'),'1')

    def test_writecurrent_snapshot_does_not_advance(self):
        r=self.reader('<p:r xmlns:p="urn:p" a="1"/>'); r.read()
        event=r._writer_current()
        self.assertEqual(event['attrs'],[('xmlns:p','urn:p'),('a','1')])
        self.assertEqual(event['kind'],'start'); self.assertEqual(r.get_member('Name'),'p:r')

if __name__=='__main__': unittest.main()
