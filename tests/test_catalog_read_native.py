"""Local batch/lifecycle tests; no target native observations are fabricated."""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'scripts')]
import catalog_read_fixture as fixture
import catalog_read_instrument as instrument
import catalog_read_run as runner
import catalog_read_inputs as inputs
import catalog_read_report as policy
from catalog_read_packet import batch,scalar_wire
from inject_metadata import _module,inject
from protocol import IMAGE
from snapshots import OracleError
NONCE='a'*32


def provenance():
    return dict(commit='b'*40,tree='c'*40,sources=inputs.source_hashes(ROOT),image=IMAGE,
        platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')


def scalar(value):
    if type(value) is str:
        raw=value.encode('utf-16-be');return 'S'+str(len(raw)//2)+':'+raw.hex()
    if type(value) is bool:return 'B'+str(int(value))
    return 'N'+str(value)


def setup_wire(b,state):
    count={'empty':0,'one':1,'several':3,'deleted':3,'reused':4}[state]
    values=[]
    for name in b.setup.names:values.extend((0,count,int(state!='empty'),int(state=='reused'),name,b.setup.record_ids[0]))
    return (scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i}: [ok|{scalar(v)}]\n'.encode() for i,v in enumerate(values,1))).decode().replace('CR-1:', 'CR-01:').replace('CR-2:', 'CR-02:').replace('CR-3:', 'CR-03:').replace('CR-4:', 'CR-04:').replace('CR-5:', 'CR-05:').replace('CR-6:', 'CR-06:').replace('CR-7:', 'CR-07:').replace('CR-8:', 'CR-08:').replace('CR-9:', 'CR-09:')


def error_wire(count=24):
    return (scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,count+1))).decode()


