"""Bounded source XDTO JSON codecs: staged, same-app, string-only, no VM."""
import unittest
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_python_direct_source_xdto_graphs as graphs
import test_source_xdto_packages as existing
from yadinassi.formats.json import json_processing as codec
from yadinassi.formats.xml import xdto_io
from yadinassi.types.values import HostFunction

class SourceXDTOJSONTests(unittest.TestCase):
    setUp=basic.SourceScalarXDTOTests.setUp
    app=graphs.GraphXDTOTests.app
    prepared=graphs.GraphXDTOTests.prepared
    def ready(self):
        app=self.prepared();app.interpreter.execute('W=New JSONWriter;W.SetString();R=New JSONReader;');return app
    def write(self,vm,value='P'):
        vm.execute('XDTOFactory.WriteJSON(W,'+value+');S=W.Close();R.SetString(S);')
    def test_nested_graph_scalar_lists_roundtrip(self):
        app=self.ready();vm=app.interpreter
        vm.execute('P.Label="parent";C.Label="child";D.Label="list child";P.Child=C;P.Children.Add(D);P.Labels.Add("quoted");P.Labels.Add("б");')
        self.write(vm);vm.execute('Copy=XDTOFactory.ReadJSON(R,T);R.Close();')
        self.assertEqual(vm.execute('Copy.Label;'),'parent')
        self.assertEqual(vm.execute('Copy.Child.Label;'),'child')
        self.assertEqual(vm.execute('Copy.Children.Get(0).Label;'),'list child')
        self.assertEqual(vm.execute('Copy.Labels.Get(1);'),'б')
        vm.execute('Copy.Child.Label="independent";')
        self.assertEqual(vm.execute('P.Child.Label;'),'child')
    def test_original_source_xdto_xml_json_scenario(self):
        original=existing.SourceXDTOTests();self.addCleanup(original.doCleanups)
        original.test_qualified_native_package_xml_and_json()
    def test_scalar_alias_roundtrip(self):
        app=self.ready();vm=app.interpreter;vm.execute('SType=XDTOFactory.Type("urn:owned:records","Code");V=XDTOFactory.Create(SType,"alias");')
        self.write(vm,'V');vm.execute('Copy=XDTOFactory.ReadJSON(R,SType);')
        self.assertEqual(vm.execute('Copy.Value;'),'alias')
    def test_nullable_child_roundtrip(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Child=Null;');self.write(vm)
        vm.execute('Copy=XDTOFactory.ReadJSON(R,T);');self.assertIsNone(vm.execute('Copy.Child;'))
    def test_bilingual_methods(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('W=Новый ЗаписьJSON;W.УстановитьСтроку();ФабрикаXDTO.ЗаписатьJSON(W,P);S=W.Закрыть();R=Новый ЧтениеJSON;R.УстановитьСтроку(S);Copy=ФабрикаXDTO.ПрочитатьJSON(R,T);R.Закрыть();')
        self.assertIsNotNone(vm.variables['copy'])
    def test_no_files_stream_settings_callbacks_or_general_events(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or '/tmp/never-written')
        for code in ('W.OpenFile(Touch());','R.OpenFile(Touch());','W.OpenStream(Touch());','R.Read();',
                     'W.WriteStartObject();','W.SetString(Touch());','XDTOFactory.ReadJSON(R,T,Touch());',
                     'XDTOFactory.WriteJSON(W,P,Touch());'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
    def test_arity_before_argument_effects(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or '')
        for code in ('New JSONWriter(Touch());','New JSONReader(Touch());','R.SetString(Touch(),Touch());','XDTOFactory.ReadJSON(Touch());','XDTOFactory.WriteJSON(Touch());'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
    def test_duplicate_and_unknown_properties_fail_atomically(self):
        for document in ('{"Label":"a","Label":"b"}','{"Unknown":1}', '{"Child":{}}'):
            app=self.ready();vm=app.interpreter;vm.variables['input']=document;vm.execute('R.SetString(Input);')
            before=(app.xdto.factory._nodes,app.xdto.factory._units);reader=dict(vm.variables['r'].__dict__)
            with self.subTest(document=document),self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadJSON(R,T);')
            self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
            self.assertEqual(vm.variables['r'].__dict__,reader)
            vm.execute('R.SetString("{}");Copy=XDTOFactory.ReadJSON(R,T);')
    def test_invalid_constants_and_malformed_input(self):
        for document in ('{"Label":NaN}','{"Label":Infinity}','{"Label":', '{"Label":1,}'):
            app=self.ready();vm=app.interpreter;vm.variables['input']=document
            vm.execute('R.SetString(Input);');before=app.xdto.factory._nodes
            with self.subTest(document=document),self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadJSON(R,T);')
            self.assertEqual(app.xdto.factory._nodes,before)
    def test_foreign_and_forged_handle_denied(self):
        app=self.ready();other=self.ready();vm=app.interpreter
        vm.variables['foreign']=other.interpreter.variables['w'];vm.variables['forged']=codec.BSLJSONWriter()
        for code in ('Foreign.SetString();','Forged.SetString();','XDTOFactory.WriteJSON(Foreign,P);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_read_quota_rollback_and_retry(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="quota";');self.write(vm)
        before=(app.xdto.factory._nodes,app.xdto.factory._units);reader=dict(vm.variables['r'].__dict__)
        with patch.object(xdto_io,'MAX_NODES',before[0]+1):
            with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadJSON(R,T);')
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
        self.assertEqual(vm.variables['r'].__dict__,reader)
        vm.execute('Copy=XDTOFactory.ReadJSON(R,T);');self.assertEqual(vm.execute('Copy.Label;'),'quota')
    def test_write_failure_preserves_destination(self):
        app=self.ready();vm=app.interpreter;before=dict(vm.variables['w'].__dict__)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteJSON(W,C);')
        self.assertEqual(vm.variables['w'].__dict__,before)
        vm.execute('C.Label="ok";XDTOFactory.WriteJSON(W,C);S=W.Close();');self.assertIn('ok',vm.variables['s'])
    def test_native_default_trailing_array_comma_preserved(self):
        app=self.ready();vm=app.interpreter;vm.variables['input']='{"Labels":["a",]}'
        vm.execute('R.SetString(Input);Copy=XDTOFactory.ReadJSON(R,T);')
        self.assertEqual(vm.execute('Copy.Labels.Get(0);'),'a')
    def test_saved_io_and_factory_methods(self):
        app=self.ready();vm=app.interpreter
        vm.execute('Write=XDTOFactory.WriteJSON;Write(W,P);Close=W.Close;S=Close();Set=R.SetString;Set(S);Read=XDTOFactory.ReadJSON;Copy=Read(R,T);')
        self.assertIsNotNone(vm.variables['copy'])
    def test_read_once_and_write_once_per_reset(self):
        app=self.ready();vm=app.interpreter;vm.execute('XDTOFactory.WriteJSON(W,P);')
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteJSON(W,P);')
        vm.execute('S=W.Close();R.SetString(S);Copy=XDTOFactory.ReadJSON(R,T);')
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadJSON(R,T);')
        vm.execute('R.SetString(S);Copy=XDTOFactory.ReadJSON(R,T);')
    def test_null_root_matches_native_explicit_type(self):
        app=self.ready();vm=app.interpreter;vm.execute('R.SetString("null");Copy=XDTOFactory.ReadJSON(R,T);')
        self.assertIsNone(vm.variables['copy'])
    def test_local_factory_json_remains_unavailable(self):
        app=self.ready();vm=app.interpreter;vm.execute('Local=New XDTOFactory;R.SetString("{}");')
        for code in ('Local.ReadJSON(R,T);','Local.WriteJSON(W,P);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_parser_and_encoder_hooks_before_effects(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or '{}')
        for module,name in ((codec.json,'loads'),(codec.json,'dumps'),(codec.json.scanner,'make_scanner'),(codec.json.encoder,'encode_basestring')):
            with patch.object(module,name,lambda *a,**k:effects.append('hook')):
                with self.subTest(name=name),self.assertRaises(basic.DENIED):vm.execute('R.SetString(Touch());')
        self.assertEqual(effects,[])
    def test_factory_conversion_instance_hooks_denied(self):
        for name in ('_from_plain','_plain','_value','_check_serialization_types'):
            app=self.ready();vm=app.interpreter;vm.execute('R.SetString("{}");');effects=[]
            setattr(app.xdto.factory,name,lambda *a,**k:effects.append('hook'))
            code='XDTOFactory.ReadJSON(R,T);' if name=='_from_plain' else 'XDTOFactory.WriteJSON(W,P);'
            with self.subTest(name=name),self.assertRaises(basic.DENIED):vm.execute(code)
            self.assertEqual(effects,[])
    def test_file_injection_never_calls_foreign_handle(self):
        app=self.ready();vm=app.interpreter;effects=[]
        class Stream:
            def write(self,*a):effects.append('write')
            def close(self):effects.append('close')
        writer=vm.variables['w'];writer._file=Stream()
        for code in ('W.Close();','W.SetString();','XDTOFactory.WriteJSON(W,P);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        app.close();self.assertIsNone(writer._file);self.assertEqual(effects,[])
    def test_saved_class_descriptor_hook_never_runs(self):
        app=self.ready();vm=app.interpreter;vm.execute('Set=R.SetString;');effects=[]
        class Hook:
            def __get__(self,*args):effects.append('descriptor');return lambda *a:None
        with patch.object(codec.BSLJSONReader,'set_string',Hook()):
            with self.assertRaises(basic.DENIED):vm.execute('Set("{}");')
        self.assertEqual(effects,[])
    def test_late_reader_mutation_before_native_decode(self):
        app=self.ready();vm=app.interpreter;vm.execute('R.SetString("{}");');before=app.xdto.factory._nodes
        def touch():vm.variables['r']._source='{"bad":0}';return vm.variables['t']
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.ReadJSON(R,Touch());')
        self.assertEqual(app.xdto.factory._nodes,before)
    def test_generic_copy_dispatch_never_called(self):
        import copy
        app=self.ready();vm=app.interpreter;effects=[]
        def trap(*a,**k):effects.append('copy');raise AssertionError('generic copying')
        with patch.dict(copy._copy_dispatch,{codec.BSLJSONReader:trap}):
            self.write(vm);vm.execute('Copy=XDTOFactory.ReadJSON(R,T);')
        self.assertEqual(effects,[])
    def test_post_decode_admission_failure_atomic(self):
        from yadinassi.execution.direct.source import python_direct_source_xdto_objects as objects
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="late";');self.write(vm)
        before=(app.xdto.factory._nodes,app.xdto.factory._units);reader=dict(vm.variables['r'].__dict__);records=objects._RECORDS[app]
        with patch.object(objects,'stage_xml_result',side_effect=BoundaryViolation('admission fault injection')):
            with self.assertRaises(BoundaryViolation):vm.execute('XDTOFactory.ReadJSON(R,T);')
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
        self.assertEqual(vm.variables['r'].__dict__,reader);self.assertIs(objects._RECORDS[app],records)
        vm.execute('Copy=XDTOFactory.ReadJSON(R,T);')
        self.assertEqual(vm.execute('Copy.Label;'),'late')
    def test_bad_reader_field_key_no_callbacks(self):
        app=self.ready();vm=app.interpreter;effects=[]
        class Key:
            def __hash__(self):return hash('_source')
            def __eq__(self,other):effects.append('eq');return False
        fields=vm.variables['r'].__dict__;fields.pop('_source');fields[Key()]='{}';effects.clear()
        with self.assertRaises(basic.DENIED):vm.execute('R.SetString("{}");')
        self.assertEqual(effects,[])
    def test_output_and_close_quota_preserve_writer(self):
        app=self.ready();vm=app.interpreter;vm.execute('P.Label="long JSON output";');before=dict(vm.variables['w'].__dict__)
        with patch.object(codec,'MAX_TEXT',8):
            with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteJSON(W,P);')
        self.assertEqual(vm.variables['w'].__dict__,before)
        vm.execute('XDTOFactory.WriteJSON(W,P);');before=dict(vm.variables['w'].__dict__)
        with patch.object(codec,'MAX_TEXT',8):
            with self.assertRaises(basic.DENIED):vm.execute('W.Close();')
        self.assertEqual(vm.variables['w'].__dict__,before)
        vm.execute('S=W.Close();');self.assertIn('long JSON output',vm.variables['s'])
    def test_internal_map_and_array_class_hooks_no_callbacks(self):
        from yadinassi.collections.maps import BSLMap
        from yadinassi.types.values import BSLArray
        app=self.ready();vm=app.interpreter;effects=[]
        for cls,name in ((BSLMap,'insert'),(BSLMap,'__iter__'),(BSLArray,'__init__')):
            with patch.object(cls,name,lambda *a,**k:effects.append('collection')):
                with self.subTest(name=name),self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteJSON(W,P);')
        self.assertEqual(effects,[])
    def test_layout_platform_string_hook_never_runs(self):
        app=self.ready();vm=app.interpreter;effects=[]
        class Evil(str):
            def __radd__(self,other):effects.append('radd');return str(other)
        with patch.object(codec.os,'linesep',Evil('\n')):
            with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.WriteJSON(W,P);')
        self.assertEqual(effects,[])
    def test_saved_method_reference_metadata_no_callbacks(self):
        app=self.ready();vm=app.interpreter;vm.execute('Set=R.SetString;');effects=[]
        class Evil:
            def __bool__(self):effects.append('bool');return False
        vm.variables['set'].reference_parameters=Evil()
        with self.assertRaises(basic.DENIED):vm.execute('Set("{}");')
        self.assertEqual(effects,[])
    def test_scalar_read_before_first_object(self):
        app=self.app();vm=app.interpreter;vm.variables['input']='"first"'
        vm.execute('SType=XDTOFactory.Type("http://www.w3.org/2001/XMLSchema","string");R=New JSONReader;R.SetString(Input);V=XDTOFactory.ReadJSON(R,SType);T=XDTOFactory.Type("urn:owned:records","Tree");P=XDTOFactory.Create(T);')
        self.assertEqual(vm.execute('V.Value;'),'first')
        self.assertIsNotNone(vm.variables['p'])
    def test_cumulative_handle_limit(self):
        app=self.app();vm=app.interpreter;vm.execute('For I=1 To 32 Do W=New JSONWriter;EndDo;')
        with self.assertRaises(basic.DENIED):vm.execute('W=New JSONWriter;')
    def test_forged_scalar_type_field_keys_no_callbacks_json_and_xml(self):
        from yadinassi.formats.xml import xdto_values
        app=self.ready();vm=app.interpreter
        vm.execute('SType=XDTOFactory.Type("http://www.w3.org/2001/XMLSchema","string");R.SetString("null");XR=New XMLReader;XR.SetString("<V/>");')
        effects=[]
        class Key:
            def __hash__(self):return hash('_factory')
            def __eq__(self,other):effects.append('eq');return False
        forged=object.__new__(xdto_values.BSLXDTOValueType);forged.__dict__.update(vm.variables['stype'].__dict__)
        forged.__dict__.pop('_factory');forged.__dict__[Key()]=app.xdto.factory;effects.clear();vm.variables['forged']=forged
        for code in ('XDTOFactory.ReadJSON(R,Forged);','XDTOFactory.ReadXML(XR,Forged);','XDTOFactory.Create(Forged,"x");'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
    def test_generic_global_codecs_denied_before_arguments(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or vm.variables['w'])
        for code in ('ReadJSON(Touch(),True);','ПрочитатьJSON(Touch(),True);','WriteJSON(Touch(),P);','ЗаписатьJSON(Touch(),P);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
        self.assertEqual(vm.variables['w']._parts,[])
    def test_generic_saved_and_renamed_codec_wrappers_denied(self):
        app=self.ready();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('arg') or vm.variables['w'])
        vm.variables['saved']=vm.functions['writejson']
        vm.variables['renamed']=HostFunction('Renamed',codec.write_json,returns_value=False)
        vm.functions['othername']=HostFunction('OtherName',codec.read_json)
        for code in ('Saved(Touch(),P);','Renamed(Touch(),P);','OtherName(Touch(),True);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
        self.assertEqual(effects,[])
    def test_generic_callable_late_swap_to_codec_denied(self):
        for invocation in ('Switchable(Touch(),P);','Saved(Touch(),P);'):
            app=self.ready();vm=app.interpreter
            function=HostFunction('Switchable',lambda *args:None,returns_value=False)
            vm.functions['switchable']=function;vm.variables['saved']=function
            def touch():function.function=codec.write_json;return vm.variables['w']
            vm.functions['touch']=HostFunction('Touch',touch)
            with self.subTest(invocation=invocation),self.assertRaises(basic.DENIED):vm.execute(invocation)
            self.assertEqual(vm.variables['w']._parts,[])
    def test_user_routine_named_readjson_not_blocked(self):
        app=self.ready();vm=app.interpreter
        vm.execute('Function ReadJSON(Val Arg) Return Arg;EndFunction Result=ReadJSON(7);')
        self.assertEqual(vm.variables['result'],7)
