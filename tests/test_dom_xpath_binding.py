import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.dom_io import BSLDOMBuilder
from yadinassi.xml_io import BSLXMLReader
from yadinassi.dom_xpath import BSLDOMNamespaceResolver, BSLDOMXPathResult
from yadinassi.dom_xpath_engine import parse

class XPathBindingTests(unittest.TestCase):
    def doc(self, text='<root><group><item id="a"/><item id="b"/></group><group><item id="c"/></group></root>'):
        reader=BSLXMLReader();reader.set_string(text);return BSLDOMBuilder().read(reader)
    def nodes(self,d,path,context=None,resolver=None):
        v=d.evaluate_xpath_expression(path,context or d,resolver or BSLDOMNamespaceResolver(d))
        result=[]
        while True:
            n=v.iterate_next()
            if n is None:return result
            result.append(n)
    def test_absolute_root_and_self(self):
        d=self.doc();self.assertEqual(self.nodes(d,'/'),[d]);self.assertEqual(self.nodes(d,'.'),[d])
    def test_parent_and_relative_steps(self):
        d=self.doc();n=d.document_element()._children[0]
        self.assertEqual(self.nodes(d,'../group',n),d.document_element()._children)
    def test_position_per_parent(self):
        d=self.doc();self.assertEqual([n.get_attribute('id') for n in self.nodes(d,'//item[1]')],['a','c'])
    def test_position_chaining_and_last(self):
        d=self.doc();self.assertEqual([n.get_attribute('id') for n in self.nodes(d,'//item[last()][1]')],['b','c'])
    def test_zero_and_absent_positions(self):
        d=self.doc();self.assertEqual(self.nodes(d,'//item[0]'),[]);self.assertEqual(self.nodes(d,'//item[99]'),[])
    def test_attribute_existence_and_equality(self):
        d=self.doc();self.assertEqual(len(self.nodes(d,'//item[@id]')),3);self.assertEqual(len(self.nodes(d,"//item[@id='b']")),1)
    def test_predicate_quote_contains_slash_and_bracket(self):
        d=self.doc('<root><item id="x/y]z"/></root>');self.assertEqual(len(self.nodes(d,"//item[@id='x/y]z']")),1)
    def test_attribute_axis_excludes_namespaces(self):
        d=self.doc('<root xmlns:p="urn:p" id="a"/>');self.assertEqual([x._name for x in self.nodes(d,'//@*')],['id'])
    def test_default_namespace_is_not_unprefixed(self):
        d=self.doc('<root xmlns="urn:d"><item/></root>');self.assertEqual(self.nodes(d,'/root/item'),[]);self.assertEqual(len(self.nodes(d,'/xmlns:root/xmlns:item')),1)
    def test_prefix_mapping_uses_uri_not_spelling(self):
        d=self.doc('<a:root xmlns:a="urn:p"><a:item/></a:root>');r=BSLDOMNamespaceResolver('b','urn:p');self.assertEqual(len(self.nodes(d,'/b:root/b:item',resolver=r)),1)
    def test_namespaced_wildcard(self):
        d=self.doc('<root xmlns:p="urn:p"><p:a/><b/></root>');self.assertEqual(len(self.nodes(d,'//p:*')),1)
    def test_unknown_prefix_even_empty_path(self):
        d=self.doc()
        with self.assertRaises(ValueError):self.nodes(d,'/absent/x:item')
    def test_context_owner_guard(self):
        d=self.doc()
        with self.assertRaises(ValueError):d.evaluate_xpath_expression('.',self.doc(),BSLDOMNamespaceResolver(d))
    def test_closed_resolver_argument_types(self):
        for args in ((),(None,),('a',),('a',''),('xml','wrong'),('a','uri','extra')):
            with self.subTest(args=args),self.assertRaises((ValueError,TypeError)):BSLDOMNamespaceResolver(*args)
    def test_no_scalar_or_general_expression(self):
        d=self.doc()
        for path in ('count(//item)','//item | //group','$x','//item[contains(@id,"a")]','//item/@id[true()]','child::item','//item[1+1]'):
            with self.subTest(path=path),self.assertRaises(ValueError):self.nodes(d,path)
    def test_malformed_expressions(self):
        for path in ('',' ','///','/root/','//item[','//item]','//item[[@x]]','//item[@x="a]'):
            with self.subTest(path=path),self.assertRaises(ValueError):parse(path)
    def test_expression_step_and_predicate_limits(self):
        for path in ('a'*4097,'/'.join(['x']*129),'x'+('[1]'*17)):
            with self.subTest(path=path[:20]),self.assertRaises(ValueError):parse(path)
    def test_shared_work_budget(self):
        d=self.doc()
        with patch('yadinassi.dom_xpath_engine.MAX_WORK',2),self.assertRaises(ValueError):self.nodes(d,'//item')
    def test_iterator_identity_mutation_and_exhaustion(self):
        d=self.doc();v=d.evaluate_xpath_expression('//item',d,BSLDOMNamespaceResolver(d));first=d.document_element()._children[0]._children[0]
        first.set_attribute('id','mutated');d.document_element().append_child(d.create_element('item'))
        self.assertFalse(v.get_member('InvalidIteratorState'));self.assertIs(v.iterate_next(),first)
        v.iterate_next();v.iterate_next();self.assertIsNone(v.iterate_next());self.assertIsNone(v.iterate_next())
    def test_type_properties_readonly_and_nonconstructor_result(self):
        v=BSLDOMXPathResult(())
        with self.assertRaises(ValueError):v.set_member('InvalidIteratorState',True)
        vm=Interpreter(lambda value:None)
        with self.assertRaises(Exception):vm.execute('V=New DOMXPathResult;')