class CatalogBatchTests(unittest.TestCase):
    def test_exact_saved_replay_and_two_identity_sets(self):
        first=fixture.load(1);second=fixture.load(2)
        self.assertNotEqual(first[0].setup,second[0].setup)
        for b,m,files in (first,second):
            self.assertEqual(len(files),15)
            self.assertEqual(len(fixture.BLOCKS),8)
            self.assertEqual(len(batch.STATES),5)
            self.assertNotEqual([r[1] for r in b.rows],sorted(r[1] for r in b.rows))
    def test_closed_selector(self):
        for value in (True,False,0,3,'1',None):
            with self.subTest(value=value),self.assertRaises(OracleError):fixture.load(value)
    def test_wrapped_modules_parse_and_session_batch(self):
        from yadinassi.syntax.parser import parse
        for repeat in (1,2):
            b,_,files=fixture.load(repeat)
            for name in ('ManagedApplicationModule.bsl','NativeOracleServer.bsl'):
                raw=instrument.instrument(_module(name,NONCE,'/tmp/onec-db-oracle/evidence'),name,b,files,nonce=NONCE,evidence='/tmp/onec-db-oracle/evidence')
                text=raw.decode('utf-8-sig');parse(text)
                self.assertEqual(text.count('Функция CBAll()'),1)
                for i,block in enumerate(fixture.BLOCKS):self.assertIn(f'Outputs.Вставить("{block}", B{i}CRRun());',text)
                self.assertNotIn('@@',text)
                self.assertIn('CREmit(Lines, Знач Label',text)
                if name.startswith('Managed'):
                    self.assertNotIn('Ghost.Delete()',text)
                    self.assertLess(text.index('NativeOracleServer.CBAuthorized(Token)'),text.index('Outputs = CBAll()'))
                else:
                    self.assertIn('ПривилегированныйРежим()',text)
                    self.assertIn('NativeПроверитьВсехПользователей();',text)
                    self.assertEqual(text.count('Ghost.Delete()'),4)
                with self.assertRaises(ValueError):instrument.instrument(raw,name,b,files,nonce=NONCE,evidence='/tmp/onec-db-oracle/evidence')
    def test_unavailable_not_observer_success(self):
        b,_,_=fixture.load(1)
        for block in fixture.BLOCKS:
            raw=error_wire(12 if block=='fresh' else 24).encode()
            self.assertEqual(fixture.validate_capture(raw,b,block)['availability'],'unavailable')
            with self.assertRaises(OracleError):fixture.validate_capture(raw.replace(b'action-error',b'observer-error',1),b,block)
    def test_setup_marker_all_states(self):
        b,_,_=fixture.load(1)
        for state in fixture.STATES:
            operation='catalog_read_setup_'+state
            value=dict(schema=1,nonce=NONCE,token='b'*32,operation=operation,status='ok',outputs={'setup':setup_wire(b,state)})
            raw=json.dumps(value).encode()
            self.assertEqual(runner.validate_marker(raw,nonce=NONCE,token='b'*32,operation=operation,b=b),value['outputs'])
            for field,bad in [('schema',True),('nonce','c'*32),('token','c'*32),('status','error'),('operation','catalog_read_setup_empty' if state!='empty' else 'catalog_read_setup_one')]:
                changed=dict(value);changed[field]=bad
                with self.subTest(state=state,field=field),self.assertRaises(OracleError):runner.validate_marker(json.dumps(changed).encode(),nonce=NONCE,token='b'*32,operation=operation,b=b)
    def test_marker_block_set_and_caps(self):
        b,_,_=fixture.load(1)
        value=dict(schema=1,nonce=NONCE,token='b'*32,operation='catalog_read_client',status='ok',outputs={block:error_wire(12 if block=='fresh' else 24) for block in fixture.BLOCKS})
        runner.validate_marker(json.dumps(value).encode(),nonce=NONCE,token='b'*32,operation='catalog_read_client',b=b)
        for outputs in ({},dict(value['outputs'],extra='x'),dict(value['outputs'],cursor='x'*8193)):
            with self.assertRaises(OracleError):runner.validate_marker(json.dumps(dict(value,outputs=outputs)).encode(),nonce=NONCE,token='b'*32,operation='catalog_read_client',b=b)
    def test_install_complete_redump_and_existing_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            raw=(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml').read_text()
            # The synthetic fixture's warning comment is outside the packet's
            # closed comment-free config profile; no production parser is widened.
            import re
            (source/'Configuration.xml').write_text(re.sub(r'<!--.*?-->','',raw))
            (source/'ConfigDumpInfo.xml').write_text('fixture')
            v1=root/'v1';inject(source,v1,nonce=NONCE,evidence=Path('/tmp/onec-db-oracle/evidence'))
            backend=object.__new__(runner.Native);backend.v1=v1;backend.root=root;backend.nonce=NONCE;backend.evidence=Path('/tmp/onec-db-oracle/evidence')
            calls=[]
            def command(db,args,label):
                calls.append(label)
                if label=='redump':shutil.copytree(root/'catalog-source-1',Path(args[1]))
            backend.batch=command
            b,helpers=backend.install(root/'db',1)
            self.assertEqual(calls,['seed-import','seed-apply','redump'])
            self.assertEqual(len(helpers),2)
            rights=(root/'catalog-source-1/Roles/NativeOracleCatalogCRUD/Ext/Rights.xml').read_text()
            for name in b.setup.names:self.assertIn('Catalog.'+name,rights)
            self.assertEqual((root/'catalog-source-1/Roles/NativeOracleSetupAdministrator/Ext/Rights.xml').read_bytes(),(v1/'Roles/NativeOracleSetupAdministrator/Ext/Rights.xml').read_bytes())


class CatalogStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.staged=Path(cls.temp.name)/'staged';cls.identity=provenance()
        inputs.stage_inputs(ROOT,cls.staged,NONCE,cls.identity)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_actual_bundle_closure(self):
        self.assertEqual(inputs.verify_inputs(self.staged,NONCE),self.identity)
        self.assertLess(len(json.dumps(self.identity)),32768)
        self.assertIn('catalog_read_run.py',inputs.SOURCE_FILES.values())
        self.assertNotIn('catalog_read_run.py',inputs.runtime.SOURCE_FILES.values())
    def test_isolated_child_import_and_public_runtime(self):
        code='''import sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import catalog_read_inputs as inputs
inputs.activate_runtime(root)
import catalog_read_run,catalog_read_readback,catalog_read_report
from yadinassi import Interpreter
from catalog_read_fixture import load
assert load(1)[0].setup.names[0].startswith('C')
print('closed')
'''
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.staged)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'closed')
    def test_failed_report_and_no_false_acceptance(self):
        value=policy.empty_report(NONCE,self.identity)
        self.assertEqual(policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=self.identity),value)
        for mutation in (dict(value,schema=True),dict(value,lane='other'),dict(value,lifecycle=dict(value['lifecycle'],status='ok')),dict(value,lifecycle=dict(value['lifecycle'],accepted=True))):
            with self.assertRaises(OracleError):policy.validate_report(policy.encode_report(mutation),nonce=NONCE,provenance=self.identity)
    def test_host_confinement_and_no_caller_database(self):
        import native_1c_catalog_read_oracle as host
        command=host.container_command(self.staged,'onec-db-oracle-'+'f'*32,NONCE)
        for option in ('--network','--read-only','--cap-drop','--security-opt','--log-driver','--tmpfs','-I','-S'):self.assertIn(option,command)
        self.assertIn('/oracle/catalog_read_run.py',command)
        self.assertNotIn('/oracle/metadata_catalog_run.py',command)

