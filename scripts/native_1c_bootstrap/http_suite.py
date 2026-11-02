"""One server-side HTTP observation with an owned loopback fixture, no client injector."""
from pathlib import Path
import base64
import json
import os
import stat
import sys
import full_suite as full
import run_stage
import native_1c_http_route as route
import native_1c_http_family_contract as contract
from native_1c_http_fixture import owned_fixture, MAX_REQUESTS


def empty_report(nonce):
    return dict(schema=route.STAGE_SCHEMA,profile=route.PROFILE,nonce=nonce,status='failed',
        failure_kind='prerequisites_failed',failure_phase='prerequisites',input_sha256={},
        source_sha256=None,module_sha256=None,module_verified_sha256=None,
        output_sha256=None,output_size=None,record_count=None,port=None,request_count=None,
        fixture_inventory=None,process_diagnostics=full.empty_process_diagnostics(),
        **{k:False for k in ('entered','completed','process_exited','quiet','witness_verified',
                            'fixture_started','fixture_stopped','fixture_clean')})


def input_hashes(inputs):
    value=full.strict_json(full.secure_bytes(inputs/'http-inputs.json',32768))
    if type(value) is not dict or not 1<=len(value)<=64:raise full.FullError('invalid_input')
    result={}
    for source,target in value.items():
        if (type(source) is not str or not source.startswith(('scripts/','integrational_tests/'))
            or type(target) is not str or target.startswith('/')
            or any(p in ('','..','.') for p in target.split('/'))):
            raise full.FullError('invalid_input')
        result[source]=full.digest(full.secure_bytes(inputs/target,full.MAX_OUTPUT))
    return result


def fixture_inventory(root):
    """Finite failed-only structure: never export names, paths or file content."""
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode):raise full.FullError('invalid_input')
    value=dict(entries=0,known_files=0,regular=0,directories=0,other=0,truncated=False)
    with os.scandir(root) as entries:
        for entry in entries:
            if value['entries']==32:
                value['truncated']=True;break
            value['entries']+=1
            if entry.name=='http-in.bin':value['known_files']|=1
            if entry.name=='http-out.bin':value['known_files']|=2
            mode=entry.stat(follow_symlinks=False).st_mode
            kind='regular' if stat.S_ISREG(mode) else 'directories' if stat.S_ISDIR(mode) else 'other'
            value[kind]+=1
    return value


def run_suite(launcher,platform,launcher_epf,root,inputs,nonce):
    report=empty_report(nonce);phase='inputs'
    old_reader,old_process,old_build=launcher.read_result,launcher.run_process,launcher.build_epf
    try:
        if not full.valid_nonce(nonce) or platform.user!='NativeSmoke' or platform.password is not None or platform.timeout!=120:
            raise full.FullError('invalid_input')
        hashes=input_hashes(inputs);report['input_sha256']=hashes
        raw=full.secure_bytes(inputs/'bootstrap/HTTPFamily.bsl',8192)
        route.source(raw);report['source_sha256']=full.digest(raw)
        full.absent(root);root.mkdir(mode=0o700)
        fixture_root=root/'fixture';fixture_root.mkdir(mode=0o700)
        baseline=full.client_process_baseline(nonce)
        phase='fixture'
        server=None
        try:
            with owned_fixture() as server:
                report.update(fixture_started=True,port=server.server_port)
                source=route.program(raw,server.server_port,nonce)
                module=full.generated_module(source);report['module_sha256']=full.digest(module)
                program_path=root/'observe.bsl';program_path.write_bytes(source)
                case=root/'case';output=root/'wire.out'
                launcher.read_result=full.read_native_result
                def process(command,directory,log,timeout):
                    if command[1]=='ENTERPRISE':
                        if directory!=case:raise full.FullError('invalid_input')
                        full.validate_case_request(command,case,False)
                    full.run_process(command,directory,log,timeout,require_clean_tree=True)
                launcher.run_process=process
                def build(p,xml,destination):
                    if full.secure_bytes(xml.parent/'TestModule/Ext/ObjectModule.bsl',8195)!=module:
                        raise full.FullError('module_mismatch')
                    old_build(p,xml,destination)
                launcher.build_epf=build
                phase='enterprise'
                try:
                    launcher.run_case(platform,program_path,launcher_epf,case,output)
                    report['process_exited']=True
                finally:
                    survivors=full.client_process_snapshot()-baseline
                    if survivors:report['process_diagnostics']=full.unexpected_process_diagnostics(survivors,'after_exit')
                    else:
                        full.require_session_bus(run_stage.ROOT,nonce)
                        report['quiet']=full.native_processes_quiet(platform.executable)
                        report['process_diagnostics']={**full.empty_process_diagnostics(),'stage':'after_exit','reason':'none' if report['quiet'] else 'native_not_quiet'}
                phase='markers'
                messages,_=full.read_native_result(case/'result.json')
                wire=full.secure_bytes(output,route.MAX_OUTPUT)
                if wire!=full.serialize_messages(messages):raise full.FullError('output_mismatch')
                canonical=route.parse_wire(wire,nonce);report['entered']=report['completed']=True
                if not report['quiet'] or report['process_diagnostics']['reason']!='none':raise full.FullError('process_failed')
                if full.secure_bytes(case/'src/TestModule/Ext/ObjectModule.bsl',8195)!=module:raise full.FullError('module_mismatch')
                report['module_verified_sha256']=full.digest(module)
                inventory=fixture_inventory(fixture_root)
                if inventory['entries'] or inventory['truncated']:
                    report['fixture_inventory']=inventory
                    raise full.FullError('invalid_result')
                report['fixture_clean']=True
        finally:
            if server is not None:
                report['request_count']=server.requests_seen
                report['fixture_stopped']=server.fileno()==-1
        phase='final'
        if not report['fixture_stopped'] or not report['fixture_clean'] or not 1<=report['request_count']<=MAX_REQUESTS:
            raise full.FullError('process_failed')
        if input_hashes(inputs)!=hashes:raise full.FullError('module_mismatch')
        with (root/'http-family.out').open('xb') as stream:stream.write(canonical)
        report.update(status='ok',failure_kind='none',failure_phase='final',witness_verified=True,
            output_sha256=full.digest(canonical),output_size=len(canonical),record_count=40)
    except Exception as error:
        report['failure_kind']=error.kind if isinstance(error,full.FullError) else 'unexpected_failure'
        report['failure_phase']=phase
        if isinstance(error,full.ClientProcessError):report['process_diagnostics']=error.diagnostics
    finally:launcher.read_result,launcher.run_process,launcher.build_epf=old_reader,old_process,old_build
    return report


