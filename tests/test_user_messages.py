"""Local UserMessage contracts; documentation-based, not native/UI evidence."""
from dataclasses import FrozenInstanceError
from decimal import Decimal
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from yadinassi import BSLError, Interpreter
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.user_messages import UserMessageContext, UserMessageRecord, MAX_TEXT, MAX_PATH
from sqlite_catalog_fixture import configuration_files


class UserMessageTests(unittest.TestCase):
    def setUp(self):
        self.records = []; self.output = []
        self.vm = Interpreter(self.output.append, user_message_sink=self.records.append)
        self.vm.execute('m = New UserMessage;')

    def test_defaults_and_bilingual_properties(self):
        for name in ('Text', 'Текст', 'Field', 'Поле', 'DataPath', 'ПутьКДанным'):
            self.assertEqual(self.vm.execute('m.' + name), '')
        for name in ('DataKey', 'КлючДанных', 'TargetID', 'ИдентификаторНазначения'):
            self.assertIsNone(self.vm.execute('m.' + name))
        self.vm.execute('m.Текст="Ошибка"; m.Поле="Объект.Склады[0].Склад"; m.ПутьКДанным="Объект";')
        self.assertEqual(self.vm.execute('m.tExT'), 'Ошибка')
        self.assertEqual(self.vm.execute('m.Field'), 'Объект.Склады[0].Склад')
        self.assertEqual(self.vm.execute('m.DataPath'), 'Объект')

    def test_type_and_dynamic_constructor(self):
        self.assertTrue(self.vm.execute('(TypeOf(m)=Тип("СообщениеПользователю"))'))
        self.assertTrue(self.vm.execute('(Type("UserMessage")=Тип("СообщениеПользователю"))'))
        self.vm.execute('r=New(Type("UserMessage")); r.Text="dynamic"; r.Message();')
        self.assertEqual(self.records[0].text, 'dynamic')

    def test_russian_constructor_and_message(self):
        self.vm.execute('s=Новый СообщениеПользователю(); s.Текст="Проверка"; s.Сообщить();')
        self.assertEqual(self.records[0].text, 'Проверка')
        self.assertEqual(self.output, [])

    def test_message_snapshots_repeated_use_without_mutating_properties(self):
        self.vm.execute('m.Text="one"; m.Field="Rows[0].Value"; m.Message(); m.Text="two"; m.Message();')
        self.assertEqual([r.text for r in self.records], ['one', 'two'])
        self.assertIsNot(self.records[0], self.records[1])
        self.assertEqual(self.vm.execute('m.Field'), 'Rows[0].Value')
        with self.assertRaises(FrozenInstanceError):
            self.records[0].text = 'changed'

    def test_default_delivery_uses_existing_output(self):
        output=[]; vm=Interpreter(output.append)
        vm.execute('m=New UserMessage; m.Text="ordinary"; m.Message();')
        self.assertEqual(output, ['ordinary'])

    def test_host_sink_can_be_replaced_or_removed(self):
        second=[]; self.vm.user_messages.set_sink(second.append)
        self.vm.execute('m.Text="second"; m.Message();')
        self.vm.user_messages.set_sink(None)
        self.vm.execute('m.Text="fallback"; m.Message();')
        self.assertEqual([r.text for r in second], ['second'])
        self.assertEqual(self.output, ['fallback'])
        self.assertEqual(self.records, [])

    def test_sink_failure_is_not_silent_or_retried(self):
        calls=[]
        def fail(record): calls.append(record); raise ValueError('controlled sink failure')
        self.vm.user_messages.set_sink(fail)
        with self.assertRaisesRegex(BSLError, 'controlled sink failure'):
            self.vm.execute('m.Text="kept"; m.Message();')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.vm.execute('m.Text'), 'kept')

    def test_message_is_procedure_not_expression(self):
        with self.assertRaises(BSLError): self.vm.execute('result=m.Message();')
        self.assertEqual(self.records, [])

    def test_constructor_and_method_arity(self):
        for source in ('m=New UserMessage("text");', 'm.Message(1);', 'm.SetData();', 'm.SetData(1,2);'):
            with self.subTest(source=source), self.assertRaises(BSLError):
                self.vm.execute(source)
        self.assertEqual(self.records, [])

    def test_unknown_properties_and_host_internals_stay_closed(self):
        for source in ('m._context', 'm.__dict__', 'm.publish()', 'm.Unknown=1;', 'm.Message=1;'):
            with self.subTest(source=source), self.assertRaises(BSLError):
                self.vm.execute(source)

    def test_invalid_assignments_leave_previous_values(self):
        self.vm.execute('m.Text="kept"; m.Field="Name";')
        for source in ('m.Text=1;', 'm.Field=Undefined;', 'm.DataPath=True;',
                       'm.DataKey=New Structure;', 'm.TargetID="not UUID";'):
            with self.subTest(source=source), self.assertRaises(BSLError):
                self.vm.execute(source)
        self.assertEqual(self.vm.execute('m.Text'), 'kept')
        self.assertEqual(self.vm.execute('m.Field'), 'Name')

    def test_text_and_path_limits_are_local_and_atomic(self):
        for property_, maximum in (('Text', MAX_TEXT), ('Field', MAX_PATH), ('DataPath', MAX_PATH)):
            self.vm.variables['value']='x'*maximum
            self.vm.execute('m.'+property_+'=value;')
            self.vm.variables['value']='x'*(maximum+1)
            with self.assertRaises(BSLError): self.vm.execute('m.'+property_+'=value;')
            self.assertEqual(len(self.vm.execute('m.'+property_)), maximum)

    def test_target_id_roundtrips_and_can_be_cleared(self):
        self.vm.execute('id=New UUID("12345678-1234-1234-1234-123456789abc"); m.TargetID=id; m.Message();')
        self.assertEqual(self.records[0].target_id.text, '12345678-1234-1234-1234-123456789abc')
        self.assertTrue(self.vm.execute('(m.ИдентификаторНазначения=id)'))
        self.vm.execute('m.TargetID=Undefined;')
        self.assertIsNone(self.vm.execute('m.TargetID'))

    def test_field_is_inert_not_interpreted_or_evaluated(self):
        self.vm.execute('m.Field="../../other; Execute(secret)"; m.Message();')
        self.assertEqual(self.records[0].field, '../../other; Execute(secret)')

    def test_string_codec_and_cross_context_transfer_are_not_invented(self):
        for source in ('String(m)', 'ValueToStringInternal(m)',
                       'ValueToStringInternal(Type("UserMessage"))'):
            with self.subTest(source=source), self.assertRaises(BSLError): self.vm.execute(source)
        vm=Interpreter(lambda _:None)
        vm.execute('&AtServer\nProcedure Consume(value) EndProcedure')
        with self.assertRaises(BSLError): vm.execute('m=New UserMessage; Consume(m);')

    def test_server_and_nocontext_messages_share_host_delivery(self):
        for directive in ('AtServer', 'AtServerNoContext'):
            with self.subTest(directive=directive):
                records=[];vm=Interpreter(lambda _:None,user_message_sink=records.append)
                vm.execute('&'+directive+'\nProcedure Emit() m=New UserMessage; m.Text="server"; m.Message(); EndProcedure Emit();')
                self.assertEqual([r.text for r in records], ['server'])

    def test_independent_interpreters_do_not_share_sinks(self):
        other=[];vm=Interpreter(lambda _:None,user_message_sink=other.append)
        vm.execute('m=New UserMessage; m.Text="other"; m.Message();')
        self.assertEqual(self.records, [])
        self.assertEqual([r.text for r in other], ['other'])

    def test_standalone_thisobject_is_not_a_catalog_object(self):
        self.vm.execute('m.DataPath="kept";')
        with self.assertRaises(BSLError): self.vm.execute('m.SetData(ThisObject);')
        self.assertEqual(self.vm.execute('m.DataPath'), 'kept')
        self.assertIsNone(self.vm.execute('m.DataKey'))

    def test_imported_module_messages_share_host_delivery(self):
        with tempfile.TemporaryDirectory(prefix='yadinassi-message-module-') as temporary:
            directory=Path(temporary)
            (directory/'Helper.bsl').write_text('Procedure Emit() Export m=New UserMessage; m.Text="imported"; m.Message(); EndProcedure', encoding='utf-8')
            self.vm.execute('// #Import Helper.bsl\nHelper.Emit();', str(directory/'Main.bsl'))
        self.assertEqual([r.text for r in self.records], ['imported'])

    def test_form_session_retains_existing_plain_message_contract(self):
        from yadinassi.form_runtime import FormSession
        source='&AtClient\nProcedure OnOpen(Cancel) m=New UserMessage; m.Text="form"; m.Field="Object.Name"; m.Message(); EndProcedure'
        session=FormSession(source,bindings={'OnOpen':'OnOpen'})
        session.open()
        self.assertEqual(session.messages, ('form',))

    def test_invalid_host_sinks_reject(self):
        with self.assertRaises(TypeError): Interpreter(user_message_sink=3)
        with self.assertRaises(TypeError): self.vm.user_messages.set_sink(3)


class CatalogUserMessageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='yadinassi-user-message-')
        self.addCleanup(self.temp.cleanup)
        self.context=SQLiteDBContext.create(Path(self.temp.name)/'owned.sqlite',
                                            import_configuration(configuration_files()))
        self.addCleanup(self.context.close)
        self.records=[]
        self.vm=Interpreter(lambda _:None,database_context=self.context,
                            user_message_sink=self.records.append)
        self.vm.execute('o=Catalogs.Products.CreateItem(); m=New UserMessage;')

    def test_set_data_reads_detached_ref_without_write_or_navigation(self):
        with patch.object(self.context.backend,'begin_read',side_effect=AssertionError('unexpected read')), \
             patch.object(self.context.backend,'begin_write',side_effect=AssertionError('unexpected write')):
            self.vm.execute('m.SetData(o); m.Text="invalid"; m.Field="Description"; m.Message();')
        self.assertTrue(self.vm.execute('(m.DataKey=o.Ref)'))
        self.assertEqual(self.records[0].data_path, '')
        self.assertTrue(self.vm.execute('o.IsNew()'))

    def test_host_binding_is_instance_specific_and_weak(self):
        obj=self.vm.execute('o'); self.vm.user_messages.bind_data(obj, 'Object')
        self.vm.execute('m.SetData(o); m.Message();')
        self.assertEqual(self.records[-1].data_path, 'Object')
        self.vm.execute('other=Catalogs.Products.CreateItem(); m.SetData(other); m.Message();')
        self.assertEqual(self.records[-1].data_path, '')
        self.vm.user_messages.unbind_data(obj)
        self.vm.execute('m.SetData(o); m.Message();')
        self.assertEqual(self.records[-1].data_path, '')
        self.vm.user_messages.bind_data(obj,'Object')
        reference=weakref.ref(obj);self.vm.execute('o=Undefined;');del obj;gc.collect()
        self.assertIsNone(reference())

    def test_equal_references_do_not_share_detached_instance_binding(self):
        self.vm.execute('o.Code="1"; o.Description="owned"; o.Write(); twin=o.Ref.GetObject();')
        original=self.vm.execute('o'); twin=self.vm.execute('twin')
        self.assertIsNot(original, twin)
        self.assertTrue(self.vm.execute('(o.Ref=twin.Ref)'))
        self.vm.user_messages.bind_data(original, 'Object')
        self.vm.execute('m.SetData(o); m.Message(); m.SetData(twin); m.Message();')
        self.assertEqual([r.data_path for r in self.records], ['Object', ''])
        self.assertEqual(self.records[0].data_key, self.records[1].data_key)
        self.vm.user_messages.bind_data(twin, 'OtherObject')
        self.vm.user_messages.unbind_data(original)
        self.vm.execute('m.SetData(twin); m.Message();')
        self.assertEqual(self.records[-1].data_path, 'OtherObject')

    def test_direct_data_key_and_manual_path_snapshot(self):
        self.vm.execute('m.DataKey=o.Ref; m.DataPath="Object"; m.Field="Rows[0].Item"; m.Message(); m.DataKey=Undefined;')
        self.assertIsNotNone(self.records[0].data_key)
        self.assertEqual(self.records[0].field, 'Rows[0].Item')
        self.assertIsNone(self.vm.execute('m.DataKey'))

    def test_failed_set_data_preserves_both_properties(self):
        self.vm.user_messages.bind_data(self.vm.execute('o'), 'Object')
        self.vm.execute('m.SetData(o);')
        before=self.vm.execute('m.DataKey')
        with self.assertRaises(BSLError):self.vm.execute('m.SetData(New Structure);')
        self.assertIs(self.vm.execute('m.DataKey'), before)
        self.assertEqual(self.vm.execute('m.DataPath'), 'Object')

    def test_only_host_can_bind_and_binding_path_is_checked(self):
        with self.assertRaises(TypeError): self.vm.user_messages.bind_data(object(), 'Object')
        with self.assertRaises(ValueError): self.vm.user_messages.bind_data(self.vm.execute('o'), 'x'*(MAX_PATH+1))
        with self.assertRaises(TypeError): self.vm.user_messages.unbind_data(object())


if __name__ == '__main__': unittest.main()
