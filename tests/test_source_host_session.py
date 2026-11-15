from pathlib import Path
import tempfile
import unittest
from test_source_manager_modules import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.source_host_session import SourceSessionCall
from yadinassi.runtime import Interpreter


class SourceHostSessionTests(unittest.TestCase):
    def app(self, code='Message(GetCurrentInfoBaseSession().GetBackgroundJob()=Undefined);',scratch=True,server=True):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        out=[]
        app=SourceApplication(configuration(code,session=server),output=out.append,
            scratch_database=Path(temp.name)/'scratch.sqlite' if scratch else None)
        self.addCleanup(app.close)
        return app,out

    def test_actual_foreground_origin(self):
        a,out=self.app();self.assertTrue(a.start());self.assertEqual(out,['Да'])

    def test_session_identity_is_stable(self):
        a,out=self.app('Message(GetCurrentInfoBaseSession()=GetCurrentInfoBaseSession());')
        a.start();self.assertEqual(out,['Да'])

    def test_missing_database_not_invented(self):
        with self.assertRaisesRegex(BSLError,'explicit source scratch'):self.app(scratch=False)[0].start()

    def test_client_not_granted(self):
        with self.assertRaisesRegex(BSLError,'synchronous server'):self.app(server=False)[0].start()

    def test_closed_session_rejected(self):
        a,_=self.app();a.start();a.close()
        with self.assertRaises(ValueError):SourceSessionCall(a.host_session,False).invoke(a.interpreter,[])

    def test_foreign_family_rejected(self):
        a,_=self.app();a.start();other=Interpreter();self.addCleanup(other.close)
        with self.assertRaises(ValueError):SourceSessionCall(a.host_session,False).invoke(other,[])

    def test_unsupported_member_explicit(self):
        with self.assertRaisesRegex(BSLError,'member is not supported'):
            self.app('Message(GetCurrentInfoBaseSession().User);')[0].start()

    def test_query_arity(self):
        with self.assertRaisesRegex(BSLError,'no arguments'):
            self.app('GetCurrentInfoBaseSession(1);')[0].start()

    def test_real_source_sqlite_connection_identity(self):
        a,out=self.app('Message(InfoBaseConnectionString());')
        a.start()
        self.assertEqual(out,['SQLite='+a.constant_store.path])
        self.assertFalse(out[0].startswith(('File=', 'Srvr=')))

    def test_connection_requires_explicit_scratch(self):
        with self.assertRaisesRegex(BSLError,'explicit source scratch'):
            self.app('InfoBaseConnectionString();',scratch=False)[0].start()

    def test_connection_client_rejected(self):
        with self.assertRaisesRegex(BSLError,'synchronous server'):
            self.app('InfoBaseConnectionString();',server=False)[0].start()
