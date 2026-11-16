import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.document_posting import _PostingInterpreter
from yadinassi.python_translation_expressions import prepare_expressions
from yadinassi.syntax.parser import parse
from tests.test_python_translation_expressions import finish

class OverrideTests(unittest.TestCase):
    def test_builtin_field_collision_keeps_builtin_over_routine(self):
        # Exercise the admitted production override, not an unregistered test
        # subclass. Minimal field stubs leave its real call dispatch unchanged.
        vm=object.__new__(_PostingInterpreter)
        Interpreter.__init__(vm,execution_backend='compiled-strict')
        vm._steps=0
        vm._member=lambda name:name.casefold()=='number'
        def semantic_name(node):
            if vm._member(node.name):return Decimal(100)
            return Interpreter.semantic_name(vm,node)
        vm.semantic_name=semantic_name
        vm.compiled_before=lambda node:None
        vm.execute('Function Number(Val x) Return 999;EndFunction')
        node=parse('r=Number("12");')[0].value
        execution=prepare_expressions([node]).bind(vm,guard=lambda node:None,access=None)
        vm._visit=lambda *args: (_ for _ in ()).throw(AssertionError('AST execution'))
        self.assertEqual(finish(execution.evaluate(node)),12)
        # The original expression service did not gain a persistent override.
        self.assertEqual(finish(execution.evaluate(node.callee)),100)

    def test_unknown_context_subclass_is_still_rejected_before_effect(self):
        from yadinassi.compiled_backend import CompiledUnsupported
        class Unknown(_PostingInterpreter):pass
        vm=object.__new__(Unknown)
        Interpreter.__init__(vm,execution_backend='compiled-strict')
        seen=[];vm.register_function('Tick',lambda:seen.append(1))
        with self.assertRaises(CompiledUnsupported):vm.execute('Tick();')
        self.assertEqual(seen,[])

    def test_override_signatures_accept_evaluation(self):
        import inspect
        from yadinassi.configuration_source_runtime import _SourceInterpreter
        from yadinassi.source_document_runtime import _ObjectInterpreter
        for cls in (_SourceInterpreter,_PostingInterpreter,_ObjectInterpreter):
            for method in ('call','argument'):
                self.assertIn('_evaluation',inspect.signature(getattr(cls,method)).parameters)

    def test_execute_shared_preadmission_and_reference_scope(self):
        from unittest.mock import patch
        from yadinassi.compiled_backend import Engine
        vm=Interpreter(execution_backend='compiled-strict');vm.variables['x']=Decimal(1)
        node=parse('Execute "x=x+1;localnew=9;";')[0]
        execution=prepare_expressions([node.expression]).bind(vm,guard=lambda node:None,access=None)
        vm._visit=lambda *args: (_ for _ in ()).throw(AssertionError('AST execution'))
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            finish(vm.semantic_execute(node,_evaluation=execution))
        self.assertEqual(vm.variables['x'],2);self.assertNotIn('localnew',vm.variables)
        self.assertIsNone(vm.locals);self.assertEqual(vm._execute_depth[0],0)

    def test_execute_rejects_whole_invalid_fragment_before_effect(self):
        from unittest.mock import patch
        from yadinassi.compiled_backend import Engine
        vm=Interpreter(execution_backend='compiled-strict');events=[]
        vm.register_function('Tick',lambda:events.append(1))
        node=parse('Execute "Tick();If";')[0]
        execution=prepare_expressions([node.expression]).bind(vm,guard=lambda node:None,access=None)
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            with self.assertRaises(Exception):finish(vm.semantic_execute(node,_evaluation=execution))
        self.assertEqual(events,[]);self.assertEqual(vm._execute_depth[0],0)
