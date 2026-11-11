"""Explicit fresh posting grant stays separate from all legacy imports."""
from dataclasses import replace
import unittest
from uuid import UUID
from yadinassi.configuration_posting import import_posting_configuration,canonical,PROFILE
from yadinassi.configuration_xml import import_configuration

MD='http://v8.1c.ru/8.3/MDClasses'
XR='http://v8.1c.ru/8.3/xcf/readable'
def wrap(kind,identity,properties,children=''):
    return (f'<MetaDataObject version="2.20" xmlns="{MD}" xmlns:xr="{XR}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema"><{kind} uuid="{UUID(int=identity)}"><Properties>{properties}</Properties><ChildObjects>{children}</ChildObjects></{kind}></MetaDataObject>').encode()
def source():
    field=lambda kind,i,name:f'<{kind} uuid="{UUID(int=i)}"><Properties><Name>{name}</Name><Type><v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>10</v8:Digits><v8:FractionDigits>0</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers></Type></Properties></{kind}>'
    return {'Configuration.xml':wrap('Configuration',1,'<Name>PostingTest</Name>','<Document>Order</Document><InformationRegister>Rows</InformationRegister>'),
        'Documents/Order.xml':wrap('Document',2,'<Name>Order</Name><NumberType>String</NumberType><NumberLength>9</NumberLength><NumberPeriodicity>Nonperiodical</NumberPeriodicity><CheckUnique>true</CheckUnique><Autonumbering>false</Autonumbering><Posting>Allow</Posting><RealTimePosting>Deny</RealTimePosting><RegisterRecordsDeletion>AutoDeleteOnUnpost</RegisterRecordsDeletion><RegisterRecordsWritingOnPost>WriteSelected</RegisterRecordsWritingOnPost><PostInPrivilegedMode>false</PostInPrivilegedMode><UnpostInPrivilegedMode>false</UnpostInPrivilegedMode><RegisterRecords><xr:Item xsi:type="xr:MDObjectRef">InformationRegister.Rows</xr:Item></RegisterRecords>'),
        'InformationRegisters/Rows.xml':wrap('InformationRegister',3,'<Name>Rows</Name><InformationRegisterPeriodicity>Nonperiodical</InformationRegisterPeriodicity><WriteMode>RecorderSubordinate</WriteMode>',field('Dimension',4,'Key')+field('Resource',5,'Amount')),
        'Documents/Order/Ext/ObjectModule.bsl':b'Procedure Posting(Cancel,Mode)\nEndProcedure\n'}

class PostingConfigurationTests(unittest.TestCase):
    def test_explicit_canonical_source_preserved(self):
        files=source();config=import_posting_configuration(files,posting_runtime=PROFILE)
        self.assertEqual(dict(config.files),files);self.assertEqual(canonical(config),config)
        self.assertEqual(config.registers[0].dimension_count,1)
        self.assertEqual(config.registers[0].recorder_documents,(config.documents[0].identity,))
    def test_missing_grant_rejected(self):
        with self.assertRaises(ValueError):import_posting_configuration(source())
    def test_unknown_grant_rejected(self):
        with self.assertRaises(ValueError):import_posting_configuration(source(),posting_runtime='unknown')
    def test_legacy_import_not_implicitly_widened(self):
        with self.assertRaises(ValueError):import_configuration(source())
    def test_forged_schema_rejected_by_reimport(self):
        config=import_posting_configuration(source(),posting_runtime=PROFILE)
        with self.assertRaises(ValueError):canonical(replace(config,name='Other'))
    def test_unknown_recorder_xml_item_rejected(self):
        files=source();p='Documents/Order.xml';files[p]=files[p].replace(b'xr:Item',b'xr:Unknown')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
    def test_unknown_recorder_xml_attribute_rejected(self):
        files=source();p='Documents/Order.xml';files[p]=files[p].replace(b'<xr:Item ',b'<xr:Item extra="x" ')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
    def test_unknown_executable_source_rejected(self):
        files=source();files['Ext/SessionModule.bsl']=b'// unknown'
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
    def test_privileged_handler_grant_rejected(self):
        files=source();p='Documents/Order.xml';files[p]=files[p].replace(b'<PostInPrivilegedMode>false',b'<PostInPrivilegedMode>true')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
    def test_periodic_recorder_not_silently_enabled(self):
        files=source();p='InformationRegisters/Rows.xml';files[p]=files[p].replace(b'Nonperiodical',b'WithinSecond')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)

def measured_source():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'scripts/document_posting_behavior'
    return {'Configuration.xml':wrap('Configuration',1,'<Name>PostingTest</Name>',
            '<Document>OwnedPostingDoc</Document><InformationRegister>OwnedPostingRows</InformationRegister>'),
        'Documents/OwnedPostingDoc.xml':(root/'Document.xml').read_bytes(),
        'InformationRegisters/OwnedPostingRows.xml':(root/'InformationRegister.xml').read_bytes(),
        'Documents/OwnedPostingDoc/Ext/ObjectModule.bsl':(root/'ObjectModule.bsl').read_bytes()}

class MeasuredPostingSourceTests(unittest.TestCase):
    def test_exact_measured_metadata_source_preserved(self):
        files=measured_source();config=import_posting_configuration(files,posting_runtime=PROFILE)
        self.assertEqual(dict(config.files),files);self.assertEqual(canonical(config),config)
    def test_changed_passive_semantic_value_refused(self):
        files=measured_source();p='Documents/OwnedPostingDoc.xml'
        files[p]=files[p].replace(b'<NumberAllowedLength>Variable',b'<NumberAllowedLength>Fixed')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
    def test_internal_executable_unknown_refused(self):
        files=measured_source();p='Documents/OwnedPostingDoc.xml'
        files[p]=files[p].replace(b'<InternalInfo>',b'<InternalInfo><Executable/>')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
    def test_unknown_default_not_cleared(self):
        files=measured_source();p='Documents/OwnedPostingDoc.xml'
        files[p]=files[p].replace(b'<SequenceFilling>AutoFill</SequenceFilling>',b'<UnknownGrant>true</UnknownGrant>')
        with self.assertRaises(ValueError):import_posting_configuration(files,posting_runtime=PROFILE)
