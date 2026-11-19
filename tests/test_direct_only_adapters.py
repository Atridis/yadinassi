"""Retired adapter execution arms are absent, not fallback choices."""
import ast
import inspect
import unittest
from types import SimpleNamespace
from yadinassi.form_runtime import FormSession
from yadinassi.configuration_runtime import ConfigurationApplication


class DirectOnlyAdapterTests(unittest.TestCase):
    def test_unprepared_form_has_no_old_execution_fallback(self):
        session = object.__new__(FormSession)
        session._bind = lambda *args: object()
        session._direct_handlers = None
        with self.assertRaisesRegex(ValueError, 'direct form handlers'):
            session._invoke('Handler', 'client', [])

    def test_unconnected_session_initialization_preserves_authorization(self):
        events = []
        application = object.__new__(ConfigurationApplication)
        application.session_parameters = SimpleNamespace(_authorize=lambda caller: events.append(caller))
        application._session_owner = object()
        caller = object()
        with self.assertRaisesRegex(ValueError, 'not connected'):
            application.initialize_session_parameters(caller, None)
        self.assertEqual(events, [caller])

    def test_selected_adapters_have_no_old_scheduler_dispatch(self):
        from yadinassi import source_forms, document_posting, form_event_simulation
        methods = (FormSession._invoke, FormSession.dispatch_completion,
                   ConfigurationApplication._invoke, ConfigurationApplication._invoke_remote,
                   source_forms._SourceNoContextServer._invoke,
                   document_posting._PostingInterpreter.invoke,
                   form_event_simulation.simulate_form_event,
                   form_event_simulation.simulate_product_form_event)
        import textwrap
        for method in methods:
            tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
            calls = {n.func.attr for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            self.assertFalse(calls & {'run_inline', 'call_routine', 'block'}, method.__qualname__)
