"""Изолированное измерение компиляции в двух событиях; без проверки runtime."""
import base64
import json
import os
import stat
import re
import inject_modules
import evidence_gates
import run_stage
from compilation_profile_packet import fixture
from pathlib import Path
import full_suite as full
from compilation_profile_packet import route, SOURCE_SHA256, FORM_SHA256, PACKET_HASHES, MAX_OUTPUT, parse_records, require_available

PROFILE='compilation-profile-v1'
SCHEMA='native-1c-compilation_profile-v1'
STAGE_SCHEMA='native-1c-compilation_profile-stage-v1'
INPUT_FILES={
    **{k:v for k,v in full.INPUT_FILES.items() if not k.startswith('integrational_tests/tests/') and k not in ('scripts/native_1c_smoke_probe.sh','scripts/native_1c_bootstrap/run_stage.py')},
    'scripts/native_1c_compilation_profile_probe.sh':'probe.sh',
    'scripts/native_1c_bootstrap/run_compilation_profile_stage.py':'bootstrap/run_stage.py',
    'scripts/native_1c_bootstrap/compilation_profile_suite.py':'bootstrap/compilation_profile_suite.py',
    **{'scripts/compilation_profile_packet/'+name:'bootstrap/compilation_profile_packet/'+name
       for name in ('__init__.py','route.py','fixture.py',*PACKET_HASHES)},
    **{'scripts/catalog_object_behavior/'+name:'bootstrap/catalog_object_behavior/'+name
       for name in ('__init__.py','route.py','fixture.py','packet.py','Catalog.xml','SOURCE.json',
                    'generated/setup.json','generated/Catalog.xml','generated/observe.bsl')},

}
PHASES=('prerequisites','inputs','build','install','enterprise','markers','final')


def input_hashes(inputs):
    return {k:full.digest(full.secure_bytes(inputs/v,full.MAX_OUTPUT)) for k,v in INPUT_FILES.items()}


def empty_report(nonce):
    if not full.valid_nonce(nonce):raise full.FullError('invalid_input')
    return {'schema':STAGE_SCHEMA,'profile':PROFILE,'nonce':nonce,'status':'not_started',
            'failure_kind':'prerequisites_failed','failure_phase':'prerequisites',
            'input_sha256':{},'source_sha256':None,'form_sha256':None,'module_sha256':None,
            'prepared_sha256':None,'config_verified':False,'event1_done':False,'entered':False,'completed':False,'process_exited':False,
            'quiet':False,'witness_verified':False,'output_sha256':None,'output_size':None,
            'record_count':None,'process_diagnostics':{**full.empty_process_diagnostics(),'stage':'before_probe','reason':'unverified'}}


def _dump_files(directory):
    # The inventory is from our fresh generated source or designer dump only;
    # all files are secure descriptor reads, never copied from user directories.
    expected=set(PACKET_HASHES)
    seen=set()
    directories={parent.as_posix() for name in expected for parent in Path(name).parents if parent.as_posix()!='.'}
    for path in directory.rglob('*'):
        if path.is_symlink():raise full.FullError('module_mismatch')
        if path.is_file():seen.add(path.relative_to(directory).as_posix())
        elif not path.is_dir() or path.relative_to(directory).as_posix() not in directories:
            raise full.FullError('module_mismatch')
    if seen!=expected:raise full.FullError('module_mismatch')
    return {name:full.secure_bytes(directory/name,route.MAX_SOURCE,allow_empty=False) for name in expected}


def bootstrap_session_source(launcher_epf):
    # Stage two already completed before this suite. Re-bind its exact rendered
    # module and validated bootstrap/verify markers before replacing the handler.
    directory=launcher_epf.parent
    if (directory.parent != run_stage.ROOT or directory.is_symlink()
            or re.fullmatch('stage2-[0-9a-f]{32}',directory.name) is None):
        raise full.FullError('invalid_input')
    marker=full.strict_json(full.secure_bytes(directory/'verify-session.json',65536))
    run_id=marker.get('run_id') if type(marker) is dict else None
    if not full.valid_nonce(run_id):raise full.FullError('invalid_input')
    for stage in ('bootstrap','verify'):
        evidence_gates.require_marker_pair(directory,stage,run_id,'NativeSmoke',returncode=0)
    if (directory/'control.json').exists():raise full.FullError('invalid_input')
    source=inject_modules.render_module(Path(inject_modules.__file__).parent/'modules/SessionModule.bsl',run_id,'NativeSmoke',str(directory))
    installed=full.secure_bytes(directory/'injected/Ext/SessionModule.bsl',fixture.MAX_FILE)
    if source!=installed:raise full.FullError('module_mismatch')
    return source


