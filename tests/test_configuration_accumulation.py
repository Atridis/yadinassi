"""Closed authored accumulation source contract, not a native parity suite."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from uuid import UUID

from yadinassi import configuration_xml as xml
from yadinassi.accumulation_movements import AccumulationRegisterKind
from yadinassi.configuration_accumulation import (
    AccumulationConfiguration, FORMAT_VERSION, PROFILE, SOURCE_PROJECTION,
    canonical, import_accumulation_configuration,
)
from yadinassi.configuration_posting import import_posting_configuration

MD = xml.MD
XR = xml.XR
DOC = 'Documents/Order.xml'
REG = 'AccumulationRegisters/Rows.xml'
MODULE = 'Documents/Order/Ext/ObjectModule.bsl'


def wrap(kind, identity, properties, children='', internal=''):
    return (f'<MetaDataObject version="2.20" xmlns="{MD}" xmlns:xr="{XR}" '
            f'xmlns:xsi="{xml.XSI}" xmlns:v8="{xml.V8}" xmlns:xs="{xml.XS}" '
            f'xmlns:cfg="{xml.CFG}"><{kind} uuid="{UUID(int=identity)}">'
            f'{internal}<Properties>{properties}</Properties>'
            f'<ChildObjects>{children}</ChildObjects></{kind}></MetaDataObject>').encode()


def generated(kind, name, base):
    categories = (('Object', 'Ref', 'Selection', 'List', 'Manager')
                  if kind == 'Document' else
                  ('Record', 'Manager', 'Selection', 'List', 'RecordSet', 'RecordKey'))
    return '<InternalInfo>' + ''.join(
        f'<xr:GeneratedType name="{kind}{category}.{name}" category="{category}">'
        f'<xr:TypeId>{UUID(int=base + 2 * i)}</xr:TypeId>'
        f'<xr:ValueId>{UUID(int=base + 2 * i + 1)}</xr:ValueId>'
        '</xr:GeneratedType>' for i, category in enumerate(categories)) + '</InternalInfo>'


def value_type(kind):
    return '<Type>' + {
        'number': '<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers>'
                  '<v8:Digits>10</v8:Digits><v8:FractionDigits>2</v8:FractionDigits>'
                  '<v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>',
        'string': '<v8:Type>xs:string</v8:Type><v8:StringQualifiers>'
                  '<v8:Length>32</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength>'
                  '</v8:StringQualifiers>',
        'boolean': '<v8:Type>xs:boolean</v8:Type>',
        'datetime': '<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers>'
                    '<v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>',
        'reference': '<v8:Type>cfg:CatalogRef.Products</v8:Type>',
    }[kind] + '</Type>'


def field(category, identity, name, kind='number'):
    totals = '<UseInTotals>true</UseInTotals>' if category == 'Dimension' else ''
    return (f'<{category} uuid="{UUID(int=identity)}"><Properties><Name>{name}</Name>'
            f'{value_type(kind)}{totals}</Properties></{category}>')


def document(name='Order', identity=2, generated_base=100):
    return wrap('Document', identity,
        f'<Name>{name}</Name><NumberType>String</NumberType><NumberLength>9</NumberLength>'
        '<NumberPeriodicity>Nonperiodical</NumberPeriodicity><CheckUnique>true</CheckUnique>'
        '<Autonumbering>false</Autonumbering><Posting>Allow</Posting>'
        '<RealTimePosting>Deny</RealTimePosting>'
        '<RegisterRecordsDeletion>AutoDeleteOnUnpost</RegisterRecordsDeletion>'
        '<RegisterRecordsWritingOnPost>WriteSelected</RegisterRecordsWritingOnPost>'
        '<PostInPrivilegedMode>false</PostInPrivilegedMode>'
        '<UnpostInPrivilegedMode>false</UnpostInPrivilegedMode>'
        '<RegisterRecords><xr:Item xsi:type="xr:MDObjectRef">'
        'AccumulationRegister.Rows</xr:Item></RegisterRecords>',
        internal=generated('Document', name, generated_base))


def source():
    return {
        'Configuration.xml': wrap('Configuration', 1, '<Name>AccumulationTest</Name>',
            '<Document>Order</Document><AccumulationRegister>Rows</AccumulationRegister>'),
        DOC: document(),
        REG: wrap('AccumulationRegister', 3,
            '<Name>Rows</Name><RegisterType>Balance</RegisterType>'
            '<EnableTotalsSplitting>false</EnableTotalsSplitting>',
            field('Dimension', 4, 'Item', 'string') + field('Resource', 5, 'Amount')
            + field('Attribute', 6, 'Note', 'string'),
            generated('AccumulationRegister', 'Rows', 200)),
        MODULE: b'Procedure Posting(Cancel, PostingMode)\nEndProcedure\n',
    }


def owned_source():
    root = Path(__file__).resolve().parents[1] / 'scripts/accumulation_register_behavior'
    return {
        'Configuration.xml': wrap('Configuration', 1, '<Name>OwnedSource</Name>',
            '<Document>OwnedAccumulationDoc</Document>'
            '<AccumulationRegister>OwnedAccumulationRows</AccumulationRegister>'),
        'Documents/OwnedAccumulationDoc.xml': (root / 'Document.xml').read_bytes(),
        'AccumulationRegisters/OwnedAccumulationRows.xml': (root.parents[1] / 'tests/fixtures/accumulation_register/RuntimeAccumulationRegister.xml').read_bytes(),
        'Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl': (root / 'ObjectModule.bsl').read_bytes(),
    }


def import_source(files=None):
    return import_accumulation_configuration(source() if files is None else files,
                                            accumulation_runtime=PROFILE)


class AccumulationSourceTests(unittest.TestCase):
    def reject(self, files):
        with self.assertRaises(ValueError):
            import_accumulation_configuration(files, accumulation_runtime=PROFILE)

    def changed(self, path, old, new):
        files = source()
        self.assertIn(old, files[path])
        files[path] = files[path].replace(old, new, 1)
        return files

    def test_explicit_profile_and_format_are_fresh(self):
        result = import_source()
        self.assertIs(type(result), AccumulationConfiguration)
        self.assertEqual((PROFILE, FORMAT_VERSION), ('accumulation-balance-scalar-v1', 14))
        self.assertEqual(SOURCE_PROJECTION, 'authored-accumulation-source-shape-v1')
        self.assertEqual(canonical(result), result)

    def test_missing_or_wrong_grant_rejected(self):
        for grant in (None, '', 'document-recorder-scalar-v1', True, 14):
            with self.subTest(grant=grant), self.assertRaises(ValueError):
                import_accumulation_configuration(source(), accumulation_runtime=grant)

    def test_grant_subclass_rejected(self):
        class Grant(str):
            pass
        with self.assertRaises(ValueError):
            import_accumulation_configuration(source(), accumulation_runtime=Grant(PROFILE))

    def test_exact_source_and_digest_retained(self):
        files = source()
        result = import_source(files)
        self.assertEqual(dict(result.files), files)
        expected = sha256(b''.join(path.encode() + b'\0' + sha256(files[path]).digest()
                                   for path in sorted(files))).hexdigest()
        self.assertEqual(result.source_digest, expected)
        self.assertEqual(result.handlers, ((UUID(int=2), MODULE, sha256(files[MODULE]).hexdigest()),))

    def test_input_order_is_canonical(self):
        self.assertEqual(import_source(), import_source(dict(reversed(list(source().items())))))

    def test_bom_and_module_line_endings_preserved(self):
        files = {path: b'\xef\xbb\xbf' + raw.replace(b'\n', b'\r\n')
                 for path, raw in source().items()}
        result = import_source(files)
        self.assertEqual(dict(result.files), files)
        self.assertEqual(canonical(result), result)
        self.assertNotEqual(result.source_digest, import_source().source_digest)

    def test_owned_candidate_bytes_preserved_without_native_claim(self):
        files = owned_source()
        result = import_source(files)
        self.assertEqual(dict(result.files), files)
        self.assertEqual(canonical(result), result)
        register, = result.registers
        self.assertEqual(tuple(f.name for f in register.dimensions), ('Item', 'Warehouse'))
        self.assertEqual(tuple(f.name for f in register.resources), ('Amount', 'Quantity'))
        self.assertEqual(tuple(f.name for f in register.attributes), ('Note',))

    def test_legacy_and_posting_imports_not_widened(self):
        with self.assertRaises(ValueError):
            xml.import_configuration(source())
        with self.assertRaises(ValueError):
            import_posting_configuration(source(), posting_runtime='document-recorder-scalar-v1')

    def test_groups_are_immutable_and_recorder_owned(self):
        result = import_source()
        register, = result.registers
        self.assertIs(register.kind, AccumulationRegisterKind.BALANCE)
        self.assertEqual(register.recorder_documents, (result.documents[0].identity,))
        for group in (register.dimensions, register.resources, register.attributes):
            self.assertIs(type(group), tuple)
        self.assertEqual(tuple(f.name for f in register.fields), ('Item', 'Amount', 'Note'))

    def test_zero_dimensions_does_not_inherit_information_register_rule(self):
        files = source()
        files[REG] = files[REG].replace(field('Dimension', 4, 'Item', 'string').encode(), b'')
        self.assertEqual(import_source(files).registers[0].dimensions, ())

    def test_scalar_dimension_and_attribute_types(self):
        for kind in ('string', 'number', 'boolean', 'datetime'):
            files = source()
            files[REG] = files[REG].replace(field('Dimension', 4, 'Item', 'string').encode(),
                                          field('Dimension', 4, 'Item', kind).encode())
            files[REG] = files[REG].replace(field('Attribute', 6, 'Note', 'string').encode(),
                                          field('Attribute', 6, 'Note', kind).encode())
            with self.subTest(kind=kind):
                result = import_source(files).registers[0]
                self.assertEqual((result.dimensions[0].kind, result.attributes[0].kind), (kind, kind))

    def test_numeric_resource_qualifiers_retained_without_sign_semantics(self):
        files = self.changed(REG, b'<v8:AllowedSign>Any', b'<v8:AllowedSign>Nonnegative')
        self.assertEqual(import_source(files).registers[0].resources[0].qualifiers,
                         (10, 2, 'Nonnegative'))

    def test_multiple_recorders_sorted_and_owned(self):
        files = source()
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'<Document>Order</Document>', b'<Document>Second</Document><Document>Order</Document>')
        files['Documents/Second.xml'] = document('Second', 8, 300)
        files['Documents/Second/Ext/ObjectModule.bsl'] = files[MODULE]
        result = import_source(files)
        self.assertEqual(result.registers[0].recorder_documents, (UUID(int=2), UUID(int=8)))
        self.assertEqual(len(result.handlers), 2)

    def test_document_scalar_fields_and_sections(self):
        extra = field('Attribute', 10, 'Flag', 'boolean')
        section = (f'<TabularSection uuid="{UUID(int=11)}"><Properties><Name>Lines</Name>'
                   '</Properties><ChildObjects>' + field('Attribute', 12, 'DateValue', 'datetime')
                   + '</ChildObjects></TabularSection>')
        files = self.changed(DOC, b'<ChildObjects></ChildObjects>',
                             ('<ChildObjects>' + extra + section + '</ChildObjects>').encode())
        doc, = import_source(files).documents
        self.assertEqual(doc.fields[0].kind, 'boolean')
        self.assertEqual(doc.tabular_sections[0].fields[0].kind, 'datetime')

    def test_document_local_decimal_numbering_is_explicit(self):
        files = self.changed(DOC, b'<Autonumbering>false', b'<Autonumbering>true')
        self.assertEqual(import_source(files).documents[0].numbering, 'decimal_v1')

    def test_absent_or_empty_generated_inventory_is_authored_shape_only(self):
        for replacement in (b'', b'<InternalInfo/>'):
            files = source()
            for path in (DOC, REG):
                files[path] = re.sub(b'<InternalInfo>.*?</InternalInfo>', replacement, files[path])
            with self.subTest(replacement=replacement):
                self.assertEqual(canonical(import_source(files)), import_source(files))

    def test_missing_configuration_or_declared_metadata_rejected(self):
        for path in ('Configuration.xml', DOC, REG, MODULE):
            files = source()
            del files[path]
            with self.subTest(path=path):
                self.reject(files)

    def test_extra_source_never_granted(self):
        for path in ('Catalogs/Products.xml', 'InformationRegisters/Rows.xml',
                     'CommonModules/Extra/Ext/Module.bsl', 'Ext/SessionModule.bsl',
                     'Documents/Order/Ext/ManagerModule.bsl',
                     'Documents/Order/Forms/Form/Ext/Form.xml',
                     'AccumulationRegisters/Rows/Ext/RecordSetModule.bsl',
                     'ConfigDumpInfo.xml'):
            files = source()
            files[path] = b'<Extra/>' if path.endswith('.xml') else b'// no grant'
            with self.subTest(path=path):
                self.reject(files)

    def test_bad_source_shapes_rejected(self):
        for files in (None, (), {}, {1: b''}, {'Configuration.xml': bytearray(b'<x/>')}):
            with self.subTest(files=files):
                self.reject(files)

    def test_unsafe_and_case_colliding_paths_rejected(self):
        for path in ('../extra.xml', '/extra.xml', 'Documents\\Extra.xml',
                     'Documents//Extra.xml', 'Documents/./Extra.xml', 'C:extra.xml',
                     'Documents/\x00Extra.xml', 'configuration.xml', 'Extra.txt'):
            files = source()
            files[path] = b'<Extra/>'
            with self.subTest(path=path):
                self.reject(files)

    def test_source_budgets_rejected(self):
        for limit, value in (('MAX_FILES', 3), ('MAX_FILE_BYTES', 32), ('MAX_TOTAL_BYTES', 32)):
            with self.subTest(limit=limit), patch.object(xml, limit, value):
                self.reject(source())

    def test_invalid_utf8_and_xml_rejected(self):
        for path in (DOC, MODULE):
            files = source()
            files[path] += b'\xff'
            with self.subTest(path=path):
                self.reject(files)
        self.reject(self.changed(REG, b'</Properties>', b'</Broken>'))

    def test_dtd_entity_and_processing_instruction_rejected(self):
        for prefix in (b'<!DOCTYPE MetaDataObject>', b'<!ENTITY x "x">', b'<?unsafe value?>'):
            files = source()
            files[REG] = prefix + files[REG]
            with self.subTest(prefix=prefix):
                self.reject(files)

    def test_unknown_metadata_declaration_rejected(self):
        for declaration in (b'<Catalog>Products</Catalog>', b'<CommonModule>Extra</CommonModule>',
                            b'<InformationRegister>Rows</InformationRegister>',
                            b'<Document extra="yes">Order</Document>',
                            b'<Document>Order<Extra/></Document>',
                            b'<xr:Document>Order</xr:Document>'):
            with self.subTest(declaration=declaration):
                self.reject(self.changed('Configuration.xml', b'<Document>Order</Document>', declaration))

    def test_duplicate_casefolded_declarations_rejected(self):
        for declaration in (b'<Document>Order</Document>', b'<Document>order</Document>'):
            with self.subTest(declaration=declaration):
                self.reject(self.changed('Configuration.xml', b'<Document>Order</Document>',
                                         b'<Document>Order</Document>' + declaration))

    def test_configuration_cannot_own_executable_or_generated_metadata(self):
        for fragment in (b'<Unknown/>', b'<InternalInfo><xr:GeneratedType/></InternalInfo>'):
            with self.subTest(fragment=fragment):
                self.reject(self.changed('Configuration.xml', b'<Properties>', fragment + b'<Properties>'))

    def test_document_and_register_names_match_paths(self):
        for path, old in ((DOC, b'<Name>Order'), (REG, b'<Name>Rows')):
            with self.subTest(path=path):
                self.reject(self.changed(path, old, b'<Name>Other'))

    def test_document_controls_exact(self):
        for tag, old, new in (
            ('NumberType', 'String', 'Number'), ('NumberPeriodicity', 'Nonperiodical', 'Year'),
            ('CheckUnique', 'true', 'false'), ('Posting', 'Allow', 'Deny'),
            ('RealTimePosting', 'Deny', 'Allow'),
            ('RegisterRecordsDeletion', 'AutoDeleteOnUnpost', 'DontDelete'),
            ('RegisterRecordsWritingOnPost', 'WriteSelected', 'WriteAll'),
            ('PostInPrivilegedMode', 'false', 'true'), ('UnpostInPrivilegedMode', 'false', 'true'),
            ('Autonumbering', 'false', 'yes'), ('NumberLength', '9', '10')):
            with self.subTest(tag=tag):
                self.reject(self.changed(DOC, f'<{tag}>{old}'.encode(), f'<{tag}>{new}'.encode()))

    def test_missing_document_controls_rejected(self):
        for tag in ('Posting', 'RealTimePosting', 'RegisterRecordsDeletion',
                    'RegisterRecordsWritingOnPost', 'PostInPrivilegedMode',
                    'UnpostInPrivilegedMode', 'Autonumbering', 'NumberLength'):
            files = source()
            files[DOC] = re.sub(f'<{tag}>.*?</{tag}>'.encode(), b'', files[DOC])
            with self.subTest(tag=tag):
                self.reject(files)

    def test_unaccepted_passive_defaults_rejected(self):
        for path, fragment in ((DOC, b'<NumberAllowedLength>Fixed</NumberAllowedLength>'),
                               (DOC, b'<SequenceFilling>DontFill</SequenceFilling>'),
                               (DOC, b'<UseStandardCommands>true</UseStandardCommands>'),
                               (REG, b'<DataLockControlMode>Automatic</DataLockControlMode>'),
                               (REG, b'<StandardAttributes><Extra/></StandardAttributes>')):
            with self.subTest(path=path, fragment=fragment):
                self.reject(self.changed(path, b'<Properties>', b'<Properties>' + fragment))

    def test_unknown_properties_and_duplicate_properties_rejected(self):
        for path in ('Configuration.xml', DOC, REG):
            for fragment in (b'<UnknownControl>false</UnknownControl>', b'<Name>Extra</Name>'):
                with self.subTest(path=path, fragment=fragment):
                    self.reject(self.changed(path, b'<Properties>', b'<Properties>' + fragment))

    def test_unknown_nested_field_nodes_and_properties_rejected(self):
        for fragment in (b'<Unknown/>', b'<ChildObjects><Dimension/></ChildObjects>',
                         b'<InternalInfo><xr:GeneratedType/></InternalInfo>',
                         b'<Properties><Name>Duplicate</Name></Properties>'):
            with self.subTest(fragment=fragment):
                self.reject(self.changed(REG, b'</Dimension>', fragment + b'</Dimension>'))
        self.reject(self.changed(REG, b'<UseInTotals>', b'<Unknown>false</Unknown><UseInTotals>'))

    def test_metadata_envelopes_and_mixed_content_rejected(self):
        for path, old, new in (
            (REG, b'version="2.20"', b'version="2.21"'),
            (REG, b'<Properties>', b'<Properties extra="yes">'),
            (REG, b'<ChildObjects>', b'<ChildObjects>mixed'),
            (REG, b'</Resource>', b'</Resource>mixed'),
            (REG, b'<Name>Rows', b'<Name extra="yes">Rows'),
            (REG, b'</RegisterType>', b'</RegisterType>mixed'),
            (DOC, b'<RegisterRecords>', b'<RegisterRecords>mixed'),
            (DOC, b'<RegisterRecords>', b'<RegisterRecords extra="yes">')):
            with self.subTest(path=path, new=new):
                self.reject(self.changed(path, old, new))

    def test_turnover_kind_and_implicit_or_split_totals_rejected(self):
        for old, new in ((b'<RegisterType>Balance', b'<RegisterType>Turnovers'),
                         (b'<RegisterType>Balance</RegisterType>', b''),
                         (b'<EnableTotalsSplitting>false', b'<EnableTotalsSplitting>true'),
                         (b'<EnableTotalsSplitting>false</EnableTotalsSplitting>', b'')):
            with self.subTest(new=new):
                self.reject(self.changed(REG, old, new))

    def test_dimension_use_in_totals_is_explicit_and_exact(self):
        for replacement in (b'', b'<UseInTotals>false</UseInTotals>',
                            b'<UseInTotals>1</UseInTotals>'):
            with self.subTest(replacement=replacement):
                self.reject(self.changed(REG, b'<UseInTotals>true</UseInTotals>', replacement))

    def test_resources_are_numeric_and_required(self):
        for kind in ('string', 'boolean', 'datetime', 'reference'):
            with self.subTest(kind=kind):
                self.reject(self.changed(REG, field('Resource', 5, 'Amount').encode(),
                                         field('Resource', 5, 'Amount', kind).encode()))
        self.reject(self.changed(REG, field('Resource', 5, 'Amount').encode(), b''))

    def test_catalog_references_are_not_granted(self):
        for category, identity, name in (('Dimension', 4, 'Item'), ('Attribute', 6, 'Note')):
            with self.subTest(category=category):
                self.reject(self.changed(REG, field(category, identity, name, 'string').encode(),
                                         field(category, identity, name, 'reference').encode()))

    def test_type_namespace_composites_and_qualifiers_fail_closed(self):
        for old, new in (
            (b'<v8:Digits>10', b'<v8:Digits>39'),
            (b'<v8:FractionDigits>2', b'<v8:FractionDigits>11'),
            (b'<v8:AllowedSign>Any', b'<v8:AllowedSign>Negative'),
            (b'xs:decimal</v8:Type>', b'bad:decimal</v8:Type>'),
            (b'xs:decimal</v8:Type>', b'xs:decimal</v8:Type><v8:Type>xs:boolean</v8:Type>'),
            (b'<v8:Digits>10', b'<v8:Digits extra="yes">10'),
            (b'</v8:NumberQualifiers>', b'<v8:Unknown>1</v8:Unknown></v8:NumberQualifiers>'),
            (b'<v8:AllowedLength>Variable', b'<v8:AllowedLength>Fixed')):
            with self.subTest(new=new):
                self.reject(self.changed(REG, old, new))

    def test_scalar_fields_reject_names_and_group_collisions(self):
        for replacement in (b'<Name>item', b'<Name>RecordType', b'<Name>Recorder',
                            b'<Name>Direction', b'<Name>bad.name'):
            with self.subTest(replacement=replacement):
                self.reject(self.changed(REG, b'<Name>Note', replacement))

    def test_dimension_and_total_field_bounds(self):
        for extra in (''.join(field('Dimension', 1000 + i, 'Dim' + str(i)) for i in range(16)),
                      ''.join(field('Attribute', 1000 + i, 'Attr' + str(i)) for i in range(62))):
            self.reject(self.changed(REG, b'</ChildObjects>', extra.encode() + b'</ChildObjects>'))

    def test_unknown_document_child_and_section_children_rejected(self):
        for extra in (field('Resource', 10, 'Unexpected'), '<Form>Extra</Form>',
                      f'<TabularSection uuid="{UUID(int=10)}"><Properties><Name>Lines</Name>'
                      '</Properties><ChildObjects>' + field('Dimension', 11, 'Key')
                      + '</ChildObjects></TabularSection>'):
            with self.subTest(extra=extra):
                self.reject(self.changed(DOC, b'</ChildObjects>', extra.encode() + b'</ChildObjects>'))

    def test_recorder_links_reject_missing_unknown_wrong_case_and_duplicate(self):
        for new in (b'InformationRegister.Rows', b'AccumulationRegister.Other',
                    b'AccumulationRegister.rows', b'AccumulationRegister.Rows.Extra', b''):
            with self.subTest(new=new):
                self.reject(self.changed(DOC, b'AccumulationRegister.Rows', new))
        item = b'<xr:Item xsi:type="xr:MDObjectRef">AccumulationRegister.Rows</xr:Item>'
        self.reject(self.changed(DOC, item, item + item))
        self.reject(self.changed(DOC, item, b''))

    def test_recorder_link_xml_grant_is_exact(self):
        for old, new in ((b'<xr:Item ', b'<xr:Unknown '),
                         (b'<xr:Item ', b'<xr:Item extra="yes" '),
                         (b'xsi:type="xr:MDObjectRef"', b'xsi:type="xs:MDObjectRef"'),
                         (b'xsi:type="xr:MDObjectRef"', b'xsi:type="xr:Other"'),
                         (b'</xr:Item>', b'<Extra/></xr:Item>'),
                         (b'</xr:Item>', b'</xr:Item>mixed')):
            with self.subTest(new=new):
                self.reject(self.changed(DOC, old, new))

    def test_every_declared_register_requires_an_owner(self):
        files = source()
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'</ChildObjects>', b'<AccumulationRegister>Other</AccumulationRegister></ChildObjects>')
        files['AccumulationRegisters/Other.xml'] = files[REG].replace(b'Rows', b'Other')
        self.reject(files)

    def test_uuid_identity_domain_covers_config_objects_and_fields(self):
        for path, old, new in ((DOC, UUID(int=2), UUID(int=1)),
                               (REG, UUID(int=3), UUID(int=2)),
                               (REG, UUID(int=4), UUID(int=1)),
                               (REG, UUID(int=6), UUID(int=5))):
            with self.subTest(path=path, old=old):
                self.reject(self.changed(path, str(old).encode(), str(new).encode()))

    def test_uuid_identity_domain_includes_all_generated_ids(self):
        for path, old, new in ((DOC, 100, 1), (DOC, 100, 2), (REG, 200, 100),
                               (REG, 200, 4), (REG, 4, 100), (REG, 201, 200)):
            with self.subTest(path=path, old=old, new=new):
                self.reject(self.changed(path, str(UUID(int=old)).encode(), str(UUID(int=new)).encode()))

    def test_nil_noncanonical_and_malformed_uuids_rejected(self):
        for value in ('00000000-0000-0000-0000-000000000000',
                      '00000000000000000000000000000003',
                      '00000000-0000-0000-0000-00000000000A', 'not-a-uuid'):
            with self.subTest(value=value):
                self.reject(self.changed(REG, str(UUID(int=3)).encode(), value.encode()))

    def test_generated_categories_names_and_child_order_are_exact(self):
        for old, new in (
            (b'name="AccumulationRegisterRecord.Rows"', b'name="AccumulationRegisterRecord.Other"'),
            (b'category="Record"', b'category="RecordManager"'),
            (b'<xr:GeneratedType ', b'<xr:GeneratedType extra="yes" '),
            (b'<xr:TypeId>', b'<xr:TypeId extra="yes">'),
            (b'</xr:ValueId>', b'</xr:ValueId><xr:Extra/>'),
            (b'<InternalInfo>', b'<InternalInfo><Unknown/>'),
            (b'<xr:TypeId>', b'<xr:ValueId>')):
            with self.subTest(new=new):
                self.reject(self.changed(REG, old, new))

    def test_generated_inventory_cannot_be_partial_or_duplicate(self):
        files = source()
        node = re.search(b'<xr:GeneratedType .*?</xr:GeneratedType>', files[REG]).group(0)
        for replacement in (b'', node + node):
            with self.subTest(replacement=replacement):
                self.reject(self.changed(REG, node, replacement))

    def test_generated_namespace_binding_is_not_prefix_based(self):
        self.reject(self.changed(REG, f'xmlns:xr="{XR}"'.encode(), b'xmlns:xr="urn:unknown"'))

    def test_unknown_object_and_internal_attributes_rejected(self):
        for old, new in ((b'<AccumulationRegister uuid=', b'<AccumulationRegister extra="yes" uuid='),
                         (b'<InternalInfo>', b'<InternalInfo extra="yes">'),
                         (b'<InternalInfo>', b'<InternalInfo>mixed'),
                         (b'</xr:TypeId>', b'</xr:TypeId>mixed')):
            with self.subTest(new=new):
                self.reject(self.changed(REG, old, new))


class AccumulationCanonicalTests(unittest.TestCase):
    def reject(self, config):
        with self.assertRaises(ValueError):
            canonical(config)

    def test_wrong_configuration_type_or_profile_rejected(self):
        self.reject(None)
        self.reject(replace(import_source(), profile='document-recorder-scalar-v1'))

    def test_configuration_identity_name_and_digest_tamper_rejected(self):
        result = import_source()
        for change in ({'identity': UUID(int=900)}, {'name': 'Other'}, {'source_digest': '0' * 64}):
            with self.subTest(change=change):
                self.reject(replace(result, **change))

    def test_document_and_register_schema_tamper_rejected(self):
        result = import_source()
        self.reject(replace(result, documents=(replace(result.documents[0], number_length=8),)))
        self.reject(replace(result, registers=(replace(result.registers[0], name='Other'),)))
        self.reject(replace(result, registers=(replace(result.registers[0], attributes=()),)))

    def test_owner_tamper_rejected(self):
        result = import_source()
        register = replace(result.registers[0], recorder_documents=(UUID(int=9),))
        self.reject(replace(result, registers=(register,)))

    def test_handler_owner_path_and_digest_tamper_rejected(self):
        result = import_source()
        owner, path, digest = result.handlers[0]
        for handler in ((UUID(int=9), path, digest), (owner, 'Other.bsl', digest),
                        (owner, path, '0' * 64)):
            with self.subTest(handler=handler):
                self.reject(replace(result, handlers=(handler,)))

    def test_omitted_or_extra_handlers_rejected(self):
        result = import_source()
        self.reject(replace(result, handlers=()))
        self.reject(replace(result, handlers=result.handlers * 2))

    def test_valid_source_drift_still_requires_matching_projection(self):
        result = import_source()
        for path in (DOC, REG, MODULE):
            files = dict(result.files)
            files[path] += b'\n'
            with self.subTest(path=path):
                self.reject(replace(result, files=tuple(sorted(files.items()))))

    def test_module_source_and_digest_cannot_be_forged_independently(self):
        result = import_source()
        files = dict(result.files)
        files[MODULE] += b'// changed\n'
        fresh = import_source(files)
        self.reject(replace(result, files=fresh.files, source_digest=fresh.source_digest))

    def test_source_order_duplicates_and_mutable_containers_rejected(self):
        result = import_source()
        for files in (tuple(reversed(result.files)), result.files + result.files[:1],
                      list(result.files), (list(result.files[0]),) + result.files[1:]):
            with self.subTest(files=files):
                self.reject(replace(result, files=files))

    def test_schema_types_cannot_hide_behind_python_equality(self):
        result = import_source()
        self.reject(replace(result, documents=(replace(result.documents[0], number_length=9.0),)))
        register = result.registers[0]
        resource = replace(register.resources[0], qualifiers=(10.0, 2, 'Any'))
        self.reject(replace(result, registers=(replace(register, resources=(resource,)),)))
        self.reject(replace(result, registers=[register]))


if __name__ == '__main__':
    unittest.main()
