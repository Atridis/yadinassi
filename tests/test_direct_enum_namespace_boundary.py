"""Direct BSL enum namespaces expose properties and For Each, not Python protocols."""
import unittest
from contextlib import closing
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections.search_directions import BSLSearchDirections
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.types.values import BSLObject


class DirectEnumNamespaceBoundaryTests(unittest.TestCase):
    def test_implicit_iteration_does_not_expose_spelled_protocol_calls(self):
        for prepared in (False, True):
            for namespace, member in (('RoundMode', 'Round15as10'),
                                      ('SearchDirection', 'FromBegin'),
                                      ('SortDirection', 'Asc')):
                with self.subTest(prepared=prepared, namespace=namespace), closing(Interpreter()) as vm:
                    code = f"""
                        Function Argument()
                            Raise "argument must not run";
                        EndFunction
                        Direction = {namespace}.{member};
                        N = 0;
                        For Each Item In {namespace} Do N = N + 1; EndDo;
                        Try {namespace}.__iter__();
                        Except IteratorError = ErrorDescription(); EndTry;
                        Try {namespace}.__getitem__(Argument());
                        Except IndexMethodError = ErrorDescription(); EndTry;
                        Try {namespace}.__setitem__(0, Argument());
                        Except WriteMethodError = ErrorDescription(); EndTry;
                        Try Result = {namespace}[0];
                        Except IndexError = ErrorDescription(); EndTry;
                        Try {namespace}[0] = 1;
                        Except WriteError = ErrorDescription(); EndTry;
                        Try For Each Item In Direction Do EndDo;
                        Except ValueError = ErrorDescription(); EndTry;
                    """
                    with patch.object(BoundaryContext, '_check', side_effect=AssertionError('unexpected Light check')):
                        if prepared:
                            vm.execute_prepared(vm.prepare_program(parse(code)))
                        else:
                            vm.execute(code)
                    self.assertEqual(vm.variables['n'], 2)
                    for key, label in (('iteratorerror', '__iter__'),
                                       ('indexmethoderror', '__getitem__'),
                                       ('writemethoderror', '__setitem__'),
                                       ('indexerror', 'Индексирование'),
                                       ('writeerror', 'Индексирование'),
                                       ('valueerror', 'Для Каждого')):
                        self.assertIn(label, vm.variables[key])
                    self.assertNotIn('result', vm.variables)

    def test_foreign_namespaces_and_hostile_metaclasses_invoke_no_hooks(self):
        calls = []

        class PretendNamespace(type):
            def __eq__(cls, other):
                calls.append('class equality')
                return True

            def __hash__(cls):
                calls.append('class hash')
                return 0

        class HostObject(BSLObject, metaclass=PretendNamespace):
            def __iter__(self):
                calls.append('iterator')
                return iter(())

            @property
            def value_type(self):
                calls.append('value_type')
                return None

        class HostNamespace(BSLSearchDirections):
            def __iter__(self):
                calls.append('subclass iterator')
                return iter(())

        with closing(Interpreter()) as vm:
            for value in (HostObject(), HostNamespace(), BSLSearchDirections()):
                vm.variables['source'] = value
                with self.assertRaisesRegex(BoundaryViolation, 'unregistered or foreign database receiver'):
                    vm.execute('For Each Item In Source Do EndDo;')
        self.assertEqual(calls, [])
