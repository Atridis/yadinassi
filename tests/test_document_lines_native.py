"""Local document-lines acquisition contracts; no invented native/physical answers."""
import copy
import hashlib
import os
import inspect
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import contextmanager, nullcontext
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'scripts')]
import document_lines_fixture as fixture
import document_lines_instrument as instrument
import document_lines_inputs as inputs
import document_lines_report as policy
import document_lines_run as runner
import document_lines_fixture as linked
from linked_card_packet.base import scalar_wire
from inject_metadata import _module,inject
from snapshots import OracleError
from protocol import IMAGE
from test_metadata_catalog_runtime_inputs import static_bundle_bytes
from test_catalog_read_native import container_metadata_paths, static_container_bytes, WindowsContainerOS
NONCE='a'*32


def audit(token='f'*32):
    return dict(token=token,actual_version='8.3.27.1508',user='NativeOracleSetup',role_verified=True,users_verified=True,nonprivileged=True)


def encode(values):
    def scalar(v):
        if v is None:return 'U'
        if type(v) is bool:return 'B'+str(int(v))
        if type(v) is int:return 'N'+str(v)
        b=v.encode('utf-16-be');return 'S'+str(len(b)//2)+':'+b.hex()
    return (scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [ok|{scalar(v)}]\n'.encode() for i,v in enumerate(values,1))).decode()


def wire(s,state):
    p=fixture.profile(s)['base'];zero='00000000-0000-0000-0000-000000000000'
    if state=='rewritten':return encode([p['document_name'],p['catalog_name'],0,1,3]+[True]*19)
    values=[p['document_name'],p['catalog_name'],3,2]
    for number,target in [('20',s.base.record_ids[1]),('30',s.base.record_ids[0]),('10',zero)]:
        values += [True,number,True,number=='30',target]
    return encode(values+[False,True,True,True,True])


def witness_wire(s,state):
    from document_lines_packet import lines_packet as packet
    p=fixture.profile(s);values=[p['base']['document_name'],p['base']['catalog_name']]
    for owner in ('10','20'):
        for i,(target,quantity,price,amount,note) in enumerate(packet.specs(state,owner),1):
            values += [True,owner,i,amount,{'present':s.base.record_ids[0],'absent':s.base.record_ids[1],'second':p['ids']['product2']}[target]]
    return encode(values+[False,0])


def _windows_source_fixture():
    return os.name == 'nt'


@contextmanager
def source_fixture_reader(*, windows=None):
    # Static repository/dependency fixtures are not Linux descriptor-race proof.
    # One scoped boundary covers source hashes, staging and all report validators;
    # hashes, path/link guards, byte caps and POSIX production reads stay intact.
    if windows is None:windows=_windows_source_fixture()
    scope=mock.patch.object(inputs.runtime,'_read',new=static_bundle_bytes) if windows else nullcontext()
    with scope:yield


class DocumentLinesSourceFixtureCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        scope=source_fixture_reader();scope.__enter__()
        self.addCleanup(scope.__exit__,None,None,None)


class DocumentLinesFixtureTests(DocumentLinesSourceFixtureCase):
    def test_modules_parse_and_all_unavailable_globals_are_dynamic(self):
        from yadinassi.syntax.parser import parse
        for repeat in (1,2):
            s,m,files=fixture.load(repeat)
            for name in ('NativeOracleServer.bsl','ManagedApplicationModule.bsl'):
                text=instrument.instrument(_module(name,NONCE,'/tmp/onec-db-oracle/evidence'),name,s,files,nonce=NONCE,evidence=PurePosixPath('/tmp/onec-db-oracle/evidence')).decode('utf-8-sig')
                parse(text);self.assertNotIn('@@',text)
                if name=='NativeOracleServer.bsl':self.assertIn('document_lines_setup_initial',text)
                if name=='ManagedApplicationModule.bsl':
                    self.assertNotIn('P.Write()',text)
                    # English action errors are accumulated, never stray stdout.
                    self.assertNotIn('Message(',text)
                else:
                    self.assertIn('Реквизиты.Количество() <> 5',text)
                    self.assertIn('Реквизиты.Количество() <> 0',text)
            for i,block in enumerate(fixture.BLOCKS):
                text=instrument.wrap(files[block+'.bsl'],'B'+str(i))
                # Strip quoted literals; no static Catalogs symbol survives.
                import re
                self.assertNotRegex(re.sub(r'"(?:[^"]|"")*"','""',text),r'\b(?:Catalogs|Documents)\b')
    def test_unavailable_capture_cannot_be_false_parity(self):
        from document_lines_readback import compare
        s,_,_=fixture.load(1)
        raw=scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,25))
        for block in fixture.BLOCKS:
            self.assertEqual(fixture.validate_capture(raw,s,block),{'availability':'unavailable'})
            self.assertFalse(compare(raw,raw,s,block)['matched'])

    def test_unadmitted_database_still_retains_all_observer_blocks(self):
        from document_lines_readback import execute
        with tempfile.TemporaryDirectory() as tmp:
            for repeat in (1,2):
                s,_,_=fixture.load(repeat)
                outputs=execute(Path(tmp).resolve(),s)
                self.assertEqual(set(outputs),set(fixture.BLOCKS))
                for block,raw in outputs.items():
                    self.assertEqual(fixture.validate_capture(raw.encode('ascii'),s,block),{'availability':'unavailable'})

    def test_setup_marker_24_witnesses_and_closed_states(self):
        s,_,_=fixture.load(1)
        value=dict(schema=1,nonce=NONCE,token='b'*32,operation='document_lines_setup_initial',status='ok',outputs={'setup':wire(s,'initial'),'witness':witness_wire(s,'initial')})
        self.assertEqual(runner.validate_marker(json.dumps(value).encode(),nonce=NONCE,token='b'*32,operation=value['operation'],b=s),value['outputs'])
        for outputs in ({'setup':wire(s,'initial')},
                        {'setup':wire(s,'initial'),'witness':witness_wire(s,'rewritten')}):
            bad=dict(value,outputs=outputs)
            with self.assertRaises((OracleError,ValueError)):
                runner.validate_marker(json.dumps(bad).encode(),nonce=NONCE,token='b'*32,operation=value['operation'],b=s)
        for field,bad in [('schema',True),('nonce','c'*32),('token','c'*32),('status','error')]:
            with self.assertRaises(OracleError):runner.validate_marker(json.dumps(dict(value,**{field:bad})).encode(),nonce=NONCE,token='b'*32,operation=value['operation'],b=s)
    def test_full_redump_existing_rights_and_actual_mapping(self):
        with container_metadata_paths():
            self._full_redump_existing_rights_and_actual_mapping()

    def test_forced_windows_complete_redump_contract(self):
        import inject_metadata
        from pathlib import PureWindowsPath
        with mock.patch.object(inject_metadata,'Path',PureWindowsPath),mock.patch.object(runner.lifecycle,'os',WindowsContainerOS()):
            with self.assertRaisesRegex(inject_metadata.DraftError,'Unexpected metadata directory'):
                self._full_redump_existing_rights_and_actual_mapping()
            with mock.patch.object(inject_metadata,'Path',PurePosixPath):
                with self.assertRaisesRegex(AttributeError,'O_NOFOLLOW'):
                    self._full_redump_existing_rights_and_actual_mapping()
            with container_metadata_paths(static_reader=True):
                self._full_redump_existing_rights_and_actual_mapping()
            self.assertIs(inject_metadata.Path,PureWindowsPath)

    def _full_redump_existing_rights_and_actual_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();source=root/'source';source.mkdir()
            import re
            raw=(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml').read_text(encoding='utf-8')
            (source/'Configuration.xml').write_text(re.sub(r'<!--.*?-->','',raw),encoding='utf-8');(source/'ConfigDumpInfo.xml').write_text('fixture')
            evidence=PurePosixPath('/tmp/onec-db-oracle/evidence');v1=root/'v1';inject(source,v1,nonce=NONCE,evidence=evidence)
            backend=object.__new__(runner.Native);backend.v1=v1;backend.root=root;backend.nonce=NONCE;backend.evidence=evidence
            calls=[]
            def command(db,args,label):
                calls.append(label)
                if label=='redump':shutil.copytree(root/'catalog-source-1',Path(args[1]))
            backend.batch=command;backend.enterprise=lambda database,operation:audit()
            s,helpers,checked,mapping=backend.install(root/'db',1)
            self.assertEqual(calls,['seed-import','seed-apply','redump']);self.assertEqual(checked,audit());self.assertEqual(len(mapping['objects']),2)
            self.assertEqual((root/'catalog-source-1/Roles/NativeOracleSetupAdministrator/Ext/Rights.xml').read_bytes(),(v1/'Roles/NativeOracleSetupAdministrator/Ext/Rights.xml').read_bytes())


class DocumentLinesStagingTests(DocumentLinesSourceFixtureCase):
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.staged=Path(self.temp.name).resolve()/'stage'
        self.identity=dict(commit='c'*40,tree='d'*40,sources=inputs.source_hashes(ROOT),image=IMAGE,platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')
        inputs.stage_inputs(ROOT,self.staged,NONCE,self.identity)
    def test_closed_inventory_and_empty_report(self):
        self.assertEqual(inputs.verify_inputs(self.staged,NONCE),self.identity)
        value=policy.empty_report(NONCE,self.identity)
        self.assertEqual(policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=self.identity),value)
        self.assertLess(len(json.dumps(self.identity)),65536)
    def test_cold_staged_imports(self):
        code='''import sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import document_lines_inputs as inputs
inputs.activate_runtime(root)
import document_lines_run,document_lines_report,document_lines_readback,document_lines_physical
def refuse():
    from yadinassi.storage.filedb_catalog import UnsupportedLayout
    raise UnsupportedLayout('descriptor_shape')
try:
    document_lines_readback._attempt('physical-observe',refuse)
except document_lines_readback.OfflineFailure as error:
    assert error.diagnostic==dict(stage='physical-observe',category='catalog_error',code='descriptor_shape',location=None)
else:raise AssertionError('cold failure diagnostic missing')
from document_lines_fixture import load
assert load(1)[1]['profile']['base']['attributes']==5
# Cold complete installer exercise: no unit-test ambient imports or cached module state.
import shutil,re
from pathlib import PurePosixPath
import inject_metadata
inject_metadata.Path=PurePosixPath # Linux-container lexical paths only; native roots below.
source=root.parent/'cold-source';source.mkdir()
raw=Path(sys.argv[2]).read_text(encoding='utf-8')
(source/'Configuration.xml').write_text(re.sub(r'<!--.*?-->','',raw),encoding='utf-8')
(source/'ConfigDumpInfo.xml').write_text('fixture')
v1=root.parent/'cold-v1';evidence=PurePosixPath('/tmp/onec-db-oracle/evidence')
inject_metadata.inject(source,v1,nonce='a'*32,evidence=evidence)
backend=object.__new__(document_lines_run.Native)
backend.root=root.parent;backend.v1=v1;backend.nonce='a'*32;backend.evidence=evidence
calls=[]
def batch(database,args,label):
    calls.append(label)
    if label=='redump':shutil.copytree(root.parent/'catalog-source-1',Path(args[1]))
backend.batch=batch
backend.enterprise=lambda *a:dict(token='f'*32,actual_version='8.3.27.1508',user='NativeOracleSetup',role_verified=True,users_verified=True,nonprivileged=True)
assert len(backend.install(root.parent/'cold-db',1)[3]['objects'])==2
assert calls==['seed-import','seed-apply','redump']
assert backend.catalog_install_failure is None
print('closed-linked')
'''
        # Same Windows static fixture bridge used by reviewed staging tests.
        if _windows_source_fixture():
            code=code.replace('import document_lines_inputs as inputs','import document_lines_inputs as inputs\n'+inspect.getsource(static_bundle_bytes)+'\ninputs.runtime._read=static_bundle_bytes')
        # Exercise the complete cold installer under an explicit missing-Unix-
        # flags contract too; the ordinary POSIX pass keeps its strict reader.
        bridge='import os\nfrom snapshots import OracleError\n'+inspect.getsource(static_bundle_bytes)+"\n"+inspect.getsource(static_container_bytes)+"\n"+inspect.getsource(WindowsContainerOS)+"\n"
        code=code.replace("source=root.parent/'cold-source';source.mkdir()",bridge+"if os.name=='nt' or sys.argv[3]=='windows-contract':\n    document_lines_run.lifecycle.os=WindowsContainerOS()\n    document_lines_run.lifecycle.regular_bytes=static_container_bytes\nsource=root.parent/('cold-source-'+sys.argv[3]);source.mkdir()")
        code=code.replace("v1=root.parent/'cold-v1'","v1=root.parent/('cold-v1-'+sys.argv[3])")
        for mode in ('native-platform','windows-contract'):
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.staged),str(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml'),mode],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'closed-linked')
            # Separate owned native-source clone namespace for the next child.
            shutil.rmtree(self.staged.parent/'catalog-source-1')



class DocumentLinesAcquisitionTests(DocumentLinesSourceFixtureCase):
    def test_twelve_sessions_fresh_clones_same_postimage_and_cleanup(self):
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
            def install(self,database,repeat):
                s,m,files=fixture.load(repeat)
                return s,{},audit(f'{repeat:032x}'),fixture.actual_mapping(s,m['profile'],{n:v for n,v in files.items() if n.endswith('.xml')})
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
            self.assertEqual(len(installations),2);self.assertEqual(len(captures),8)
            self.assertEqual(len(backend.launches),12)
            self.assertEqual(sum(op.startswith('document_lines_setup_') for _,op in backend.launches),4)
            self.assertEqual(sum(origin.startswith('catalog_applied_') for origin,_ in backend.clones),2
            )
            self.assertEqual(sum(origin=='lines_initial' and name=='catalog_setup' for origin,name in backend.clones),2)
            self.assertEqual(sum(origin in ('lines_initial','lines_rewritten') and name=='catalog_observe' for origin,name in backend.clones),8)
            self.assertEqual(seen,['catalog_postimage']*8)
            self.assertEqual(backend.removed.count('catalog_postimage'),8)
            self.assertEqual(sum(backend.removed.count(n) for n in ('lines_initial','lines_rewritten')),4)
            self.assertIsNone(backend.catalog_attempt)
            # A known offline refusal must not erase an authenticated native
            # capture, but its postimage is retained only after final inspection.
            from document_lines_readback import OfflineFailure
            diagnostic = dict(stage='physical-observe', category='value_error', code=None, location=None)
            def refused(*args):
                raise OfflineFailure(diagnostic)
            backend=Backend(Path(tmp));seen.clear()
            with mock.patch.object(runner,'freeze_database',return_value=dict(bytes=123,sha256='a'*64)),mock.patch.object(runner,'inspect_frozen_catalog',side_effect=inspect):
                with self.assertRaises(OracleError) as raised:
                    runner.acquire(backend,readback=refused)
            self.assertEqual(raised.exception.kind,'metadata_rejected')
            self.assertEqual(len(backend.catalog_captures),1)
            retained=backend.catalog_captures[0]
            self.assertEqual(retained['offline'],{'failure':diagnostic})
            self.assertEqual(retained['postimage'],dict(bytes=123,sha256='a'*64))
            self.assertEqual(retained['native']['token'],'00000000000000000000000000000002')
            self.assertEqual(backend.catalog_attempt,dict(repeat=1,state='initial',context='client',phase='offline'))
            self.assertIn('catalog_postimage',backend.removed)
            backend=Backend(Path(tmp))
            def changed(directory,*,read_catalog,**kw):
                read_catalog(lambda *_:b'',123,limits=None)
                raise OracleError('snapshot_changed')
            with mock.patch.object(runner,'freeze_database',return_value=dict(bytes=123,sha256='a'*64)),mock.patch.object(runner,'inspect_frozen_catalog',side_effect=changed):
                with self.assertRaises(OracleError) as raised:
                    runner.acquire(backend,readback=refused)
            self.assertEqual(raised.exception.kind,'snapshot_changed')
            self.assertEqual(backend.catalog_captures,[])


class DocumentLinesHostTests(DocumentLinesSourceFixtureCase):
    def test_new_test_modules_import_cold_with_tests_path_only(self):
        modules=('test_document_lines_packet','test_document_lines_fixture',
                 'test_document_lines_physical','test_document_lines_native','test_document_lines_workflow')
        code="import sys,importlib;sys.path.insert(0,sys.argv[1]);importlib.import_module(sys.argv[2]);\nif sys.argv[2].endswith('_native'): importlib.import_module('yadinassi')"
        with tempfile.TemporaryDirectory() as directory:
            for module in modules:
                result=subprocess.run([sys.executable,'-I','-B','-c',code,str(ROOT/'tests'),module],
                    cwd=directory,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,(module,result.stderr))

    def test_specialization_restored_even_on_failure(self):
        import native_1c_document_lines_oracle as entry
        h=entry.host
        previous=(h.inputs,h.policy,h.OUTPUT,h.container_command)
        def run(argv):
            self.assertIs(h.inputs,inputs);self.assertIs(h.policy,policy)
            self.assertEqual(h.OUTPUT,Path('native-document-lines/document-lines.json'))
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(inputs,'verify_inputs'):
                command=h.container_command(Path(tmp).resolve(),'onec-db-oracle-'+NONCE,NONCE)
            self.assertIn('/oracle/document_lines_run.py',command)
            self.assertNotIn('/oracle/catalog_read_run.py',command)
            self.assertIn('--network',command);self.assertIn('none',command)
            raise RuntimeError('synthetic host failure')
        with mock.patch.object(h,'main',side_effect=run),self.assertRaisesRegex(RuntimeError,'synthetic host'):
            entry.main(['--run'])
        self.assertEqual((h.inputs,h.policy,h.OUTPUT,h.container_command),previous)

    def test_cold_actual_entrypoint_without_ambient_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            code="import runpy,sys; m=runpy.run_path(sys.argv[1],run_name='not_main'); assert callable(m['main'])"
            # Real script execution supplies its scripts directory; -I run_path does not.
            code="import sys;sys.path.insert(0,sys.argv[2]);"+code
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT/'scripts/native_1c_document_lines_oracle.py'),str(ROOT/'scripts')],cwd=tmp,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

