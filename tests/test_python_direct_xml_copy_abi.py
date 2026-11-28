"""Ordinary XML copying must coexist with strict source XDTO admission."""
import copy
import unittest
from unittest.mock import patch
from yadinassi.formats.xml import xml_io,xml_writer
from yadinassi.execution.direct.source import python_direct_source_xdto_xml as xml
from yadinassi.execution.direct.source import python_direct_source_xdto as shared
from yadinassi.formats.xml.dom_io import BSLDOMBuilder
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
import test_python_direct_source_xdto as basic

class XMLCopyABITests(unittest.TestCase):
    def test_copy_preserves_sealed_class_dictionaries_and_reader_state(self):
        classes=(xml_io.BSLXMLReader,xml_io.BSLXMLReaderSettings,xml_writer.BSLXMLWriter,xml_writer.BSLXMLWriterSettings)
        before=[tuple(vars(cls).items()) for cls in classes]
        reader=xml_io.BSLXMLReader();reader.set_string('<r/>')
        duplicate=copy.copy(reader);settings=copy.copy(reader._settings)
        self.assertIsNot(duplicate,reader);self.assertIsNot(settings,reader._settings)
        self.assertEqual(duplicate.__dict__,reader.__dict__)
        for cls in classes:copy.copy(cls())
        copy.deepcopy(xml_writer.BSLXMLWriterSettings())
        for cls,old in zip(classes,before):
            self.assertFalse(any('__slots__' in vars(base) for base in cls.__mro__))
            self.assertEqual(tuple(vars(cls)),tuple(name for name,_ in old))
            self.assertTrue(all(vars(cls)[name] is value for name,value in old))
        xml._hooks()

    def test_dom_failure_then_source_xdto_remains_admitted(self):
        for source in ('<!DOCTYPE r [<!ENTITY x "abc">]><r>&x;</r>', '<r>'):
            reader=xml_io.BSLXMLReader();reader.set_string(source)
            with self.assertRaises(ValueError):BSLDOMBuilder().read(reader)
            self.assertEqual(reader._position,-1)
        case=basic.SourceScalarXDTOTests();case.setUp();self.addCleanup(case.doCleanups)
        app=case.app()
        self.assertEqual(app.interpreter.execute('T=XDTOFactory.Type("http://www.w3.org/2001/XMLSchema","string");XDTOFactory.Create(T,"ok").Value;'),'ok')

    def test_added_changed_and_mutated_copy_metadata_still_rejected(self):
        for cls in (xml_io.BSLXMLReader,xml_io.BSLXMLReaderSettings,xml_writer.BSLXMLWriter,xml_writer.BSLXMLWriterSettings):
            with patch.object(cls,'__slotnames__',[]):
                with self.assertRaises(BoundaryViolation):xml._hooks()
            original=cls.__slotnames__
            original.append('foreign')
            try:
                with self.assertRaises(BoundaryViolation):xml._hooks()
            finally:original.clear()
            delattr(cls,'__slotnames__')
            try:
                with self.assertRaises(BoundaryViolation):xml._hooks()
            finally:setattr(cls,'__slotnames__',original)
            with patch.object(cls,'_foreign_copy_hook',object(),create=True):
                with self.assertRaises(BoundaryViolation):xml._hooks()
        xml._hooks()
