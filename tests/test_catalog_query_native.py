"""Output-only CatalogQuery harness: no platform sessions or database files."""
from pathlib import Path
from decimal import Decimal
import contextlib
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'scripts/native_1c_bootstrap')]
import catalog_query_suite as suite
from catalog_query_behavior import fixture,route
from test_catalog_query_fixture import baseline

NONCE='a'*32

def observations():
    booleans={2,3,4,13,14,15,18,24}
    return [True if i in booleans else Decimal(1) if i==19 else 'owned' for i in range(1,25)]

def wire(values=None):
    rows=['CQ|'+NONCE+'|entered']
    for n,v in enumerate(values or observations(),1):
        tag,text=('B','1' if v else '0') if type(v) is bool else ('N',str(v)) if type(v) is Decimal else ('S',v)
        rows.append(f'CQ|{NONCE}|{n}|{tag}|{text}')
    return ('\n'.join(rows+['CQ|'+NONCE+'|completed'])+'\n').encode()

def write_files(root,files):
    for name,raw in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

@contextlib.contextmanager
def synthetic_container_files(root):
    """Owned static fixtures only; not Linux descriptor-security evidence.

    Model the container's file facts with portable path lstat, rather than
    Windows DirEntry's cached nlink=0 or macOS /var parent alias handling.
    The production reader/stat guards are unchanged and restored on exit.
    """
    root=Path(root).resolve(strict=True)
    original_scandir=os.scandir
    def checked(path):
        path=Path(path).absolute()
        try:relative=path.relative_to(root)
        except ValueError:raise suite.full.FullError('invalid_input') from None
        current=root
        for part in relative.parts:
            current=current/part
            if stat.S_ISLNK(current.lstat().st_mode):raise suite.full.FullError('invalid_input')
        return path
    def read(path,limit,*,allow_empty=False):
        path=checked(path);before=path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1
                or not (0 if allow_empty else 1)<=before.st_size<=limit):
            raise suite.full.FullError('artifact_missing')
        with path.open('rb') as stream:raw=stream.read(limit+1)
        after=path.lstat()
        identity=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_nlink)
        if identity(before)!=identity(after) or len(raw)!=before.st_size:
            raise suite.full.FullError('artifact_missing')
        return raw
    @contextlib.contextmanager
    def scan(path):
        path=checked(path)
        with original_scandir(path) as entries:
            yield (types.SimpleNamespace(path=entry.path,
                       stat=lambda *,follow_symlinks=False,p=Path(entry.path):
                           p.stat() if follow_symlinks else p.lstat()) for entry in entries)
    with mock.patch.object(suite,'os',types.SimpleNamespace(scandir=scan)),mock.patch.object(suite.full,'secure_bytes',side_effect=read):
        yield

class RouteTests(unittest.TestCase):
    def test_wire_and_canonical_are_exact(self):
        values=route.parse_wire(wire(),NONCE)
        self.assertEqual(values,observations())
        raw=route.canonical(values)
        self.assertEqual(route.canonical(json.loads(raw)),raw)
        self.assertIs(type(json.loads(raw)[18]),int)
    def test_nonce_case_type_and_marker_mutations_rejected(self):
        raw=wire()
        changes=[raw.replace(NONCE.encode(),b'b'*32,1),raw.replace(b'|2|B|1',b'|3|B|1',1),
                 raw.replace(b'|19|N|1',b'|19|N|01'),raw.replace(b'|19|N|1',b'|19|B|1'),
                 raw.replace(b'|2|B|1',b'|2|S|true'),raw.replace(b'completed',b'entered'),
                 raw+b'private\n',raw.replace(b'\n',b'\r\n'),raw[:-1],b'\xff']
        for changed in changes:
            self.assertNotEqual(changed,raw)
            with self.subTest(changed=changed[:50]),self.assertRaises(ValueError):route.parse_wire(changed,NONCE)
    def test_full_wrapped_program_executes_on_real_owned_sqlite(self):
        from yadinassi import Interpreter
        from yadinassi.configuration_xml import import_configuration
        from yadinassi.database_context import SQLiteDBContext
        from catalog_query_behavior.replay import logical_model_files,replay
        setup,_=fixture.load_saved();messages=[]
        with tempfile.TemporaryDirectory() as td:
            context=SQLiteDBContext.create(Path(td)/'owned.sqlite',import_configuration(logical_model_files(setup)))
            try:
                Interpreter(output=messages.append,database_context=context).execute(route.program(setup,NONCE).decode('utf-8'))
            finally:context.close()
        raw=suite.full.serialize_messages(messages)
        self.assertEqual(route.canonical(route.parse_wire(raw,NONCE)),route.canonical(replay()))
        self.assertEqual(len(messages),26)

    def test_source_nonce_and_scalar_bounds(self):
        setup,_=fixture.load_saved();raw=route.program(setup,NONCE)
        self.assertLessEqual(len(raw),route.MAX_OUTPUT)
        self.assertEqual(raw.count(b'Procedure CQEmit'),1)
        self.assertEqual(raw.count(b'EndProcedure'),1)
        for nonce in ('',NONCE+'0',NONCE.upper(),None):
            with self.assertRaises(ValueError):route.program(setup,nonce)
        for count in (True,4,-1,'1'):
            values=observations();values[18]=count
            with self.assertRaises(ValueError):route.canonical(values)
        values=observations();values[8]='x'*65
        with self.assertRaises(ValueError):route.canonical(values)