if __name__=='__main__':unittest.main()

class CatalogAcquisitionTests(unittest.TestCase):
    def test_thirty_sessions_fresh_clones_same_postimage_and_cleanup(self):
        class Backend:
            def __init__(self,root):
                self.artifacts=root;self.nonce=NONCE;self.launches=[];self.clones=[];self.removed=[]
            def begin_stage(self,stage):self.stage=stage
            def seed(self):return self.artifacts/'seed'
            def freeze(self,database,name):return dict(bytes=123,sha256='a'*64)
            @contextmanager
            def temporary_clone(self,origin,name):
                self.clones.append((origin,name));yield self.artifacts/name
                self.removed.append(name)
            def install(self,database,repeat):return fixture.load(repeat)[0],{}
            def physical_summary(self,path):return dict(bytes=123,sha256='a'*64)
            def launch(self,database,*,operation,b):
                self.launches.append((database.name,operation))
                return dict(token=f'{len(self.launches):032x}',marker_sha256='b'*64,outputs={})
            def command_context(self,operation):return mock.MagicMock()
            def budgets(self,*a):pass
            def quiescent(self):return True
            def remaining(self):pass
            def remove(self,path):self.removed.append(path.name)
            def discard(self,*names):self.removed.extend(names)
        with tempfile.TemporaryDirectory() as tmp:
            backend=Backend(Path(tmp))
            seen=[]
            def inspect(directory,*,read_catalog,**kw):
                seen.append(directory.name)
                return dict(bytes=123,sha256='a'*64),read_catalog(lambda *_:b'',123,limits=None)
            with mock.patch.object(runner,'freeze_database',return_value=dict(bytes=123,sha256='a'*64)),mock.patch.object(runner,'inspect_frozen_catalog',side_effect=inspect):
                installations,captures=runner.acquire(backend,readback=lambda *a:{'fixture':'not-native'})
            self.assertEqual(len(installations),2);self.assertEqual(len(captures),20)
            self.assertEqual(len(backend.launches),30)
            self.assertEqual(sum(op.startswith('catalog_read_setup_') for _,op in backend.launches),10)
            self.assertEqual(sum(origin.startswith('catalog_applied_') for origin,_ in backend.clones),10)
            self.assertEqual(sum(origin=='catalog_state' for origin,_ in backend.clones),20)
            self.assertEqual(seen,['catalog_postimage']*20)
            self.assertEqual(backend.removed.count('catalog_postimage'),20)
            self.assertEqual(backend.removed.count('catalog_state'),10)
            self.assertIsNone(backend.catalog_attempt)

    def test_public_runtime_executes_all_saved_blocks_with_synthetic_context(self):
        from types import SimpleNamespace as NS
        from decimal import Decimal
        from uuid import UUID
        from yadinassi.storage.catalog_metadata import CatalogMetadataIdentity
        import catalog_read_readback as readback
        b,_,_=fixture.load(1)
        context=mock.Mock()
        context.catalog_metadata.return_value=tuple(CatalogMetadataIdentity(u,n) for n,u in zip(b.setup.names,b.setup.metadata_ids))
        def rows(name):
            i=b.setup.names.index(name)
            values={'_CODE':'30','_DESCRIPTION':'Alpha','_MARKED':False,'_FLD7':'first','_FLD8':Decimal(11)}
            return NS(identity=NS(name=name,metadata_uuid=b.setup.metadata_ids[i]),
                binding=NS(attributes=(NS(name='Payload',physical_name='_FLD7'),NS(name='Amount',physical_name='_FLD8'))),
                rows=(NS(reference_uuid=UUID(b.setup.record_ids[0]),physical_record=NS(fields=tuple(NS(declaration=NS(name=n),value=v) for n,v in values.items()))),))
        context.catalog_rows.side_effect=rows
        with mock.patch('yadinassi.database_context.FileDBContext',return_value=context):actual=readback.execute(Path('/synthetic-never-opened'),b)
        self.assertEqual(set(actual),set(fixture.BLOCKS))
        for block,output in actual.items():
            assessment=fixture.validate_capture(output.encode(),b,block)
            self.assertEqual(assessment['availability'],'available')
        first=readback.compare(actual['fresh'].encode(),actual['fresh'].encode(),b,'fresh')
        self.assertTrue(first['matched']);self.assertEqual(first['mode'],'fresh_relations')
        from yadinassi import Interpreter
        _,_,files=fixture.load(1)
        for i,block in enumerate(fixture.BLOCKS):
            lines=[];runtime=Interpreter(lines.append,database_context=context)
            try:runtime.execute(instrument.wrap(files[block+'.bsl'],'B'+str(i))+f'Message(B{i}CRRun());')
            finally:runtime.close()
            self.assertEqual(len(lines),1)
            comparison=readback.compare(lines[0].encode(),actual[block].encode(),b,block)
            self.assertTrue(comparison['matched'],block)


