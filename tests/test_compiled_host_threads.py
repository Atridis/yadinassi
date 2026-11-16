"""Real loopback request threads preserve the server's host-selected backend."""
from http.client import HTTPConnection
import json
from threading import Thread, current_thread
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine
from yadinassi.execution_policy import current_backend, execution_backend_policy
from yadinassi.ui.local_app import LocalUIServer
from yadinassi.ui.main_demo_web import MainDemoHandler
from yadinassi.ui.editor_protocol import PROTOCOL as EDITOR_PROTOCOL


class CompiledHostThreadTests(unittest.TestCase):
    def request(self,server,method,params):
        # These real request-thread tests compile demo forms, not a 5-second
        # latency contract. Keep a finite CI allowance for slower hosted CPUs;
        # do not retry requests or weaken strict-backend/result assertions.
        connection=HTTPConnection(server.authority,timeout=30)
        raw=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()+b'\n'
        try:
            connection.request('POST','/rpc',body=raw,headers={
                'Host':server.authority,'Origin':server.origin,'Content-Type':'application/x-ndjson',
                'X-Yadinassi-Session':server.token})
            response=connection.getresponse();body=response.read()
            self.assertEqual(response.status,200,body)
            return json.loads(body)['result']
        finally:connection.close()

    def _run_surface(self,surface):
        entry_backend=current_backend()
        from test_main_demo_host import MainDemoHostTests
        fixture=MainDemoHostTests('test_original_product_form_refuses_empty_write_and_switch')
        server=None;thread=None
        try:
            with execution_backend_policy('compiled-strict'):
                fixture.setUp()
                server=LocalUIServer(fixture.host,handler=MainDemoHandler)
            self.assertEqual(current_backend(),entry_backend)
            thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
            thread.start()
            created=[];stats=[]
            original_init=Interpreter.__init__;original_engine=Engine.__init__
            def initialize(vm,*args,**kwargs):
                original_init(vm,*args,**kwargs)
                created.append((current_thread().ident,type(vm).__name__,vm.execution_backend))
            def engine_initialize(engine,vm):
                original_engine(engine,vm);stats.append(engine.stats)
            sequence=0
            def dispatch(method,params):
                nonlocal sequence
                sequence+=1
                result=self.request(server,'demo.dispatch',{'epoch':fixture.host.epoch,'request':{
                    'jsonrpc':'2.0','id':sequence,'method':method,'params':params}})
                self.assertIsNone(result['error'])
                payload=result['payload'];self.assertNotIn('error',payload,payload)
                return payload['result']
            with patch.object(Interpreter,'__init__',initialize),patch.object(Engine,'__init__',engine_initialize):
                if surface=='catalogs':
                    result=dispatch('editor.hello',{'protocol':EDITOR_PROTOCOL})
                    product=next(c for c in fixture.config.catalogs if c.name=='Номенклатура')
                    result=dispatch('editor.event',{'event':'selectCatalog','catalog':str(product.identity),
                        'baseRevision':result['revision']})
                    result=dispatch('editor.event',{'event':'create','baseRevision':result['revision']})
                    self.assertIsNotNone(fixture.host.owner.editor)
                else:
                    from yadinassi.ui.configuration_app import PROTOCOL as APP_PROTOCOL
                    switched=self.request(server,'demo.select',{'epoch':fixture.host.epoch,'surface':'documents'})
                    self.assertIsNone(switched['error'])
                    dispatch('application.hello',{'protocol':APP_PROTOCOL})
                    opened=dispatch('application.open',{'entry':fixture.host.owner.names['document.receipt.form.card'],'request':'one'})
                    self.assertIsNone(opened['error'])
                    self.assertIn(opened['session'],fixture.host.owner.sessions)
            self.assertTrue(created)
            self.assertTrue(all(tid!=current_thread().ident and mode=='compiled-strict' for tid,_,mode in created),created)
            self.assertTrue(any(name=='_FormInterpreter' for _,name,_ in created))
            self.assertGreater(sum(row.get('emitted_executions',0)+row.get('helper_executions',0)+row.get('inline_blocks',0)+row.get('inline_fragments',0)+row.get('python_translated_blocks',0)+sum(row.get('python_translated_node_kinds',{}).values()) for row in stats),0)
            self.assertEqual(sum(row.get('interpreter_fallbacks',0) for row in stats),0)
            self.assertEqual(sum(row.get('plain_adapter_blocks',0) for row in stats),0)
            self.assertEqual(current_backend(),entry_backend)
        finally:
            if server is not None:
                if thread is not None:server.shutdown()
                server.server_close()
            if thread is not None:thread.join(3)
            fixture.doCleanups()

    def test_late_main_demo_catalog_factories_remain_strict(self):
        self._run_surface('catalogs')

    def test_late_main_demo_document_server_and_client_remain_strict(self):
        self._run_surface('documents')

    def test_source_workspace_server_client_on_new_request_thread(self):
        from test_source_forms import files
        from yadinassi.configuration_source import import_source
        from yadinassi.configuration_source_runtime import SourceApplication
        from yadinassi.ui.source_workspace import SourceWorkspace, SourceWorkspaceHandler
        with execution_backend_policy('compiled-strict'):
            application=SourceApplication(import_source(files()))
            application.start()
            workspace=SourceWorkspace(application)
            server=LocalUIServer(workspace,handler=SourceWorkspaceHandler)
        thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
        created=[];stats=[];original=Interpreter.__init__;original_engine=Engine.__init__
        def initialize(vm,*args,**kwargs):
            original(vm,*args,**kwargs)
            created.append((current_thread().ident,type(vm).__name__,vm.execution_backend))
        def engine_initialize(engine,vm):
            original_engine(engine,vm);stats.append(engine.stats)
        try:
            thread.start()
            with patch.object(Interpreter,'__init__',initialize),patch.object(Engine,'__init__',engine_initialize):
                result=self.request(server,'workspace.open',{'name':'CommonForm.Main'})
            self.assertIsNotNone(workspace.form)
            self.assertGreaterEqual(sum(name=='_SourceFormInterpreter' for _,name,_ in created),2)
            self.assertTrue(all(tid!=current_thread().ident and mode=='compiled-strict' for tid,_,mode in created),created)
            self.assertGreater(sum(row.get('emitted_executions',0)+row.get('helper_executions',0)+row.get('inline_blocks',0)+row.get('inline_fragments',0)+row.get('python_translated_blocks',0)+sum(row.get('python_translated_node_kinds',{}).values()) for row in stats),0)
            self.assertEqual(sum(row.get('interpreter_fallbacks',0) for row in stats),0)
            self.assertEqual(sum(row.get('plain_adapter_blocks',0) for row in stats),0)
        finally:
            server.shutdown();server.server_close();thread.join(3);application.close()

    def test_real_catalog_child_receives_strict_selection_without_environment_policy(self):
        from pathlib import Path
        import tempfile,sys
        from ui_catalog_fixture import repository
        from yadinassi.ui.local_app import RuntimeBridge
        owner,path,unused,ids=repository(self);owner.close()
        with tempfile.TemporaryDirectory() as directory:
            witness=Path(directory)/'witness.jsonl'
            script="""import json,runpy,sys
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine
witness=sys.argv.pop(1)
def record(row):
    with open(witness,'a',encoding='utf-8') as output:output.write(json.dumps(row)+'\\n')
original=Interpreter.__init__
def initialize(vm,*args,**kwargs):
    original(vm,*args,**kwargs)
    record({'backend':vm.execution_backend})
    if vm.execution_backend!='compiled-strict':raise RuntimeError('old child backend')
Interpreter.__init__=initialize
original_block=Engine.run_block
def block(engine,*args,**kwargs):
    result=yield from original_block(engine,*args,**kwargs)
    record({'compiled_block':True})
    return result
Engine.run_block=block
module=sys.argv.pop(1);sys.argv[0]=module
runpy.run_module(module,run_name='__main__')
"""
            original_start=RuntimeBridge._start
            def start(bridge,command,environment):
                self.assertIn('--execution-backend',command)
                self.assertEqual(command[command.index('--execution-backend')+1],'compiled-strict')
                self.assertEqual(command[1],'-m')
                return original_start(bridge,[sys.executable,'-c',script,str(witness),*command[2:]],environment)
            bridge=None
            try:
                with patch.object(RuntimeBridge,'_start',start),execution_backend_policy('compiled-strict'):
                    bridge=RuntimeBridge(str(path))
                hello=bridge.exchange({'jsonrpc':'2.0','id':1,'method':'editor.hello','params':{'protocol':EDITOR_PROTOCOL}})
                self.assertEqual(hello['result']['revision'],0)
                selected=bridge.exchange({'jsonrpc':'2.0','id':2,'method':'editor.event',
                    'params':{'event':'selectCatalog','catalog':ids['category'],'baseRevision':0}})
                created=bridge.exchange({'jsonrpc':'2.0','id':3,'method':'editor.event',
                    'params':{'event':'create','baseRevision':selected['result']['revision']}})
                self.assertIn('result',created)
                rows=[json.loads(line) for line in witness.read_text(encoding='utf-8').splitlines()]
                self.assertTrue(any(row.get('backend')=='compiled-strict' for row in rows))
                self.assertTrue(any(row.get('compiled_block') for row in rows))
                self.assertFalse(any(row.get('backend','compiled-strict')!='compiled-strict' for row in rows))
            finally:
                if bridge is not None:bridge.close()

if __name__=='__main__':unittest.main()
