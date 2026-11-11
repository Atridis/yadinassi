"""Idle policy against real controllers/SQLite child, never a successful-close stub."""
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
import unittest

from yadinassi.ui.local_app import LocalUIServer, RuntimeBridge
from yadinassi.ui.browser_session import BrowserSession
from yadinassi.ui import local_app, form_app, orders_workspace, reference_orders_workspace, configuration_app
from yadinassi.ui.protocol import encode_value
from ui_catalog_fixture import repository
import test_form_app as forms
import test_orders_workspace as orders
import test_reference_orders as references


class IdleLifecycleTests(unittest.TestCase):
    def host(self, bridge, response):
        calls = []
        def exchange(request):
            calls.append(deepcopy(request))
            return bridge.exchange(request)
        host = object.__new__(LocalUIServer)
        host.bridge = SimpleNamespace(exchange=exchange)
        host.last_response = response
        return host, calls

    def editor(self, mode='list'):
        old, path, _, ids = repository(self); old.close()
        bridge = RuntimeBridge(path); self.addCleanup(bridge.close)
        response = bridge.exchange({'jsonrpc':'2.0','id':1,'method':'editor.hello','params':{'protocol':'yadinassi-editor/0'}})
        def event(event, **values):
            nonlocal response
            response = bridge.exchange({'jsonrpc':'2.0','id':1,'method':'editor.event',
                'params':{'event':event,'baseRevision':response['result']['revision'],**values}})
            return response
        if mode != 'catalogs': event('selectCatalog', catalog=ids['category'])
        if mode in ('new','dirty'):
            event('create')
            if mode == 'dirty': event('change', control='InputData0', value=encode_value('20'))
        return self.host(bridge, response)

    def form(self, *, dirty_contract=True):
        package = forms.load_server(forms.EXAMPLE)
        server = forms.ReplicatedFormServer(package.source, package.endpoints,
            handlers=package.handlers, attributes=package.attributes,
            initial_values=package.initial_values, bindings=package.lifecycle)
        client = forms.load_client(forms.EXAMPLE)
        if dirty_contract:
            client = replace(client, dirty_attribute='Dirty')
        controller = forms.FormController(client, server.exchange)
        self.addCleanup(server.session.interpreter.close)
        self.addCleanup(controller.session.interpreter.close)
        response = controller.exchange(forms.request())
        return controller, self.host(controller, response)

    def workspace(self, cls):
        fixture = cls(); self.addCleanup(fixture.doCleanups); fixture.setUp()
        return fixture, self.host(fixture.controller, {'result':fixture.hello})

    def assert_only_close(self, calls, method, event=None):
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['method'], method)
        if event is not None: self.assertEqual(calls[0]['params']['event'], event)
        self.assertNotIn('Save', repr(calls)); self.assertNotIn('Discard', repr(calls))

    def test_catalog_inventory_and_list_close_real_runtime(self):
        for mode in ('catalogs','list'):
            with self.subTest(mode=mode):
                host, calls = self.editor(mode)
                self.assertTrue(host._close_known_idle())
                self.assertEqual(host.last_response['result']['state']['kind'], 'closed')
                self.assert_only_close(calls, 'editor.event', 'close')

    def test_clean_new_editor_closes_without_saving(self):
        host, calls = self.editor('new')
        self.assertFalse(host.last_response['result']['state']['editor']['dirty'])
        self.assertTrue(host._close_known_idle())
        self.assert_only_close(calls, 'editor.event', 'close')

    def test_dirty_editor_is_retained_without_dispatch(self):
        host, calls = self.editor('dirty'); before = deepcopy(host.last_response)
        self.assertFalse(host._close_known_idle()); self.assertEqual(calls, [])
        self.assertEqual(host.last_response, before)

    def test_uncertain_and_postcommit_editor_snapshots_never_dispatch(self):
        host, calls = self.editor('new'); clean = deepcopy(host.last_response)
        for state in ('uncertain','committed','rejected','saving'):
            host.last_response = deepcopy(clean)
            host.last_response['result']['state']['editor']['saveState'] = state
            self.assertFalse(host._close_known_idle())
        host.last_response = deepcopy(clean)
        host.last_response['result']['state']['uncertain'] = True
        self.assertFalse(host._close_known_idle()); self.assertEqual(calls, [])

    def test_clean_form_runs_ordinary_close(self):
        controller, (host, calls) = self.form()
        self.assertTrue(host._close_known_idle()); self.assertTrue(controller.session.closed)
        self.assert_only_close(calls, 'form.event', 'close')

    def test_generic_form_without_explicit_dirty_contract_is_retained(self):
        controller, (host, calls) = self.form(dirty_contract=False)
        self.assertNotIn('dirty', host.last_response['result']['state'])
        self.assertFalse(host._close_known_idle())
        self.assertEqual(calls, [])
        self.assertFalse(controller.session.closed)

    def test_dirty_form_is_not_discarded(self):
        controller, (host, calls) = self.form()
        result = forms.event(controller, event='change', control='FieldPrice', value=encode_value(Decimal('2')))
        # Use the declared field, selected from the authoritative projection.
        if result['error'] is not None:
            self.fail('fixture input must reach the real OnChange handler')
        host.last_response = {'result':result}
        self.assertTrue(result['state']['dirty'])
        self.assertFalse(host._close_known_idle()); self.assertFalse(controller.session.closed)
        self.assertEqual(calls, [])

    def test_stale_clean_hint_does_not_override_bsl_close_refusal(self):
        controller, (host, calls) = self.form()
        changed = forms.event(controller, event='change', control='FieldPrice', value=encode_value(Decimal('2')))
        self.assertIsNone(changed['error'])
        self.assertTrue(changed['state']['dirty'])
        host.last_response = controller.exchange(forms.request('snapshot'))
        host.last_response['result']['state']['dirty'] = False
        self.assertFalse(host._close_known_idle())
        self.assertFalse(controller.session.closed)
        self.assert_only_close(calls, 'form.event', 'close')

    def test_empty_workspaces_close_through_real_controllers(self):
        for cls in (orders.WorkspaceTests, references.ReferenceOrdersTests):
            with self.subTest(workspace=cls.__name__):
                fixture, (host, calls) = self.workspace(cls)
                self.assertTrue(host._close_known_idle()); self.assertTrue(fixture.controller.closed)
                self.assert_only_close(calls, 'workspace.close')

    def test_nonempty_workspaces_retain_forms(self):
        for cls in (orders.WorkspaceTests, references.ReferenceOrdersTests):
            with self.subTest(workspace=cls.__name__):
                fixture, (host, calls) = self.workspace(cls)
                response = fixture.open(); host.last_response = {'result':response}
                self.assertFalse(host._close_known_idle()); self.assertEqual(calls, [])
                self.assertFalse(fixture.controller.closed); self.assertEqual(len(fixture.controller.sessions), 1)

    def test_detached_pending_input_blocks_real_idle_callback(self):
        controller, (host, calls) = self.form()
        now = [0]
        attachments = BrowserSession('a'*43, clock=lambda:now[0], lease_seconds=10, grace_seconds=3)
        writer = attachments.attach('a'*43, '1'*32)
        attachments.command(writer['credential'],writer['attachment'],'detach',writer['generation'],True)
        now[0] = 4
        self.assertFalse(attachments.idle_shutdown(host._close_known_idle))
        self.assertEqual(calls, []); self.assertFalse(controller.session.closed)

    def test_unknown_failed_and_incomplete_snapshots_never_dispatch(self):
        controller, (host, calls) = self.form()
        for response in (None, {}, {'error':{}}, {'result':{'error':'busy'}},
            {'result':{'protocol':'unknown','state':{'kind':'list'}}},
            {'result':{'protocol':'yadinassi-form-ui/1','state':{'dirty':False}}}):
            host.last_response = response
            self.assertFalse(host._close_known_idle())
        self.assertEqual(calls, []); self.assertFalse(controller.session.closed)

    def test_attachment_profile_is_explicit_and_boolean(self):
        controller, _ = self.form()
        for enabled in (False, True):
            host = LocalUIServer(controller, browser_session=enabled)
            try:
                self.assertEqual(host.attachments is not None, enabled)
                self.assertEqual('&attachment=1' in host.launch_url, enabled)
            finally: host.server_close()
        with self.assertRaises(ValueError): LocalUIServer(controller, browser_session=1)

    def test_all_cli_profiles_expose_explicit_attachment_flag(self):
        for module in (local_app, form_app, orders_workspace, reference_orders_workspace, configuration_app):
            with self.subTest(module=module.__name__), redirect_stdout(StringIO()) as output:
                with self.assertRaises(SystemExit) as exit: module.main(['--help'])
                self.assertEqual(exit.exception.code, 0)
                self.assertIn('--browser-session', output.getvalue())
        # Startup forwarding is checked structurally; no fake process or successful
        # lifecycle substitutes for the real-controller checks above.
        import ast, inspect
        for module in (local_app, form_app, orders_workspace, reference_orders_workspace, configuration_app):
            tree = ast.parse(inspect.getsource(module.main))
            calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='LocalUIServer']
            self.assertEqual(len(calls), 1)
            value = next(k.value for k in calls[0].keywords if k.arg=='browser_session')
            self.assertIn('args.browser_session', ast.unparse(value))
