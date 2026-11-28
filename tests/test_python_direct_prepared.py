import unittest
from decimal import Decimal
from unittest.mock import patch
from dataclasses import FrozenInstanceError, dataclass
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508

class PreparedDirectTests(unittest.TestCase):
    def test_compile_once_current_state(self):
        vm=Interpreter();vm.variables['x']=Decimal(1);p=vm.prepare('x=x+1;x;')
        with patch('yadinassi.execution.direct.python_direct._compile',side_effect=AssertionError('recompile')):
            self.assertEqual(vm.execute_prepared(p),2)
            self.assertEqual(vm.execute_prepared(p),3)
        self.assertIsNone(p._plan.last_state)

    def test_owned_ast_snapshot(self):
        nodes=parse('x=1;');vm=Interpreter();p=vm.prepare_program(nodes)
        nodes[0].value.value=Decimal(99);nodes.clear()
        vm.execute_prepared(p);self.assertEqual(vm.variables['x'],1)
        with self.assertRaises(FrozenInstanceError):p._layout=frozenset()

    def test_reject_host_literal_without_deepcopy(self):
        class Host:
            def __deepcopy__(self,memo):raise AssertionError('host hook')
        nodes=parse('x=1;');nodes[0].value.value=Host()
        with self.assertRaisesRegex(PythonDirectUnsupported,'immutable parser'):Interpreter().prepare_program(nodes)

    def test_snapshot_looks_up_exact_syntax_vocabulary_once_per_copy(self):
        from yadinassi.execution.direct import python_direct as direct
        from yadinassi.syntax import ast
        from yadinassi.syntax.lexer import Token

        class GuardedType(type):
            def __hash__(self): raise AssertionError('host type hash')
            def __eq__(self, other): raise AssertionError('host type equality')

        @dataclass
        class ExtensionNode(ast.Node, metaclass=GuardedType):
            child: ast.Node

        token = Token('NAME', 'n', 1, 1, 'test')
        node = ExtensionNode(token, ast.Name(token, 'n'))
        inventory_reads = []
        def observe(owner):
            inventory_reads.append(owner)
            return vars(owner)

        with patch.object(direct, 'vars', observe, create=True):
            with self.assertRaisesRegex(PythonDirectUnsupported, 'unsupported host payloads'):
                direct._snapshot([node])
            with patch.object(ast, 'ExtensionNode', ExtensionNode, create=True):
                copied = direct._snapshot([node, [node]])[0]
                self.assertIs(type(copied), ExtensionNode)
                self.assertIsNot(copied, node)
                self.assertIsNot(copied.child, node.child)
                self.assertIsNot(copied.token, token)
            with self.assertRaisesRegex(PythonDirectUnsupported, 'unsupported host payloads'):
                direct._snapshot([node])
        self.assertEqual(inventory_reads, [ast, ast, ast])

    def test_cross_vm_current_registry(self):
        a=Interpreter(allow_extensions=True);b=Interpreter(allow_extensions=True);a.register_function('Read',lambda:1);b.register_function('Read',lambda:9)
        p=a.prepare('x=Read();')
        a.execute_prepared(p);b.execute_prepared(p)
        self.assertEqual(a.variables['x'],1);self.assertEqual(b.variables['x'],9)
        b.register_function('Read',lambda:20);b.variables={}
        b.execute_prepared(p);self.assertEqual(b.variables['x'],20)

    def test_layout_and_own_declarations(self):
        vm=Interpreter();p=vm.prepare('Var x;Function F() x=x+1;EndFunction x=0;F();')
        vm.execute_prepared(p);vm.execute_prepared(p);self.assertEqual(vm.variables['x'],1)
        vm.module_names.add('extra');vm.variables.clear()
        with self.assertRaisesRegex(PythonDirectUnsupported,'layout changed'):vm.execute_prepared(p)
        self.assertEqual(vm.variables,{})
        fresh=vm.prepare('Var x;x=2;');vm.execute_prepared(fresh);self.assertEqual(vm.variables['x'],2)

    def test_target_backend_and_profile_binding(self):
        p=Interpreter().prepare('x=1;')
        vm=Interpreter(native_target=LINUX_8_3_27_1508)
        with self.assertRaisesRegex(PythonDirectUnsupported,'contract changed'):vm.execute_prepared(p)
        self.assertEqual(vm.variables,{})
        for removed in ('compiled-strict','interpreter'):
            with self.subTest(backend=removed), self.assertRaises(ValueError):
                Interpreter(execution_backend=removed)

    def test_closed_and_restricted_before_effects(self):
        a=Interpreter();p=a.prepare('x=1;');a.close()
        with self.assertRaises(Exception):a.execute_prepared(p)
        self.assertEqual(a.variables,{})
        b=Interpreter();b._configuration_runtime=object()
        with self.assertRaises(PythonDirectUnsupported):b.execute_prepared(p)
        self.assertEqual(b.variables,{})

    def test_subclass_rejected_before_descriptor_contract_access(self):
        class Hostile(Interpreter):
            @property
            def execution_backend(self):raise AssertionError('descriptor called')
        vm=object.__new__(Hostile);p=Interpreter().prepare('x=1;')
        with self.assertRaisesRegex(PythonDirectUnsupported,'specialized'):vm.execute_prepared(p)
        with self.assertRaisesRegex(PythonDirectUnsupported,'specialized'):vm.prepare('x=1;')

    def test_immutable_literal_payloads(self):
        vm=Interpreter();p=vm.prepare("a=Null;b='20200101';")
        vm.execute_prepared(p)
        from yadinassi.types.values import NULL
        self.assertIs(vm.variables['a'],NULL)
        previous=vm.variables['b'];vm.variables.clear();vm.execute_prepared(p)
        self.assertIs(vm.variables['b'],previous)

    def test_current_constructor_registry(self):
        vm=Interpreter(allow_extensions=True);p=vm.prepare('x=1;a=New Array;');vm.register_type('Array',lambda:[])
        with self.assertRaisesRegex(PythonDirectUnsupported,'overridden'):vm.execute_prepared(p)
        self.assertEqual(vm.variables,{})

    def test_partial_state_and_error_source(self):
        vm=Interpreter();p=vm.prepare('x=1;\ny=1/0;','prepared.bsl')
        for _ in range(2):
            vm.variables.clear()
            with self.assertRaisesRegex(Exception,'prepared.bsl'):vm.execute_prepared(p)
            self.assertEqual(vm.variables,{'x':1})

    def test_callback_restriction_not_authorization_cached(self):
        vm=Interpreter(allow_extensions=True);p=vm.prepare('Install();x=1;');vm.register_function('Install',lambda:setattr(vm,'_configuration_runtime',object()))
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        with self.assertRaises(BoundaryViolation):vm.execute_prepared(p)
        self.assertNotIn('x',vm.variables)

if __name__=='__main__':unittest.main()
