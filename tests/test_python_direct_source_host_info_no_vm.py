"""Explicit source host information without legacy execution or native claims."""
import unittest
import test_source_system_info as system
import test_source_host_session as sessions


class NoVM:
    def setUp(self):
        super().setUp()


class SourceSystemInfoNoVM(NoVM,system.SourceSystemInfoTests):
    def test_russian_constructor_alias(self):
        app,out=self.app('S=New СистемнаяИнформация; Message(S.ВерсияПриложения);','8.3.27.1508')
        app.start();self.assertEqual(out,['8.3.27.1508'])


class SourceHostSessionNoVM(NoVM,sessions.SourceHostSessionTests):
    def test_saved_background_method(self):
        app,out=self.app('S=GetCurrentInfoBaseSession(); F=S.GetBackgroundJob; Message(F()=Undefined);')
        app.start();self.assertEqual(out,['Да'])


if __name__=='__main__':unittest.main()
