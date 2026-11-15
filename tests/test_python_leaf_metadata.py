import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine,CompiledUnsupported
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
from yadinassi.owned_syntax import syntax_kind
from yadinassi.python_translation_expressions import prepare_expressions,UnsupportedExpression

class LeafMetadataTests(unittest.TestCase):
 def test_no_duplicate_leaf_execution_registry(self):
  vm=Interpreter();program=parse('Function F(Val x=2) Return x+1;EndFunction r=F();')
  engine=vm._compiled();engine.prepare(program,module_entry=True)
  units={id(u):u for _,u in engine._python_units.values()}
  leaves=[p for p in engine._nodes.values() if p.tier=='shared-leaf']
  self.assertTrue(leaves)
  self.assertLessEqual(len({id(p.function) for p in leaves}),2)
  for unit in units.values():
   self.assertFalse(unit.expressions.sync_functions)
   self.assertTrue(all(syntax_kind(n) not in (ast.Literal,ast.Name) for n in unit.expressions.nodes))
   self.assertTrue(all(syntax_kind(n) not in (ast.Literal,ast.Name) for n,_ in unit.expressions.functions.values()))
  vm.execute_program(program);self.assertEqual(vm.variables['r'],3)
  vm.execute('other=99;');vm.execute('r=F(4);');self.assertEqual(vm.variables['r'],5)
 def test_owned_limits_not_exempted_for_leaf_only_program(self):
  for name in ('MAX_NODES','MAX_REGISTRY_ENTRIES'):
   with self.subTest(name=name),patch.object(Engine,name,1):
    vm=Interpreter()
    with self.assertRaises(CompiledUnsupported):vm.execute('r=1;')
    self.assertNotIn('r',vm.variables)
 def test_standalone_expression_node_cap_unchanged(self):
  with self.assertRaises(UnsupportedExpression):prepare_expressions([parse('r=1;')[0].value],max_nodes=0)
 def test_foreign_leaf_cannot_resolve_in_another_engine(self):
  first=Interpreter();second=Interpreter();first._compiled().prepare(parse('a=1;'),module_entry=True)
  leaf=next(p.node for p in first._compiled()._nodes.values() if p.tier=='shared-leaf')
  self.assertIsNone(second._compiled()._python_leaf_operation(leaf))
 def test_generated_calls_defaults_member_receivers_and_execute(self):
  vm=Interpreter();vm.execute('Function F(Val x=3) Return x+1;EndFunction a=New Array;a.Add(F());r=a[0];s=0;Execute "s=7;";')
  self.assertEqual((vm.variables['r'],vm.variables['s']),(4,7))
  self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
