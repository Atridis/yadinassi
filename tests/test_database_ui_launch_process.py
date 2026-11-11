"""Stored-source launch with the real owned Python child and no external source."""
from contextlib import closing
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui import configuration_app, database_launch
from yadinassi.ui.local_app import RuntimeBridge
from yadinassi.ui.protocol import encode_value
from ui_catalog_fixture import configuration_files
from yadinassi.configuration_xml import import_configuration

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/configuration-document-forms'


class StoredSourceProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'owned.sqlite'

    def create_documents(self):
        files={p.relative_to(EXAMPLE).as_posix():p.read_bytes() for p in EXAMPLE.rglob('*') if p.is_file()}
        SQLiteCatalogBackend.create_document_forms(self.path,files).close()

    def test_document_launch_without_source_folder_writes_and_reopens(self):
        self.create_documents();roots=[]
        def run(args):
            roots.append(Path(args[0]));bound=args[args.index('--launch-binding')+1]
            forms=configuration_app.load_application(roots[-1],document_objects=True)
            process=configuration_app.ConfigurationProcess(roots[-1],self.path,document_objects=True,launch_binding=bound)
            app=configuration_app.ConfigurationController(forms,process.exchange)
            try:
                def rpc(method,**params):
                    result=app.exchange({'jsonrpc':'2.0','id':1,'method':'application.'+method,'params':params})['result']
                    self.assertIsNone(result['error']);return result
                rpc('hello',protocol=configuration_app.PROTOCOL)
                self.assertEqual(rpc('catalog',entry=1)['state']['catalog']['rows'],[])
                sid=rpc('open',entry=1,request='owned')['session']
                def event(kind,**values):
                    result=rpc('form',session=sid,request={'jsonrpc':'2.0','id':1,'method':'form.event','params':{
                        'event':kind,'revision':app.sessions[sid][0].session.revision,**values}})
                    self.assertIsNone(result['form']['result']['error']);return result
                event('command',control='NewLineButton')
                event('cell',control='LinesTable',row=1,column='Label',value=encode_value('Stored source row'))
                saved=event('command',control='WriteButton');rows=saved['state']['catalog']['rows']
                self.assertEqual(len(rows),1);event('close')
                reopened=rpc('openRecord',entry=1,request='reopen',record=rows[0]['key'])['session']
                table=next(iter(app.sessions[reopened][0].session.form._tables.values()))
                self.assertEqual(table._snapshot().rows[0][1][0],'Stored source row')
                return 0
            finally:
                app.close();process.close()
        with mock.patch.object(configuration_app,'main',side_effect=run):
            self.assertEqual(database_launch.main(['--f',str(self.path)]),0)
        self.assertFalse(roots[0].exists())
        with closing(SQLiteCatalogBackend(self.path)) as backend:
            view=backend.begin_document_read()
            try:
                from yadinassi.document_backend import DocumentSelection
                cards=view.select_documents(view.documents()[0].identity,DocumentSelection())
                self.assertEqual(len(cards),1)
            finally:view.close()

    def test_catalog_child_accepts_only_exact_database_binding(self):
        SQLiteCatalogBackend.create(self.path,import_configuration(configuration_files())).close()
        with closing(SQLiteCatalogBackend(self.path,read_only=True)) as backend:bound=database_launch.binding(backend.launch_snapshot())
        bridge=RuntimeBridge(str(self.path),launch_binding=bound)
        try:
            result=bridge.exchange({'jsonrpc':'2.0','id':1,'method':'editor.hello','params':{'protocol':'yadinassi-editor/0'}})
            self.assertIn('result',result)
            self.assertEqual(result['result']['state']['kind'],'catalogs')
        finally:bridge.close()

    def test_replaced_document_database_refused_in_real_child(self):
        self.create_documents()
        with closing(SQLiteCatalogBackend(self.path,read_only=True)) as backend:snapshot=backend.launch_snapshot()
        other=Path(self.tmp.name)/'other.sqlite'
        SQLiteCatalogBackend.create_document_forms(other,{f.path:f.content for f in snapshot.files}).close()
        with database_launch.materialize(snapshot) as root:
            process=configuration_app.ConfigurationProcess(root,other,document_objects=True,launch_binding=database_launch.binding(snapshot))
            try:
                from yadinassi.ui.protocol import encode_line
                from yadinassi.ui.local_app import LocalTransportError
                with self.assertRaises(LocalTransportError):
                    process.exchange(encode_line({'id':1,'operation':'hello','session':None,'payload':{'source':'0'*64}}))
            finally:process.close()
        with closing(SQLiteCatalogBackend(other)) as backend:
            view=backend.begin_document_read()
            try:
                from yadinassi.document_backend import DocumentSelection
                self.assertEqual(view.select_documents(view.documents()[0].identity,DocumentSelection()),())
            finally:view.close()

    def test_python_module_and_frozen_stub_expose_same_ui_help_from_other_cwd(self):
        env=dict(os.environ,PYTHONPATH=str(ROOT))
        for command in ([sys.executable,'-m','yadinassi'],[sys.executable,str(ROOT/'scripts/entrypoint.py')]):
            result=subprocess.run([*command,'--ui','--help'],cwd=self.tmp.name,env=env,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            help=result.stdout.decode();self.assertIn('yadinassi --ui',help);self.assertIn('--f SQLITE_FILE',help)
            self.assertNotIn('CONFIGURATION_DIRECTORY',help);self.assertNotIn('--catalog-ui',help)

    def business_broker(self):
        from business_configuration_fixture import sources
        files=sources();SQLiteCatalogBackend.create_business_application(self.path,files).close()
        with closing(SQLiteCatalogBackend(self.path,read_only=True)) as backend:snapshot=backend.launch_snapshot()
        with database_launch.materialize(snapshot) as root:
            forms=configuration_app.load_application(root,business_application=True)
        broker=configuration_app.ConfigurationBroker(forms,self.path,business_application=True,
            launch_binding=database_launch.binding(snapshot),launch_route='business')
        self.addCleanup(broker.close)
        broker.exchange({'operation':'hello','session':'','payload':{'source':forms.source_sha256}})
        return broker,files

    def test_late_same_source_database_replacement_cannot_open_common_form(self):
        broker,files=self.business_broker()
        replacement=Path(self.tmp.name)/'replacement.sqlite'
        SQLiteCatalogBackend.create_business_application(replacement,files).close()
        self.path.replace(Path(self.tmp.name)/'previous.sqlite');replacement.replace(self.path)
        entry=next(i for i,d in broker.definitions.items() if d.catalog_schema is None and d.document_schema is None)
        with self.assertRaisesRegex(ValueError,'database UI source changed'):
            broker.exchange({'operation':'create','session':'','payload':{'entry':entry,'parameters':{},'record':None}})
        self.assertEqual(broker.sessions,{})

    def test_object_context_rechecked_after_catalog_preflight(self):
        broker,files=self.business_broker()
        replacement=Path(self.tmp.name)/'replacement.sqlite'
        SQLiteCatalogBackend.create_business_application(replacement,files).close()
        entry=next(i for i,d in broker.definitions.items() if d.document_schema is not None)
        actual=configuration_app.SQLiteDBContext
        # A deterministic same-source replacement between _catalog and new VM.
        contexts=[]
        def replaced(path):
            context=actual(replacement);contexts.append(context);return context
        with mock.patch.object(configuration_app,'SQLiteDBContext',side_effect=replaced):
            with self.assertRaisesRegex(ValueError,'database UI source changed'):
                broker.exchange({'operation':'create','session':'','payload':{'entry':entry,'parameters':{},'record':None}})
        self.assertEqual(broker.sessions,{})
        self.assertEqual(len(contexts),1);self.assertTrue(contexts[0].backend._closed)
