from pathlib import Path
from dataclasses import replace
import re
import unittest

from yadinassi.configuration_diagnostics import (ImportDiagnostic, ImportRefusal,
    from_exception, location, safe_path, safe_identifier, MAX_DIAGNOSTICS)
from yadinassi.configuration_profile_import import prepare_files, ACCUMULATION, POSTING
from yadinassi.configuration_xml import import_configuration
from yadinassi.catalog_backend import BackendError
from yadinassi.errors import BSLError
from sqlite_catalog_fixture import configuration_files
from test_configuration_accumulation import source as accumulation_source
from test_configuration_posting import source as posting_source


class ImportDiagnosticsTests(unittest.TestCase):
    def test_qualifier_failure_names_file_object_field_property_without_value(self):
        files=configuration_files();path='Catalogs/Products.xml'
        files[path]=re.sub(rb'<v8:NumberQualifiers>.*?</v8:NumberQualifiers>',b'',files[path])
        with self.assertRaises(ImportRefusal) as caught:prepare_files(files)
        self.assertEqual(caught.exception.diagnostic.as_dict(),{
            'code':'field_qualifiers_missing','stage':'schema','file':path,
            'object':'Products','field':'Amount','property':'NumberQualifiers'})

    def test_accumulation_qualifiers_keep_register_and_field_location(self):
        files=accumulation_source();path='AccumulationRegisters/Rows.xml'
        files[path]=files[path].replace(b'<v8:Digits>10</v8:Digits>',b'<v8:Digits>PRIVATE</v8:Digits>')
        with self.assertRaises(ImportRefusal) as caught:prepare_files(files,profile=ACCUMULATION)
        d=caught.exception.diagnostic
        self.assertEqual((d.file,d.object,d.field), (path,'Rows','Amount'))
        self.assertNotIn('PRIVATE',d.text())

    def test_posting_register_qualifiers_location(self):
        files=posting_source();path='InformationRegisters/Rows.xml'
        files[path]=re.sub(rb'<v8:NumberQualifiers>.*?</v8:NumberQualifiers>',b'',files[path],count=1)
        with self.assertRaises(ImportRefusal) as caught:prepare_files(files,profile=POSTING)
        d=caught.exception.diagnostic
        self.assertEqual((d.file,d.object,d.field),(path,'Rows','Key'))

    def test_malformed_xml_names_only_relative_file(self):
        files=configuration_files();files['Catalogs/Products.xml']=b'<PRIVATE'
        with self.assertRaises(ImportRefusal) as caught:prepare_files(files)
        d=caught.exception.diagnostic
        self.assertEqual((d.code,d.stage,d.file),('xml_malformed','xml','Catalogs/Products.xml'))
        self.assertNotIn('PRIVATE',d.text())

    def test_dtd_processing_instruction_and_utf8_are_closed_codes(self):
        for raw,code in ((b'<!DOCTYPE x><x/>','xml_dtd_forbidden'),(b'<?private SECRET?><x/>','xml_processing_instruction_forbidden')):
            files=configuration_files();files['Configuration.xml']=raw
            with self.subTest(code=code), self.assertRaises(ImportRefusal) as caught:prepare_files(files)
            self.assertEqual(caught.exception.diagnostic.code,code)
            self.assertNotIn('SECRET',caught.exception.diagnostic.text())

    def test_unknown_exception_never_stringifies_or_reads_subclass_attributes(self):
        class Hostile(ValueError):
            def __str__(self):raise AssertionError('stringified')
            def __getattribute__(self,name):
                if name in ('args','code','errno','__class__'):raise AssertionError('subclass hook')
                return super().__getattribute__(name)
        self.assertEqual(from_exception(Hostile('PRIVATE')).code,'import_refused')
        with self.assertRaises(ImportRefusal) as caught:
            with location(file='Configuration.xml'):raise Hostile('PRIVATE')
        self.assertNotIn('PRIVATE',caught.exception.diagnostic.text())
        class HostileBSL(BSLError):
            def __str__(self):raise AssertionError('stringified')
            def __getattribute__(self,name):
                if name in ('args','__dict__','__class__','source','message'):
                    raise AssertionError('subclass hook')
                return super().__getattribute__(name)
        opaque=HostileBSL('PRIVATE','/private',1,1)
        with self.assertRaises(HostileBSL) as kept:
            with location(file='Configuration.xml'):raise opaque
        self.assertIs(kept.exception,opaque)
        self.assertEqual(from_exception(opaque).code,'import_refused')

    def test_arbitrary_value_error_and_os_error_are_not_messages(self):
        for error in (ValueError('/private/token'),OSError(13,'SECRET','/private/token')):
            self.assertNotIn('private',from_exception(error).text())
            self.assertNotIn('SECRET',from_exception(error).text())

    def test_backend_code_is_closed(self):
        self.assertEqual(from_exception(BackendError('unsupported'),'storage').code,'backend_unsupported')

    def test_source_compile_location_never_renders_error_message(self):
        error=BSLError('PRIVATE source token','/private/host',4,9)
        with self.assertRaises(BSLError) as caught:
            with location(file='Documents/Order/Ext/ObjectModule.bsl'):
                raise error
        self.assertIs(caught.exception,error)
        self.assertEqual(from_exception(caught.exception).as_dict(),{
            'code':'module_compile_refused','stage':'compile','file':'Documents/Order/Ext/ObjectModule.bsl','line':4,'column':9})
        # Real legacy CommonModule failures must not be misattributed to the
        # containing Configuration.xml or expose their initializer text.
        from configuration_runtime_fixture import module_files
        files=module_files([('Tools','Message("PRIVATE initializer");',{})])
        with self.assertRaises(ImportRefusal) as actual:
            prepare_files(files,module_runtime='managed-client-server-v1')
        self.assertEqual(actual.exception.diagnostic.file,'CommonModules/Tools/Ext/Module.bsl')
        self.assertEqual(actual.exception.diagnostic.stage,'compile')
        self.assertNotIn('PRIVATE',actual.exception.diagnostic.text())


    def test_unsafe_context_is_omitted_not_rewritten(self):
        for value in ('../secret.xml','/private/secret.xml','A/../B.xml','x\nSECRET.xml','A\\B.xml','file:secret.xml'):
            self.assertIsNone(safe_path(value))
        with self.assertRaises(ImportRefusal) as caught:
            with location(file='../secret.xml',object='bad\nname',property='PrivateProperty'):
                raise ValueError('missing qualifiers')
        self.assertEqual(caught.exception.diagnostic.as_dict(),{'code':'field_qualifiers_missing','stage':'schema'})

    def test_forged_diagnostic_cannot_render_arbitrary_reason(self):
        for kwargs in ({'code':'PRIVATE','stage':'schema'},{'code':'import_refused','stage':'PRIVATE'},
                       {'code':'import_refused','stage':'schema','file':'/private/path'},
                       {'code':'import_refused','stage':'schema','property':'PRIVATE'}):
            with self.assertRaises(ValueError):ImportDiagnostic(**kwargs)

    def test_nested_context_uses_innermost_precise_location(self):
        with self.assertRaises(ImportRefusal) as caught:
            with location(file='Configuration.xml'):
                with location(file='Catalogs/Products.xml',object='Products'):
                    with location(field='Amount',property='NumberQualifiers'):
                        raise ValueError('missing qualifiers')
        self.assertEqual(caught.exception.diagnostic.file,'Catalogs/Products.xml')
        self.assertEqual(caught.exception.diagnostic.field,'Amount')

    def test_locations_do_not_survive_into_another_import(self):
        with self.assertRaises(ImportRefusal):
            with location(file='Catalogs/Products.xml'):raise ValueError('missing qualifiers')
        with self.assertRaises(ImportRefusal) as caught:
            with location():raise ValueError('missing qualifiers')
        self.assertIsNone(caught.exception.diagnostic.file)

    def test_activation_diagnostics_bounded_and_stored_issues_unchanged(self):
        files=configuration_files()
        for i in range(40):files[f'Unknown{i}.xml']=b'<Root/>'
        original=import_configuration(files)
        prepared=prepare_files(files)
        self.assertEqual(prepared.configuration.activation_issues,original.activation_issues)
        self.assertEqual(len(prepared.report()['diagnostics']),MAX_DIAGNOSTICS)

    def test_configuration_digest_does_not_include_diagnostic_metadata(self):
        files=accumulation_source();first=prepare_files(files,profile=ACCUMULATION)
        second=prepare_files(dict(reversed(list(files.items()))),profile=ACCUMULATION)
        self.assertEqual(first.configuration.source_digest,second.configuration.source_digest)
        self.assertEqual(first.report(),second.report())
