"""Generated form-table reads preserve context, timing and live ownership."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi.execution.execution_policy import execution_backend_policy
from yadinassi.forms.form_runtime import FormSession
from yadinassi.forms.form_model import BSLFormAttribute
from yadinassi.types.type_descriptions import BSLTypeDescription
from test_form_tables import make, active
import test_form_tables as form_tests

class TranslatedFormTableIndexTests(unittest.TestCase):
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

    def test_generated_index_actual_reads_one_live_row(self):
        source = form_tests.SOURCE.replace(' Work();', ' Status = LabelOf(Lines[Index()]);') + '''
&AtClient
Function Index()
    Message("index");
    Return 0;
EndFunction
&AtClient
Function LabelOf(Val Row)
    Return Row.Label;
EndFunction
'''
        session = FormSession(source, tables=(form_tests.SCHEMA,),
            attributes=(BSLFormAttribute('Status', BSLTypeDescription('String')),),
            bindings={'OnCreateAtServer': 'Create'})
        session.open()
        snapshot = session.dispatch('command', revision=1, control='RunButton')
        self.assertEqual(dict(snapshot.attributes)['Status'], 'first')
        self.assertEqual(session.messages, ('index',))

    def test_index_preparation_and_finished_read_require_current_form_table(self):
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        from yadinassi.execution.direct.python_direct_forms import FormBoundary

        session = make()
        other = make()
        session.open()
        other.open()
        table = session.form._tables['lines']
        foreign = other.form._tables['lines']
        with active(session):
            context = FormBoundary(session, session.interpreter.server_routines['work'])
            context.enter()
            try:
                with self.assertRaisesRegex(BoundaryViolation, 'foreign direct form receiver'):
                    context.resolve_member(foreign, '__getitem__')
                read = context.resolve_member(table, '__getitem__')
                self.assertIs(read(Decimal(0)), table.get(Decimal(0)))
                for invalid in (Decimal(-1), Decimal('0.5'), Decimal(1), True):
                    with self.assertRaises(ValueError):
                        read(invalid)
                with self.assertRaises(ValueError):
                    context.resolve_member(table, '__setitem__')
                with patch.dict(session.form._tables):
                    session.form._tables.pop('lines')
                    with self.assertRaisesRegex(ValueError, 'отсоединенная'):
                        read(Decimal(0))
            finally:
                context.leave()
        session.dispatch('close', revision=1)
        other.dispatch('close', revision=1)

    def test_unscoped_source_form_factory_is_not_an_ownership_grant(self):
        from yadinassi.configuration.configuration_source import import_source
        from yadinassi.configuration.configuration_source_runtime import SourceApplication
        from yadinassi.forms.source_forms import _SourceFormInterpreter
        from yadinassi.forms.form_runtime import FormSession
        from yadinassi.forms.form_model import BSLFormAttribute
        from yadinassi.types.type_descriptions import BSLTypeDescription
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
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
