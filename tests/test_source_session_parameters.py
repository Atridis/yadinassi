"""Source-family typed session storage; no native default-value claims."""
from decimal import Decimal
import unittest
from uuid import uuid5, NAMESPACE_URL

from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.runtime import Interpreter
from yadinassi.maps import BSLMap, BSLFixedMap
from yadinassi.configuration_source_session import source_session_definitions


def declaration(name, body):
    return ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" '
            'xmlns:v8="http://v8.1c.ru/8.1/data/core" '
            'xmlns:xs="http://www.w3.org/2001/XMLSchema"><SessionParameter uuid="'
            + str(uuid5(NAMESPACE_URL, name)) + '"><Properties><Name>' + name
            + '</Name><Synonym/><Comment/><Type>' + body
            + '</Type></Properties></SessionParameter></MetaDataObject>').encode()


def package(body, *, app='', kind='v8:FixedMap', extra=None):
    files = {
        'SessionParameters/State.xml': declaration('State', '<v8:Type>' + kind + '</v8:Type>'),
        'Ext/SessionModule.bsl': ('Procedure SessionParametersSetting(Names)\n' + body + '\nEndProcedure').encode(),
    }
    files.update(extra or {})
    return source(app.encode(), files)


class SourceSessionTests(unittest.TestCase):
    def run_source(self, configuration):
        output = []
        app = SourceApplication(configuration, output=output.append)
        self.addCleanup(app.close)
        app.start()
        return app, output

    def test_fixed_map_assignment_then_read(self):
        _, output = self.run_source(package('M=New Map; M.Insert("key",42);\n'
            'SessionParameters.State=New FixedMap(M); Message(SessionParameters.State.Get("key"));'))
        self.assertEqual(output, ['42'])

    def test_dot_and_index_share_value(self):
        _, output = self.run_source(package('M=New Map; M.Insert("key",42);\n'
            'SessionParameters["State"]=New FixedMap(M); Message(SessionParameters.State.Get("key"));'))
        self.assertEqual(output, ['42'])

    def test_mutable_map_rejected_preserves_fixed_value(self):
        _, output = self.run_source(package('M=New Map; M.Insert("key",42);\n'
            'SessionParameters.State=New FixedMap(M);\n'
            'Try SessionParameters.State=M; Except EndTry; Message(SessionParameters.State.Get("key"));'))
        self.assertEqual(output, ['42'])

    def test_unknown_type_only_fails_when_accessed(self):
        app, output = self.run_source(package('', kind='v8:FutureType'))
        self.assertEqual(output, [])
        with self.assertRaisesRegex(BSLError, 'unsupported session parameter type'):
            self.run_source(package('SessionParameters.State=Undefined;', kind='v8:FutureType'))

    def test_fixed_map_no_invented_empty_default(self):
        with self.assertRaisesRegex(BSLError, 'not set'):
            self.run_source(package('If Names=Undefined Then Message(SessionParameters.State.Count()); EndIf;'))

    def test_lazy_handler_can_assign_real_fixed_map(self):
        _, output = self.run_source(package('If Names=Undefined Then\n'
            'Message(SessionParameters.State.Count());\nElse\n'
            'M=New Map; M.Insert("key",42); SessionParameters.State=New FixedMap(M); EndIf;'))
        self.assertEqual(output, ['1'])

    def test_recursive_initialization_still_bounded(self):
        with self.assertRaisesRegex(BSLError, 'recursive session parameter'):
            self.run_source(package('Message(SessionParameters.State.Count());'))

    def test_client_has_no_session_access(self):
        with self.assertRaisesRegex(BSLError, 'server application context'):
            self.run_source(package('', app='Procedure OnStart()\nMessage(SessionParameters.State);\nEndProcedure'))

    def test_closed_source_cannot_lend_handle(self):
        app, _ = self.run_source(package('M=New Map; SessionParameters.State=New FixedMap(M);'))
        store = app.session_parameters
        app.close()
        vm = Interpreter(output=lambda _: None)
        self.addCleanup(vm.close)
        vm.variables['old'] = store
        with self.assertRaisesRegex(BSLError, 'closed application'):
            vm.execute('Old.State')

    def test_foreign_live_source_cannot_lend_handle(self):
        first, _ = self.run_source(package('M=New Map; SessionParameters.State=New FixedMap(M);'))
        second, _ = self.run_source(package(''))
        second._session_owner.variables['old'] = first.session_parameters
        with self.assertRaisesRegex(BSLError, 'another or closed'):
            second._session_owner.execute('Old.State')

    def test_scalar_existing_contract_reused(self):
        _, output = self.run_source(package('SessionParameters.State=True; Message(SessionParameters.State);', kind='xs:boolean'))
        self.assertEqual(output, ['Да'])

    def test_unknown_namespace_is_not_fixed_map(self):
        config = package('', extra={'SessionParameters/State.xml': declaration('State','<v8:Type>xs:FixedMap</v8:Type>')})
        definitions, unsupported = source_session_definitions(config)
        self.assertEqual(definitions, ())
        self.assertIn('state', unsupported)

    def test_compound_type_is_not_silently_reduced(self):
        config = package('', extra={'SessionParameters/State.xml': declaration('State','<v8:Type>v8:FixedMap</v8:Type><v8:Type>xs:boolean</v8:Type>')})
        definitions, unsupported = source_session_definitions(config)
        self.assertEqual(definitions, ())
        self.assertIn('state', unsupported)

    def test_metadata_type_no_fake_scalar_description(self):
        app, _ = self.run_source(package(''))
        metadata = app.session_parameters.metadata.get_member('State')
        with self.assertRaisesRegex(ValueError, 'unsupported metadata field type'):
            metadata.get_member('Type')

    def test_failed_start_closes_session_store(self):
        app = SourceApplication(package('SessionParameters.State=False;'))
        with self.assertRaisesRegex(BSLError, 'unsupported session parameter assignment'):
            app.start()
        self.assertTrue(app.session_parameters._closed)
        self.assertEqual(app.state, 'failed')

    def test_run_mode_is_undefined_for_headless_source_not_a_fake_client(self):
        _, output = self.run_source(package('Message(CurrentRunMode()=Undefined);',
            app='Procedure OnStart()\nMessage(ТекущийРежимЗапуска()=Undefined);\nEndProcedure'))
        self.assertEqual(output, ['Да', 'Да'])

    def test_closed_run_mode_binding_is_not_reusable(self):
        app, _ = self.run_source(package(''))
        app.close()
        with self.assertRaisesRegex(ValueError, 'not running'): app.current_run_mode()

    def cached_source(self, mode='DuringSession', body=None):
        xml = ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000003"><Properties><Name>Helpers</Name><Server>true</Server><ReturnValuesReuse>'+mode+'</ReturnValuesReuse></Properties></CommonModule></MetaDataObject>').encode()
        return package(body or 'Message(Helpers.Value().Get("key")); Message(Helpers.Value().Get("key"));', extra={
            'CommonModules/Helpers.xml': xml,
            'CommonModules/Helpers/Ext/Module.bsl': b'Function Value() Export\nMessage("compute"); M=New Map; M.Insert("key",42); Return New FixedMap(M);\nEndFunction'})

    def test_same_side_cached_fixed_map_is_reused(self):
        _, output = self.run_source(self.cached_source())
        self.assertEqual(output, ['compute', '42', '42'])

    def test_session_reuse_survives_next_request(self):
        app, output = self.run_source(self.cached_source())
        owner = app._session_owner
        owner._context_stack.append('server')
        try: owner.execute('Message(Helpers.Value().Get("key"));')
        finally: owner._context_stack.pop()
        self.assertEqual(output, ['compute', '42', '42', '42'])

    def test_request_reuse_expires_at_next_request(self):
        app, output = self.run_source(self.cached_source('DuringRequest'))
        owner = app._session_owner
        owner._context_stack.append('server')
        try: owner.execute('Message(Helpers.Value().Get("key"));')
        finally: owner._context_stack.pop()
        self.assertEqual(output, ['compute', '42', '42', 'compute', '42'])

    def test_refresh_invalidates_source_cache(self):
        _, output = self.run_source(self.cached_source(body='Message(Helpers.Value().Get("key")); RefreshReusableValues(); Message(Helpers.Value().Get("key"));'))
        self.assertEqual(output, ['compute', '42', 'compute', '42'])

    def test_caches_do_not_leak_between_source_applications(self):
        _, first = self.run_source(self.cached_source())
        _, second = self.run_source(self.cached_source())
        self.assertEqual(first, second)
        self.assertEqual(second.count('compute'), 1)
