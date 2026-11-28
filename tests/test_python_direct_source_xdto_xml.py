"""Source string-only XDTO XML staging never grants file IO or a legacy VM."""
from decimal import Decimal
import unittest
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_python_direct_source_xdto_graphs as graphs
from yadinassi.formats.xml import xml_io,xml_writer,xdto_io,xdto_values
from yadinassi.types.values import HostFunction

class SourceXDTOXMLTests(unittest.TestCase):
    setUp=basic.SourceScalarXDTOTests.setUp
    app=graphs.GraphXDTOTests.app
    prepared=graphs.GraphXDTOTests.prepared
    def ready(self):
        app=self.prepared();app.interpreter.execute('W=New XMLWriter;W.SetString();R=New XMLReader;');return app
    def write(self,vm,value='P'):
        vm.execute('XDTOFactory.WriteXML(W,'+value+',"Root","urn:owned:records");S=W.Close();R.SetString(S);')
    def test_nested_object_scalar_list_roundtrip(self):
        app=self.ready();vm=app.interpreter
        vm.execute('P.Label="parent";C.Label="first";D.Label="second";P.Child=C;P.Children.Add(D);P.Labels.Add("a<&");P.Labels.Add("б");')
        self.write(vm);vm.execute('Copy=XDTOFactory.ReadXML(R,T);R.Close();')
        self.assertEqual(vm.execute('Copy.Label;'),'parent')
        self.assertEqual(vm.execute('Copy.Child.Label;'),'first')
        self.assertEqual(vm.execute('Copy.Children.Get(0).Label;'),'second')
        self.assertEqual(vm.execute('Copy.Labels.Get(0);'),'a<&')
        self.assertEqual(vm.execute('Copy.Labels.Get(1);'),'б')
        vm.execute('Copy.Child.Label="changed";')
        self.assertEqual(vm.execute('P.Child.Label;'),'first')
    def test_scalar_alias_roundtrip(self):
        app=self.ready();vm=app.interpreter
        vm.execute('ScalarType=XDTOFactory.Type("urn:owned:records","Code");V=XDTOFactory.Create(ScalarType,"alias");')
        self.write(vm,'V');vm.execute('Copy=XDTOFactory.ReadXML(R,ScalarType);')
        self.assertEqual(vm.execute('Copy.Value;'),'alias')
    def test_nullable_child_roundtrip(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Child=Null;')
        self.write(vm);vm.execute('Copy=XDTOFactory.ReadXML(R,T);')
        self.assertIsNone(vm.execute('Copy.Child;'))
    def test_bilingual_surface(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('W=Новый ЗаписьXML;W.УстановитьСтроку();ФабрикаXDTO.ЗаписатьXML(W,P,"Root","urn:owned:records");S=W.Закрыть();R=Новый ЧтениеXML;R.УстановитьСтроку(S);Copy=ФабрикаXDTO.ПрочитатьXML(R,T);R.Закрыть();')
        self.assertIsNotNone(vm.variables['copy'])
    def test_file_stream_settings_json_and_general_xml_denied(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or '/tmp/never-written')
        for code in ('W.OpenFile(Touch());','R.OpenFile(Touch());','W.OpenStream(Touch());',
                     'W.WriteStartElement(Touch());','R.Read();','New XMLWriterSettings;',
                     'New XMLReaderSettings;','XDTOFactory.ReadJSON(R,T);','XDTOFactory.WriteJSON(W,P);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
    def test_arity_refused_before_argument_effects(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or '')
        for code in ('New XMLReader(Touch());','New XMLWriter(Touch());','W.SetString(Touch());',
                     'R.SetString(Touch(),Touch());','XDTOFactory.ReadXML(R);','XDTOFactory.WriteXML(W,P,Touch());'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
    def test_foreign_and_forged_receivers_denied(self):
        app=self.ready();other=self.ready();vm=app.interpreter
        vm.variables['foreign']=other.interpreter.variables['w'];vm.variables['forged']=xml_writer.BSLXMLWriter()
        for code in ('Foreign.SetString();','XDTOFactory.WriteXML(Foreign,P,"Root","urn:x");','Forged.SetString();'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_write_failure_keeps_empty_writer_reusable(self):
        app=self.ready();vm=app.interpreter
        # Required Flat.Label is absent. Native validation must fail before writer publication.
        before=dict(vm.variables['w'].__dict__)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteXML(W,C,"Child","urn:owned:records");')
        self.assertEqual(vm.variables['w'].__dict__,before)
        vm.execute('C.Label="ok";XDTOFactory.WriteXML(W,C,"Child","urn:owned:records");S=W.Close();')
        self.assertIn('ok',vm.variables['s'])
    def test_read_wrong_type_keeps_reader_and_counters(self):
        app=self.ready();vm=app.interpreter
        vm.execute('R.SetString("<Root><Unknown/></Root>");')
        reader=vm.variables['r'];before=dict(reader.__dict__);counts=(app.xdto.factory._nodes,app.xdto.factory._units)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadXML(R,T);')
        self.assertEqual(reader.__dict__,before)
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),counts)
        vm.execute('R.SetString("<Root/>");Copy=XDTOFactory.ReadXML(R,T);')
        self.assertIsNotNone(vm.variables['copy'])
    def test_dtd_and_entity_input_refused_without_allocation(self):
        for text in ('<!DOCTYPE Root [<!ENTITY evil "boom">]><Root>&evil;</Root>',
                     '<!DOCTYPE Root SYSTEM "https://external.invalid/evil"><Root/>'):
            app=self.ready();vm=app.interpreter;vm.variables['input']=text
            before=(app.xdto.factory._nodes,app.xdto.factory._units)
            with self.subTest(text=text),self.assertRaises(basic.DENIED):
                vm.execute('R.SetString(Input);XDTOFactory.ReadXML(R,T);')
            self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_failed_read_quota_does_not_publish_partial_graph(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="quota";');self.write(vm)
        before=(app.xdto.factory._nodes,app.xdto.factory._units);reader=dict(vm.variables['r'].__dict__)
        with patch.object(xdto_io,'MAX_NODES',before[0]+1):
            with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadXML(R,T);')
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
        self.assertEqual(vm.variables['r'].__dict__,reader)
        vm.execute('Copy=XDTOFactory.ReadXML(R,T);')
        self.assertEqual(vm.execute('Copy.Label;'),'quota')
    def test_writer_output_quota_preserves_destination(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="some long text";');before=dict(vm.variables['w'].__dict__)
        with patch.object(xml_writer,'MAX_TEXT',8):
            with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");')
        self.assertEqual(vm.variables['w'].__dict__,before)
        self.write(vm)
    def test_second_document_requires_reset(self):
        app=self.ready();vm=app.interpreter;vm.execute('XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");')
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");')
        vm.execute('S=W.Close();W.SetString();XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");')
    def test_reader_position_not_reused_until_setstring(self):
        app=self.ready();vm=app.interpreter;vm.execute('R.SetString("<Root/>");Copy=XDTOFactory.ReadXML(R,T);')
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadXML(R,T);')
        vm.execute('R.SetString("<Root/>");Copy=XDTOFactory.ReadXML(R,T);')
    def test_closed_app_receivers_not_reowned(self):
        app=self.ready();other=self.ready();receiver=other.interpreter.variables['w'];other.close()
        app.interpreter.variables['old']=receiver
        with self.assertRaises(basic.DENIED):app.interpreter.execute('Old.SetString();')
    def test_parser_hook_rejected_before_argument(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or '<Root/>')
        with patch.object(xml_io.expat,'ParserCreate',lambda *a,**k:effects.append('parser')):
            with self.assertRaises(basic.DENIED):vm.execute('R.SetString(Touch());')
        self.assertEqual(effects,[])
    def test_reader_source_late_mutation_prevents_read(self):
        app=self.ready();vm=app.interpreter;vm.execute('R.SetString("<Root/>");');before=app.xdto.factory._nodes
        def touch():vm.variables['r']._source='<Root><bad/></Root>';return vm.variables['t']
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadXML(R,Touch());')
        self.assertEqual(app.xdto.factory._nodes,before)
    def test_writer_stream_tamper_never_calls_stream(self):
        app=self.ready();vm=app.interpreter;effects=[]
        class Stream:
            def write(self,*a):effects.append('write')
            def close(self):effects.append('close')
        writer=vm.variables['w'];writer._stream=Stream()
        try:
            for code in ('W.Close();','W.SetString();','XDTOFactory.WriteXML(W,P,"Root","urn:x");'):
                with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
            self.assertEqual(effects,[])
        finally:writer._stream=None
    def test_writer_late_mutation_prevents_publication(self):
        app=self.ready();vm=app.interpreter
        def touch():vm.variables['w']._roots=[];return 'urn:owned:records'
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteXML(W,P,"Root",Touch());')
        self.assertEqual(vm.variables['w']._roots,[])
    def test_bad_receiver_field_key_never_compared(self):
        app=self.ready();vm=app.interpreter;effects=[]
        class Key:
            def __hash__(self):return hash('_source')
            def __eq__(self,other):effects.append('eq');return False
        fields=vm.variables['r'].__dict__;fields.pop('_source');fields[Key()]='<Root/>';effects.clear()
        with self.assertRaises(basic.DENIED):vm.execute('R.SetString("<Root/>");')
        self.assertEqual(effects,[])
    def test_saved_methods_revalidate_contract(self):
        app=self.ready();vm=app.interpreter;vm.execute('Set=R.SetString;Set("<Root/>");Read=XDTOFactory.ReadXML;Copy=Read(R,T);')
        self.assertIsNotNone(vm.variables['copy'])
        vm.execute('Write=XDTOFactory.WriteXML;Write(W,P,"Root","urn:owned:records");Close=W.Close;S=Close();')
        self.assertIn('Root',vm.variables['s'])
    def test_saved_method_reference_metadata_no_callbacks(self):
        app=self.ready();vm=app.interpreter;vm.execute('Set=R.SetString;');effects=[]
        class Evil:
            def __bool__(self):effects.append('bool');return False
        vm.variables['set'].reference_parameters=Evil()
        with self.assertRaises(basic.DENIED):vm.execute('Set("<Root/>");')
        self.assertEqual(effects,[])
    def test_generic_copy_dispatch_not_invoked(self):
        import copy
        app=self.ready();vm=app.interpreter;effects=[]
        def trap(*a,**k):effects.append('copy');raise AssertionError('generic copy callback')
        with patch.dict(copy._copy_dispatch,{xml_io.BSLXMLReader:trap}),patch.dict(copy._deepcopy_dispatch,{xml_writer.BSLXMLWriterSettings:trap}):
            self.write(vm);vm.execute('Copy=XDTOFactory.ReadXML(R,T);')
        self.assertEqual(effects,[])
    def test_property_graph_tamper_rejected_before_write(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="old";')
        vm.variables['p']._values['Label']._value='changed';before=dict(vm.variables['w'].__dict__)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");')
        self.assertEqual(vm.variables['w'].__dict__,before)
    def test_utf8_input_byte_limit(self):
        app=self.ready();vm=app.interpreter;vm.variables['input']='<Root>яя</Root>';before=dict(vm.variables['r'].__dict__)
        with patch.object(xml_io,'MAX_XML_BYTES',len(vm.variables['input'])):
            with self.assertRaises(basic.DENIED):vm.execute('R.SetString(Input);')
        self.assertEqual(vm.variables['r'].__dict__,before)
    def test_scalar_read_before_first_object_does_not_poison_inventory(self):
        app=self.app();vm=app.interpreter
        vm.execute('S=XDTOFactory.Type("http://www.w3.org/2001/XMLSchema","string");R=New XMLReader;R.SetString("<Value>first</Value>");V=XDTOFactory.ReadXML(R,S);T=XDTOFactory.Type("urn:owned:records","Tree");P=XDTOFactory.Create(T);P.Label="next";')
        self.assertEqual(vm.execute('V.Value;'),'first')
        self.assertEqual(vm.execute('P.Label;'),'next')
    def test_factory_internal_instance_hooks_never_invoked(self):
        for name in ('_from_tree','_value','_check_serialization_types'):
            app=self.ready();vm=app.interpreter;vm.execute('R.SetString("<Root/>");');effects=[]
            setattr(app.xdto.factory,name,lambda *a:effects.append('hook'))
            code='XDTOFactory.ReadXML(R,T);' if name=='_from_tree' else 'XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");'
            with self.subTest(name=name),self.assertRaises(basic.DENIED):vm.execute(code)
            self.assertEqual(effects,[])
    def test_failed_close_quota_keeps_writer_reusable(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="long close content";XDTOFactory.WriteXML(W,P,"Root","urn:owned:records");')
        before=dict(vm.variables['w'].__dict__)
        with patch.object(xml_writer,'MAX_TEXT',8):
            with self.assertRaises(basic.DENIED):vm.execute('W.Close();')
        self.assertEqual(vm.variables['w'].__dict__,before)
        vm.execute('S=W.Close();')
        self.assertIn('long close content',vm.variables['s'])
    def test_local_factory_xml_not_granted(self):
        app=self.ready();vm=app.interpreter;vm.execute('Local=New XDTOFactory;R.SetString("<Root/>");')
        for code in ('Local.ReadXML(R,T);','Local.WriteXML(W,P,"Root","urn:x");'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_saved_io_class_descriptor_no_callbacks(self):
        app=self.ready();vm=app.interpreter;vm.execute('Set=R.SetString;');effects=[]
        class Hook:
            def __get__(self,*args):effects.append('descriptor');return lambda *a:None
        with patch.object(xml_io.BSLXMLReader,'set_string',Hook()):
            with self.assertRaises(basic.DENIED):vm.execute('Set("<Root/>");')
        self.assertEqual(effects,[])
    def test_post_native_adoption_refusal_is_atomic(self):
        from yadinassi.execution.direct.source import python_direct_source_xdto_objects as objects
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="late";');self.write(vm)
        factory=app.xdto.factory;before=(factory._nodes,factory._units);reader=dict(vm.variables['r'].__dict__)
        records=objects._RECORDS[app];identities=tuple(records)
        with patch.object(objects,'stage_xml_result',side_effect=BoundaryViolation('admission fault injection')):
            with self.assertRaises(BoundaryViolation):vm.execute('XDTOFactory.ReadXML(R,T);')
        self.assertEqual((factory._nodes,factory._units),before)
        self.assertEqual(vm.variables['r'].__dict__,reader)
        self.assertIs(objects._RECORDS[app],records)
        self.assertEqual(tuple(records),identities)
        vm.execute('Copy=XDTOFactory.ReadXML(R,T);')
        self.assertEqual(vm.execute('Copy.Label;'),'late')
    def test_handle_quota_is_cumulative_and_close_sanitizes_stream(self):
        app=self.app();vm=app.interpreter
        vm.execute('For I=1 To 32 Do W=New XMLWriter;EndDo;')
        with self.assertRaises(basic.DENIED):vm.execute('W=New XMLWriter;')
        effects=[]
        class Stream:
            def close(self):effects.append('close')
        writer=vm.variables['w'];writer._stream=Stream()
        app.close()
        self.assertIsNone(writer._stream)
        self.assertEqual(effects,[])
