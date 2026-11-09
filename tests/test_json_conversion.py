"""JSON conversion composition and explicit boundaries, not native captures."""
from decimal import Decimal as D
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.json_processing import BSLJSONReader
from yadinassi.values import BSLType


UUID_TEXT = '12345678-1234-1234-1234-123456789abc'
ISO_TEXT = '2024-01-02T03:04:05'
SOURCE = '''
Var Count, Seen, id, reader;
Function Convert(Property, Value, Extra, Cancel) Export
    Count=Count+1; Seen.Add(Property);
    If Extra<>Undefined Then Extra.Add(Value); EndIf;
    Return String(Value);
EndFunction
Function Revive(Property, Value, Extra) Export
    Count=Count+1; Seen.Add(Property);
    If Extra<>Undefined Then Extra.Add(Value); EndIf;
    Return Value;
EndFunction
Function ConvertFalse(Property, Value, Extra, Cancel) Export Return False; EndFunction
Function ReviveFalse(Property, Value, Extra) Export Return False; EndFunction
Function FailWrite(Property, Value, Extra, Cancel) Export
    Count=Count+1; Raise "write handler failed";
EndFunction
Function FailRead(Property, Value, Extra) Export
    Count=Count+1; Raise "read handler failed";
EndFunction
Function CancelWrite(Property, Value, Extra, Cancel) Export
    Cancel=True; Return "discarded";
EndFunction
Count=0; Seen=New Array;
'''


class JSONConversionTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(lambda _: None)
        self.vm.execute(SOURCE, 'JSONHandlers.bsl')
        self.vm.execute(f'id=New UUID("{UUID_TEXT}");')

    def tearDown(self):
        self.vm.close()

    def reader(self, text):
        reader = BSLJSONReader()
        reader.set_string(text)
        self.vm.variables['reader'] = reader
        return reader

    def writer(self):
        self.vm.execute('writer=New JSONWriter; '
                        'writer.SetString(New JSONWriterSettings(JSONLineBreak.None));')
        return self.vm.variables['writer']

    def test_bilingual_settings_defaults_and_type_identity(self):
        for name in ('JSONSerializerSettings', 'НастройкиСериализацииJSON'):
            with self.subTest(name=name):
                self.vm.execute(f's=New {name};')
                self.assertIs(self.vm.execute('TypeOf(s)'), BSLType.JSON_SERIALIZER_SETTINGS)
                self.assertIs(self.vm.execute(f'Type("{name}")'), BSLType.JSON_SERIALIZER_SETTINGS)
                self.assertTrue(self.vm.execute('(s.DateWritingVariant=JSONDateWritingVariant.LocalDate)'))
                self.assertTrue(self.vm.execute('(s.DateSerializationFormat=JSONDateFormat.ISO)'))
                self.assertFalse(self.vm.execute('s.SerializeArraysAsObjects'))
                for ru, en in (('ВариантЗаписиДаты', 'DateWritingVariant'),
                               ('ФорматСериализацииДат', 'DateSerializationFormat'),
                               ('СериализовыватьМассивыКакОбъекты', 'SerializeArraysAsObjects')):
                    self.assertIs(self.vm.execute('s.'+ru), self.vm.execute('s.'+en))
        self.assertIs(self.vm.execute('TypeOf(New("JSONSerializerSettings"))'),
                      BSLType.JSON_SERIALIZER_SETTINGS)

    def test_settings_writable_aliases_reject_wrong_types_and_python_fields(self):
        self.vm.execute('s=New JSONSerializerSettings; '
                        's.ФорматСериализацииДат=ФорматДатыJSON.JavaScript; '
                        's.ВариантЗаписиДаты=ВариантЗаписиДатыJSON.УниверсальнаяДата; '
                        's.СериализовыватьМассивыКакОбъекты=True;')
        self.assertTrue(self.vm.execute('(s.DateSerializationFormat=JSONDateFormat.JavaScript)'))
        self.assertTrue(self.vm.execute('(s.DateWritingVariant=JSONDateWritingVariant.UniversalDate)'))
        self.assertTrue(self.vm.execute('s.SerializeArraysAsObjects'))
        for expression in ('New JSONSerializerSettings(1)',
                           's.SerializeArraysAsObjects=1;', 's.DateSerializationFormat="ISO";',
                           's.DateWritingVariant=JSONDateFormat.ISO;',
                           's.__dict__', 's.date_serialization_format',
                           's.DateSerializationFormat()',
                           's.ФорматСериализацииДаты', 's.СериализоватьМассивыКакОбъекты'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_bilingual_date_globals_and_enum_type_tokens(self):
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'UTC'}):
            self.vm.execute('d=Date(2024,1,2,3,4,5);')
            for read, write, formats in (('ReadJSONDate', 'WriteJSONDate', 'JSONDateFormat'),
                                         ('ПрочитатьДатуJSON', 'ЗаписатьДатуJSON', 'ФорматДатыJSON')):
                for member in ('ISO', 'JavaScript', 'Microsoft'):
                    with self.subTest(read=read, member=member):
                        variant = ('JSONDateWritingVariant.LocalDate' if member == 'ISO'
                                   else 'JSONDateWritingVariant.UniversalDate')
                        self.vm.execute(f'text={write}(d,{formats}.{member},{variant}); '
                                        f'restored={read}(text,{formats}.{member});')
                        self.assertEqual(self.vm.variables['restored'], self.vm.variables['d'])
            self.assertIs(self.vm.execute('TypeOf(JSONDateFormat.ISO)'), BSLType.JSON_DATE_FORMAT)
            self.assertIs(self.vm.execute('TypeOf(ВариантЗаписиДатыJSON.ЛокальнаяДата)'),
                          BSLType.JSON_DATE_WRITING_VARIANT)

    def test_serializer_settings_format_dates_without_converter(self):
        with patch.dict(os.environ, {'YADINASSI_TIMEZONE': 'UTC'}):
            for format_name, expected in (('ISO', ISO_TEXT),
                                          ('JavaScript', 'new Date(1704164645000)'),
                                          ('Microsoft', '/Date(1704164645000)/')):
                with self.subTest(format_name=format_name):
                    self.writer()
                    variant = ('LocalDate' if format_name == 'ISO' else 'UniversalDate')
                    self.vm.execute('s=New JSONSerializerSettings; '
                                    f's.DateSerializationFormat=JSONDateFormat.{format_name}; '
                                    f's.DateWritingVariant=JSONDateWritingVariant.{variant}; '
                                    'WriteJSON(writer,Date(2024,1,2,3,4,5),s,"Convert",ThisObject);')
                    self.assertEqual(json.loads(self.vm.execute('writer.Close()')), expected)
            self.assertEqual(self.vm.variables['count'], D(0))

    def test_arrays_as_objects_are_explicitly_unsupported(self):
        self.writer()
        self.vm.execute('s=New JSONSerializerSettings; s.SerializeArraysAsObjects=True;')
        with self.assertRaises(BSLError):
            self.vm.execute('WriteJSON(writer,New Array,s);')
        self.vm.execute('WriteJSON(writer,1);')
        self.assertEqual(self.vm.execute('writer.Close()'), '1')

    def test_serializer_settings_and_type_tokens_do_not_cross_internal_codec(self):
        for value in ('New JSONSerializerSettings', 'Type("JSONSerializerSettings")',
                      'JSONDateFormat.ISO', 'Type("JSONDateFormat")',
                      'JSONDateWritingVariant.LocalDate', 'Type("JSONDateWritingVariant")'):
            for function in ('ValueToStringInternal', 'New ValueStorage'):
                with self.subTest(value=value, function=function), self.assertRaises(BSLError):
                    self.vm.execute(f'{function}({value})')

    def test_bilingual_write_converter_on_unsupported_root(self):
        for write, module in (('WriteJSON', 'ThisObject'), ('ЗаписатьJSON', 'ЭтотОбъект')):
            with self.subTest(write=write):
                self.writer()
                self.vm.execute(f'{write}(writer,id,,"cONVERT",{module},);')
                self.assertEqual(json.loads(self.vm.execute('writer.Close()')), UUID_TEXT)
        self.assertEqual(self.vm.variables['seen'].items, [None, None])

    def test_converter_receives_property_names_and_unnamed_array_elements(self):
        self.writer()
        self.vm.execute('a=New Array; a.Add(id); a.Add(New Structure("nested",id)); '
                        'value=New Structure("first,items,last",id,a,7); '
                        'WriteJSON(writer,value,,"Convert",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')),
                         {'first': UUID_TEXT, 'items': [UUID_TEXT, {'nested': UUID_TEXT}], 'last': 7})
        self.assertEqual(self.vm.variables['seen'].items, ['first', None, 'nested'])

    def test_converter_is_not_called_for_supported_values(self):
        self.reader('[null,false,true,1.25,"text",{},[]]')
        self.writer()
        self.vm.execute('value=ReadJSON(reader); WriteJSON(writer,value,,"Convert",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')),
                         [None, False, True, 1.25, 'text', {}, []])
        self.assertEqual(self.vm.variables['count'], D(0))

    def test_false_converter_return_is_preserved(self):
        self.writer()
        self.vm.execute('WriteJSON(writer,id,,"ConvertFalse",ThisObject);')
        self.assertEqual(self.vm.execute('writer.Close()'), 'false')

    def test_converter_additional_parameters_share_identity_and_repeated_state(self):
        self.vm.execute('extra=New Array;')
        for _ in range(2):
            self.writer()
            self.vm.execute('WriteJSON(writer,id,,"Convert",ThisObject,extra); writer.Close();')
        self.assertEqual(self.vm.variables['count'], D(2))
        self.assertEqual(len(self.vm.variables['extra'].items), 2)
        for item in self.vm.variables['extra'].items:
            self.assertIs(item, self.vm.variables['id'])
        self.assertIsNone(self.vm.locals)

    def test_stored_module_receiver_works_for_write_and_read(self):
        self.vm.execute('module=ThisObject; box=New Structure("Module",module);')
        self.writer()
        self.vm.execute('WriteJSON(writer,id,,"Convert",box.Module);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), UUID_TEXT)
        self.reader('false')
        self.assertIs(self.vm.execute('ReadJSON(reader,,,,"Revive",module)'), False)
        self.assertEqual(self.vm.variables['count'], D(2))

    def test_imported_and_string_modules_keep_owner_state(self):
        module = '''
Var Count;
Function Convert(P,V,E,C) Export Count=Count+1; Return E+String(Count); EndFunction
Function Revive(P,V,E) Export Count=Count+1; Return V+Count; EndFunction
Count=0;
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'A.bsl').write_text(module, encoding='utf-8')
            (root/'B.bsl').write_text(module, encoding='utf-8')
            self.vm.execute('// #Import A.bsl\n// #Import B.bsl\n', str(root/'Main.bsl'))
            for receiver, expected in (('A', 'a1'), ('"a"', 'a2'), ('B', 'a1')):
                self.writer()
                self.vm.execute(f'WriteJSON(writer,id,,"Convert",{receiver},"a");')
                self.assertEqual(json.loads(self.vm.execute('writer.Close()')), expected)
            self.reader('10')
            self.assertEqual(self.vm.execute('ReadJSON(reader,,,,"Revive","a")'), D(13))
            self.reader('10')
            self.assertEqual(self.vm.execute('ReadJSON(reader,,,,"Revive",B)'), D(12))
        self.assertEqual(self.vm.variables['count'], D(0))

    def test_converter_handles_fixed_collections(self):
        self.writer()
        self.vm.execute('a=New Array; a.Add(id); s=New Structure("id",id); '
                        'm=New Map; m.Insert("id",id); all=New Array; '
                        'all.Add(New FixedArray(a)); all.Add(New FixedStructure(s)); '
                        'all.Add(New FixedMap(m)); WriteJSON(writer,all,,"Convert",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')),
                         [[UUID_TEXT], {'id': UUID_TEXT}, {'id': UUID_TEXT}])

    def test_converter_can_return_collection_with_nested_unsupported_child(self):
        self.vm.execute('''
Function Expand(P,V,E,C) Export
    Count=Count+1;
    If Count=1 Then Return New Structure("child",V); EndIf;
    Return String(V);
EndFunction
''')
        self.writer()
        self.vm.execute('WriteJSON(writer,id,,"Expand",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), {'child': UUID_TEXT})
        self.assertEqual(self.vm.variables['count'], D(2))

    def test_unsupported_converter_result_does_not_loop(self):
        self.vm.execute('Function Same(P,V,E,C) Export Count=Count+1; Return V; EndFunction')
        self.writer()
        with self.assertRaises(BSLError):
            self.vm.execute('WriteJSON(writer,id,,"Same",ThisObject);')
        self.assertEqual(self.vm.variables['count'], D(1))
        self.vm.execute('WriteJSON(writer,False);')
        self.assertEqual(self.vm.execute('writer.Close()'), 'false')

    def test_cyclic_graphs_and_converter_created_cycles_fail_boundedly(self):
        self.vm.execute('a=New Array; a.Add(a); '
                        'Function Cycle(P,V,E,C) Export Return E; EndFunction')
        for value, tail in (('a', ''), ('id', ',,"Cycle",ThisObject,a')):
            with self.subTest(value=value):
                self.writer()
                with self.assertRaises(BSLError):
                    self.vm.execute(f'WriteJSON(writer,{value}{tail});')
                self.vm.execute('WriteJSON(writer,0);')
                self.assertEqual(self.vm.execute('writer.Close()'), '0')

    def test_converter_error_is_atomic_for_pending_property_and_array_slot(self):
        for object_mode in (False, True):
            with self.subTest(object_mode=object_mode):
                self.writer()
                if object_mode:
                    self.vm.execute('writer.WriteStartObject(); writer.WritePropertyName("value");')
                else:
                    self.vm.execute('writer.WriteStartArray(); writer.WriteValue(1);')
                with self.assertRaises(BSLError):
                    self.vm.execute('WriteJSON(writer,New Structure("ok,bad",1,id),,"FailWrite",ThisObject);')
                self.vm.execute('WriteJSON(writer,2);')
                self.vm.execute('writer.WriteEndObject();' if object_mode else 'writer.WriteEndArray();')
                self.assertEqual(json.loads(self.vm.execute('writer.Close()')),
                                 {'value': 2} if object_mode else [1, 2])

    def test_handler_errors_are_catchable_and_following_operations_recover(self):
        self.writer()
        self.reader('1')
        self.vm.execute('Try WriteJSON(writer,id,,"FailWrite",ThisObject); '
                        'Except writeError=ErrorInfo().Description; EndTry; '
                        'Try bad=ReadJSON(reader,,,,"FailRead",ThisObject); '
                        'Except readError=ErrorInfo().Description; EndTry; '
                        'WriteJSON(writer,id,,"Convert",ThisObject);')
        self.assertEqual(self.vm.variables['writeerror'], 'write handler failed')
        self.assertEqual(self.vm.variables['readerror'], 'read handler failed')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), UUID_TEXT)
        self.reader('3')
        self.assertEqual(self.vm.execute('ReadJSON(reader,,,,"Revive",ThisObject)'), D(3))
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm._handled_errors, [])

    def test_cancellation_skips_only_named_unsupported_property(self):
        self.writer()
        self.vm.execute('value=New Structure("before,drop,after",1,id,2); '
                        'WriteJSON(writer,value,,"CancelWrite",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), {'before': 1, 'after': 2})

    def test_by_value_cancel_does_not_cancel_property(self):
        self.vm.execute('Function Keep(P,V,E,Val Cancel) Export Cancel=True; Return "kept"; EndFunction')
        self.writer()
        self.vm.execute('WriteJSON(writer,New Structure("value",id),,"Keep",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), {'value': 'kept'})

    def test_cancellation_of_root_or_array_element_is_explicitly_unsupported(self):
        self.vm.execute('a=New Array; a.Add(id);')
        for value in ('id', 'a'):
            with self.subTest(value=value):
                self.writer()
                with self.assertRaises(BSLError):
                    self.vm.execute(f'WriteJSON(writer,{value},,"CancelWrite",ThisObject);')
                self.vm.execute('WriteJSON(writer,1);')
                self.assertEqual(self.vm.execute('writer.Close()'), '1')

    def test_cancel_must_remain_boolean(self):
        self.vm.execute('Function BadCancel(P,V,E,C) Export C=1; Return "x"; EndFunction')
        self.writer()
        with self.assertRaises(BSLError):
            self.vm.execute('WriteJSON(writer,id,,"BadCancel",ThisObject);')

    def test_invalid_handler_contracts_fail_before_consuming_reader(self):
        self.vm.execute('''
Function Hidden(P,V,E) Count=Count+1; Return V; EndFunction
Function Short(P,V) Export Count=Count+1; Return V; EndFunction
Function Long(P,V,E,Required) Export Count=Count+1; Return V; EndFunction
Procedure Proc(P,V,E) Export Count=Count+1; EndProcedure
Async Function AsyncHandler(P,V,E) Export Count=Count+1; Return V; EndFunction
''')
        for name in ('Hidden', 'Short', 'Long', 'Proc', 'AsyncHandler', 'Missing'):
            with self.subTest(name=name):
                reader = self.reader('1')
                with self.assertRaises(BSLError):
                    self.vm.execute(f'ReadJSON(reader,,,,"{name}",ThisObject)')
                self.assertEqual(reader._position, -1)
                self.assertIsNone(reader._tokens)
        self.assertEqual(self.vm.variables['count'], D(0))

    def test_invalid_write_handlers_fail_before_invoking_or_writing(self):
        self.vm.execute('''
Function Short(P,V,E) Export Count=Count+1; Return V; EndFunction
Procedure Proc(P,V,E,C) Export Count=Count+1; EndProcedure
Async Function AsyncHandler(P,V,E,C) Export Count=Count+1; Return V; EndFunction
''')
        for name in ('Short', 'Proc', 'AsyncHandler', 'Missing'):
            with self.subTest(name=name):
                self.writer()
                with self.assertRaises(BSLError):
                    self.vm.execute(f'WriteJSON(writer,id,,"{name}",ThisObject);')
                self.vm.execute('WriteJSON(writer,1);')
                self.assertEqual(self.vm.execute('writer.Close()'), '1')
        self.assertEqual(self.vm.variables['count'], D(0))

    def test_handler_name_and_module_validation_never_evaluates_strings(self):
        for name, module in (('1', 'ThisObject'), ('""', 'ThisObject'),
                             ('Undefined', 'ThisObject'), ('"Revive"', 'Undefined'),
                             ('"Revive"', '1'), ('"Revive"', 'New Structure'),
                             ('"Revive"', '"not.imported"'),
                             ('"Revive"', '"../Handlers.bsl"'),
                             ('"Revive(reader,1,2)"', 'ThisObject')):
            with self.subTest(name=name, module=module):
                reader = self.reader('1')
                with self.assertRaises(BSLError):
                    self.vm.execute(f'ReadJSON(reader,,,,{name},{module})')
                self.assertEqual(reader._position, -1)
        self.assertEqual(self.vm.variables['count'], D(0))

    def test_foreign_modules_and_python_receivers_are_not_reflected(self):
        class Trap:
            def __getattr__(self, name):
                raise AssertionError('JSON module lookup must not reflect Python attributes')
        other = Interpreter(lambda _: None)
        try:
            other.execute(SOURCE)
            for value in (Trap(), other._self_module):
                self.vm.variables['target'] = value
                reader = self.reader('1')
                with self.assertRaises(BSLError):
                    self.vm.execute('ReadJSON(reader,,,,"Revive",target)')
                self.assertEqual(reader._position, -1)
            self.assertEqual(other.variables['count'], D(0))
        finally:
            other.close()

    def test_handlers_cannot_cross_context_or_restore_context_in_nocontext_routine(self):
        self.vm.execute('''
&AtServer
Function ServerRead(P,V,E) Export Return V; EndFunction
&AtClientAtServerNoContext
Function NoContext(R,M) Return ReadJSON(R,,,,"Revive",M); EndFunction
''')
        for expression in ('ReadJSON(reader,,,,"ServerRead",ThisObject)',
                           'NoContext(reader,ThisObject)'):
            reader = self.reader('1')
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)
            self.assertEqual(reader._position, -1)

    def test_read_reviver_postorder_includes_root_and_unnamed_array_elements(self):
        self.reader('{"first":[1,{"leaf":2}],"last":3}')
        self.vm.execute('extra=New Array; value=ReadJSON(reader,,,,"Revive",ThisObject,extra);')
        self.assertEqual(self.vm.variables['seen'].items,
                         [None, 'leaf', None, 'first', 'last', None])
        extra = self.vm.variables['extra'].items
        self.assertEqual(extra[0], D(1))
        self.assertEqual(extra[1], D(2))
        self.assertIs(extra[-1], self.vm.variables['value'])
        self.assertIs(extra[2], self.vm.execute('value.first[1]'))
        self.assertIs(extra[3], self.vm.execute('value.first'))

    def test_read_replacements_are_visible_to_parent_and_false_root_is_kept(self):
        self.vm.execute('''
Function Replace(P,V,E) Export
    If TypeOf(V)=Type("Number") Then Return V*10; EndIf;
    If P=Undefined Then Return V.item+V.array[0]; EndIf;
    Return V;
EndFunction
''')
        self.reader('{"item":2,"array":[3]}')
        self.assertEqual(self.vm.execute('ReadJSON(reader,,,,"Replace",ThisObject)'), D(50))
        self.reader('123')
        self.assertIs(self.vm.execute('ReadJSON(reader,,,,"ReviveFalse",ThisObject)'), False)

    def test_read_filter_uses_exact_case_array_and_fixed_array(self):
        for fixed in (False, True):
            with self.subTest(fixed=fixed):
                self.vm.execute('Seen=New Array; names=New Array; names.Add("A");')
                if fixed:
                    self.vm.execute('names=New FixedArray(names);')
                self.reader('{"A":1,"a":2,"nested":{"A":3},"array":[4]}')
                self.vm.execute('value=ReadJSON(reader,True,,,"ReviveFalse",ThisObject,,names);')
                self.assertIs(self.vm.execute('value.Get("A")'), False)
                self.assertEqual(self.vm.execute('value.Get("a")'), D(2))
                self.assertIs(self.vm.execute('value.Get("nested").Get("A")'), False)
                self.assertEqual(self.vm.execute('value.Get("array")[0]'), D(4))

    def test_date_property_string_is_one_name_not_comma_separated(self):
        self.reader(json.dumps({'a,b': ISO_TEXT, 'a': ISO_TEXT, 'b': ISO_TEXT}))
        self.vm.execute('value=ReadJSON(reader,True,"a,b");')
        self.assertIs(self.vm.execute('TypeOf(value.Get("a,b"))'), BSLType.DATE)
        self.assertEqual(self.vm.execute('value.Get("a")'), ISO_TEXT)
        self.assertEqual(self.vm.execute('value.Get("b")'), ISO_TEXT)

    def test_date_property_arrays_restore_dates_without_handler_using_exact_names(self):
        for fixed in (False, True):
            with self.subTest(fixed=fixed):
                self.vm.execute('names=New Array; names.Add("Date");')
                if fixed:
                    self.vm.execute('names=New FixedArray(names);')
                self.reader(json.dumps({'Date': ISO_TEXT, 'date': ISO_TEXT,
                                        'nested': {'Date': ISO_TEXT}, 'array': [ISO_TEXT]}))
                self.vm.execute('value=ReadJSON(reader,True,names);')
                self.assertIs(self.vm.execute('TypeOf(value.Get("Date"))'), BSLType.DATE)
                self.assertIs(self.vm.execute('TypeOf(value.Get("nested").Get("Date"))'), BSLType.DATE)
                self.assertEqual(self.vm.execute('value.Get("date")'), ISO_TEXT)
                self.assertEqual(self.vm.execute('value.Get("array")[0]'), ISO_TEXT)

    def test_selected_reviver_takes_precedence_over_date_restoration(self):
        self.vm.execute('dates=New Array; dates.Add("first"); dates.Add("second"); '
                        'names=New Array; names.Add("first");')
        self.reader(json.dumps({'first': ISO_TEXT, 'second': ISO_TEXT}))
        self.vm.execute('value=ReadJSON(reader,,dates,,"Revive",ThisObject,,names);')
        self.assertEqual(self.vm.execute('value.first'), ISO_TEXT)
        self.assertIs(self.vm.execute('TypeOf(value.second)'), BSLType.DATE)
        self.assertEqual(self.vm.variables['seen'].items, ['first'])

    def test_optional_holes_defaults_and_bilingual_nine_argument_read(self):
        for expression in ('ReadJSON(reader,,,,,,,,)',
                           'ПрочитатьJSON(reader,,,,"Revive",ЭтотОбъект,,,500)',
                           'ReadJSON(reader,Undefined,Undefined,Undefined,Undefined,Undefined,'
                           'Undefined,Undefined,Undefined)'):
            with self.subTest(expression=expression):
                self.reader('[null,false,2]')
                self.assertEqual(self.vm.execute(expression).items, [None, False, D(2)])
        self.writer()
        self.vm.execute('WriteJSON(writer,False,,,,);')
        self.assertEqual(self.vm.execute('writer.Close()'), 'false')

    def test_expanded_global_argument_limits_and_required_holes(self):
        self.reader('1')
        self.writer()
        for expression in ('ReadJSON()', 'ReadJSON(,)', 'ReadJSON(reader,,,,,,,,,)',
                           'WriteJSON(writer)', 'WriteJSON(writer,,)',
                           'WriteJSON(writer,1,,,,,)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)
        self.assertEqual(self.vm.variables['reader']._position, -1)
        self.vm.execute('WriteJSON(writer,1);')
        self.assertEqual(self.vm.execute('writer.Close()'), '1')

    def test_maximum_nesting_is_enforced_and_valid_limit_is_honored(self):
        for text in ('[[]]', '[[1]]', '{"a":{}}', '{"a":{"b":1}}'):
            with self.subTest(text=text):
                self.reader(text)
                with self.assertRaises(BSLError):
                    self.vm.execute('ReadJSON(reader,,,,,,,,1)')
        for text in ('[]', '[1]', '{}', '{"a":1}'):
            with self.subTest(text=text):
                self.reader(text)
                self.vm.execute('ReadJSON(reader,,,,,,,,1)')
        self.reader('[[1]]')
        self.vm.execute('value=ReadJSON(reader,,,,,,,,2);')
        self.assertEqual(self.vm.execute('value[0][0]'), D(1))

    def test_invalid_read_options_fail_before_consuming_reader(self):
        tails = ('1', ',1', ',,"ISO"')
        expressions = ['ReadJSON(reader,'+tail+')' for tail in tails]
        expressions += ['ReadJSON(reader,,,,"Revive",ThisObject,,"name")']
        expressions += [f'ReadJSON(reader,,,,,,,,{limit})'
                        for limit in ('0', '-1', '1.5', '501', 'True', '"2"')]
        self.vm.execute('names=New Array; names.Add(1);')
        expressions += ['ReadJSON(reader,,names)',
                        'ReadJSON(reader,,,,"Revive",ThisObject,,names)']
        for expression in expressions:
            with self.subTest(expression=expression):
                reader = self.reader('1')
                with self.assertRaises(BSLError):
                    self.vm.execute(expression)
                self.assertEqual(reader._position, -1)

    def test_nested_read_and_write_handlers_are_reentrant(self):
        self.vm.execute('''
Function NestedWrite(P,V,E,C) Export
    w=New JSONWriter; w.SetString(New JSONWriterSettings(JSONLineBreak.None));
    WriteJSON(w,V,,"Convert",ThisObject); Return w.Close();
EndFunction
Function NestedRead(P,V,E) Export
    If TypeOf(V)=Type("Number") Then
        r=New JSONReader; r.SetString("7");
        Return V+ReadJSON(r,,,,"Revive",ThisObject);
    EndIf;
    Return V;
EndFunction
''')
        self.writer()
        self.vm.execute('WriteJSON(writer,id,,"NestedWrite",ThisObject);')
        self.assertEqual(json.loads(json.loads(self.vm.execute('writer.Close()'))), UUID_TEXT)
        self.reader('[1,2]')
        self.assertEqual(self.vm.execute('ReadJSON(reader,,,,"NestedRead",ThisObject)').items,
                         [D(8), D(9)])
        self.assertIsNone(self.vm.locals)

    def test_json_handlers_interoperate_with_normal_callbacks(self):
        self.vm.execute('''
Function Add(V,E) Export Return V+E; EndFunction
Function ReadCallback(P,V,E) Export Return RunCallback(E,V); EndFunction
Function WriteCallback(P,V,E,C) Export Return RunCallback(E,String(V)); EndFunction
''')
        self.reader('2')
        self.vm.execute('c=New CallbackDescription("Add",ThisObject,5); '
                        'value=ReadJSON(reader,,,,"ReadCallback",ThisObject,c);')
        self.assertEqual(self.vm.variables['value'], D(7))
        self.writer()
        self.vm.execute('c=New CallbackDescription("Add",ThisObject,"!"); '
                        'WriteJSON(writer,id,,"WriteCallback",ThisObject,c);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), UUID_TEXT+'!')

    def test_async_caller_can_read_and_write_with_synchronous_handlers(self):
        self.vm.execute('''
Async Function Work(Val Input)
    pause=Await 0;
    r=New JSONReader; r.SetString(Input);
    value=ReadJSON(r,,,,"Revive",ThisObject);
    w=New JSONWriter; w.SetString(New JSONWriterSettings(JSONLineBreak.None));
    WriteJSON(w,id,,"Convert",ThisObject); Return String(value)+":"+w.Close();
EndFunction
''')
        self.vm.execute('first=Work("1"); second=Work("2");')
        self.assertEqual(self.vm.variables['first'].result, '1:"'+UUID_TEXT+'"')
        self.assertEqual(self.vm.variables['second'].result, '2:"'+UUID_TEXT+'"')
        self.assertEqual(self.vm.variables['count'], D(4))
        self.assertIsNone(self.vm.locals)

    def test_handler_optional_parameters_and_argument_evaluation_order(self):
        self.vm.execute('''
Var Trace;
Function R() Trace=Trace+"R"; Return reader; EndFunction
Function N() Trace=Trace+"N"; Return "ReadExtra"; EndFunction
Function M() Trace=Trace+"M"; Return ThisObject; EndFunction
Function E() Trace=Trace+"E"; Return 2; EndFunction
Function ReadExtra(P,V,E,Tail=3) Export Return V+E+Tail; EndFunction
Function WriteExtra(P,V,E,C,Tail="!") Export Return String(V)+Tail; EndFunction
Trace="";
''')
        self.reader('4')
        self.assertEqual(self.vm.execute('ReadJSON(R(),,,,N(),M(),E())'), D(9))
        self.assertEqual(self.vm.variables['trace'], 'RNME')
        self.writer()
        self.vm.execute('WriteJSON(writer,id,,"WriteExtra",ThisObject);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')), UUID_TEXT+'!')

    def test_handler_settings_mutation_does_not_change_in_flight_date_format(self):
        self.vm.execute('''
Function ChangeSettings(P,V,E,C) Export
    E.DateSerializationFormat=JSONDateFormat.JavaScript; Return String(V);
EndFunction
''')
        self.writer()
        self.vm.execute('s=New JSONSerializerSettings; '
                        'value=New Structure("id,date",id,Date(2024,1,2,3,4,5)); '
                        'WriteJSON(writer,value,s,"ChangeSettings",ThisObject,s);')
        self.assertEqual(json.loads(self.vm.execute('writer.Close()')),
                         {'id': UUID_TEXT, 'date': ISO_TEXT})
        self.assertTrue(self.vm.execute('(s.DateSerializationFormat=JSONDateFormat.JavaScript)'))


if __name__ == '__main__':
    unittest.main()
