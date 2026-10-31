"""Local linked-card acquisition contracts; no invented native/physical answers."""
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
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'scripts')]
import linked_card_fixture as fixture
import linked_card_instrument as instrument
import linked_card_inputs as inputs
import linked_card_report as policy
import linked_card_run as runner
from linked_card_packet import linked
from linked_card_packet.base import scalar_wire
from inject_metadata import _module,inject
from snapshots import OracleError
from protocol import IMAGE
from test_metadata_catalog_runtime_inputs import static_bundle_bytes
from test_catalog_read_native import container_metadata_paths
NONCE='a'*32


def audit(token='f'*32):
    return dict(token=token,actual_version='8.3.27.1508',user='NativeOracleSetup',role_verified=True,users_verified=True,nonprivileged=True)


def wire(s,state):
    zero='00000000-0000-0000-0000-000000000000';filled=state=='filled'
    values=[*s.base.names,3 if filled else 0,1 if filled else 0,int(filled),0,int(filled),0]
    for code,boolean,target in [('10',False,zero),('20',True,s.base.record_ids[1]),('30',True,s.base.record_ids[0])]:
        values+=([True,code,boolean,True,target] if filled else [False,None,None,False,None])
    values+=[False]
    def scalar(v):
        if v is None:return 'U'
        if type(v) is bool:return 'B'+str(int(v))
        if type(v) is int:return 'N'+str(v)
        b=v.encode('utf-16-be');return 'S'+str(len(b)//2)+':'+b.hex()
    return (scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [ok|{scalar(v)}]\n'.encode() for i,v in enumerate(values,1))).decode()


class LinkedFixtureTests(unittest.TestCase):
    def test_saved_requests_and_mapping_without_uuid_alias(self):
        for repeat in (1,2):
            s,m,files=fixture.load(repeat)
            self.assertEqual(len(files),8)
            mapping=fixture.actual_mapping(s,m['schema'],{n:b for n,b in files.items() if n.endswith('.xml')})
            self.assertEqual(len(mapping),2)
            for value in mapping:self.assertNotEqual(value['ref_type_uuid'],value['metadata_uuid'])
            self.assertEqual([len(c['attributes']) for c in m['schema']['catalogs']],[5,0])
            for state in fixture.STATES:linked.require_setup_evidence(wire(s,state).encode(),s,state)
    def test_redump_ignores_only_unused_namespaces_not_used_qname_changes(self):
        s,m,files=fixture.load(1);saved={n:v for n,v in files.items() if n.endswith('.xml')}
        actual={n:v.replace(b'<MetaDataObject ',b'<MetaDataObject xmlns:unused="urn:synthetic-unused" ',1) for n,v in saved.items()}
        self.assertTrue(linked.verify_redump(s,m['schema'],saved,actual))
        self.assertEqual(fixture.actual_mapping(s,m['schema'],actual),fixture.actual_mapping(s,m['schema'],saved))
        with self.assertRaises(ValueError):linked.validate_fragments(s,m['schema'],actual)
        changed=dict(actual);name=next(iter(saved));changed[name]=changed[name].replace(b'http://www.w3.org/2001/XMLSchema"',b'urn:wrong-used-schema"')
        with self.assertRaises(ValueError):linked.verify_redump(s,m['schema'],saved,changed)
        changed=dict(actual);changed[name]=changed[name].replace(b'<FillFromFillingValue>false</FillFromFillingValue>',b'<FillFromFillingValue>true</FillFromFillingValue>')
        with self.assertRaises(ValueError):linked.verify_redump(s,m['schema'],saved,changed)

    def test_measured_nil_defaults_are_exact_not_stripped(self):
        for repeat in (1,2):
            setup,manifest,files=fixture.load(repeat)
            saved={n:v for n,v in files.items() if n.endswith('.xml')}
            name='Catalogs/'+setup.base.names[0]+'.xml';raw=saved[name]
            needle=b'<FillValue xsi:nil="true"/>'
            self.assertEqual(raw.count(needle),3)
            for replacement in (b'<FillValue xsi:nil="false"/>',b'<FillValue xsi:nil="true">nonempty</FillValue>',b'<FillValue xsi:nil="true" extra="x"/>',b'<FillValue xsi:nil="true" xsi:type="xs:boolean"/>',b''):
                changed=dict(saved);changed[name]=raw.replace(needle,replacement,1)
                with self.subTest(repeat=repeat,replacement=replacement),self.assertRaises(ValueError):
                    linked.verify_redump(setup,manifest['schema'],saved,changed)

    def test_fractional_number_transport_and_guarded_cursor(self):
        for repeat in (1,2):
            s,_,files=fixture.load(repeat)
            numbers=[expression for label,expression in linked.cases(s,'values') if label.endswith('.number')]
            self.assertEqual(len(numbers),3)
            self.assertTrue(all(expression.startswith('XMLString(') for expression in numbers))
            self.assertIn(b'S = Undefined;\nTry S = Catalogs.',files['cursor.bsl'])
            self.assertIn(b'.Select(); Except EndTry;',files['cursor.bsl'])

    def test_modules_parse_and_all_unavailable_globals_are_dynamic(self):
        from yadinassi.syntax.parser import parse
        for repeat in (1,2):
            s,m,files=fixture.load(repeat)
            for name in ('NativeOracleServer.bsl','ManagedApplicationModule.bsl'):
                text=instrument.instrument(_module(name,NONCE,'/tmp/onec-db-oracle/evidence'),name,s,files,nonce=NONCE,evidence=PurePosixPath('/tmp/onec-db-oracle/evidence')).decode('utf-8-sig')
                parse(text);self.assertNotIn('@@',text)
                if name=='NativeOracleServer.bsl':self.assertIn('linked_card_setup_filled',text)
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
                self.assertNotRegex(re.sub(r'"(?:[^"]|"")*"','""',text),r'\bCatalogs\b')
    def test_unavailable_capture_cannot_be_false_parity(self):
        from linked_card_readback import compare
        s,_,_=fixture.load(1)
        raw=scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,25))
        for block in fixture.BLOCKS:
            self.assertEqual(fixture.validate_capture(raw,s,block),{'availability':'unavailable'})
            self.assertFalse(compare(raw,raw,s,block)['matched'])

    def test_unadmitted_database_still_retains_all_observer_blocks(self):
        from linked_card_readback import execute
        with tempfile.TemporaryDirectory() as tmp:
            for repeat in (1,2):
                s,_,_=fixture.load(repeat)
                outputs=execute(Path(tmp).resolve(),s)
                self.assertEqual(set(outputs),set(fixture.BLOCKS))
                for block,raw in outputs.items():
                    self.assertEqual(fixture.validate_capture(raw.encode('ascii'),s,block),{'availability':'unavailable'})

    def test_setup_marker_24_witnesses_and_closed_states(self):
        s,_,_=fixture.load(1)
        value=dict(schema=1,nonce=NONCE,token='b'*32,operation='linked_card_setup_filled',status='ok',outputs={'setup':wire(s,'filled')})
        self.assertEqual(runner.validate_marker(json.dumps(value).encode(),nonce=NONCE,token='b'*32,operation=value['operation'],b=s),value['outputs'])
        for field,bad in [('schema',True),('nonce','c'*32),('token','c'*32),('status','error')]:
            with self.assertRaises(OracleError):runner.validate_marker(json.dumps(dict(value,**{field:bad})).encode(),nonce=NONCE,token='b'*32,operation=value['operation'],b=s)
    def test_full_redump_existing_rights_and_actual_mapping(self):
        with container_metadata_paths():
            self._full_redump_existing_rights_and_actual_mapping()

    def test_forced_windows_complete_redump_contract(self):
        import inject_metadata
        from pathlib import PureWindowsPath
        with mock.patch.object(inject_metadata,'Path',PureWindowsPath):
            with self.assertRaisesRegex(inject_metadata.DraftError,'Unexpected metadata directory'):
                self._full_redump_existing_rights_and_actual_mapping()
            with container_metadata_paths():
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
            self.assertEqual(calls,['seed-import','seed-apply','redump']);self.assertEqual(checked,audit());self.assertEqual(len(mapping),2)
            self.assertEqual((root/'catalog-source-1/Roles/NativeOracleSetupAdministrator/Ext/Rights.xml').read_bytes(),(v1/'Roles/NativeOracleSetupAdministrator/Ext/Rights.xml').read_bytes())


class LinkedStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.staged=Path(self.temp.name).resolve()/'stage'
        self.scope=mock.patch.object(inputs.runtime,'_read',new=static_bundle_bytes) if os.name=='nt' else nullcontext();self.scope.__enter__();self.addCleanup(self.scope.__exit__,None,None,None)
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
import linked_card_inputs as inputs
inputs.activate_runtime(root)
import linked_card_run,linked_card_report,linked_card_readback,linked_card_physical
from linked_card_fixture import load
assert len(load(1)[1]['schema']['catalogs'][0]['attributes'])==5
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
backend=object.__new__(linked_card_run.Native)
backend.root=root.parent;backend.v1=v1;backend.nonce='a'*32;backend.evidence=evidence
calls=[]
def batch(database,args,label):
    calls.append(label)
    if label=='redump':shutil.copytree(root.parent/'catalog-source-1',Path(args[1]))
backend.batch=batch
backend.enterprise=lambda *a:dict(token='f'*32,actual_version='8.3.27.1508',user='NativeOracleSetup',role_verified=True,users_verified=True,nonprivileged=True)
assert len(backend.install(root.parent/'cold-db',1)[3])==2
assert calls==['seed-import','seed-apply','redump']
assert backend.catalog_install_failure is None
print('closed-linked')
'''
        # Same Windows static fixture bridge used by reviewed staging tests.
        if os.name=='nt':
            code=code.replace('import linked_card_inputs as inputs','import linked_card_inputs as inputs\n'+inspect.getsource(static_bundle_bytes)+'\ninputs.runtime._read=static_bundle_bytes')
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.staged),str(ROOT/'tests/fixtures/native_bootstrap/Configuration.xml')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'closed-linked')


class LinkedAcquisitionTests(unittest.TestCase):
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
                return s,{},audit(f'{repeat:032x}'),fixture.actual_mapping(s,m['schema'],{n:v for n,v in files.items() if n.endswith('.xml')})
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
            self.assertEqual(sum(op.startswith('linked_card_setup_') for _,op in backend.launches),4)
            self.assertEqual(sum(origin.startswith('catalog_applied_') for origin,_ in backend.clones),4)
            self.assertEqual(sum(origin=='catalog_state' for origin,_ in backend.clones),8)
            self.assertEqual(seen,['catalog_postimage']*8)
            self.assertEqual(backend.removed.count('catalog_postimage'),8)
            self.assertEqual(backend.removed.count('catalog_state'),4)
            self.assertIsNone(backend.catalog_attempt)


class LinkedHostTests(unittest.TestCase):
    def test_specialization_restored_even_on_failure(self):
        import native_1c_linked_catalog_oracle as entry
        h=entry.host
        previous=(h.inputs,h.policy,h.OUTPUT,h.container_command)
        def run(argv):
            self.assertIs(h.inputs,inputs);self.assertIs(h.policy,policy)
            self.assertEqual(h.OUTPUT,Path('native-linked-catalog/linked-card.json'))
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(inputs,'verify_inputs'):
                command=h.container_command(Path(tmp).resolve(),'onec-db-oracle-'+NONCE,NONCE)
            self.assertIn('/oracle/linked_card_run.py',command)
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
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT/'scripts/native_1c_linked_catalog_oracle.py'),str(ROOT/'scripts')],cwd=tmp,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

class LinkedReportTests(unittest.TestCase):
    def test_eight_context_report_keeps_unavailable_and_raw_unresolved(self):
        from test_linked_card_physical import image
        import linked_card_physical
        from linked_card_readback import compare
        identity=dict(commit='c'*40,tree='d'*40,sources=inputs.source_hashes(ROOT),image=IMAGE,platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')
        value=policy.empty_report(NONCE,dict(identity,actual_version='8.3.27.1508'))
        serial=0
        for repeat in (1,2):
            s,m,files=fixture.load(repeat)
            mapping=fixture.actual_mapping(s,m['schema'],{n:v for n,v in files.items() if n.endswith('.xml')})
            helpers={name:hashlib.sha256(instrument.instrument(_module(name,NONCE,'/tmp/onec-db-oracle/evidence'),name,s,files,nonce=NONCE,evidence='/tmp/onec-db-oracle/evidence')).hexdigest() for name in ('NativeOracleServer.bsl','ManagedApplicationModule.bsl')}
            value['installations'].append(dict(repeat=repeat,helpers=helpers,mapping=mapping,applied=dict(bytes=123,sha256='c'*64),audit=audit(f'{100+repeat:032x}')))
            source=image(m['schema']);physical=linked_card_physical.observe(source.read_at,source.size,m['schema'],mapping)
            raw=(scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,25))).decode()
            outputs={block:raw for block in fixture.BLOCKS}
            comparison={block:compare(raw.encode(),raw.encode(),s,block) for block in fixture.BLOCKS}
            for state in fixture.STATES:
                serial+=1;setup=dict(token=f'{serial:032x}',marker_sha256='b'*64,outputs={'setup':wire(s,state)},assessment={'setup':'query_witnesses_validated'})
                for context in ('client','server'):
                    serial+=1
                    value['states'].append(dict(repeat=repeat,state=state,context=context,setup=setup,origin=dict(bytes=123,sha256='d'*64),postimage=dict(bytes=123,sha256='e'*64),native=dict(token=f'{serial:032x}',marker_sha256='f'*64,outputs=outputs,assessment={block:fixture.validate_capture(raw.encode(),s,block) for block in fixture.BLOCKS}),offline=dict(physical=physical,outputs=outputs,comparison=comparison)))
        value['lifecycle'].update(status='ok',failure_kind='none')
        value['lifecycle']['cleanup'].update(native_processes_stopped=True,raw_files_removed=True)
        self.assertEqual(policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity),value)
        self.assertFalse(value['states'][0]['offline']['comparison']['values']['matched'])
        for change in ('mapping','origin','token','comparison','raw'):
            bad=copy.deepcopy(value)
            if change=='mapping':bad['installations'][0]['mapping'][0]['ref_type_uuid']=bad['installations'][0]['mapping'][0]['metadata_uuid']
            elif change=='origin':bad['states'][1]['origin']['sha256']='0'*64
            elif change=='token':bad['states'][1]['native']['token']=bad['states'][0]['native']['token']
            elif change=='comparison':bad['states'][0]['offline']['comparison']['values']['matched']=True
            else:bad['states'][0]['offline']['physical']['catalogs'][0]['physical']['raw_hex']='00'
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):
                policy.validate_report(policy.encode_report(bad),nonce=NONCE,provenance=identity)

class LinkedDiagnosticsTests(unittest.TestCase):
    def test_extended_witness_phase_preserves_finite_projection(self):
        import linked_card_diagnostics as diagnostics
        # The linked collector passes only the finite common shape to the shared
        # one-pass compiler collector and restores the authenticated fixed phase.
        previous=dict(site='completion',phase='setup-witness-24',status='error',operation_matches=True)
        seen=[]
        def collect(backend,database,value):
            seen.append(value.copy())
            return dict(value)
        with mock.patch.object(diagnostics.base,'collect',side_effect=collect),mock.patch.object(diagnostics.base,'validate'):
            result=diagnostics.collect(object(),Path('/owned'),previous)
            self.assertEqual(seen[0]['phase'],'setup');self.assertEqual(result['phase'],'setup-witness-24')
            self.assertEqual(previous['phase'],'setup-witness-24')
            with self.assertRaises(OracleError):diagnostics.collect(object(),Path('/owned'),dict(previous,phase='raw private exception'))

class LinkedInstallDiagnosticsTests(unittest.TestCase):
    def test_redump_namespace_and_default_shape_have_bounded_reason(self):
        import linked_card_diagnostics as d
        _,_,files=fixture.load(1);saved={n:v for n,v in files.items() if n.endswith('.xml')}
        redumped=dict(saved);name=next(iter(saved))
        redumped[name]=redumped[name].replace(b'<DescriptionLength>8</DescriptionLength>',b'<DescriptionLength>9</DescriptionLength>')
        value=d.install_failure('fragments',ValueError('saved-xml-profile'),saved,redumped)
        self.assertEqual(value['category'],'saved-xml-profile')
        self.assertTrue(any(x['kind']=='text' and 'DescriptionLength' in x['path'] for x in value['catalogs'][0]['differences']))
        self.assertNotIn('DescriptionLength>9',json.dumps(value))
        inserted=dict(saved)
        inserted[name]=saved[name].replace(b'<DescriptionLength>8</DescriptionLength>',b'<DescriptionLength>8</DescriptionLength><FillValue/>')
        projected=d.install_failure('fragments',ValueError('saved-xml-profile'),saved,inserted)
        self.assertTrue(any(x['kind']=='added' and 'FillValue' in x['path'] for x in projected['catalogs'][0]['differences']))

        self.assertEqual(d.install_failure('prepare',RuntimeError('private exception text'),{},{}),dict(stage='prepare',category='unexpected',catalogs=[]))
        changed=dict(saved);changed[name]=changed[name].replace(b'xmlns:cfg=',b'xmlns:unused=')
        value=d.install_failure('fragments',ValueError('saved-namespace-profile'),saved,changed)
        self.assertFalse(value['catalogs'][0]['namespaces']['bindings_equal'])
        for bad in (dict(value,category='private text'),dict(value,stage='arbitrary stage')):
            with self.assertRaises(OracleError):d.validate_install_failure(bad,saved)
        value['catalogs'][0]['differences']=[dict(path='private-data',kind='text')]
        with self.assertRaises(OracleError):d.validate_install_failure(value,saved)

    def test_typed_synthetic_defaults_are_owned_and_bounded(self):
        import xml.etree.ElementTree as ET
        import linked_card_diagnostics as d
        _,_,files=fixture.load(1)
        # Preserve the original omitted-default diagnostic scenario after input correction.
        saved={n:__import__('re').sub(rb'<FillValue\s+xsi:nil="true"\s*/>',b'',v) for n,v in files.items() if n.endswith('.xml')};name=next(iter(saved))
        md='{http://v8.1c.ru/8.3/MDClasses}';xsi='{http://www.w3.org/2001/XMLSchema-instance}'
        root=ET.fromstring(saved[name]);root.set('xmlns:xs','http://www.w3.org/2001/XMLSchema')
        attrs=root.findall(md+'Catalog/'+md+'ChildObjects/'+md+'Attribute')
        for index,kind,text in ((2,'xs:boolean','false'),(3,'xs:dateTime','0001-01-01T00:00:00'),(4,None,'')):
            node=ET.SubElement(attrs[index].find(md+'Properties'),md+'FillValue')
            if kind is not None:node.set(xsi+'type',kind)
            else:node.set(xsi+'nil','true')
            node.text=text
        redumped=dict(saved);redumped[name]=ET.tostring(root)
        value=d.install_failure('fragments',ValueError('redump-profile'),saved,redumped)
        rows=value['catalogs'][0]['fill_values'];self.assertEqual(len(rows),3)
        self.assertEqual([r['text'] for r in rows],['false','0001-01-01T00:00:00',''])
        self.assertEqual(rows[0]['type_namespace'],'http://www.w3.org/2001/XMLSchema')
        self.assertEqual(rows[2]['nil'],'true')
        bad=copy.deepcopy(value);bad['catalogs'][0]['fill_values'][0]['attribute_uuid']='0'*36
        with self.assertRaises(OracleError):d.validate_install_failure(bad,saved)
        bad=copy.deepcopy(value);bad['catalogs'][0]['fill_values'][0]['text']='x'*129
        with self.assertRaises(OracleError):d.validate_install_failure(bad,saved)
        attrs[2].set('uuid','0'*36);redumped[name]=ET.tostring(root)
        value=d.install_failure('fragments',ValueError('redump-profile'),saved,redumped)
        self.assertEqual([r['attribute_index'] for r in value['catalogs'][0]['fill_values']],[3,4])

    def test_install_exception_stays_fixed_and_report_bound(self):
        backend=object.__new__(runner.Native)
        def fail(*args):raise ModuleNotFoundError('private path')
        backend._install=fail
        with self.assertRaises(ModuleNotFoundError):backend.install(Path('/owned'),1)
        self.assertEqual(backend.catalog_install_failure,dict(stage='prepare',category='import-error',catalogs=[]))
        identity=dict(commit='c'*40,tree='d'*40,sources=inputs.source_hashes(ROOT),image=IMAGE,platform='linux/amd64',actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')
        value=policy.empty_report(NONCE,identity)
        value['failure_context']=dict(repeat=1,state=None,context=None,phase='install')
        value['install_failure']=backend.catalog_install_failure
        policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity)
        value['failure_context']['phase']='native'
        with self.assertRaises(OracleError):policy.validate_report(policy.encode_report(value),nonce=NONCE,provenance=identity)
