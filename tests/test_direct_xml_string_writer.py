"""Direct XML string output, bound to selected archived native XML33 rows."""
from pathlib import Path
import unittest

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_xml_ownership import mark_source_owned
from yadinassi.formats.xml.xml_writer import BSLXMLWriter
from yadinassi.streams.binary_streams import BSLMemoryStream


class DirectXMLStringWriterTests(unittest.TestCase):
    def test_archived_xml33_element_text_and_attribute(self):
        lines = (Path(__file__).parent / 'fixtures/xml_workflow_family/native33.out')
        rows = dict(line.split(': ', 1) for line in lines.read_text().splitlines() if ': ' in line)
        for label, additions in (
            ('XF-13', ''),
            ('XF-14', 'W.ЗаписатьТекст("<&>я");'),
            ('XF-15', 'W.ЗаписатьАтрибут("a", "<&""");'),
        ):
            payload = rows[label].split(':', 1)[1].removesuffix(']')
            expected = bytes.fromhex(payload).decode('utf-16-be')
            for prepared in (False, True):
                with self.subTest(label=label, prepared=prepared):
                    vm = Interpreter()
                    self.addCleanup(vm.close)
                    source = ('W=Новый ЗаписьXML; W.УстановитьСтроку(); '
                              'W.ЗаписатьНачалоЭлемента("r"); ' + additions +
                              'W.ЗаписатьКонецЭлемента(); Result=W.Закрыть();')
                    if prepared:
                        vm.execute_prepared(vm.prepare(source))
                    else:
                        vm.execute(source)
                    self.assertEqual(vm.variables['result'], expected)

    def test_source_owned_and_stream_writers_keep_their_io_boundary(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        source_owned = BSLXMLWriter()
        source_owned.set_string()
        mark_source_owned(source_owned)
        stream = BSLMemoryStream()
        writer = BSLXMLWriter()
        writer.open_stream(stream)
        writer.write_start_element('before')
        writer.write_end_element()
        for protected in (source_owned, writer):
            vm.variables['w'] = protected
            for source in ('W.SetString();', 'W.WriteStartElement("after");', 'R=W.Close();'):
                with self.subTest(source=source, sink=protected is writer):
                    with self.assertRaises(BoundaryViolation):
                        vm.execute(source)
        self.assertEqual(stream.size(), 0)
        source_owned.write_start_element('before')
        source_owned.write_end_element()
        self.assertEqual(source_owned.close(), '<before/>')
        writer.close()
        self.assertGreater(stream.size(), 0)