def finish_report(report,nonce,root,*,quiet,bus_cleanup_failed):
    suite=empty_report(nonce);outputs=[]
    try:
        suite=full.strict_json(full.secure_bytes(root.parent/'stage3-report.json',full.MAX_STAGE_REPORT))
        if type(suite) is not dict or suite.get('schema')!=route.STAGE_SCHEMA or suite.get('profile')!=route.PROFILE or suite.get('nonce')!=nonce:
            raise full.FullError('invalid_result')
        if not quiet or bus_cleanup_failed:raise full.FullError('process_failed')
        full.final_client_process_census(nonce)
        if report['status']=='ok' and suite['status']=='ok':
            raw=full.secure_bytes(root/'http-family.out',route.MAX_OUTPUT)
            contract.validate_output(raw)
            if suite['output_sha256']!=full.digest(raw) or suite['output_size']!=len(raw):raise full.FullError('invalid_result')
            outputs=[dict(name='http-family.out',size=len(raw),sha256=full.digest(raw),data_b64=base64.b64encode(raw).decode('ascii'))]
            report['native_tests_completed']=True
    except Exception:suite=empty_report(nonce);suite.update(failure_kind='export_failed')
    if suite['status']!='ok':outputs=[];report.update(status='stage3_failed',native_tests_completed=False)
    report['stage3']=suite
    raw=json.dumps(dict(schema=route.SCHEMA,profile=route.PROFILE,nonce=nonce,report=report,outputs=outputs),sort_keys=True,separators=(',',':')).encode()+b'\n'
    if len(raw)>65536:raise full.FullError('export_failed')
    return raw


def main(args):
    if len(args)!=2 or args[0]!='--invocation-nonce' or not full.valid_nonce(args[1]):return 2
    nonce=args[1]
    if run_stage.main([])!=0:return 1
    report=empty_report(nonce)
    try:
        launchers=list(run_stage.ROOT.glob('stage2-*/Launcher.epf'))
        if len(launchers)!=1:raise full.FullError('invalid_input')
        launcher=run_stage.load_launcher();platform=launcher.Platform(run_stage.ONEC,run_stage.ROOT/'db',120,'NativeSmoke')
        report=run_suite(launcher,platform,launchers[0],run_stage.ROOT/('stage3-'+nonce),run_stage.INPUTS,nonce)
    except Exception:pass
    raw=json.dumps(report,sort_keys=True,separators=(',',':')).encode()
    if len(raw)>full.MAX_STAGE_REPORT:return 1
    with (run_stage.ROOT/'stage3-report.json').open('xb') as stream:stream.write(raw)
    return 0 if report['status']=='ok' else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
