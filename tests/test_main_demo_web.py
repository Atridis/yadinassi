"""One launcher, closed asset table and the existing browser attachment boundary."""
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
import tempfile
import unittest
from unittest.mock import patch
from test_main_demo_configuration import source, ROOT
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.database_launch import binding, main
from yadinassi.ui.main_demo_host import MainDemoHost
from yadinassi.ui.main_demo_web import MainDemoHandler
from yadinassi.ui.local_app import LocalUIServer

class MainDemoWebTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'demo.sqlite'
        with SQLiteDBContext.create_main_demo(self.path,import_main_demo_configuration(source(),profile=PROFILE)) as context:
            self.binding=binding(context.backend.launch_snapshot())

    def test_ui_routes_one_existing_database_without_materializing_second_configuration(self):
        with patch('yadinassi.ui.main_demo_web.main',return_value=0) as launch, patch('yadinassi.ui.database_launch.materialize',side_effect=AssertionError('not needed')):
            self.assertEqual(main(['--f',str(self.path)]),0)
        self.assertEqual(launch.call_args.args[0],['--f',str(self.path),'--launch-binding',self.binding])

    def test_actual_http_assets_have_closed_routes_and_existing_security_headers(self):
        host=MainDemoHost(self.path,self.binding)
        server=LocalUIServer(host,handler=MainDemoHandler,browser_session=True,idle_close=host.idle_close)
        thread=Thread(target=server.serve_forever,kwargs={'poll_interval':0.01},daemon=True);thread.start()
        try:
            for path,expected in (('/',200),('/app.js',200),('/catalog.js',200),('/configuration.js',200),('/../configuration_main_demo.py',404),('/rpc',404)):
                connection=HTTPConnection(server.authority,timeout=3)
                try:
                    connection.request('GET',path);reply=connection.getresponse();body=reply.read()
                    self.assertEqual(reply.status,expected,path)
                    self.assertIn("frame-ancestors 'none'",reply.getheader('Content-Security-Policy'))
                    self.assertEqual(reply.getheader('Cache-Control'),'no-store')
                    if path=='/configuration.js':self.assertIn(b'export const mountApplication',body)
                finally:connection.close()
            connection=HTTPConnection(server.authority,timeout=3)
            try:
                connection.request('GET','/',headers={'Host':'foreign.example'})
                reply=connection.getresponse();reply.read();self.assertEqual(reply.status,403)
            finally:connection.close()
        finally:
            server.shutdown();thread.join(3);server.server_close();host.close()

    def test_old_protocol_is_not_exposed_at_top_level(self):
        self.assertEqual(set(MainDemoHandler.methods),{'demo.hello','demo.snapshot','demo.select','demo.dispatch','demo.close'})
        self.assertNotIn('editor.event',MainDemoHandler.methods)

    def test_new_renderer_assets_are_in_wheel_package_data(self):
        self.assertIn('"ui/assets/main-demo/*"',(ROOT/'pyproject.toml').read_text(encoding='utf-8'))
