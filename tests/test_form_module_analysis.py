"""Synthetic static-only evidence, not native execution or activation evidence."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import UUID

from yadinassi import form_module_analysis as fm
from yadinassi.configuration_xml import import_configuration
from sqlite_catalog_fixture import configuration_files


SOURCE = '''&НаКлиенте
Процедура NameChanged(Элемент)
 Объект.Наименование = СокрЛП(Объект.Наименование);
 Если СтрДлина(Объект.Наименование) < 3 Тогда
  Сообщение = Новый СообщениеПользователю;
  Сообщение.Текст = "At least three characters";
  Сообщение.Поле = "Объект.Наименование";
  Сообщение.Сообщить();
 КонецЕсли;
КонецПроцедуры
&НаСервере
Процедура BeforeSave(Отказ, ТекущийОбъект, ПараметрыЗаписи)
 Если ТекущийОбъект.ПометкаУдаления Тогда
  Возврат;
 КонецЕсли;
 ТекущийОбъект.Наименование = СокрЛП(ТекущийОбъект.Наименование);
 Если СтрДлина(ТекущийОбъект.Наименование) < 3 Тогда
  Отказ = Истина;
  Сообщение = Новый СообщениеПользователю;
  Сообщение.Текст = "Please enter a longer name";
  Сообщение.Поле = "Объект.Наименование";
  Сообщение.Сообщить();
 КонецЕсли;
КонецПроцедуры
'''.encode()
CATALOG = b'''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Catalog uuid="00000000-0000-0000-0000-000000000003"><Properties><Name>Products</Name><CodeType>String</CodeType><CodeLength>9</CodeLength><DescriptionLength>100</DescriptionLength><DefaultObjectForm>Catalog.Products.Form.Item</DefaultObjectForm></Properties><ChildObjects><Form>Item</Form></ChildObjects></Catalog></MetaDataObject>'''
FORM = b'''<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Form uuid="00000000-0000-0000-0000-000000000004"><Properties><Name>Item</Name><FormType>Managed</FormType></Properties></Form></MetaDataObject>'''
DEFINITION = '''<Form xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config">
<Events><Event name="BeforeWriteAtServer">BeforeSave</Event></Events>
<ChildItems><InputField name="Code" id="1"><DataPath>Объект.Code</DataPath><ReadOnly>true</ReadOnly></InputField>
<InputField name="Description" id="4"><DataPath>Объект.Description</DataPath><Events><Event name="OnChange">NameChanged</Event></Events></InputField></ChildItems>
<Attributes><Attribute name="Объект" id="1"><Type><v8:Type>cfg:CatalogObject.Products</v8:Type></Type><MainAttribute>true</MainAttribute><SavedData>true</SavedData></Attribute></Attributes></Form>'''.encode()
PATHS = dict(catalog_path='Catalogs/Products.xml', form_path='Catalogs/Products/Forms/Item.xml',
    definition_path='Catalogs/Products/Forms/Item/Ext/Form.xml',
    module_path='Catalogs/Products/Forms/Item/Ext/Form/Module.bsl')


def binding(source=SOURCE, catalog=CATALOG, form=FORM, definition=DEFINITION):
    return fm.FormModuleBinding(UUID(int=1), UUID(int=2), 1, UUID(int=3), 'Products', UUID(int=4), 'Item',
        *(sha256(raw).hexdigest() for raw in (source, catalog, form, definition)))


class FormModuleAnalysisTests(unittest.TestCase):
    def analyze(self, source=SOURCE, catalog=CATALOG, form=FORM, definition=DEFINITION, bound=None, **paths):
        return fm.analyze_form_module(source, bound if bound is not None else binding(source, catalog, form, definition),
            catalog_xml=catalog, form_xml=form, definition_xml=definition, **(PATHS | paths))

    def reject(self, **kwargs):
        with self.assertRaises(fm.FormModuleAnalysisError): self.analyze(**kwargs)

    def mutate(self, old, new):
        self.assertIn(old.encode(), SOURCE)
        return SOURCE.replace(old.encode(), new.encode())

    def test_complete_static_description(self):
        result = self.analyze()
        self.assertIs(result.source, SOURCE)
        self.assertEqual(result.profile, 'catalog-form-name-validation-static-v1')
        self.assertIs(result.native_parity, False)
        self.assertEqual([(e.event, e.execution_context) for e in result.events],
            [('OnChange', 'client'), ('BeforeWriteAtServer', 'server')])
        self.assertEqual(result.fields[0].metadata_path, 'Объект.Code')
        self.assertTrue(result.fields[0].read_only)
        self.assertEqual(result.fields[1].source_path, 'Объект.Наименование')
        self.assertEqual(result.fields[1].maximum_length, 100)
        self.assertFalse(hasattr(result, 'execute'))
        self.assertFalse(hasattr(result, 'ast'))

    def test_immutable_description(self):
        result = self.analyze()
        for obj, field in ((result, 'source'), (result.binding, 'catalog_id'),
                           (result.fields[0], 'read_only'), (result.events[0], 'message_text')):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError): setattr(obj, field, None)

    def test_bom_crlf_and_comments_preserve_exact_source(self):
        source = b'\xef\xbb\xbf' + SOURCE.replace(b'\n', b'\r\n') + b'// harmless comment\r\n'
        self.assertIs(self.analyze(source=source).source, source)

    def test_alternative_catalog_and_form_names_derive_paths(self):
        catalog = CATALOG.replace(b'Products', b'Goods').replace(b'Item', b'Editor')
        form = FORM.replace(b'Item', b'Editor')
        definition = DEFINITION.replace(b'Products', b'Goods')
        bound = replace(binding(SOURCE, catalog, form, definition), catalog_name='Goods', form_name='Editor')
        paths = {k: v.replace('Products', 'Goods').replace('Item', 'Editor') for k, v in PATHS.items()}
        self.assertEqual(self.analyze(catalog=catalog, form=form, definition=definition, bound=bound, **paths).binding, bound)

    def test_all_four_hashes_checked_before_parse(self):
        for key in ('source_sha256', 'catalog_sha256', 'form_sha256', 'definition_sha256'):
            with self.subTest(key=key), patch.object(fm, 'Parser', side_effect=AssertionError('parsed')):
                self.reject(bound=replace(binding(), **{key: '0' * 64}))

    def test_bad_hash_format(self):
        for value in ('A' * 64, 'abc', None, 1):
            self.reject(bound=replace(binding(), source_sha256=value))

    def test_identity_types_collisions_and_generation(self):
        self.reject(bound={})
        for key in ('database_id', 'configuration_id', 'catalog_id', 'form_id'):
            for value in (UUID(int=0), 'not-uuid', None, UUID(int=1)):
                if key == 'database_id' and value == UUID(int=1): continue
                self.reject(bound=replace(binding(), **{key: value}))
        for value in (0, -1, True, 2**63, '1'):
            self.reject(bound=replace(binding(), configuration_generation=value))

    def test_canonical_paths_reject_alias_traversal_and_owner_swap(self):
        for key, original in PATHS.items():
            for value in ('/' + original, original.replace('/', '\\'), '../' + original,
                          original.replace('Products', 'Other'), original + '/', None):
                self.reject(**{key: value})

    def test_source_and_metadata_byte_types_and_budgets(self):
        for raw in ('text', bytearray(SOURCE), b'', b'x' * (fm.MAX_SOURCE_BYTES + 1)):
            self.reject(source=raw, bound=binding())
        for key in ('catalog', 'form', 'definition'):
            self.reject(**{key: b'x' * (fm.MAX_XML_BYTES + 1)}, bound=binding())

    def test_invalid_encoding_and_xml(self):
        self.reject(source=b'\xff')
        self.reject(source=b'\x00' + SOURCE)
        for key in ('catalog', 'form', 'definition'):
            for raw in (b'\xff', b'<broken>', b'<!DOCTYPE a><a/>'):
                self.reject(**{key: raw})

    def test_xml_entity_expansion_and_utf16_rejected(self):
        self.reject(definition=b'<!DOCTYPE Form [<!ENTITY x "x">]>' + DEFINITION)
        self.reject(definition=DEFINITION.decode().encode('utf-16'))
        self.reject(definition=b'<?hidden instruction?>' + DEFINITION)

    def test_metadata_owner_names_uuids_and_default_form(self):
        for old, new in ((b'Products', b'Other'), (b'000000000003', b'000000000099'),
                         (b'Catalog.Products.Form.Item', b'Catalog.Other.Form.Item')):
            self.reject(catalog=CATALOG.replace(old, new))
        self.reject(form=FORM.replace(b'000000000004', b'000000000099'))
        self.reject(form=FORM.replace(b'<Name>Item', b'<Name>Other'))

    def test_unknown_metadata_elements_and_attributes(self):
        for raw, key in ((CATALOG, 'catalog'), (FORM, 'form')):
            self.reject(**{key: raw.replace(b'<Properties>', b'<Properties extra="x">')})
            self.reject(**{key: raw.replace(b'</Properties>', b'<Unknown/></Properties>')})
        self.reject(catalog=CATALOG.replace(b'</ChildObjects>', b'<Attribute/></ChildObjects>'))

    def test_duplicate_metadata_settings_and_owner(self):
        self.reject(catalog=CATALOG.replace(b'<Name>Products</Name>', b'<Name>Products</Name>' * 2))
        self.reject(form=FORM.replace(b'</Properties>', b'<FormType>Managed</FormType></Properties>'))

    def test_scalar_metadata_qualifiers(self):
        for old, new in ((b'>String<', b'>Number<'), (b'>9<', b'>0<'),
                         (b'>100<', b'>1025<'), (b'>9<', b'>9999999<')):
            self.reject(catalog=CATALOG.replace(old, new))

    def test_main_object_type_namespace_and_saved_data(self):
        for old, new in ((b'CatalogObject.Products', b'CatalogObject.Other'),
                         (b'CatalogObject.Products', b'CatalogRef.Products'),
                         (b'http://v8.1c.ru/8.1/data/enterprise/current-config', b'urn:fake'),
                         (b'<MainAttribute>true', b'<MainAttribute>false'),
                         (b'<SavedData>true', b'<SavedData>false')):
            self.reject(definition=DEFINITION.replace(old, new))
        declaration = b' xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"'
        unbound = DEFINITION.replace(declaration, b'')
        self.reject(definition=unbound)
        # An unrelated sibling declaration does not bind the QName's use site.
        self.reject(definition=unbound.replace(b'<Events>', b'<Events' + declaration + b'>', 1))
        self.reject(definition=DEFINITION.replace(b'<Type>', b'<Type xmlns:cfg="urn:wrong">'))
        # A local correct declaration is valid, including shadowing an unrelated one.
        local = unbound.replace(b'<Type>', b'<Type' + declaration + b'>')
        self.assertEqual(self.analyze(definition=local).fields[1].maximum_length, 100)
        local = local.replace(b'<Events>', b'<Events xmlns:cfg="urn:unrelated">', 1)
        self.analyze(definition=local)

    def test_unknown_form_elements_attributes_events(self):
        for old, new in ((b'<ChildItems>', b'<ChildItems><Button/>'),
                         (b'<ChildItems>', b'<ChildItems extra="x">'),
                         (b'OnChange', b'OnOpen'), (b'BeforeWriteAtServer', b'OnCreateAtServer'),
                         (b'</Events>', b'<Event name="Other">Other</Event></Events>')):
            self.reject(definition=DEFINITION.replace(old, new))

    def test_form_mapping_readonly_and_duplicate_fields(self):
        for old, new in ((b'.Description', b'.Ref'), (b'.Code', b'.Description'),
                         (b'<ReadOnly>true', b'<ReadOnly>false'),
                         (b'name="Description"', b'name="Code"'),
                         (b'<ReadOnly>true</ReadOnly>', b'<ReadOnly>true</ReadOnly>' * 2)):
            self.reject(definition=DEFINITION.replace(old, new))

    def test_event_signature_context_arity_and_export(self):
        for old, new in (('NameChanged(Элемент)', 'NameChanged(Другой)'),
                         ('BeforeSave(Отказ, ТекущийОбъект, ПараметрыЗаписи)', 'BeforeSave(Отказ)'),
                         ('&НаСервере', '&НаКлиенте'), ('&НаКлиенте', '&НаСервере'),
                         ('NameChanged(Элемент)', 'NameChanged(Элемент) Экспорт'),
                         ('NameChanged(Элемент)', 'NameChanged(Знач Элемент)'),
                         ('NameChanged(Элемент)', 'NameChanged(Элемент = 1)')):
            self.reject(source=self.mutate(old, new))

    def test_no_context_dual_and_conditional_hidden_bodies_rejected(self):
        for annotation in ('&НаСервереБезКонтекста', '&НаКлиентеНаСервереБезКонтекста', '&Extension'):
            self.reject(source=self.mutate('&НаСервере', annotation))
        self.reject(source=SOURCE + b'\n#If Server Then\nwhatever\n#EndIf')
        self.reject(source=SOURCE + b'\n// #Import "secret.bsl"')

    def test_extra_routines_and_initialization_rejected(self):
        self.reject(source=SOURCE + b'Procedure Extra() EndProcedure')
        self.reject(source=SOURCE + 'Сообщить("extra");'.encode())
        self.reject(source=SOURCE + b'Var Extra;')

    def test_complete_server_body_checked(self):
        self.reject(source=self.mutate('ТекущийОбъект.Наименование = СокрЛП', 'ТекущийОбъект.Наименование = Eval'))
        self.reject(source=self.mutate('ТекущийОбъект.ПометкаУдаления', 'ТекущийОбъект.Записать()'))
        self.reject(source=self.mutate('Возврат;', 'Сообщить("unreachable"); Возврат;'))

    def test_foreign_calls_paths_and_constructors_rejected(self):
        for old, new in (('СокрЛП', 'Eval'), ('Новый СообщениеПользователю', 'Новый HTTPСоединение'),
                         ('Новый СообщениеПользователю', 'Новый("СообщениеПользователю")'),
                         ('Новый СообщениеПользователю', 'Новый СообщениеПользователю(1)'),
                         ('Сообщение.Сообщить()', 'Сообщение.УстановитьДанные(Объект)'),
                         ('Объект.Наименование', 'Объект.Ссылка.Наименование'),
                         ('Сообщение.Поле', 'Сообщение.КлючДанных')):
            self.reject(source=self.mutate(old, new))

    def test_wrong_literals_and_message_field_rejected(self):
        for old, new in (('Отказ = Истина', 'Отказ = 1'), ('< 3', '< 4'),
                         ('"Объект.Наименование"', '"Объект.Code"'),
                         ('"At least three characters"', 'Объект.Наименование')):
            self.reject(source=self.mutate(old, new))

    def test_long_messages_and_empty_messages_rejected(self):
        for message in ('', 'x' * (fm.MAX_TEXT + 1)):
            self.reject(source=self.mutate('At least three characters', message))

    def test_token_ast_and_xml_budgets(self):
        for constant in ('MAX_TOKENS', 'MAX_AST_NODES', 'MAX_XML_NODES', 'MAX_DEPTH'):
            with patch.object(fm, constant, 1): self.reject()
        with self.assertRaisesRegex(fm.FormModuleAnalysisError, 'token budget'):
            self.analyze(source=SOURCE + b'x;' * fm.MAX_TOKENS)
        with self.assertRaisesRegex(fm.FormModuleAnalysisError, 'AST budget'):
            self.analyze(source=SOURCE + b'x;' * 110)
        with self.assertRaisesRegex(fm.FormModuleAnalysisError, 'XML budget'):
            self.analyze(catalog=CATALOG.replace(b'</Properties>', b'<Extra/>' * fm.MAX_XML_NODES + b'</Properties>'))

    def test_deep_source_rejected_before_parser(self):
        source = SOURCE.replace('СтрДлина(Объект.Наименование)'.encode(),
            ('(' * 40 + '3' + ')' * 40).encode())
        with patch.object(fm, 'Parser', side_effect=AssertionError('parsed')):
            self.reject(source=source)

    def test_no_interpreter_execution_or_activation(self):
        with patch('yadinassi.runtime.Interpreter.execute', side_effect=AssertionError('executed')), \
             patch('yadinassi.runtime.Interpreter.execute_program', side_effect=AssertionError('executed')):
            self.analyze()

    def test_configuration_import_remains_fail_closed(self):
        files = configuration_files()
        files[PATHS['module_path']] = SOURCE
        before = import_configuration(files)
        self.analyze()
        after = import_configuration(files)
        self.assertEqual(before, after)
        self.assertTrue(after.activation_issues)
        self.assertTrue(any(PATHS['module_path'] in issue for issue in after.activation_issues))


if __name__ == '__main__': unittest.main()
