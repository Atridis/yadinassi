"""Independent old visitor hooks and new compiler adapter hooks."""
import ast
import inspect
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse

PAIRS={'semantic_name':'visit_Name','semantic_attribute':'visit_Attribute',
       'semantic_index':'visit_Index','semantic_assign':'visit_Assign',
       'semantic_new':'visit_New','semantic_dynamic_new':'visit_DynamicNew',
       'semantic_import':'visit_Import','semantic_raise':'visit_Raise',
       'semantic_execute':'visit_Execute'}

class LegacySemanticBoundaryTests(TestCase):
    def test_base_aliases_share_implementation_not_forwarding_frames(self):
        for semantic,visitor in PAIRS.items():
            self.assertIs(getattr(Interpreter,semantic),getattr(Interpreter,visitor))
            self.assertEqual(inspect.isgeneratorfunction(getattr(Interpreter,visitor)),
                             semantic not in ('semantic_name','semantic_import'))

    def test_dynamic_class_hooks_target_the_explicit_backend(self):
        for attribute,expected in (('visit_Name',(42,1)),('semantic_name',(1,42))):
            with patch.object(Interpreter,attribute,lambda vm,node:42):
                for mode,value in zip(('interpreter','compiled-strict'),expected):
                    vm=Interpreter(execution_backend=mode);vm.variables['x']=1
                    self.assertEqual(vm.execute('(x);'),value)

    def test_instance_visitor_and_superclass_hook_order_remain_live(self):
        events=[];original=Interpreter.visit_Name
        def parent(vm,node):events.append('parent');return original(vm,node)
        class Child(Interpreter):
            def visit_Name(self,node):
                events.append('child');return super().visit_Name(node)
        vm=Child(execution_backend='interpreter');vm.variables['x']=3
        with patch.object(Interpreter,'visit_Name',parent):
            self.assertEqual(vm.execute('(x);'),3)
        self.assertEqual(events,['child','parent'])
        vm.visit_Name=lambda node:7
        self.assertEqual(vm.execute('(x);'),7)

    def test_generator_send_throw_close_and_deferred_effects(self):
        events=[]
        class Child(Interpreter):
            def _visit(self,node):
                events.append('start')
                try:return (yield 'operand')
                finally:events.append('closed')
        vm=Child(execution_backend='interpreter');node=parse('x=1;')[0]
        generator=vm.visit_Assign(node)
        self.assertEqual(events,[]);self.assertEqual(vm.variables,{})
        self.assertEqual(next(generator),'operand')
        with self.assertRaises(StopIteration):generator.send(9)
        self.assertEqual(vm.variables['x'],9)
        self.assertEqual(events,['start','closed'])
        for action in ('throw','close'):
            events.clear();vm.variables.clear();generator=vm.visit_Assign(node)
            next(generator)
            if action=='throw':
                error=RuntimeError('host fault')
                with self.assertRaises(RuntimeError) as caught:generator.throw(error)
                self.assertIs(caught.exception,error)
            else:generator.close()
            self.assertEqual(events,['start','closed']);self.assertEqual(vm.variables,{})

    def test_all_context_adapter_bodies_match_except_dispatch_names(self):
        root=Path(__file__).resolve().parents[1]/'yadinassi'
        seen=[]
        class Normalize(ast.NodeTransformer):
            def visit_FunctionDef(self,node):
                node.name=PAIRS.get(node.name,node.name)
                return self.generic_visit(node)
            def visit_Attribute(self,node):
                node.attr=PAIRS.get(node.attr,node.attr)
                return self.generic_visit(node)
        for module in ('catalog_object_preparation','configuration_source_runtime',
                       'document_posting','form_event_simulation','form_runtime',
                       'source_constant_managers'):
            tree=ast.parse((root/(module+'.py')).read_text())
            for cls in [n for n in tree.body if isinstance(n,ast.ClassDef)]:
                methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
                for semantic,visitor in PAIRS.items():
                    if semantic not in methods:continue
                    self.assertIn(visitor,methods)
                    self.assertEqual(ast.dump(Normalize().visit(methods[semantic])),
                                     ast.dump(Normalize().visit(methods[visitor])))
                    seen.append((module,semantic))
        self.assertEqual(len(seen),9)
