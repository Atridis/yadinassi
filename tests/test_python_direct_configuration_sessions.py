"""Direct session startup uses an isolated server initializer, not client RPC."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_configuration_session_parameters import files_for_session
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct_configuration_sessions import SessionStartup
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import HostFunction


class DirectConfigurationSessionTests(unittest.TestCase):
    def app(self,files=None,**kwargs):
        files=files_for_session() if files is None else files
        app=ConfigurationApplication.from_files(files,**kwargs)
        self.addCleanup(lambda:app.close(force=True))
        return app

    def test_startup_failure_clears_values_and_closes_family(self):
        app=self.app(files_for_session('Procedure SessionParametersSetting(P) '
            'SessionParameters.Flag=True; Raise "fail after write"; EndProcedure'))
        self.assertEqual(app.state,'prepared')
        with self.assertRaisesRegex(BSLRuntimeError,'fail after write'):app.start()
        self.assertEqual(app.state,'failed')
        self.assertEqual(app.session_parameters._values,{})
        self.assertTrue(app.session_parameters._closed)
        self.assertTrue(app.interpreter._family_closed)

    def test_sqlite_owned_application_can_start_without_db_operations(self):
        files=files_for_session()
        config=import_configuration(files,module_runtime=MODULE_RUNTIME)
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        context=SQLiteDBContext.create(Path(folder.name)/'config.sqlite',config)
        self.addCleanup(context.close)
        app=self.app(files,database_context=context)
        self.assertTrue(app.start())
        self.assertTrue(app.session_parameters._values['ready'])
        self.assertEqual(app.session_parameters._values['calls'],Decimal(0))
        self.assertIsNone(context.backend._active)

    def test_absent_handler_leaves_declared_parameters_unset(self):
        app=self.app(files_for_session(''))
        self.assertTrue(app.start())
        from yadinassi.application.session_parameters import _UNSET
        self.assertIs(app.session_parameters._values['flag'],_UNSET)
        self.assertIsNone(app._session_owner)

    def test_startup_uses_canonical_message_without_inheriting_host_services(self):
        messages, calls = [], []
        app=self.app(files_for_session('Procedure SessionParametersSetting(P) '
            'Message("first"); Сообщить("second"); EndProcedure'), output=messages.append)
        self.assertTrue(app.start())
        self.assertEqual(messages,['first','second'])

        denied=self.app(files_for_session('Procedure SessionParametersSetting(P) '
            'OtherService(); EndProcedure'),
            host_services={'OtherService':HostFunction('OtherService', lambda:calls.append(True))})
        with self.assertRaisesRegex(BoundaryViolation,'unsupported session initializer host service'):
            denied.start()
        self.assertEqual(calls,[])

    def test_pure_startup_loop_has_no_routine_context_checks(self):
        check=SessionStartup._check
        counts=[]
        for iterations in (1,128):
            source=('Procedure УстановкаПараметровСеанса(P) '
                    'Total=0; For I=1 To '+str(iterations)+' Do Total=Total+1; EndDo; '
                    'SessionParameters["Calls"]=Total; '
                    'ПараметрыСеанса.Ready=SessionParameters.Calls=Total; EndProcedure')
            app=self.app(files_for_session(source))
            calls=[]
            def observe(context):
                calls.append(None)
                return check(context)
            with patch.object(SessionStartup,'_check',observe), \
                 patch.object(BoundaryContext,'checkpoint',side_effect=AssertionError('routine checkpoint')):
                self.assertTrue(app.start())
            self.assertEqual(app.session_parameters._values['calls'],Decimal(iterations))
            self.assertTrue(app.session_parameters._values['ready'])
            counts.append(len(calls))
        self.assertEqual(counts,[2,2])