class DocumentLinesReportTests(DocumentLinesSourceFixtureCase):
    def test_eight_context_report_keeps_unavailable_and_raw_unresolved(self):
        from test_document_lines_physical import image
        import document_lines_physical
        from document_lines_readback import compare
        identity=dict(commit='c'*40,tree='d'*40,sources=inputs.source_hashes(ROOT),image=IMAGE,platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')
        value=policy.empty_report(NONCE,dict(identity,actual_version='8.3.27.1508'))
        serial=0
        for repeat in (1,2):
            s,m,files=fixture.load(repeat)
            mapping=fixture.actual_mapping(s,m['profile'],{n:v for n,v in files.items() if n.endswith('.xml')})
            helpers={name:hashlib.sha256(instrument.instrument(_module(name,NONCE,'/tmp/onec-db-oracle/evidence'),name,s,files,nonce=NONCE,evidence='/tmp/onec-db-oracle/evidence')).hexdigest() for name in ('NativeOracleServer.bsl','ManagedApplicationModule.bsl')}
            value['installations'].append(dict(repeat=repeat,helpers=helpers,mapping=mapping,applied=dict(bytes=123,sha256='c'*64),audit=audit(f'{100+repeat:032x}')))
            source=image(m['profile']);physical=document_lines_physical.observe(source.read_at,source.size,m['profile'],mapping)
            raw=(scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,25))).decode()
            outputs={block:raw for block in fixture.BLOCKS}
            comparison={block:compare(raw.encode(),raw.encode(),s,block) for block in fixture.BLOCKS}
            for state in fixture.STATES:
                serial+=1;setup=dict(token=f'{serial:032x}',marker_sha256='b'*64,outputs={'setup':wire(s,state),'witness':witness_wire(s,state)},assessment={'setup':'query_witnesses_validated','witness':'query_witnesses_validated'})
                for context in ('client','server'):
                    serial+=1
                    value['states'].append(dict(repeat=repeat,state=state,context=context,setup=setup,setup_origin=dict(bytes=123,sha256=('c' if state=='initial' else 'd')*64),origin=dict(bytes=123,sha256='d'*64),postimage=dict(bytes=123,sha256='e'*64),native=dict(token=f'{serial:032x}',marker_sha256='f'*64,outputs=outputs,assessment={block:fixture.validate_capture(raw.encode(),s,block) for block in fixture.BLOCKS}),offline=dict(physical=physical,outputs=outputs,comparison=comparison)))
        value['lifecycle'].update(status='ok',failure_kind='none')
        value['lifecycle']['cleanup'].update(native_processes_stopped=True,raw_files_removed=True)
        self.assertEqual(policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity),value)
        self.assertFalse(value['states'][0]['offline']['comparison']['rows']['matched'])
        failed=copy.deepcopy(value);failed['states']=failed['states'][:1];failed['installations']=failed['installations'][:1]
        failed['lifecycle'].update(status='failed',failure_kind='metadata_rejected')
        failed['failure_context']=dict(repeat=1,state='initial',context='client',phase='offline')
        failed['states'][0]['offline']={'failure':dict(stage='physical-observe',category='value_error',code=None,location=None)}
        self.assertEqual(policy.validate_report(policy.encode_report(failed),nonce=NONCE,provenance=identity),failed)
        for mutation in ('success','raw_error','wrong_state','not_last'):
            bad=copy.deepcopy(failed)
            if mutation=='success':bad['lifecycle'].update(status='ok',failure_kind='none')
            elif mutation=='raw_error':bad['states'][0]['offline']['failure']['message']='private source text'
            elif mutation=='wrong_state':bad['failure_context']['context']='server'
            else:bad['states'].append(copy.deepcopy(value['states'][1]))
            with self.subTest(offline_failure=mutation),self.assertRaises((OracleError,ValueError)):
                policy.validate_report(policy.encode_report(bad),nonce=NONCE,provenance=identity)
        for change in ('mapping','origin','setup_origin','token','comparison','raw'):
            bad=copy.deepcopy(value)
            if change=='mapping':bad['installations'][0]['mapping']['objects'][0]['ref_type_uuid']=bad['installations'][0]['mapping']['objects'][0]['metadata_uuid']
            elif change=='origin':bad['states'][1]['origin']['sha256']='0'*64
            elif change=='setup_origin':bad['states'][2]['setup_origin']['sha256']='0'*64
            elif change=='token':bad['states'][1]['native']['token']=bad['states'][0]['native']['token']
            elif change=='comparison':bad['states'][0]['offline']['comparison']['rows']['matched']=True
            else:bad['states'][0]['offline']['physical']['objects'][0]['physical']['raw_hex']='00'
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):
                policy.validate_report(policy.encode_report(bad),nonce=NONCE,provenance=identity)