def bootstrap_application_source(launcher_epf):
    # Stage two already completed before this suite. Re-bind its exact rendered
    # module and validated bootstrap/verify markers before replacing the handler.
    directory=launcher_epf.parent
    if (directory.parent != run_stage.ROOT or directory.is_symlink()
            or re.fullmatch('stage2-[0-9a-f]{32}',directory.name) is None):
        raise full.FullError('invalid_input')
    marker=full.strict_json(full.secure_bytes(directory/'verify-session.json',65536))
    run_id=marker.get('run_id') if type(marker) is dict else None
    if not full.valid_nonce(run_id):raise full.FullError('invalid_input')
    for stage in ('bootstrap','verify'):
        evidence_gates.require_marker_pair(directory,stage,run_id,'NativeSmoke',returncode=0)
    if (directory/'control.json').exists():raise full.FullError('invalid_input')
    source=inject_modules.render_module(Path(inject_modules.__file__).parent/'modules/ManagedApplicationModule.bsl',run_id,'NativeSmoke',str(directory))
    installed=full.secure_bytes(directory/'injected/Ext/ManagedApplicationModule.bsl',fixture.MAX_FILE)
    if source!=installed:raise full.FullError('module_mismatch')
    return source


def dump_files(root):
    result={};total=0;pending=[root];seen=0
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                seen+=1
                if seen>512:raise full.FullError('output_limit')
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path));continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise full.FullError('invalid_input')
                path=Path(entry.path);name=path.relative_to(root).as_posix()
                raw=full.secure_bytes(path,fixture.MAX_FILE,allow_empty=name.endswith('.bsl'))
                total+=len(raw)
                if total>fixture.MAX_TOTAL or len(result)>=256:raise full.FullError('output_limit')
                result[name]=raw
    fixture.original._files(result)
    return result


def run_suite(platform,root,inputs,nonce,launcher_epf):
    report=empty_report(nonce);report.update(status='failed',failure_kind='unexpected_failure')
    phase='inputs';baseline=None
    try:
        if (root!=Path('/tmp/onec-smoke')/('stage3-'+nonce)
                or platform.database!=Path('/tmp/onec-smoke/db') or platform.timeout!=120
                or platform.user!='NativeSmoke' or platform.password is not None):
            raise full.FullError('invalid_input')
        hashes=input_hashes(inputs)
        try:route.verify_hashes(hashes)
        except ValueError:raise full.FullError('invalid_input') from None
        report.update(input_sha256=hashes,source_sha256=SOURCE_SHA256,form_sha256=route.FORM_SHA256)
        prepared=route.sources()
        report['module_sha256']=route.module_digest(prepared)
        baseline=full.client_process_baseline(nonce)
        report['process_diagnostics']={**full.empty_process_diagnostics(),'stage':'before_probe','reason':'native_not_quiet'}
        if not full.native_processes_quiet(platform.executable):raise full.FullError('process_failed')
        report['process_diagnostics']['reason']='none'
        full.absent(root);root.mkdir(mode=0o700)
        def designer(label,args):
            full.run_process(platform.command('DESIGNER')+args+['/Out',str(root/(label+'.log')),
                '/DumpResult',str(root/(label+'.result'))],root,root/(label+'-console.log'),120,require_clean_tree=True)
            full.require_zero_result(root/(label+'.result'),0)
            if not full.native_processes_quiet(platform.executable):raise full.FullError('process_failed')
        before=root/'before';before.mkdir()
        designer('before',['/DumpConfigToFiles',str(before),'-Format','Hierarchical'])
        expected=fixture.prepare(dump_files(before),bootstrap_session_source(launcher_epf),bootstrap_application_source(launcher_epf))
        config=root/'configuration';config.mkdir()
        for name,raw in expected.items():
            path=config/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        phase='install'
        designer('load',['/LoadConfigFromFiles',str(config)])
        designer('update',['/UpdateDBCfg'])
        if dump_files(config)!=expected:raise full.FullError('module_mismatch')
        report['config_verified']=True
        src=root/'src';src.mkdir()
        for relative,raw in prepared.items():
            target=src/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(full.generated_module(raw) if relative.endswith('.bsl') else raw)
        try:route.validate_prepared(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        phase='build';epf=root/'CompilationProbe.epf'
        full.run_process(platform.command('DESIGNER')+[
            '/LoadExternalDataProcessorOrReportFromFiles',str(src/'Launcher.xml'),str(epf),
            '/Out',str(root/'build.log'),'/DumpResult',str(root/'build.result')],
            root,root/'build-console.log',120,require_clean_tree=True)
        full.require_epf(epf)
        epf_digest=full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))
        full.require_zero_result(root/'build.result',0)
        report['prepared_sha256']=route.validate_prepared(_dump_files(src))
        entered,completed,request=root/'entered.json',root/'completed.json',root/'request.json'
        trace=root/'trace.json'
        event1=root/'event1.json'
        full.absent(entered,completed,request,trace,event1)
        request_value={'nonce':nonce,'entered':str(entered),'completed':str(completed),'trace':str(trace),'event1_done':str(event1)}
        with request.open('x',encoding='utf-8') as stream:json.dump(request_value,stream)
        # Read back the exact owned request before handing its only path to1C.
        if full.strict_json(full.secure_bytes(request,4096))!=request_value:raise full.FullError('invalid_input')
        # Exact authored source and the exclusive built executable are reread
        # immediately before execution; Designer XML spelling is not an oracle.
        try:route.validate_prepared(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        if input_hashes(inputs)!=hashes or full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))!=epf_digest:
            raise full.FullError('module_mismatch')
        phase='enterprise'
        try:
            full.run_process(platform.command('ENTERPRISE')+[
                '/RunModeManagedApplication','/VL','ru_RU','/Execute',str(epf),'/C',str(request),
                '/Out',str(root/'enterprise.log')],root,root/'enterprise-console.log',120,require_clean_tree=True)
            report['process_exited']=True
        finally:
            survivors=full.client_process_snapshot()-baseline
            if survivors:report['process_diagnostics']=full.unexpected_process_diagnostics(survivors,'after_exit')
            else:
                full.require_session_bus(Path('/tmp/onec-smoke'),nonce)
                report['quiet']=full.native_processes_quiet(platform.executable)
                report['process_diagnostics']={**full.empty_process_diagnostics(),'stage':'after_exit','reason':'none' if report['quiet'] else 'native_not_quiet'}
            for path,label in ((entered,'entered'),(event1,'event1_done'),(completed,'completed')):
                try:
                    route.marker(full.secure_bytes(path,route.MAX_MARKER),nonce,label)
                    report[label]=True
                except (ValueError,full.FullError):pass
        phase='markers'
        try:
            route.marker(full.secure_bytes(entered,route.MAX_MARKER),nonce,'entered')
            first=route.marker(full.secure_bytes(event1,route.MAX_MARKER),nonce,'event1_done')
            marker=full.secure_bytes(completed,route.MAX_MARKER)
            route.marker(marker,nonce,'completed')
        except ValueError:raise full.FullError('invalid_result') from None
        if not entered.stat().st_mtime_ns<=event1.stat().st_mtime_ns<=completed.stat().st_mtime_ns:raise full.FullError('invalid_result')
        if not report['quiet'] or report['process_diagnostics']['reason']!='none':raise full.FullError('process_failed')
        raw=full.strict_json(marker)['records'].encode('ascii')
        if not raw.startswith(first['records'].encode('ascii')):raise full.FullError('invalid_result')
        require_available(parse_records(raw))
        output=root/'compilation_profile.out';full.absent(output)
        with output.open('xb') as stream:stream.write(raw)
        phase='final'
        try:route.validate_prepared(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        if (dump_files(config)!=expected or input_hashes(inputs)!=hashes or route.module_digest(_dump_files(src))!=report['module_sha256']
                or full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))!=epf_digest):
            raise full.FullError('module_mismatch')
        report.update(status='ok',failure_kind='none',failure_phase='final',witness_verified=True,
                      output_sha256=full.digest(raw),output_size=len(raw),record_count=16)
    except Exception as error:
        report['failure_kind']=error.kind if isinstance(error,full.FullError) else 'unexpected_failure'
        report['failure_phase']=phase
        if isinstance(error,full.ClientProcessError):report['process_diagnostics']=error.diagnostics
    return report