class CatalogReportTests(unittest.TestCase):
    def test_complete_twenty_context_measurement_report_keeps_mismatch(self):
        from test_catalog_read_physical import PhysicalSlotMeasurementTests
        from catalog_read_readback import compare
        identity=provenance();value=policy.empty_report(NONCE,dict(identity,actual_version='8.3.27.1508'))
        physical=PhysicalSlotMeasurementTests().envelope()[1]
        serial=0
        for repeat in (1,2):
            b,_,files=fixture.load(repeat)
            helpers={name:hashlib.sha256(instrument.instrument(_module(name,NONCE,'/tmp/onec-db-oracle/evidence'),name,b,files,nonce=NONCE,evidence='/tmp/onec-db-oracle/evidence')).hexdigest() for name in ('NativeOracleServer.bsl','ManagedApplicationModule.bsl')}
            value['installations'].append(dict(repeat=repeat,helpers=helpers,applied=dict(bytes=123,sha256='c'*64)))
            raw_physical=copy.deepcopy(physical)
            for item,name,uid in zip(raw_physical['catalogs'],b.setup.names,b.setup.metadata_ids):item.update(name=name,metadata_uuid=uid)
            outputs={block:error_wire(12 if block=='fresh' else 24) for block in fixture.BLOCKS}
            comparison={block:compare(raw.encode(),raw.encode(),b,block) for block,raw in outputs.items()}
            for state in fixture.STATES:
                serial+=1;setup=dict(token=f'{serial:032x}',marker_sha256='b'*64,outputs={'setup':setup_wire(b,state)},assessment={'setup':'query_witnesses_validated'})
                for context in ('client','server'):
                    serial+=1
                    value['states'].append(dict(repeat=repeat,state=state,context=context,setup=setup,
                        origin=dict(bytes=123,sha256='d'*64),postimage=dict(bytes=123,sha256='e'*64),
                        native=dict(token=f'{serial:032x}',marker_sha256='f'*64,outputs=outputs,assessment={block:fixture.validate_capture(raw.encode(),b,block) for block,raw in outputs.items()}),
                        offline=dict(physical=raw_physical,outputs=outputs,comparison=comparison)))
        value['lifecycle'].update(status='ok',failure_kind='none')
        value['lifecycle']['cleanup'].update(native_processes_stopped=True,raw_files_removed=True)
        raw=policy.encode_report(value)
        self.assertLess(len(raw),policy.MAX_REPORT_BYTES)
        self.assertEqual(policy.validate_report(raw,nonce=NONCE,provenance=identity),value)
        self.assertFalse(value['states'][0]['offline']['comparison']['cursor']['matched'])
        for change in ('origin','token','witness','helpers','comparison','version','boolrepeat'):
            bad=copy.deepcopy(value)
            if change=='origin':bad['states'][1]['origin']['sha256']='0'*64
            elif change=='token':bad['states'][1]['native']['token']=bad['states'][0]['native']['token']
            elif change=='witness':bad['states'][0]['setup']['outputs']['setup']=setup_wire(fixture.load(1)[0],'one')
            elif change=='helpers':bad['installations'][0]['helpers']['NativeOracleServer.bsl']='0'*64
            elif change=='comparison':bad['states'][0]['offline']['comparison']['cursor']['matched']=True
            elif change=='version':bad['provenance']['actual_version']=None
            elif change=='boolrepeat':bad['states'][0]['repeat']=True
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):policy.validate_report(policy.encode_report(bad),nonce=NONCE,provenance=identity)
        value['lifecycle']['cleanup'].update(container_removed=True,private_staging_removed=True)
        value['lifecycle']['accepted']=True
        policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity,final=True)
