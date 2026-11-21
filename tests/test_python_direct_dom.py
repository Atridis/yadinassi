"""Direct DOM wiring retains the existing document-owner and XML boundaries."""
import unittest
from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectDOMTests(unittest.TestCase):
    def test_prepared_builder_writer_and_live_node_lists(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute_prepared(vm.prepare('R=New XMLReader;R.SetString("<r><a/></r>");B=New DOMBuilder;D=B.Read(R);L=D.DocumentElement.ChildNodes;D.DocumentElement.AppendChild(D.CreateElement("b"));N=L.Count();Name=L[1].NodeName;W=New XMLWriter;W.SetString();DW=New DOMWriter;DW.Write(D,W);Text=W.Close();'))
        self.assertEqual(vm.variables['n'],2);self.assertEqual(vm.variables['name'],'b')
        self.assertIn('<b/>',vm.variables['text'])

    def test_foreign_document_node_rejected_without_mutation(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('A=New DOMDocument("","a");B=New DOMDocument("","b");')
        with self.assertRaises(BSLError):vm.execute('A.DocumentElement.AppendChild(B.DocumentElement);')
        self.assertEqual(vm.execute('A.DocumentElement.ChildNodes.Count()'),0)
        self.assertIsNotNone(vm.execute('B.DocumentElement'))

    def test_foreign_node_and_index_do_not_invoke_python_hooks(self):
        seen=[]
        class Meta(type):
            def __eq__(self,other):seen.append('eq');raise AssertionError()
        class Foreign(metaclass=Meta):
            def __index__(self):seen.append('index');raise AssertionError()
        vm=Interpreter();self.addCleanup(vm.close);vm.variables['foreign']=Foreign()
        vm.execute('D=New DOMDocument("","r");')
        for source in ('D.DocumentElement.AppendChild(foreign);','D.DocumentElement.ChildNodes.Item(foreign);'):
            with self.assertRaises(BSLError):vm.execute(source)
        self.assertEqual(seen,[])

    def test_close_before_mutation_and_private_members(self):
        vm=Interpreter(allow_extensions=True);vm.execute('D=New DOMDocument("","r");')
        root=vm.variables['d'].document_element()
        vm.register_function('Stop',lambda:vm.close() or root)
        with self.assertRaises(BoundaryViolation):vm.execute('D.DocumentElement.AppendChild(Stop());')
        self.assertEqual(root._children,[])
        vm=Interpreter();self.addCleanup(vm.close);vm.execute('D=New DOMDocument("","r");')
        for source in ('D._children;','D._reserve(1,1);'):
            with self.assertRaises((BSLError,BoundaryViolation)):vm.execute(source)

    def test_missing_dom_factory_is_catchable_not_a_foreign_capability(self):
        vm=Interpreter();self.addCleanup(vm.close);vm.types.pop('domdocument')
        vm.execute('Caught=False;Try D=New DOMDocument("","r");Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught'])