class DocumentLinesInstallDiagnosticsTests(DocumentLinesSourceFixtureCase):
    def test_owned_exact_redump_capture_does_not_admit_defaults_or_foreign_identity(self):
        import document_lines_diagnostics as d
        _,_,files=fixture.load(1);saved={n:v for n,v in files.items() if n.endswith('.xml')}
        name=next(n for n in saved if n.startswith('Documents/'))
        actual=dict(saved);actual[name]=saved[name].replace(b'<StandardAttributes>',b'<StandardAttributes><Synthetic/>',1)
        with self.assertRaises(ValueError):fixture.verify_redump(fixture.load(1)[0],fixture.load(1)[1]['profile'],saved,actual)
        value=d.install_failure('fragments',ValueError('document-redump-profile'),saved,actual)
        row=next(x for x in value['objects'] if x['owned_xml']['identity']['kind']=='Document')
        self.assertEqual(bytes.fromhex(row['owned_xml']['xml_hex']),actual[name])
        self.assertEqual(row['owned_xml']['sha256'],hashlib.sha256(actual[name]).hexdigest())
        for needle,replacement in ((b'<Name>D',b'<Name>E'),(b'<Document uuid="',b'<Document uuid="0')):
            other=dict(actual);other[name]=actual[name].replace(needle,replacement,1)
            rejected=d.install_failure('fragments',ValueError('document-redump-profile'),saved,other)
            self.assertIsNone(rejected['objects'][list(saved).index(name)]['owned_xml'])
        bad=copy.deepcopy(value);bad['objects'][0]['owned_xml']['tags']+=1
        with self.assertRaises(OracleError):d.validate_install_failure(bad,saved)
        self.assertEqual(d.install_failure('prepare',RuntimeError('private exception'),{},{}),dict(stage='prepare',category='unexpected',objects=[]))

    def test_install_exception_stays_fixed_and_report_bound(self):
        backend=object.__new__(runner.Native)
        def fail(*args):raise ModuleNotFoundError('private path')
        backend._install=fail
        with self.assertRaises(ModuleNotFoundError):backend.install(Path('/owned'),1)
        self.assertEqual(backend.catalog_install_failure,dict(stage='prepare',category='import-error',objects=[]))
        identity=dict(commit='c'*40,tree='d'*40,sources=inputs.source_hashes(ROOT),image=IMAGE,platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')
        value=policy.empty_report(NONCE,identity)
        value['failure_context']=dict(repeat=1,state=None,context=None,phase='install')
        value['install_failure']=backend.catalog_install_failure
        policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity)
        value['failure_context']['phase']='native'
        with self.assertRaises(OracleError):policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity)