def write_report(path,report):
    raw=json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>full.MAX_STAGE_REPORT:raise full.FullError('export_failed')
    with path.open('xb') as stream:stream.write(raw)


def finish_report(report,nonce,root,*,quiet,bus_cleanup_failed):
    suite=empty_report(nonce);outputs=[]
    try:
        suite=full.strict_json(full.secure_bytes(root.parent/'stage3-report.json',full.MAX_STAGE_REPORT))
        if type(suite) is not dict or suite.get('schema')!=STAGE_SCHEMA or suite.get('profile')!=PROFILE or suite.get('nonce')!=nonce:
            raise full.FullError('invalid_result')
        if not quiet or bus_cleanup_failed:raise full.FullError('process_failed')
        full.final_client_process_census(nonce)
        if report['status']=='ok' and suite['status']=='ok':
            raw=full.secure_bytes(root/'compilation_profile.out',MAX_OUTPUT)
            require_available(parse_records(raw))
            if suite['output_sha256']!=full.digest(raw) or suite['output_size']!=len(raw):raise full.FullError('invalid_result')
            outputs=[{'name':'compilation_profile.out','size':len(raw),'sha256':full.digest(raw),'data_b64':base64.b64encode(raw).decode('ascii')}]
            report['native_tests_completed']=True
    except Exception:
        suite=empty_report(nonce);suite.update(status='failed',failure_kind='export_failed')
    if suite['status']!='ok':
        outputs=[];report.update(status='stage3_failed',native_tests_completed=False)
    report['stage3']=suite
    raw=json.dumps({'schema':SCHEMA,'profile':PROFILE,'nonce':nonce,'report':report,'outputs':outputs},
                   sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(json.dumps(report,separators=(',',':')).encode())>full.MAX_REPORT or len(raw)>65536:
        raise full.FullError('export_failed')
    return raw
