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


if __name__=='__main__':unittest.main()
