"""Explicit source session type alternatives and immutable retained state."""
import unittest
from decimal import Decimal
from test_source_session_parameters import declaration, package
from test_configuration_source_runtime import source
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.configuration_source_session import source_session_definitions
from yadinassi.errors import BSLError


class SourceSessionTypesTests(unittest.TestCase):
    def run_source(self, body, types, *, handler='Names'):
        mapping={item.path:item.content for item in package('',kind='v8:FixedMap').files}
        mapping['SessionParameters/State.xml']=declaration('State',types)
        mapping['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting('+handler+')\n'+body+'\nEndProcedure').encode()
        app=SourceApplication(import_source(mapping),output=lambda text:None)
        self.addCleanup(app.close);app.start()
        return app

    def test_uuid_write_read(self):
        app=self.run_source('SessionParameters.State=New UUID("11111111-1111-1111-1111-111111111111");','<v8:Type>v8:UUID</v8:Type>')
        self.assertEqual(app.session_parameters._values['state'].text,'11111111-1111-1111-1111-111111111111')
        self.assertTrue(app.session_parameters.metadata.get_member('State').get_member('Type').types)

    def test_uuid_rejects_string_without_coercion(self):
        with self.assertRaises(BSLError):
            self.run_source('SessionParameters.State="11111111-1111-1111-1111-111111111111";','<v8:Type>v8:UUID</v8:Type>')

    def test_value_storage_snapshot_isolation(self):
        app=self.run_source('M=New Map; M.Insert("key",1); SessionParameters.State=New ValueStorage(M); M.Insert("key",2);','<v8:Type>v8:ValueStorage</v8:Type>')
        stored=app.session_parameters._values['state']
        first=stored.get();first.insert('key',Decimal(3))
        self.assertEqual(stored.get().get('key'),Decimal(1))

    def test_type_description(self):
        app=self.run_source('SessionParameters.State=New TypeDescription("UUID");','<v8:Type>v8:TypeDescription</v8:Type>')
        self.assertEqual(len(app.session_parameters._values['state'].types),1)

    def test_fixed_array_nested_values(self):
        app=self.run_source('A=New Array; A.Add(New UUID); A.Add(Undefined); B=New Array; B.Add(True); A.Add(B); SessionParameters.State=New FixedArray(A);','<v8:Type>v8:FixedArray</v8:Type>')
        self.assertEqual(len(app.session_parameters._values['state'].items),3)

    def test_fixed_array_rejects_nested_mutable_structure(self):
        with self.assertRaisesRegex(BSLError,'mutable or unsupported'):
            self.run_source('A=New Array; A.Add(New Structure); SessionParameters.State=New FixedArray(A);','<v8:Type>v8:FixedArray</v8:Type>')

    def test_fixed_map_rejects_nested_mutable(self):
        with self.assertRaisesRegex(BSLError,'mutable or unsupported'):
            self.run_source('A=New Map; A.Insert("key",New Array); SessionParameters.State=New FixedMap(A);','<v8:Type>v8:FixedMap</v8:Type>')

    def test_fixed_structure_nested_immutable(self):
        app=self.run_source('A=New Array; A.Add(Undefined); SessionParameters.State=New FixedStructure("key",New FixedArray(A));','<v8:Type>v8:FixedStructure</v8:Type>')
        self.assertEqual(len(app.session_parameters._values['state'].get('key').items),1)

    def test_union_uuid_boolean_preserves_both(self):
        app=self.run_source('SessionParameters.State=New UUID; SessionParameters.State=True;','<v8:Type>v8:UUID</v8:Type><v8:Type>xs:boolean</v8:Type>')
        self.assertIs(app.session_parameters._values['state'],True)

    def test_union_qualifiers_are_not_dropped(self):
        types='<v8:Type>xs:string</v8:Type><v8:Type>xs:boolean</v8:Type><v8:StringQualifiers><v8:Length>3</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'
        app=self.run_source('SessionParameters.State="yes"; Try SessionParameters.State="long"; Except EndTry;',types)
        self.assertEqual(app.session_parameters._values['state'],'yes')

    def test_union_rejection_preserves_previous_value(self):
        app=self.run_source('SessionParameters.State=True; Try SessionParameters.State=1; Except EndTry;','<v8:Type>v8:UUID</v8:Type><v8:Type>xs:boolean</v8:Type>')
        self.assertIs(app.session_parameters._values['state'],True)

    def test_unknown_union_not_partially_accepted(self):
        with self.assertRaisesRegex(BSLError,'unsupported session parameter type'):
            self.run_source('SessionParameters.State=True;','<v8:Type>xs:boolean</v8:Type><v8:Type>v8:FutureType</v8:Type>')

    def test_unknown_union_unused_is_retained(self):
        app=self.run_source('','<v8:Type>xs:boolean</v8:Type><v8:Type>v8:FutureType</v8:Type>')
        self.assertIn('state',app.session_parameters._unsupported)

    def test_duplicate_types_rejected(self):
        app=self.run_source('','<v8:Type>v8:UUID</v8:Type><v8:Type>v8:UUID</v8:Type>')
        self.assertIn('duplicate',app.session_parameters._unsupported['state'])

    def test_orphan_qualifier_rejected(self):
        app=self.run_source('','<v8:Type>v8:UUID</v8:Type><v8:StringQualifiers><v8:Length>2</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>')
        self.assertIn('qualifier',app.session_parameters._unsupported['state'])

    def test_no_fake_uuid_default(self):
        with self.assertRaisesRegex(BSLError,'not set|recursive'):
            self.run_source('Message(SessionParameters.State);','<v8:Type>v8:UUID</v8:Type>')

    def test_zero_parameter_session_handler(self):
        app=self.run_source('SessionParameters.State=New UUID;','<v8:Type>v8:UUID</v8:Type>',handler='')
        self.assertIn('state',app.session_parameters._values)

    def test_zero_parameter_lazy_handler(self):
        mapping={item.path:item.content for item in package('',kind='v8:UUID').files}
        mapping['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting() SessionParameters.State=New UUID; EndProcedure'
        app=SourceApplication(import_source(mapping),output=lambda text:None)
        self.addCleanup(app.close);app.start()
        from yadinassi.session_parameters import _UNSET
        app.session_parameters._values['state']=_UNSET
        app._session_owner.execute('&AtServer\nProcedure Read() Message(SessionParameters.State); EndProcedure\nRead();')
        self.assertIsNot(app.session_parameters._values['state'],_UNSET)

    def test_unknown_binary_declaration_stays_explicit(self):
        app=self.run_source('','<v8:Type>v8:BinaryData</v8:Type>')
        self.assertIn('state',app.session_parameters._unsupported)

    def test_graph_bounds_and_cycles(self):
        from yadinassi.source_session_values import validate_session_value
        from yadinassi.values import BSLFixedArray,BSLArray
        bad=BSLFixedArray(BSLArray());bad.items=(bad,)
        with self.assertRaisesRegex(ValueError,'cycle'):validate_session_value(bad)
        big=BSLFixedArray(BSLArray());big.items=(None,)*10001
        with self.assertRaisesRegex(ValueError,'structural limit'):validate_session_value(big)


class SourceStartupBindingTests(unittest.TestCase):
    def run_app(self,code):
        output=[];app=SourceApplication(source(code.encode()),output=output.append)
        self.addCleanup(app.close);app.start();return app,output

    def test_before_start_no_arguments_runs(self):
        _,out=self.run_app('Procedure BeforeStart() Message("before"); EndProcedure\nProcedure OnStart() Message("after"); EndProcedure')
        self.assertEqual(out,['before','after'])

    def test_russian_before_start_no_arguments(self):
        _,out=self.run_app('Процедура ПередНачаломРаботыСистемы() Сообщить("before"); КонецПроцедуры')
        self.assertEqual(out,['before'])

    def test_cancel_parameter_still_cancels(self):
        app,out=self.run_app('Procedure BeforeStart(Cancel) Cancel=True; EndProcedure\nProcedure OnStart() Message("wrong"); EndProcedure')
        self.assertEqual(app.state,'cancelled');self.assertEqual(out,[])

    def test_extra_parameter_not_ignored(self):
        with self.assertRaisesRegex(ValueError,'сигнатура'):
            self.run_app('Procedure BeforeStart(Cancel,Extra) EndProcedure')

    def test_val_cancel_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'ссылке'):
            self.run_app('Procedure BeforeStart(Val Cancel) EndProcedure')

    def test_function_handler_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'сигнатура'):
            self.run_app('Function BeforeStart() Return True; EndFunction')

    def test_zero_handler_error_is_not_skipped(self):
        with self.assertRaisesRegex(BSLError,'failure'):
            self.run_app('Procedure BeforeStart() Raise "failure"; EndProcedure')

    def test_strict_host_keeps_required_session_argument(self):
        from yadinassi.configuration_modules import compile_session_module
        with self.assertRaisesRegex(ValueError,'signature'):
            compile_session_module(b'Procedure SessionParametersSetting() EndProcedure')
        program,handler=compile_session_module(b'Procedure SessionParametersSetting() EndProcedure',allow_omitted_parameters=True)
        self.assertEqual(len(handler.parameters),0)

    def test_value_storage_aggregate_budget(self):
        from unittest.mock import patch
        from yadinassi.source_session_values import validate_session_value
        from yadinassi.value_storage import BSLValueStorage
        from yadinassi.values import BSLArray,BSLFixedArray
        a=BSLArray();a.items.extend([BSLValueStorage('x'*100),BSLValueStorage('y'*100)])
        with patch('yadinassi.source_session_values.MAX_UNITS',1000):
            with self.assertRaisesRegex(ValueError,'resource limit'):
                validate_session_value(BSLFixedArray(a))
