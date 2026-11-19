"""Plain direct XML uses the existing finite XML and file protocols."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.formats.xml.xml_io import BSLXMLReader

class DirectXMLTests(unittest.TestCase):
    def test_source_ast_prepared_bilingual_roundtrip(self):
        source='W=New XMLWriter;W.SetString();W.WriteStartElement("r");W.WriteText("a&b");W.WriteEndElement();S=W.Close();R=New ЧтениеXML;R.УстановитьСтроку(S);R.Прочитать();Name=R.Имя;R.Read();Text=R.Value;'
        for route in ('source','ast','prepared'):
            vm=Interpreter();self.addCleanup(vm.close)
            if route=='source':vm.execute(source)
            elif route=='ast':vm.execute_program(parse(source))
            else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual((vm.variables['name'],vm.variables['text']),('r','a&b'))

    def test_required_argument_and_procedure_value_fail_before_effects(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
        vm.register_function('Touch',lambda:seen.append(1) or '<a/>')
        vm.execute('R=New XMLReader;')
        for source in ('R.SetString(,Touch());','X=R.SetString(Touch());'):
            with self.assertRaises(BSLError):vm.execute(source)
        self.assertEqual(seen,[])

    def test_dtd_external_entity_and_private_member_remain_closed(self):
        vm=Interpreter();self.addCleanup(vm.close);vm.execute('R=New XMLReader;')
        with self.assertRaises(BSLError):vm.execute('R.SetString("<!DOCTYPE r [<!ENTITY x SYSTEM ""file:///not-read"">]><r>&x;</r>");R.Read();')
        for source in ('R._source;','R._parse();','R.Name="x";'):
            with self.assertRaises((BSLError,BoundaryViolation)):vm.execute(source)

    def test_owned_file_io_keeps_external_access_gate(self):
        from yadinassi.execution import safe_mode
        class Deny:
            def active(self):return True
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'r.xml';target.write_text('<r/>',encoding='utf-8')
            vm=Interpreter();self.addCleanup(vm.close);vm.variables['path']=str(target)
            vm.execute('R=New XMLReader;W=New XMLWriter;')
            token=safe_mode._CURRENT.set(Deny())
            try:
                with self.assertRaises(PythonDirectUnsupported):vm.execute('R.OpenFile(path);')
                with self.assertRaises(PythonDirectUnsupported):vm.execute('W.OpenFile(path);')
                with self.assertRaises(ValueError):vm.variables['r'].open_file(str(target))
                with self.assertRaises(ValueError):vm.variables['w'].open_file(str(target))
            finally:safe_mode._CURRENT.reset(token)
            self.assertEqual(target.read_text(encoding='utf-8'),'<r/>')

    def test_close_during_argument_stops_reader_mutation(self):
        vm=Interpreter(allow_extensions=True);vm.execute('R=New XMLReader;R.SetString("<before/>");')
        reader=vm.variables['r'];vm.register_function('Stop',lambda:vm.close() or '<after/>')
        with self.assertRaises(BoundaryViolation):vm.execute('R.SetString(Stop());')
        self.assertEqual(reader._source,'<before/>')

    def test_missing_and_rebound_constructor_are_distinct(self):
        vm=Interpreter();self.addCleanup(vm.close);vm.types.pop('xmlreader')
        vm.execute('Caught=False;Try R=New XMLReader;Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught'])
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
        factory=vm.types['xmlreadersettings']
        def change():factory.function=lambda *args:seen.append(1);return '1.0'
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('S=New XMLReaderSettings(Change());')
        self.assertEqual(seen,[])

    def test_source_owned_handles_cannot_gain_plain_xml_or_dom_methods(self):
        from test_python_direct_source_xdto_xml import SourceXDTOXMLTests
        fixture=SourceXDTOXMLTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        app=fixture.ready();vm=Interpreter();self.addCleanup(vm.close)
        vm.variables.update(r=app.interpreter.variables['r'],w=app.interpreter.variables['w'])
        vm.execute('B=New DOMBuilder;DW=New DOMWriter;D=New DOMDocument("","r");Plain=New XMLWriter;Plain.SetString();')
        for source in ('R.SetString("<r/>");','W.WriteStartElement("r");','B.Read(R);','DW.Write(D,W);','Plain.WriteCurrent(R);'):
            with self.subTest(source=source),self.assertRaises(BoundaryViolation):vm.execute(source)
        app.close()
        with self.assertRaises(BoundaryViolation):vm.execute('R.Close();')
