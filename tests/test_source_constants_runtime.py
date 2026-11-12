import contextlib
import io
from pathlib import Path
import tempfile
import sqlite3
import unittest
from test_configuration_source_runtime import source
from test_source_session_parameters import declaration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
from yadinassi.cli import main


def package(body):
    xml = declaration('Flag', '<v8:Type>xs:boolean</v8:Type>').replace(b'SessionParameter', b'Constant')
    configuration_xml = source().files[0].content
    configuration_xml = configuration_xml.replace(b'</Configuration>', b'<ChildObjects><Constant>Flag</Constant></ChildObjects></Configuration>')
    return source(extra={'Configuration.xml': configuration_xml, 'Constants/Flag.xml': xml, 'Ext/SessionModule.bsl':
        ('Procedure SessionParametersSetting(Names) ' + body + ' EndProcedure').encode()})


class SourceConstantsRuntimeTests(unittest.TestCase):
    def test_explicit_real_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scratch.sqlite'
            output = []
            app = SourceApplication(package('Constants.Flag.Set(True); Message(Constants.Flag.Get());'),
                                    output=output.append, scratch_database=path)
            try:
                self.assertTrue(app.start())
                self.assertEqual(output, ['Да'])
                self.assertTrue(path.is_file())
                self.assertIs(app.constant_store.get('Flag'), True)
            finally: app.close()
            self.assertTrue(path.is_file())  # Owned artifact is not silently deleted.

    def test_no_implicit_database(self):
        app = SourceApplication(package('Constants.Flag.Get();'))
        try:
            with self.assertRaisesRegex(BSLError, 'scratch database'): app.start()
        finally: app.close()

    def test_safe_frame_cannot_write_database(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SourceApplication(package('SetSafeMode(True); Constants.Flag.Set(True);'),
                                    scratch_database=Path(directory)/'scratch.sqlite')
            try:
                with self.assertRaisesRegex(BSLError, 'safe mode'): app.start()
                with sqlite3.connect(Path(directory)/'scratch.sqlite') as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM constant_value').fetchone(), (0,))
            finally: app.close()

    def test_existing_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'existing.sqlite'; path.write_bytes(b'owner bytes')
            with self.assertRaises((ValueError, OSError)):
                SourceApplication(package(''), scratch_database=path)
            self.assertEqual(path.read_bytes(), b'owner bytes')

    def test_scratch_cli_requires_source_and_explicit_startup(self):
        for args in (['--source-scratch-db','unused.sqlite'],
                     ['--configuration-source','unused','--source-scratch-db','unused.sqlite']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): main(args)

    def test_saved_method_rejects_client_and_foreign_actual_caller(self):
        from yadinassi.source_constants_runtime import SourceConstants
        with tempfile.TemporaryDirectory() as directory:
            app = SourceApplication(package('Constants.Flag.Set(False);'),
                                    scratch_database=Path(directory)/'scratch.sqlite')
            other = SourceApplication(package(''))
            try:
                app.start(); other.start()
                app._session_owner._context_stack.append('server')
                try:
                    manager = SourceConstants(app).member(app._session_owner, 'Flag')
                finally:
                    app._session_owner._context_stack.pop()
                setter = manager.get_member('Set')
                app.interpreter.register_function('CapturedSetter', setter.function, returns_value=False)
                with self.assertRaisesRegex(BSLError, 'owning synchronous server'):
                    app.interpreter.execute('CapturedSetter(True);')
                other._session_owner.register_function('CapturedSetter', setter.function, returns_value=False)
                other._session_owner._context_stack.append('server')
                try:
                    with self.assertRaisesRegex(BSLError, 'owning synchronous server'):
                        other._session_owner.execute('CapturedSetter(True);')
                finally:
                    other._session_owner._context_stack.pop()
                self.assertIs(app.constant_store.get('Flag'), False)
            finally:
                app.close(); other.close()
