"""Explicit source host information without legacy execution or native claims."""
import unittest
from unittest.mock import patch
import test_source_system_info as system
import test_source_host_session as sessions
from yadinassi.runtime import Interpreter


class NoVM:
    def setUp(self):
        super().setUp()
        for name in ('_execute_program','call_routine'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start();self.addCleanup(poison.stop)


class SourceSystemInfoNoVM(NoVM,system.SourceSystemInfoTests):
    def test_russian_constructor_alias(self):
        app,out=self.app('S=New СистемнаяИнформация; Message(S.ВерсияПриложения);','8.3.27.1508')
        app.start();self.assertEqual(out,['8.3.27.1508'])


class SourceHostSessionNoVM(NoVM,sessions.SourceHostSessionTests):
    def test_saved_background_method(self):
        app,out=self.app('S=GetCurrentInfoBaseSession(); F=S.GetBackgroundJob; Message(F()=Undefined);')
        app.start();self.assertEqual(out,['Да'])


class SourceHostInfoLegacyControl(unittest.TestCase):
    def test_factory_marker_keeps_explicit_legacy_backend(self):
        from yadinassi.execution_policy import execution_backend_policy
        from yadinassi.configuration_source_runtime import SourceApplication
        from test_configuration_source_runtime import source
        out=[]
        with execution_backend_policy('compiled-strict'):
            app=SourceApplication(source(b'Procedure OnStart() S=New SystemInfo; Message(S.AppVersion); EndProcedure'),
                output=out.append,compatibility_target='8.3.27.1508')
            self.addCleanup(app.close);app.start()
        self.assertEqual(out,['8.3.27.1508'])


if __name__=='__main__':unittest.main()
