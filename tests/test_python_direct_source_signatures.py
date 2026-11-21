"""Every mutable signature field remains checked at every source checkpoint."""
import copy
import unittest
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct_source import _signature, _signature_matches
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class SourceSignatureTests(unittest.TestCase):
    def setUp(self):
        self.node=parse('Function F(Val X=1,Y) Return X;EndFunction')[0]
        self.saved=_signature(self.node)

    def test_all_signature_fields_and_parameter_shape(self):
        self.assertTrue(_signature_matches(self.node,self.saved))
        for field,value in [('name','G'),('execution_context','server'),('is_function',False),('is_async',True),('is_dual',True),('module_context',False),('exported',True)]:
            node=copy.deepcopy(self.node);setattr(node,field,value)
            self.assertEqual(_signature_matches(node,self.saved),_signature(node)==self.saved)
        for field,value in [('name','Z'),('by_value',False),('default',None)]:
            node=copy.deepcopy(self.node);setattr(node.parameters[0],field,value)
            self.assertFalse(_signature_matches(node,self.saved))
        node=copy.deepcopy(self.node);node.parameters.pop()
        self.assertFalse(_signature_matches(node,self.saved))
        node=copy.deepcopy(self.node);node.parameters.append(copy.deepcopy(node.parameters[0]))
        self.assertFalse(_signature_matches(node,self.saved))

    def test_invalid_fields_still_raise_even_after_an_earlier_difference(self):
        for field,value in [('name',None),('execution_context',None),('is_function',1),('is_async',0),('is_dual',1),('module_context',1),('exported',1),('parameters',())]:
            node=copy.deepcopy(self.node);setattr(node,field,value)
            with self.assertRaises(BoundaryViolation):_signature_matches(node,self.saved)
        for field,value in [('name',None),('by_value',1)]:
            node=copy.deepcopy(self.node);node.name='G';setattr(node.parameters[-1],field,value)
            with self.assertRaises(BoundaryViolation):_signature_matches(node,self.saved)
        node=copy.deepcopy(self.node);node.parameters[-1]=object()
        with self.assertRaises(BoundaryViolation):_signature_matches(node,self.saved)

    def test_length_mismatch_does_not_skip_added_invalid_parameter(self):
        node=copy.deepcopy(self.node);node.parameters.append(object())
        with self.assertRaises(BoundaryViolation):_signature_matches(node,self.saved)
