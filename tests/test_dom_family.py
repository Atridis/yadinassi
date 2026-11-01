"""Ordinary DOM workflows and local integrity/resource guards, not native goldens."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi import Interpreter
from yadinassi import dom_nodes as n
from yadinassi.dom_io import BSLDOMBuilder, BSLDOMWriter
from yadinassi.xml_io import BSLXMLReader, BSLXMLReaderSettings
from yadinassi.xml_writer import BSLXMLWriter, BSLXMLWriterSettings
from yadinassi.type_values import type_of
from yadinassi.values import BSLType


class DOMFamilyTests(unittest.TestCase):
    def doc(self): return n.BSLDOMDocument('', 'root')
    def parse(self, text, settings=None):
        reader=BSLXMLReader();reader.set_string(text,settings)
        return BSLDOMBuilder().read(reader)
    def serialize(self,node):
        writer=BSLXMLWriter();writer.set_string(BSLXMLWriterSettings('', '1.0', False))
        BSLDOMWriter().write(node,writer);return writer.close()

    def test_construct_types_aliases_and_scalar_properties(self):
        out=[];vm=Interpreter(out.append)
        vm.execute('Д=Новый ДокументDOM("","корень");У=Д.СоздатьЭлемент("узел");Д.ЭлементДокумента.ДобавитьДочерний(У);Сообщить(У.РодительскийУзел.ИмяУзла);Сообщить(ТипЗнч(У)=Тип("DOMElement"));Сообщить(У.ТипУзла=ТипУзлаDOM.Элемент);Сообщить(У.УзелИдентичен(У));')
        self.assertEqual(out,['корень','Да','Да','Да'])
        self.assertIs(type_of(self.doc()),BSLType.DOM_DOCUMENT)
        self.assertIs(type_of(BSLDOMBuilder()),BSLType.DOM_BUILDER)
        self.assertIs(type_of(BSLDOMWriter()),BSLType.DOM_WRITER)

    def test_child_move_replace_remove_and_live_lists(self):
        d=self.doc();r=d.document_element();a=d.create_element('a');b=d.create_element('b');view=n.BSLDOMNodeList(r)
        self.assertIs(r.append_child(a),a);r.insert_before(b,a)
        self.assertEqual([x._name for x in view],['b','a']);self.assertIs(a.get_member('PreviousSibling'),b)
        self.assertIs(r.replace_child(a,b),b);self.assertIsNone(b._parent)
        self.assertEqual(view.count(),1);self.assertIs(r.remove_child(a),a);self.assertEqual(view.count(),0)

    def test_fragment_splice_and_document_hierarchy_atomicity(self):
        d=self.doc();r=d.document_element();f=d.create_document_fragment()
        f.append_child(d.create_element('a'));f.append_child(d.create_text_node('x'));r.append_child(f)
        self.assertFalse(f._children);self.assertEqual(r.text_content(),'x')
        bad=d.create_document_fragment();bad.append_child(d.create_element('b'));bad.append_child(d.create_element('c'))
        before=tuple(d._children)
        with self.assertRaises(ValueError):d.append_child(bad)
        self.assertEqual(tuple(d._children),before);self.assertEqual(len(bad._children),2)

    def test_cycle_foreign_owner_and_wrong_type_leave_graph(self):
        d=self.doc();r=d.document_element();a=d.create_element('a');r.append_child(a)
        for parent,child in ((a,r),(r,r),(r,self.doc().document_element())):
            with self.assertRaises(ValueError):parent.append_child(child)
        class Fake:
            def __eq__(self,other):raise AssertionError('callback')
        with self.assertRaises(TypeError):r.append_child(Fake())
        self.assertEqual(r._children,[a]);self.assertIs(a._parent,r)

    def test_attribute_map_mutation_and_ownership(self):
        d=self.doc();r=d.document_element();m=n.BSLDOMAttributeMap(r);r.set_attribute('a','one')
        a=d.create_attribute('a');a.set_member('Value','two');old=m.set_named_item(a)
        self.assertEqual(old._data,'one');self.assertIsNone(old._owner_element);self.assertEqual(m.item(0)._data,'two')
        b=d.create_element('b')
        with self.assertRaises(ValueError):b.set_attribute_node(a)
        self.assertIs(m.remove_named_item('a'),a);self.assertEqual(m.count(),0)
        with self.assertRaises(ValueError):m.remove_named_item('a')

    def test_namespace_create_search_and_explicit_mappings(self):
        d=self.doc();r=d.document_element();a=d.create_element('urn:x','p:a');r.append_child(a)
        mapping=r.set_namespace_mapping('p','urn:x')
        self.assertEqual(mapping._uri,n._XMLNS_URI);self.assertIsNone(r.set_namespace_mapping('p','urn:y'))
        self.assertEqual(a.lookup_namespace_uri('p'),'urn:x');self.assertEqual(a.lookup_prefix('urn:x'),'p')
        attr=d.create_attribute('urn:x','p:id');attr.set_member('Value','42');a.set_attribute_node(attr)
        self.assertEqual(a.get_attribute('urn:x','id'),'42');self.assertEqual(d.get_elements('urn:x','a').count(),1)
        r.unset_namespace_mapping('p');self.assertIsNone(mapping._owner_element)
        with self.assertRaises(ValueError):r.set_namespace_mapping('urn:auto')
        with self.assertRaises(ValueError):r.set_namespace_mapping('p','urn:x',True)

    def test_namespace_change_validates_before_mutation(self):
        d=self.doc();r=d.document_element();a=r.set_namespace_mapping('p','urn:x')
        with self.assertRaises(ValueError):a.set_member('Value','')
        self.assertEqual(r.lookup_namespace_uri('p'),'urn:x');self.assertEqual(a._data,'urn:x')
        a.set_member('Value','urn:y');self.assertEqual(r.lookup_namespace_uri('p'),'urn:y')

    def test_text_character_data_split_normalize_unicode(self):
        d=self.doc();r=d.document_element();a=d.create_text_node('я😀xy');r.append_child(a)
        self.assertEqual(a.get_member('Length'),5);self.assertEqual(a.substring_data(1,2),'😀')
        self.assertIsNone(a.split_text(3));b=a._parent._children[1];self.assertEqual((a._data,b._data),('я😀','xy'));self.assertEqual(a.get_member('WholeText'),'я😀xy')
        b.insert_data(1,'z');b.delete_data(0,1);b.append_data('!');b.replace_data(0,1,'Q')
        self.assertEqual(b._data,'Qy!');r.normalize();self.assertEqual(r._children,[a]);self.assertEqual(a._data,'я😀Qy!')
        before=a._data
        with self.assertRaises(UnicodeDecodeError):a.split_text(2)
        self.assertEqual(a._data,before)

    def test_text_content_excludes_comment_and_pi(self):
        d=self.doc();r=d.document_element()
        for child in (d.create_text_node('a'),d.create_comment('c'),d.create_cdata_section('b'),d.create_processing_instruction('task','x')):r.append_child(child)
        self.assertEqual(r.text_content(),'ab');old=list(r._children);r.set_member('TextContent','new')
        self.assertEqual(r.text_content(),'new');self.assertTrue(all(x._parent is None for x in old))

    def test_clone_import_and_document_owner(self):
        d=self.doc();r=d.document_element();r.set_attribute('a','v');r.append_child(d.create_text_node('t'))
        shallow=r.clone_node(False);deep=r.clone_node(True)
        self.assertFalse(shallow._children);self.assertIsNone(shallow.get_attribute('a'));self.assertTrue(deep.is_equal_node(r));self.assertIsNot(deep,r)
        other=self.doc();copy=other.import_node(r,True);other.document_element().append_child(copy)
        self.assertIs(copy._owner,other);self.assertIs(copy._attrs[0]._owner,other);self.assertIs(copy._children[0]._owner,other)
        cloned=d.clone_node(True);self.assertIs(cloned.document_element()._owner,cloned)
        with self.assertRaises(ValueError):other.import_node(d,True)

    def test_document_queries_snapshot_while_child_lists_remain_live(self):
        d=self.doc();r=d.document_element();view=d.get_elements('x')
        self.assertEqual(view.count(),0);a=d.create_element('x');r.append_child(a)
        self.assertEqual(view.count(),0);self.assertIsNone(view.item(0));fresh=d.get_elements('x');self.assertIs(fresh.item(0),a);r.remove_child(a);self.assertEqual(fresh.count(),1)
        out=[];Interpreter(out.append).execute('D=New DOMDocument("","r");D.DocumentElement.AppendChild(D.CreateElement("x"));For Each N In D.DocumentElement.ChildNodes Do Сообщить(N.NodeName);EndDo;')
        self.assertEqual(out,['x'])

    def test_measured_document_query_and_builder_defaults_are_local(self):
        d=self.doc();r=d.document_element()
        for node in (d.create_element('urn:n','p:a'), d.create_element('a'), d.create_element('b')):r.append_child(node)
        self.assertEqual(d.get_elements('a').count(),2)
        self.assertEqual(d.get_elements('urn:n','a').count(),2)
        self.assertEqual(d.get_elements('missing','z').count(),0)
        # Existing element query behavior is not generalized from Document facts.
        self.assertEqual(r.get_elements('urn:n','a').count(),1)
        reader=BSLXMLReader();reader.set_string('<r><![CDATA[a<b]]><!--c--><?task x?></r>')
        settings=reader._settings;self.assertTrue(settings.ignore_comments)
        doc=BSLDOMBuilder().read(reader)
        self.assertEqual([x._kind for x in doc.document_element()._children],[n.K.TEXT,n.K.COMMENT,n.K.PI])
        self.assertIs(reader._settings,settings);self.assertTrue(settings.ignore_comments);self.assertFalse(reader.read())
        regular=BSLXMLReader();regular.set_string('<r><!--c--></r>');kinds=[]
        while regular.read():kinds.append(regular._current['kind'])
        from yadinassi.xml_io import T
        self.assertNotIn(T.COMMENT,kinds)
        declaration=BSLXMLReader();declaration.set_string('<?xml version="1.0" encoding="UTF-8"?><r/>')
        BSLDOMBuilder().read(declaration)
        self.assertEqual((declaration._version,declaration._xml_encoding),('1.0','UTF-8'))
        broken=BSLXMLReader();broken.set_string('<?xml version="1.0" encoding="UTF-8"?><r>')
        saved=(broken._version,broken._xml_encoding,broken._tokens,broken._position)
        with self.assertRaises(ValueError):BSLDOMBuilder().read(broken)
        self.assertEqual((broken._version,broken._xml_encoding,broken._tokens,broken._position),saved)
        other=self.doc();r.set_attribute('k','v')
        self.assertEqual(other.import_node(r,False).get_attribute('k'),'v')

    def test_budget_before_creation_clone_or_text_mutation(self):
        d=self.doc();r=d.document_element();r.append_child(d.create_text_node('a'));before=(d._allocated,d._units)
        with mock.patch.object(n,'MAX_NODES',d._allocated):
            with self.assertRaises(ValueError):d.create_element('more')
            with self.assertRaises(ValueError):r.clone_node(True)
        self.assertEqual((d._allocated,d._units),before)
        with mock.patch.object(n,'MAX_UNITS',d._units):
            with self.assertRaises(ValueError):r.set_member('TextContent','replacement')
        self.assertEqual(r.text_content(),'a');self.assertEqual((d._allocated,d._units),before)

    def test_depth_guard_and_iterative_subtree_work_budget(self):
        d=self.doc();r=d.document_element();a=d.create_element('a');b=d.create_element('b');a.append_child(b)
        with mock.patch.object(n,'MAX_DEPTH',2):
            with self.assertRaises(ValueError):r.append_child(a)
        self.assertIsNone(a._parent);self.assertEqual(a._children,[b])
        r.append_child(a)
        with mock.patch.object(n,'MAX_WORK',2):
            with self.assertRaises(ValueError):r.clone_node(True)
        self.assertEqual(r._children,[a])

    def test_xml_read_settings_preserved_and_borrowed_reader(self):
        reader=BSLXMLReader();reader.set_string('<r><![CDATA[x]]><!--c--><?task z?></r>',BSLXMLReaderSettings(ignore_comments=False,cdata_as_text=False))
        d=BSLDOMBuilder().read(reader);self.assertEqual([x._kind for x in d.document_element()._children],[n.K.CDATA,n.K.COMMENT,n.K.PI])
        self.assertIsNotNone(reader._source);self.assertFalse(reader.read());reader.close();self.assertIsNone(reader._source)

    def test_dtd_external_entity_and_malformed_input_are_rejected(self):
        for source in ('<!DOCTYPE r [<!ENTITY x "abc">]><r>&x;</r>', '<!DOCTYPE r SYSTEM "file:///not-used"><r/>','<r>'):
            reader=BSLXMLReader();reader.set_string(source)
            with self.assertRaises(ValueError):BSLDOMBuilder().read(reader)
            self.assertEqual(reader._position,-1)

    def test_roundtrip_text_attributes_namespace_and_fragment(self):
        d=n.BSLDOMDocument('urn:x','p:r');r=d.document_element();r.set_attribute('a','<&"я');r.append_child(d.create_text_node('😀<&'))
        parsed=self.parse(self.serialize(d));e=parsed.document_element()
        self.assertEqual((e._uri,e._local,e.get_attribute('a'),e.text_content()),('urn:x','r','<&"я','😀<&'))
        f=d.create_document_fragment();f.append_child(d.create_element('a'));f.append_child(d.create_element('b'))
        writer=BSLXMLWriter();writer.set_string();writer.write_start_element('r');BSLDOMWriter().write(f,writer);writer.write_end_element()
        self.assertEqual(self.parse(writer.close()).document_element().get_elements('*').count(),2)

    def test_nested_writer_preserves_no_namespace_children(self):
        d=self.doc();fragment=d.create_document_fragment()
        fragment.append_child(d.create_element('a'));fragment.append_child(d.create_element('b'))
        prefixed=n.BSLDOMDocument('urn:p','p:root');prefixed.document_element().append_child(prefixed.create_element('','child'))
        for node in (d.document_element(),fragment,prefixed.document_element()):
            writer=BSLXMLWriter();writer.set_string();writer.write_start_element('outer')
            writer.write_namespace_mapping('','urn:outer');BSLDOMWriter().write(node,writer);writer.write_end_element()
            parsed=self.parse(writer.close());outer=parsed.document_element()
            self.assertEqual(outer._uri,'urn:outer')
            if node is prefixed.document_element():
                self.assertEqual(outer._children[0]._uri,'urn:p')
                self.assertEqual(outer._children[0]._children[0]._uri,'')
            else:self.assertTrue(all(child._uri=='' for child in outer._children))

    def test_writer_failure_does_not_commit_partial_target(self):
        d=self.doc();d.document_element().append_child(d.create_comment('invalid--comment'))
        w=BSLXMLWriter();w.set_string();w.write_start_element('before');before=(w._cost,w._nodes,len(w._roots),dict(w._stack[-1]))
        with self.assertRaises(ValueError):BSLDOMWriter().write(d,w)
        self.assertEqual((w._cost,w._nodes,len(w._roots),dict(w._stack[-1])),before)
        w.write_text('ok');w.write_end_element();self.assertIn('ok',w.close())

    def test_file_roundtrip_owns_no_new_path_authority(self):
        with tempfile.TemporaryDirectory(prefix='dom-owned-') as tmp:
            p=Path(tmp)/'a.xml';d=self.doc();d.document_element().set_member('TextContent','я😀')
            w=BSLXMLWriter();w.open_file(str(p));BSLDOMWriter().write(d,w)
            self.assertIsNotNone(w._stream);w.close()
            r=BSLXMLReader();r.open_file(str(p));copy=BSLDOMBuilder().read(r);r.close()
            self.assertEqual(copy.document_element().text_content(),'я😀')

    def test_exact_xml_adapter_admission_and_readonly_properties(self):
        class Reader(BSLXMLReader):pass
        class Writer(BSLXMLWriter):pass
        with self.assertRaises(TypeError):BSLDOMBuilder().read(Reader())
        with self.assertRaises(TypeError):BSLDOMWriter().write(self.doc(),Writer())
        d=self.doc()
        with self.assertRaises(Exception):d.set_member('DocumentElement',None)
        self.assertIsNotNone(d.document_element())


if __name__=='__main__':unittest.main()
