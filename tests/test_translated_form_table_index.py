"""Generated form-table reads preserve context, timing and live ownership."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution_policy import execution_backend_policy
from yadinassi import translated_access as access
from test_form_tables import make, active
import test_form_tables as form_tests

class TranslatedFormTableIndexTests(unittest.TestCase):
    def test_original_nested_call_case_direct(self):
        for backend in ('python-direct',):
            with self.subTest(backend=backend), execution_backend_policy(backend):
                case = form_tests.FormTableTests('test_bare_member_iteration_and_index_access')
                case.test_bare_member_iteration_and_index_access()

    def test_each_generated_table_read_runs_once(self):
        for backend in ('python-direct',):
            with self.subTest(backend=backend), execution_backend_policy(backend):
                session = make(work='Status = Lines[0].Label + Lines[0].Label;')
                session.open()
                table = session.form._tables['lines']
                original = type(table).get_index
                seen = []
                def read(value, index):
                    seen.append(index)
                    return original(value, index)
                with patch.object(type(table), 'get_index', read):
                    snapshot = session.dispatch('command', revision=1, control='RunButton')
                self.assertEqual(dict(snapshot.attributes)['Status'], 'firstfirst')
                self.assertEqual(seen, [Decimal(0), Decimal(0)])
                session.dispatch('close', revision=2)

    def test_value_service_keeps_live_checks_and_other_vm_rejection(self):
        session = make(); session.open()
        table = session.form._tables['lines']
        vm = session.interpreter
        operation = access.prepare_index_read(vm, table)
        with self.assertRaises(ValueError):
            vm._scheduler.run_inline(operation.finish(Decimal(0)))
        with active(session):
            self.assertIs(vm._scheduler.run_inline(operation.finish(Decimal(0))), table.get(Decimal(0)))
            for invalid in (Decimal(-1), Decimal('0.5'), Decimal(1), True):
                with self.assertRaises(ValueError):
                    vm._scheduler.run_inline(operation.finish(invalid))
            ordinary = Interpreter()
            try:
                with self.assertRaises(TypeError):access.prepare_index_read(ordinary, table)
            finally:ordinary.close()
            from yadinassi.form_runtime import _FormInterpreter
            class UnknownForm(_FormInterpreter): pass
            with self.assertRaises(TypeError):
                access.prepare_index_read(object.__new__(UnknownForm), table)
        session.dispatch('close', revision=1)
        with self.assertRaises(ValueError):
            vm._scheduler.run_inline(operation.finish(Decimal(0)))

    def test_unscoped_source_form_factory_is_not_an_ownership_grant(self):
        from yadinassi.configuration_source import import_source
        from yadinassi.configuration_source_runtime import SourceApplication
        from yadinassi.source_forms import _SourceFormInterpreter
        from yadinassi.form_runtime import FormSession
        from yadinassi.form_model import BSLFormAttribute
        from yadinassi.type_descriptions import BSLTypeDescription
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        from test_source_forms import files
        application=SourceApplication(import_source(files()))
        try:
            application.start()
            def factory(session,output,**kwargs):
                return _SourceFormInterpreter(application,session,output,**kwargs)
            # Supported owned source forms are exercised through their controller
            # in test_python_direct_source_forms_security. A caller-supplied
            # interpreter factory alone does not establish its execution scope.
            with self.assertRaisesRegex(BoundaryViolation,'source form scope changed'):
                FormSession(form_tests.SOURCE,tables=(form_tests.SCHEMA,),
                    attributes=(BSLFormAttribute('Status',BSLTypeDescription('String')),),
                    bindings={'OnCreateAtServer':'Create'},interpreter_factory=factory)
        finally:application.close()
