"""Closed owned scalar XML admission; local coverage, not native runtime parity."""
from contextlib import closing
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import (
    MD, V8, XR, XS, XSI, _catalog_profile_fingerprint, _object,
    _SCALAR_PROFILE_SHA256, import_configuration,
)
from yadinassi.database_context import SQLiteDBContext
from yadinassi.errors import BSLRuntimeError
from yadinassi.sqlite_catalog_layout import quote_identifier
from test_official_catalog_xml_profile import files as empty_profile_files

CATALOG = ROOT / 'scripts/catalog_query_behavior/generated/Catalog.xml'
NAME = 'OwnedQuery31339d83'
PATH = 'Catalogs/'+NAME+'.xml'


def files(raw=None, name=NAME, config_id=None):
    return empty_profile_files(CATALOG.read_bytes() if raw is None else raw,
                               name, config_id)


def field_properties(root, index=0):
    return root[0].findall('{'+MD+'}ChildObjects/{'+MD+'}Attribute')[index].find('{'+MD+'}Properties')


def changed(change):
    root = ET.fromstring(CATALOG.read_bytes())
    change(root)
    # QName values are strings, so ElementTree does not retain their declaration.
    root.set('xmlns:xs', XS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


class OfficialCatalogScalarProfileTests(unittest.TestCase):
    def assert_refused(self, raw=None, source=None):
        source = files(raw) if source is None else source
        try:
            result = import_configuration(source)
        except ValueError:
            return
        self.assertTrue(result.activation_issues, 'mutation unexpectedly activated')
        self.assertEqual({item.path: item.content for item in result.files}, source)

    def test_owned_profile_preserves_exact_xml_and_typed_schema(self):
        source = files()
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual({item.path: item.content for item in result.files}, source)
        schema = result.catalogs[0]
        self.assertEqual((schema.name, schema.code_length, schema.description_length), (NAME, 8, 64))
        self.assertEqual([(f.name, f.kind, f.qualifiers, f.target_catalog_id) for f in schema.fields],
                         [('Quantity', 'number', (12, 2, 'Any'), None),
                          ('Active', 'boolean', (), None), ('Stamp', 'datetime', ('DateTime',), None)])
        self.assertEqual(schema.tabular_sections, ())

    def test_fixture_fingerprint_is_whole_object_and_generated_ids_only(self):
        obj, namespaces = _object(CATALOG.read_bytes(), 'Catalog')
        digest, generated = _catalog_profile_fingerprint(obj, namespaces, scalar_attributes=True)
        self.assertEqual(digest, _SCALAR_PROFILE_SHA256)
        self.assertEqual(len(generated), 10)
        fields = obj.findall('{'+MD+'}ChildObjects/{'+MD+'}Attribute')
        self.assertFalse(generated & {UUID(f.get('uuid')) for f in fields})

    def test_renamed_fields_catalog_and_fresh_uuids_remain_supported(self):
        raw = CATALOG.read_bytes().replace(NAME.encode(), 'Товары'.encode())
        for old, new in (('Quantity', 'Количество'), ('Active', 'Доступен'), ('Stamp', 'ДатаСобытия')):
            raw = raw.replace(('<Name>'+old+'</Name>').encode(), ('<Name>'+new+'</Name>').encode())
        root = ET.fromstring(raw)
        for node in root.iter():
            if 'uuid' in node.attrib:
                raw = raw.replace(node.get('uuid').encode(), str(uuid4()).encode())
            if node.tag in ('{'+XR+'}TypeId', '{'+XR+'}ValueId'):
                raw = raw.replace(node.text.encode(), str(uuid4()).encode())
        raw = raw.replace(b'<CodeLength>8</CodeLength>', b'<CodeLength>64</CodeLength>')
        raw = raw.replace(b'<DescriptionLength>64</DescriptionLength>', b'<DescriptionLength>1024</DescriptionLength>')
        result = import_configuration(files(raw, 'Товары'))
        self.assertEqual(result.activation_issues, ())
        self.assertEqual([f.name for f in result.catalogs[0].fields], ['Количество', 'Доступен', 'ДатаСобытия'])
        self.assertEqual((result.catalogs[0].code_length, result.catalogs[0].description_length), (64, 1024))
        self.assertEqual({f.path: f.content for f in result.files}, files(raw, 'Товары', str(result.config_uuid)))

    def test_legal_qname_aliases_and_bom_crlf_preserve_source(self):
        raw = CATALOG.read_bytes().replace(b'xmlns:xs=', b'xmlns:scalar=').replace(b'xs:', b'scalar:')
        raw = b'\xef\xbb\xbf' + raw.replace(b'\n', b'\r\n')
        source = files(raw)
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual({f.path: f.content for f in result.files}, source)

    def test_default_write_explicit_write_reopen_read_query_and_physical_fields(self):
        source = files()
        config = import_configuration(source)
        schema = config.catalogs[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'owned.sqlite'
            with SQLiteDBContext.create(path, config) as context:
                vm = Interpreter(database_context=context)
                vm.execute('P=Catalogs.'+NAME+'.CreateItem();P.Code="default";P.Write();'
                           'P=Catalogs.'+NAME+'.CreateItem();P.Code="typed";P.Description="owned";'
                           'P.Quantity=-123.45;P.Active=True;P.Stamp=Date(2024,2,29,12,34,56);P.Write();')
                mapping = context.backend.inspect_storage_mapping()
                self.assertEqual(mapping[0][:2], (schema.identity, NAME))
                self.assertEqual([(f[0], f[1]) for f in mapping[0][3]],
                                 [(f.identity, f.name) for f in schema.fields])
            with closing(sqlite3.connect(path)) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertNotIn('catalog_record', tables)
                table = quote_identifier(mapping[0][2])
                columns = {row[1] for row in connection.execute('PRAGMA table_info('+table+')')}
                self.assertEqual(columns, {'record_id', 'revision', 'code', 'description', 'deletion_mark'} |
                                 {f[2] for f in mapping[0][3]})
            with SQLiteDBContext(path) as context:
                vm = Interpreter(database_context=context)
                self.assertEqual(context.backend.inspect_storage_mapping(), mapping)
                self.assertEqual(context.backend.export_configuration(), source)
                vm.execute('D=Catalogs.'+NAME+'.FindByCode("default");R=Catalogs.'+NAME+'.FindByCode("typed");')
                self.assertEqual(vm.execute('D.Quantity'), Decimal(0))
                self.assertIs(vm.execute('D.Active'), False)
                self.assertEqual(vm.execute('XMLString(D.Stamp)'), '0001-01-01T00:00:00')
                self.assertEqual(vm.execute('R.Quantity'), Decimal('-123.45'))
                self.assertIs(vm.execute('R.Active'), True)
                self.assertEqual(vm.execute('XMLString(R.Stamp)'), '2024-02-29T12:34:56')
                vm.execute('Q=New Query("SELECT Code AS Item,Quantity,Active,Stamp FROM Catalog.'+NAME+
                           ' WHERE Quantity=&N AND Active=&A AND Stamp=&D");'
                           'Q.SetParameter("N",-123.45);Q.SetParameter("A",True);'
                           'Q.SetParameter("D",Date(2024,2,29,12,34,56));Result=Q.Execute();S=Result.Select();')
                self.assertIs(vm.execute('S.Next()'), True)
                self.assertEqual(vm.execute('S.Item'), 'typed')
                self.assertEqual(vm.execute('S.Quantity'), Decimal('-123.45'))
                self.assertIs(vm.execute('S.Active'), True)
                self.assertEqual(vm.execute('XMLString(S.Stamp)'), '2024-02-29T12:34:56')
                self.assertIs(vm.execute('S.Next()'), False)
                vm.execute('T=Result.Unload();')
                self.assertEqual(vm.execute('T.Columns[1].ValueType.NumberQualifiers.Digits'), Decimal(12))
                self.assertEqual(vm.execute('T.Columns[1].ValueType.NumberQualifiers.FractionDigits'), Decimal(2))
                self.assertEqual(context.backend.export_configuration(), source)

    def test_wrong_runtime_types_remain_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteDBContext.create(Path(directory)/'owned.sqlite', import_configuration(files())) as context:
                vm = Interpreter(database_context=context)
                vm.execute('P=Catalogs.'+NAME+'.CreateItem();P.Code="1";')
                for code, error in (('P.Quantity=True;', 'catalog field type mismatch'),
                                    ('P.Active=1;', 'catalog field type mismatch'),
                                    ('P.Stamp="2024-01-01";', 'Date field requires Date')):
                    with self.subTest(code=code), self.assertRaisesRegex(BSLRuntimeError, error):
                        vm.execute(code)
                self.assertIs(vm.execute('P.IsNew()'), True)

    def test_numeric_qualifiers_apply_before_write_without_widening_xml_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            source = files()
            with SQLiteDBContext.create(Path(directory)/'owned.sqlite', import_configuration(source)) as context:
                vm = Interpreter(database_context=context)
                vm.execute('P=Catalogs.'+NAME+'.CreateItem();P.Code="1";P.Quantity=1.005;')
                self.assertEqual(vm.execute('P.Quantity'), Decimal('1.01'))
                vm.execute('P.Quantity=10000000000;')
                self.assertEqual(vm.execute('P.Quantity'), Decimal('9999999999.99'))
                vm.execute('P.Write();')
                self.assertEqual(vm.execute('P.Ref.Quantity'), Decimal('9999999999.99'))
                self.assertEqual(context.backend.export_configuration(), source)

    def test_every_scalar_default_property_is_bound_to_the_whole_profile(self):
        root = ET.fromstring(CATALOG.read_bytes())
        for index in range(3):
            for node in field_properties(root, index):
                local = node.tag.rsplit('}', 1)[-1]
                if local in ('Name', 'Type'):
                    continue
                with self.subTest(index=index, property=local):
                    def mutate(tree):
                        field_properties(tree, index).find(node.tag).text = 'unexpected'
                    self.assert_refused(changed(mutate))

    def test_fill_value_types_nil_and_whitespace_are_not_discarded(self):
        for index in range(3):
            for attrs, content in (({'{'+XSI+'}type': 'xs:string'}, '0'),
                                   ({'{'+XSI+'}nil': 'true'}, None),
                                   ({'{'+XSI+'}type': 'xs:decimal', '{'+XSI+'}nil': 'true'}, '0'),
                                   (None, ' ')):
                with self.subTest(index=index, attrs=attrs, content=content):
                    def mutate(root):
                        node = field_properties(root, index).find('{'+MD+'}FillValue')
                        if attrs is not None:
                            node.attrib.clear(); node.attrib.update(attrs)
                        node.text = content
                    self.assert_refused(changed(mutate))

    def test_unknown_property_and_embedded_executable_components_are_blocked(self):
        for tag in ('Unexpected', 'ObjectModule', 'Script', 'Procedure'):
            with self.subTest(tag=tag):
                def mutate(root):
                    ET.SubElement(field_properties(root), '{'+MD+'}'+tag).text = 'Run()'
                self.assert_refused(changed(mutate))

    def test_unknown_attribute_envelopes_never_match(self):
        for target in ('field', 'properties', 'name', 'type', 'qualifier', 'default'):
            with self.subTest(target=target):
                def mutate(root):
                    p = field_properties(root)
                    node = {'field': root[0].find('{'+MD+'}ChildObjects')[0], 'properties': p,
                            'name': p.find('{'+MD+'}Name'), 'type': p.find('{'+MD+'}Type'),
                            'qualifier': p.find('{'+MD+'}Type/{'+V8+'}NumberQualifiers'),
                            'default': p.find('{'+MD+'}FillValue')}[target]
                    node.set('unknown', 'true')
                self.assert_refused(changed(mutate))

    def test_nested_attribute_objects_and_mixed_content_are_blocked(self):
        for target in ('child', 'text', 'tail'):
            with self.subTest(target=target):
                def mutate(root):
                    field = root[0].find('{'+MD+'}ChildObjects')[0]
                    if target == 'child':
                        ET.SubElement(field, '{'+MD+'}ChildObjects')
                    elif target == 'text':
                        field.text = 'unexpected'
                    else:
                        field_properties(root).find('{'+MD+'}Type').tail = 'unexpected'
                self.assert_refused(changed(mutate))

    def test_complete_fields_may_be_removed_added_or_reordered(self):
        for operation in ('remove', 'add', 'reorder', 'section'):
            with self.subTest(operation=operation):
                def mutate(root):
                    child = root[0].find('{'+MD+'}ChildObjects')
                    if operation == 'remove': child.remove(child[0])
                    elif operation == 'reorder':
                        field = child[1]; child.remove(field); child.insert(0, field)
                    elif operation == 'section':
                        ET.SubElement(child, '{'+MD+'}TabularSection', uuid=str(uuid4()))
                    else:
                        field = deepcopy(child[0]); field.set('uuid', str(uuid4()))
                        field.find('{'+MD+'}Properties/{'+MD+'}Name').text = 'Additional'
                        child.append(field)
                raw = changed(mutate)
                if operation == 'section':
                    self.assert_refused(raw)
                else:
                    source = files(raw)
                    result = import_configuration(source)
                    self.assertEqual(result.activation_issues, ())
                    self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_type_substitution_and_composite_type_are_blocked(self):
        for index, replacement in ((0, 'xs:boolean'), (1, 'xs:decimal'), (2, 'xs:string'),
                                   (0, 'cfg:CatalogRef.'+NAME)):
            with self.subTest(index=index, replacement=replacement):
                def mutate(root):
                    root.set('xmlns:cfg', 'http://v8.1c.ru/8.1/data/enterprise/current-config')
                    field_properties(root, index).find('{'+MD+'}Type/{'+V8+'}Type').text = replacement
                self.assert_refused(changed(mutate))
        self.assert_refused(changed(lambda root: ET.SubElement(
            field_properties(root, 1).find('{'+MD+'}Type'), '{'+V8+'}Type')))

    def test_qualifiers_remain_exact_even_when_other_bounds_are_valid(self):
        for tag, values in (('Digits', ('1', '13', '38', '0', '39', '012', '+12', '１２')),
                            ('FractionDigits', ('0', '3', '13', '-1')),
                            ('AllowedSign', ('Nonnegative', 'Unknown'))):
            for value in values:
                with self.subTest(tag=tag, value=value):
                    def mutate(root):
                        field_properties(root).find('{'+MD+'}Type/{'+V8+'}NumberQualifiers/{'+V8+'}'+tag).text = value
                    self.assert_refused(changed(mutate))
        for value in ('Date', 'Time', 'Unknown'):
            with self.subTest(fractions=value):
                def mutate(root):
                    field_properties(root, 2).find('{'+MD+'}Type/{'+V8+'}DateQualifiers/{'+V8+'}DateFractions').text = value
                self.assert_refused(changed(mutate))

    def test_duplicate_or_foreign_type_qualifiers_are_blocked(self):
        for operation in ('duplicate', 'foreign', 'unknown'):
            with self.subTest(operation=operation):
                def mutate(root):
                    t = field_properties(root).find('{'+MD+'}Type')
                    q = t.find('{'+V8+'}NumberQualifiers')
                    if operation == 'duplicate': t.append(deepcopy(q))
                    elif operation == 'foreign': q[0].tag = '{urn:foreign}Digits'
                    else: ET.SubElement(q, '{'+V8+'}Unexpected').text = '0'
                self.assert_refused(changed(mutate))

    def test_global_and_local_type_namespace_rebinding_are_blocked(self):
        raw = CATALOG.read_bytes()
        for old, new in ((b'xmlns:xs="'+XS.encode()+b'"', b'xmlns:xs="urn:foreign"'),
                         (b'<v8:Type>xs:boolean', b'<v8:Type xmlns:xs="urn:foreign">xs:boolean'),
                         (b'<FillValue xsi:type=', b'<FillValue xmlns:xs="urn:foreign" xsi:type=')):
            with self.subTest(old=old):
                self.assertIn(old, raw)
                self.assert_refused(raw.replace(old, new, 1))

    def test_standard_property_mutation_does_not_admit_valid_custom_fields(self):
        raw = CATALOG.read_bytes()
        for old, new in ((b'<xr:FillValue xsi:type="xs:string"/>', b'<xr:FillValue xsi:type="xs:string"> </xr:FillValue>'),
                         (b'<QuickChoice>false</QuickChoice>', b'<QuickChoice>true</QuickChoice>'),
                         (b'<Owners/>', b'<Owners><Catalog>Other</Catalog></Owners>')):
            with self.subTest(old=old):
                self.assertIn(old, raw)
                self.assert_refused(raw.replace(old, new, 1))

    def test_duplicate_property_and_missing_default_are_blocked(self):
        for operation in ('duplicate', 'remove'):
            with self.subTest(operation=operation):
                def mutate(root):
                    props = field_properties(root)
                    node = props.find('{'+MD+'}FillValue')
                    if operation == 'duplicate': props.append(deepcopy(node))
                    else: props.remove(node)
                self.assert_refused(changed(mutate))

    def test_field_uuid_collisions_with_catalog_generated_and_sibling_are_blocked(self):
        for target in ('catalog', 'generated', 'sibling'):
            with self.subTest(target=target):
                def mutate(root):
                    fields = root[0].find('{'+MD+'}ChildObjects')
                    value = {'catalog': root[0].get('uuid'), 'generated': root.find('.//{'+XR+'}TypeId').text,
                             'sibling': fields[1].get('uuid')}[target]
                    fields[0].set('uuid', value)
                self.assert_refused(changed(mutate))

    def test_field_and_generated_uuids_cannot_collide_with_configuration(self):
        root = ET.fromstring(CATALOG.read_bytes())
        for identity in (root[0].find('{'+MD+'}ChildObjects')[0].get('uuid'),
                         root.find('.//{'+XR+'}TypeId').text):
            with self.subTest(identity=identity):
                self.assert_refused(source=files(config_id=identity))

    def test_cross_catalog_uuid_collisions_are_blocked_in_both_inventory_orders(self):
        first = files()
        other = CATALOG.read_bytes().replace(NAME.encode(), b'Other')
        root = ET.fromstring(other)
        for node in root.iter():
            if 'uuid' in node.attrib: other = other.replace(node.get('uuid').encode(), str(uuid4()).encode())
            if node.tag in ('{'+XR+'}TypeId', '{'+XR+'}ValueId'):
                other = other.replace(node.text.encode(), str(uuid4()).encode())
        second = ET.fromstring(other)
        original = ET.fromstring(first[PATH])
        generated = original.find('.//{'+XR+'}TypeId').text
        field_id = original[0].find('{'+MD+'}ChildObjects')[0].get('uuid')
        second_field = second[0].find('{'+MD+'}ChildObjects')[0].get('uuid')
        second_generated = second.find('.//{'+XR+'}TypeId').text
        for old, new in ((second_field, generated), (second_generated, field_id),
                         (second_field, field_id), (second[0].get('uuid'), field_id)):
            for reverse in (False, True):
                with self.subTest(old=old, new=new, reverse=reverse):
                    source = dict(first)
                    order = ('Other', NAME) if reverse else (NAME, 'Other')
                    config = ET.fromstring(source['Configuration.xml'])
                    children = config[0].find('{'+MD+'}ChildObjects')
                    children.clear()
                    for name in order: ET.SubElement(children, '{'+MD+'}Catalog').text = name
                    source['Configuration.xml'] = ET.tostring(config, encoding='utf-8')
                    source['Catalogs/Other.xml'] = other.replace(old.encode(), new.encode(), 1)
                    self.assert_refused(source=source)

    def test_field_names_reject_reserved_case_collisions_and_nonidentifiers(self):
        for value in ('Code', 'код', 'Write', 'Метаданные', 'active', 'Bad.Name', ' Quantity ', ''):
            with self.subTest(value=value):
                def mutate(root):
                    field_properties(root).find('{'+MD+'}Name').text = value
                self.assert_refused(changed(mutate))

    def test_invalid_field_uuid_spelling_is_not_normalized(self):
        for value in ('00000000-0000-0000-0000-000000000000', 'invalid', uuid4().hex):
            with self.subTest(value=value):
                def mutate(root): root[0].find('{'+MD+'}ChildObjects')[0].set('uuid', value)
                self.assert_refused(changed(mutate))

    def test_generated_names_must_reference_the_actual_catalog(self):
        self.assert_refused(CATALOG.read_bytes().replace(
            ('CatalogRef.'+NAME).encode(), b'CatalogRef.Other', 1))

    def test_document_envelope_and_processing_instructions_are_not_bypassed(self):
        raw = CATALOG.read_bytes()
        for old, new in ((b'version="2.20"', b'version="2.99"'),
                         (b'version="2.20"', b'version="2.20" unknown="true"'),
                         (b'<Attribute uuid=', b'<?unknown x?><Attribute uuid=')):
            with self.subTest(old=old, new=new): self.assert_refused(raw.replace(old, new, 1))

    def test_full_configuration_and_language_are_still_unsupported(self):
        source = files()
        source['Configuration.xml'] = source['Configuration.xml'].replace(
            b'</Properties>', b'<DefaultLanguage>Language.English</DefaultLanguage></Properties>')
        source['Languages/English.xml'] = b'<Language/>'
        self.assert_refused(source=source)

    def test_nonempty_module_is_archived_but_cannot_activate_or_execute(self):
        source = files()
        source['Catalogs/'+NAME+'/Ext/ObjectModule.bsl'] = b'Procedure BeforeWrite(Cancel)\nCancel=True;\nEndProcedure'
        config = import_configuration(source)
        self.assertTrue(config.activation_issues)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(BackendError):
                SQLiteDBContext.create(Path(directory)/'active.sqlite', config)
            self.assertFalse((Path(directory)/'active.sqlite').exists())
            with SQLiteDBContext.create(Path(directory)/'archive.sqlite', config, activate=False) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)

    def test_partial_match_does_not_clear_other_configuration_issues(self):
        source = files()
        source['Other.xml'] = b'<Unknown/>'
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ('unsupported configuration file:Other.xml',))


if __name__ == '__main__':
    unittest.main()
