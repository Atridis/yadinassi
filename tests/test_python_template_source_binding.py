import unittest
from yadinassi.python_translation_template_bindings import bind_generated_source

class SourceBindingTests(unittest.TestCase):
 def test_literals_handles_and_attribute_names_remain_distinct(self):
  class Host:
   def __hash__(self):raise AssertionError('host hash')
   def __eq__(self,other):raise AssertionError('host eq')
  value=Host()
  source='def f(_p):\n return (_nodes[0], "_nodes[0] vm.result", 17, True, None)\n'
  text,operands=bind_generated_source(source,[value]);namespace={};exec(text,namespace)
  result=namespace['f'](operands)
  self.assertIs(result[0],value)
  self.assertEqual(result[1:],('_nodes[0] vm.result',17,True,None))
 def test_control_operators_and_parentheses_are_not_rewritten(self):
  src='def f(_p):\n return (3+2)*4 if True else 99\n'
  text,operands=bind_generated_source(src,[]);ns={};exec(text,ns)
  self.assertEqual(ns['f'](operands),20)
 def test_binding_shape_is_independent_of_payload_values(self):
  a,ap=bind_generated_source('def f(_p):\n return _nodes[0]+"one"\n',[1])
  b,bp=bind_generated_source('def f(_p):\n return _nodes[0]+"two"\n',[2])
  self.assertEqual(a,b)
  self.assertEqual(ap,(1,'one'));self.assertEqual(bp,(2,'two'))
