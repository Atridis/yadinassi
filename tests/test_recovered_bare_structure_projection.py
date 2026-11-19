import ast
import unittest
from unittest.mock import patch
from recovered_bare_fixture import Interpreter
from yadinassi.execution.codegen.native_bare_collections import BareStructure,BareMapEntry
import yadinassi.execution.codegen.native_bare_compiler as compiler

class RecoveredStructureProjection(unittest.TestCase):
    def test_known_structure_direct_items_and_no_entry_allocation(self):
        vm=Interpreter()
        with patch.object(compiler,'BareMapEntry',side_effect=AssertionError('allocation')):
            p=vm.prepare('S=New Structure("A,B",3,4); R=0; For Each P In S Do R=R+P.Value; EndDo;')
        vm.execute_prepared(p);self.assertEqual(vm.variables['r'],7)
        tree=ast.parse(p.generated_source);loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For))
        self.assertFalse(any(isinstance(n,(ast.If,ast.IfExp)) for n in ast.walk(loop)))
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr=='get_member' for n in ast.walk(loop)))
    def test_passed_structure_conditional_assignment_allocates_only_once(self):
        seen=[]
        def entry(*args):seen.append(args);return BareMapEntry(*args)
        vm=Interpreter();vm.variables['s']=BareStructure('A,B',3,4)
        with patch.object(compiler,'BareMapEntry',entry):
            p=vm.prepare('R=0; For Each P In S Do R=R+P.Value; If P.Key="b" Then Alias=P; EndIf; EndDo;')
        vm.execute_prepared(p)
        self.assertEqual(seen,[('b',4)]);self.assertEqual(vm.variables['r'],7)
        self.assertIs(type(vm.variables['alias']),BareMapEntry)
    def test_python_level_iteration_still_has_observable_entry_type(self):
        s=BareStructure('A',3);p=next(iter(s))
        self.assertIs(type(p),BareMapEntry);self.assertEqual(p.get_member('value'),3)
