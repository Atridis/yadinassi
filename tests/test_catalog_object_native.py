"""Output-only CatalogObject harness: no platform sessions or database files."""
from pathlib import Path
from decimal import Decimal
import contextlib
import json
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'scripts/native_1c_bootstrap')]
import catalog_object_suite as suite
from catalog_object_behavior import fixture,route
from test_catalog_object_fixture import baseline

NONCE='a'*32

def observations():
    values=[True]*24
    for number in (9,10,13,17,20,21):values[number-1]='owned'
    values[17]=Decimal(1)
    return values

def wire(values=None):
    rows=['CBO|'+NONCE+'|entered']
    for n,v in enumerate(values or observations(),1):
        tag,text=('B','1' if v else '0') if type(v) is bool else ('N',str(v)) if type(v) is Decimal else ('S',v)
        rows.append(f'CBO|{NONCE}|{n}|{tag}|{text}')
    return ('\n'.join(rows+['CBO|'+NONCE+'|completed'])+'\n').encode()

def write_files(root,files):
    for name,raw in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

class RouteTests(unittest.TestCase):
    def test_wire_and_canonical_are_exact(self):
        values=route.parse_wire(wire(),NONCE)
        self.assertEqual(values,observations())
        raw=route.canonical(values)
        self.assertEqual(route.canonical(json.loads(raw)),raw)
        self.assertIs(type(json.loads(raw)[17]),int)
    def test_nonce_case_type_and_marker_mutations_rejected(self):
        raw=wire()
        changes=[raw.replace(NONCE.encode(),b'b'*32,1),raw.replace(b'|1|B|1',b'|2|B|1',1),
                 raw.replace(b'|18|N|1',b'|18|N|01'),raw.replace(b'|18|N|1',b'|18|B|1'),
                 raw.replace(b'|1|B|1',b'|1|S|true'),raw.replace(b'completed',b'entered'),
                 raw+b'private\n',raw.replace(b'\n',b'\r\n'),raw[:-1],b'\xff']
        for changed in changes:
            self.assertNotEqual(changed,raw)
            with self.subTest(changed=changed[:50]),self.assertRaises(ValueError):route.parse_wire(changed,NONCE)
    def test_full_wrapped_program_executes_on_real_owned_sqlite(self):
        from yadinassi import Interpreter
        from yadinassi.configuration_xml import import_configuration
        from yadinassi.database_context import SQLiteDBContext
        from catalog_object_behavior.replay import logical_model_files,replay
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
        self.assertEqual(raw.count(b'Procedure CBOEmit'),1)
        self.assertEqual(raw.count(b'EndProcedure'),1)
        for nonce in ('',NONCE+'0',NONCE.upper(),None):
            with self.assertRaises(ValueError):route.program(setup,nonce)
        for count in (True,4,-1,'1'):
            values=observations();values[17]=count
            with self.assertRaises(ValueError):route.canonical(values)
        values=observations();values[8]='x'*65
        with self.assertRaises(ValueError):route.canonical(values)

class DumpTests(unittest.TestCase):
    def test_official_xml_inventory_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);files=baseline();write_files(root,files)
            self.assertEqual(suite.dump_files(root),files)
    def test_symlinks_and_entry_bound_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'target.xml').write_bytes(b'<a/>')
            try:(root/'link.xml').symlink_to(root/'target.xml')
            except OSError:self.skipTest('symlink unavailable')
            with self.assertRaises(suite.full.FullError):suite.dump_files(root)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for n in range(257):(root/f'{n}.xml').write_bytes(b'<a/>')
            with self.assertRaises(suite.full.FullError):suite.dump_files(root)
    def test_input_manifest_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for target in ('../outside','/outside','a//b','./a'):
                (root/'catalog-inputs.json').write_text(json.dumps({'scripts/owned.py':target}),encoding='utf-8')
                with self.assertRaises(suite.full.FullError):suite.input_hashes(root)

class SuiteTests(unittest.TestCase):
    def exercise(self, failure=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        parent=Path(temp.name);root=parent/'run';inputs=parent/'inputs';inputs.mkdir()
        (inputs/'owned.py').write_bytes(b'# source\n')
        (inputs/'catalog-inputs.json').write_text(json.dumps({'scripts/owned.py':'owned.py'}),encoding='utf-8')
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
        self.assertEqual((root/'catalog-object.out').read_bytes(),route.canonical(observations()))
    def test_redump_refusal_prevents_action(self):
        result,actions,root=self.exercise('redump')
        self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_phase'],'redump')
        self.assertNotIn('case',actions);self.assertFalse(result['witness_verified'])
        self.assertFalse((root/'catalog-object.out').exists())
    def test_failed_action_or_changed_evidence_never_accepts(self):
        for failure in ('enterprise','nonce','module','input'):
            with self.subTest(failure=failure):
                result,actions,root=self.exercise(failure)
                self.assertEqual(result['status'],'failed',result);self.assertFalse(result['witness_verified'])
                self.assertFalse((root/'catalog-object.out').exists())

if __name__=='__main__':unittest.main()
