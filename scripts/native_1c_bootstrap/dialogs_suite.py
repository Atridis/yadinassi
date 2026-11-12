"""Closed one-form dialog lifecycle acquisition; no runtime parity or modal-window claim."""
import base64
import json
from pathlib import Path
import full_suite as full
from dialog_packet import route, SOURCE_SHA256, FORM_SHA256, PACKET_HASHES, MAX_OUTPUT, parse_records, require_available

PROFILE='managed-dialogs-v1'
SCHEMA='native-1c-dialogs-v1'
STAGE_SCHEMA='native-1c-dialogs-stage-v1'
INPUT_FILES={
    **{k:v for k,v in full.INPUT_FILES.items() if not k.startswith('integrational_tests/tests/') and k not in ('scripts/native_1c_smoke_probe.sh','scripts/native_1c_bootstrap/run_stage.py')},
    'scripts/native_1c_dialogs_probe.sh':'probe.sh',
    'scripts/native_1c_bootstrap/run_dialogs_stage.py':'bootstrap/run_stage.py',
    'scripts/native_1c_bootstrap/dialogs_suite.py':'bootstrap/dialogs_suite.py',
    **{'scripts/dialog_packet/'+name:'bootstrap/dialog_packet/'+name
       for name in ('__init__.py','route.py',*PACKET_HASHES)},
}
PHASES=('prerequisites','inputs','build','redump','enterprise','markers','final')


def input_hashes(inputs):
    return {k:full.digest(full.secure_bytes(inputs/v,full.MAX_OUTPUT)) for k,v in INPUT_FILES.items()}


def empty_report(nonce):
    if not full.valid_nonce(nonce):raise full.FullError('invalid_input')
    return {'schema':STAGE_SCHEMA,'profile':PROFILE,'nonce':nonce,'status':'not_started',
            'failure_kind':'prerequisites_failed','failure_phase':'prerequisites',
            'input_sha256':{},'source_sha256':None,'form_sha256':None,'module_sha256':None,
            'roundtrip_sha256':None,'entered':False,'completed':False,'process_exited':False,
            'quiet':False,'witness_verified':False,'output_sha256':None,'output_size':None,
            'record_count':None,'redump_projection':None,'process_diagnostics':{**full.empty_process_diagnostics(),'stage':'before_probe','reason':'unverified'}}


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


def _dump_executable_files(directory):
    # XML output spelling/inventory is not executable evidence. Do not read it.
    # Still reject links, special files, unbounded trees and unknown non-XML
    # payloads rather than admitting another executable source or binary.
    import stat
    expected=set(route.EXECUTABLE_MODULES);seen=set()
    for index,path in enumerate(directory.rglob('*')):
        if index>=256:raise full.FullError('module_mismatch')
        mode=path.lstat().st_mode
        if stat.S_ISDIR(mode):continue
        if not stat.S_ISREG(mode):raise full.FullError('module_mismatch')
        name=path.relative_to(directory).as_posix()
        if name in expected:seen.add(name)
        elif path.suffix.lower()!='.xml':raise full.FullError('module_mismatch')
    if seen!=expected:raise full.FullError('module_mismatch')
    return {name:full.secure_bytes(directory/name,route.MAX_SOURCE) for name in expected}


def run_suite(platform,root,inputs,nonce):
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
        src=root/'src';src.mkdir()
        for relative,raw in prepared.items():
            target=src/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(full.generated_module(raw) if relative.endswith('.bsl') else raw)
        try:route.validate_redump(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        phase='build';epf=root/'DialogsProbe.epf'
        full.run_process(platform.command('DESIGNER')+[
            '/LoadExternalDataProcessorOrReportFromFiles',str(src/'Launcher.xml'),str(epf),
            '/Out',str(root/'build.log'),'/DumpResult',str(root/'build.result')],
            root,root/'build-console.log',120,require_clean_tree=True)
        full.require_epf(epf)
        epf_digest=full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))
        phase='redump';dumped=root/'roundtrip';dumped.mkdir()
        full.run_process(platform.command('DESIGNER')+[
            '/DumpExternalDataProcessorOrReportToFiles',str(dumped/'Launcher.xml'),str(epf),
            '/Out',str(root/'dump.log'),'/DumpResult',str(root/'dump.result')],
            root,root/'dump-console.log',120,require_clean_tree=True)
        dumped_files=_dump_executable_files(dumped)
        try:report['roundtrip_sha256']=route.validate_executable_redump(dumped_files)
        except ValueError:raise full.FullError('module_mismatch') from None
        if report['roundtrip_sha256']!=report['module_sha256']:raise full.FullError('module_mismatch')
        entered,completed,request=root/'entered.json',root/'completed.json',root/'request.json'
        trace=root/'trace.json'
        full.absent(entered,completed,request,trace)
        request_value={'nonce':nonce,'entered':str(entered),'completed':str(completed),'trace':str(trace)}
        with request.open('x',encoding='utf-8') as stream:json.dump(request_value,stream)
        # Read back the exact owned request before handing its only path to1C.
        if full.strict_json(full.secure_bytes(request,4096))!=request_value:raise full.FullError('invalid_input')
        # Exact authored source and the exclusive built executable are reread
        # immediately before execution; Designer XML spelling is not an oracle.
        try:route.validate_redump(_dump_files(src))
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
            for path,label in ((entered,'entered'),(completed,'completed')):
                try:
                    route.marker(full.secure_bytes(path,route.MAX_MARKER),nonce,label)
                    report[label]=True
                except (ValueError,full.FullError):pass
        phase='markers'
        try:
            route.marker(full.secure_bytes(entered,route.MAX_MARKER),nonce,'entered')
            marker=full.secure_bytes(completed,route.MAX_MARKER)
            route.marker(marker,nonce,'completed')
        except ValueError:raise full.FullError('invalid_result') from None
        if completed.stat().st_mtime_ns<entered.stat().st_mtime_ns:raise full.FullError('invalid_result')
        if not report['quiet'] or report['process_diagnostics']['reason']!='none':raise full.FullError('process_failed')
        raw=full.strict_json(marker)['records'].encode('ascii')
        require_available(parse_records(raw))
        output=root/'dialogs.out';full.absent(output)
        with output.open('xb') as stream:stream.write(raw)
        phase='final'
        try:route.validate_redump(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        if (input_hashes(inputs)!=hashes or route.module_digest(_dump_files(src))!=report['module_sha256']
                or full.digest(full.secure_bytes(epf,full.MAX_OUTPUT))!=epf_digest):
            raise full.FullError('module_mismatch')
        report.update(status='ok',failure_kind='none',failure_phase='final',witness_verified=True,
                      output_sha256=full.digest(raw),output_size=len(raw),record_count=6)
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
            raw=full.secure_bytes(root/'dialogs.out',MAX_OUTPUT)
            require_available(parse_records(raw))
            if suite['output_sha256']!=full.digest(raw) or suite['output_size']!=len(raw):raise full.FullError('invalid_result')
            outputs=[{'name':'dialogs.out','size':len(raw),'sha256':full.digest(raw),'data_b64':base64.b64encode(raw).decode('ascii')}]
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