class DocumentLinesSourceFixtureBoundaryTests(unittest.TestCase):
    def test_forced_windows_metadata_mismatch_covers_reports_install_and_staging(self):
        from types import SimpleNamespace
        real_os=inputs.runtime.os
        class DescriptorMismatchOS:
            def __getattr__(self,name):return getattr(real_os,name)
            def fstat(self,fd):
                value=real_os.fstat(fd)
                result=SimpleNamespace(**{name:getattr(value,name) for name in dir(value) if name.startswith('st_')})
                result.st_ctime_ns+=1
                return result
        actual_reader=inputs.runtime._read
        fixture_path=ROOT/'scripts/native_1c_db_oracle/document_lines_inputs.py'
        with mock.patch.object(inputs.runtime,'os',DescriptorMismatchOS()):
            with self.assertRaises(OracleError):actual_reader(fixture_path)
            for kind,name in (
                (DocumentLinesReportTests,'test_eight_context_report_keeps_unavailable_and_raw_unresolved'),
                (DocumentLinesInstallDiagnosticsTests,'test_install_exception_stays_fixed_and_report_bound'),
                (DocumentLinesStagingTests,'test_closed_inventory_and_empty_report'),
                (DocumentLinesStagingTests,'test_cold_staged_imports')):
                with self.subTest(case=name),mock.patch(__name__+'._windows_source_fixture',return_value=True):
                    result=unittest.TestResult();kind(name).run(result)
                    self.assertTrue(result.wasSuccessful(),result.errors+result.failures)
                    self.assertIs(inputs.runtime._read,actual_reader)
            with self.assertRaises(OracleError):actual_reader(fixture_path)
        self.assertIs(inputs.runtime.os,real_os)

    def test_adapter_keeps_hashes_caps_and_restores_on_exception(self):
        actual_reader=inputs.runtime._read
        with source_fixture_reader(windows=False):self.assertIs(inputs.runtime._read,actual_reader)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory).resolve()/'fixture';path.write_bytes(b'bound')
            with self.assertRaisesRegex(RuntimeError,'fixture exit'):
                with source_fixture_reader(windows=True):
                    self.assertEqual(inputs.runtime._read(path,5),b'bound')
                    with self.assertRaises(OracleError):inputs.runtime._read(path,4)
                    with self.assertRaises(OracleError):inputs.runtime._read(path.parent)
                    raise RuntimeError('fixture exit')
        self.assertIs(inputs.runtime._read,actual_reader)
        with source_fixture_reader(windows=True):windows_hashes=inputs.source_hashes(ROOT)
        if os.name!='nt':
            with source_fixture_reader(windows=False):self.assertEqual(windows_hashes,inputs.source_hashes(ROOT))


if __name__=='__main__':unittest.main()