class DumpTests(unittest.TestCase):
    def test_official_xml_inventory_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();files=baseline();write_files(root,files)
            with synthetic_container_files(root):self.assertEqual(suite.dump_files(root),files)
    def test_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();(root/'target.xml').write_bytes(b'<a/>')
            try:(root/'link.xml').symlink_to(root/'target.xml')
            except OSError:self.skipTest('symlink unavailable')
            with synthetic_container_files(root),self.assertRaises(suite.full.FullError):suite.dump_files(root)
    def test_entry_bound_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()
            for n in range(257):(root/f'{n}.xml').write_bytes(b'<a/>')
            with synthetic_container_files(root),self.assertRaises(suite.full.FullError):suite.dump_files(root)
    def test_static_adapter_bounds_and_restoration(self):
        original_reader=suite.full.secure_bytes;original_os=suite.os
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();path=root/'owned.xml';path.write_bytes(b'<a/>')
            with self.assertRaisesRegex(RuntimeError,'exit'):
                with synthetic_container_files(root):
                    self.assertEqual(suite.full.secure_bytes(path,4),b'<a/>')
                    with self.assertRaises(suite.full.FullError):suite.full.secure_bytes(path,3)
                    with self.assertRaises(suite.full.FullError):suite.full.secure_bytes(root.parent/'outside',100)
                    raise RuntimeError('exit')
        self.assertIs(suite.full.secure_bytes,original_reader);self.assertIs(suite.os,original_os)

    def test_input_manifest_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve()
            for target in ('../outside','/outside','a//b','./a'):
                (root/'catalog-query-inputs.json').write_text(json.dumps({'scripts/owned.py':target}),encoding='utf-8')
                with synthetic_container_files(root),self.assertRaises(suite.full.FullError):suite.input_hashes(root)

class SuiteTests(unittest.TestCase):
    def exercise(self, failure=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        parent=Path(temp.name).resolve();root=parent/'run';inputs=parent/'inputs';inputs.mkdir()
        (inputs/'owned.py').write_bytes(b'# source\n')
        (inputs/'catalog-query-inputs.json').write_text(json.dumps({'scripts/owned.py':'owned.py'}),encoding='utf-8')
        platform=types.SimpleNamespace(user='NativeSmoke',password=None,timeout=120,executable=Path('/owned/platform'),
            command=lambda mode:['/owned/platform',mode])
        actions=[];base=baseline();expected=fixture.prepare(base)[1]
        def native_process(command,directory,log,timeout,**kwargs):
            self.assertEqual(timeout,120);self.assertIs(kwargs.get('require_clean_tree'),True)
            if '/DumpConfigToFiles' in command:
                target=Path(command[command.index('/DumpConfigToFiles')+1]);actions.append('dump-'+target.name)
                files=base if target.name=='before' else dict(expected)
                if failure=='redump' and target.name=='after':files['Ext/SessionModule.bsl']+=b'// changed\n'
                write_files(target,files)
            elif '/LoadConfigFromFiles' in command:actions.append('load')
            elif '/UpdateDBCfg' in command:actions.append('update')
            else:actions.append('enterprise')
        launcher=types.SimpleNamespace(read_result=object(),run_process=object(),build_epf=lambda *a:None)
        original=(launcher.read_result,launcher.run_process,launcher.build_epf)
        def run_case(p,source,epf,case,output):
            actions.append('case');case.mkdir()
            module=case/'src/TestModule/Ext/ObjectModule.bsl';module.parent.mkdir(parents=True)
            module.write_bytes(suite.full.generated_module(source.read_bytes()))
            launcher.build_epf(p,case/'src/TestModule.xml',case/'TestModule.epf')
            launcher.run_process(p.command('ENTERPRISE'),case,case/'log',120)
            if failure=='enterprise':raise suite.full.FullError('process_failed')
            raw=wire()
            if failure=='nonce':raw=raw.replace(NONCE.encode(),b'b'*32)
            output.write_bytes(raw)
            (case/'result.json').write_text(json.dumps({'messages':raw.decode().splitlines(),'error':''}),encoding='utf-8')
            if failure=='module':module.write_bytes(b'changed')
            if failure=='input':(inputs/'owned.py').write_bytes(b'changed')
        launcher.run_case=run_case
        with contextlib.ExitStack() as stack:
            stack.enter_context(synthetic_container_files(parent))
            for name,value in [('run_process',native_process),('client_process_baseline',lambda n:set()),
                               ('client_process_snapshot',lambda:set()),('native_processes_quiet',lambda p:True),
                               ('require_session_bus',lambda *a:None),('validate_case_request',lambda *a:None)]:
                stack.enter_context(mock.patch.object(suite.full,name,value))
            result=suite.run_suite(launcher,platform,parent/'Launcher.epf',root,inputs,NONCE)
        self.assertEqual((launcher.read_result,launcher.run_process,launcher.build_epf),original)
        return result,actions,root
    def test_official_install_and_single_action_sequential_success(self):
        result,actions,root=self.exercise()
        self.assertEqual(result['status'],'ok',result)
        self.assertEqual(actions,['dump-before','load','update','dump-after','case','enterprise'])
        self.assertTrue(result['config_verified']);self.assertTrue(result['witness_verified'])
        self.assertEqual(result['record_count'],24)
        self.assertEqual((root/'catalog-query.out').read_bytes(),route.canonical(observations()))
    def test_redump_refusal_prevents_action(self):
        result,actions,root=self.exercise('redump')
        self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_phase'],'redump')
        self.assertNotIn('case',actions);self.assertFalse(result['witness_verified'])
        self.assertFalse((root/'catalog-query.out').exists())
    def test_failed_action_or_changed_evidence_never_accepts(self):
        for failure in ('enterprise','nonce','module','input'):
            with self.subTest(failure=failure):
                result,actions,root=self.exercise(failure)
                self.assertEqual(result['status'],'failed',result);self.assertFalse(result['witness_verified'])
                self.assertFalse((root/'catalog-query.out').exists())

if __name__=='__main__':unittest.main()
