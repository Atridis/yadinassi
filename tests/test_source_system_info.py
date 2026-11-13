import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from test_configuration_source_runtime import source
from yadinassi import __version__
from yadinassi.cli import main
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


class SourceSystemInfoTests(unittest.TestCase):
    def app(self, code, target=None):
        out=[];app=SourceApplication(source(('Procedure OnStart()\n'+code+'\nEndProcedure').encode()), output=out.append,compatibility_target=target)
        self.addCleanup(app.close);return app,out

    def test_default_does_not_claim_platform_version(self):
        with self.assertRaisesRegex(BSLError,'not 1C:Enterprise'):
            self.app('S=New SystemInfo; Message(S.AppVersion);')[0].start()

    def test_opt_in_target(self):
        a,out=self.app('S=New SystemInfo; Message(S.AppVersion); Message(S.IsCompatibilityTarget);','8.3.27.1508')
        a.start();self.assertEqual(out,['8.3.27.1508','Да'])

    def test_actual_version_separate(self):
        a,out=self.app('S=New SystemInfo; Message(S.YadinassiVersion);','8.3.27.1508')
        a.start();self.assertEqual(out,[__version__])

    def test_invalid_target_rejected(self):
        for target in ['',True,'latest','8.3.1','8.3.01.0','8.3.0.1 trailing']:
            with self.subTest(target=target),self.assertRaises(ValueError):self.app('',target)

    def test_unknown_host_property_not_guessed(self):
        with self.assertRaisesRegex(BSLError,'property is not supported'):
            self.app('S=New SystemInfo; Message(S.OperatingSystemVersion);')[0].start()

    def test_target_read_only(self):
        with self.assertRaises(BSLError):self.app('S=New SystemInfo; S.AppVersion="x";','8.3.27.1508')[0].start()

    def test_cli_discloses_actual_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            for f in source(b'Procedure OnStart()\n S=New SystemInfo; Message(S.AppVersion);\nEndProcedure').files:
                p=Path(d)/f.path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(f.content)
            out=io.StringIO();err=io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                result=main(['--configuration-source',d,'--run-startup','--source-compatibility-target','8.3.27.1508'])
            self.assertEqual(result,0);self.assertIn('не установленная 1С',err.getvalue());self.assertIn(__version__,err.getvalue())

    def test_cli_requires_source_and_startup(self):
        for args in [['--source-compatibility-target','8.3.27.1508'],['--configuration-source','missing','--source-compatibility-target','8.3.27.1508']]:
            with self.subTest(args=args),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(args)
