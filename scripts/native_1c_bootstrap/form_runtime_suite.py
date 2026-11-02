"""Closed managed-form-only native lane; no paired object-module/tree claim."""
import base64
import json
from pathlib import Path
import full_suite as full
from form_runtime_packet import route, SOURCE_SHA256, MAX_OUTPUT, parse_records, require_available

PROFILE='managed-form-programmatic-v1'
SCHEMA='native-1c-managed-form-v1'
STAGE_SCHEMA='native-1c-managed-form-stage-v1'
SOURCE='scripts/form_runtime_packet/module.bsl'
FORM='scripts/form_runtime_packet/form.xml'
MODULE='Launcher/Forms/Main/Ext/Form/Module.bsl'
FORM_PATH='Launcher/Forms/Main/Ext/Form.xml'
INPUT_FILES={
    **{k:v for k,v in full.INPUT_FILES.items() if not k.startswith('integrational_tests/tests/')},
    'scripts/native_1c_bootstrap/form_runtime_suite.py':'bootstrap/form_runtime_suite.py',
    **{'scripts/form_runtime_packet/'+name:'bootstrap/form_runtime_packet/'+name
       for name in ('__init__.py','route.py','module.bsl','form.xml')},
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
            'record_count':None,'process_diagnostics':{**full.empty_process_diagnostics(),'stage':'before_probe','reason':'unverified'}}


def _dump_files(directory):
    # The inventory is from our fresh generated source or designer dump only;
    # all files are secure descriptor reads, never copied from user directories.
    expected={'Launcher.xml','Launcher/Forms/Main.xml',FORM_PATH,MODULE,'Launcher/Ext/ObjectModule.bsl'}
    seen=set()
    directories={str(Path(name).parent) for name in expected}
    directories |= {str(parent) for name in expected for parent in Path(name).parents if str(parent)!='.'}
    for path in directory.rglob('*'):
        if path.is_symlink():raise full.FullError('module_mismatch')
        if path.is_file():seen.add(path.relative_to(directory).as_posix())
        elif not path.is_dir() or path.relative_to(directory).as_posix() not in directories:
            raise full.FullError('module_mismatch')
    if seen!=expected:raise full.FullError('module_mismatch')
    return {name:full.secure_bytes(directory/name,route.MAX_MARKER,allow_empty=name.endswith('ObjectModule.bsl')) for name in expected}


def run_suite(platform,root,inputs,nonce):
    report=empty_report(nonce);report.update(status='failed',failure_kind='unexpected_failure')
    phase='inputs';baseline=None
    try:
        if (root!=Path('/tmp/onec-smoke')/('stage3-'+nonce)
                or platform.database!=Path('/tmp/onec-smoke/db') or platform.timeout!=120
                or platform.user!='NativeSmoke' or platform.password is not None):
            raise full.FullError('invalid_input')
        hashes=input_hashes(inputs)
        if hashes[SOURCE]!=SOURCE_SHA256 or hashes[FORM]!=route.FORM_SHA256:
            raise full.FullError('invalid_input')
        report.update(input_sha256=hashes,source_sha256=SOURCE_SHA256,form_sha256=route.FORM_SHA256)
        module=full.generated_module(route.module())
        report['module_sha256']=full.digest(module)
        baseline=full.client_process_baseline(nonce)
        report['process_diagnostics']={**full.empty_process_diagnostics(),'stage':'before_probe','reason':'native_not_quiet'}
        if not full.native_processes_quiet(platform.executable):raise full.FullError('process_failed')
        report['process_diagnostics']['reason']='none'
        full.absent(root);root.mkdir(mode=0o700)
        src=root/'src';src.mkdir()
        for relative in ('Launcher.xml','Launcher/Forms/Main.xml','Launcher/Ext/ObjectModule.bsl'):
            origin=inputs/'launcher/launcher_1c'/relative
            raw=full.secure_bytes(origin,route.MAX_MARKER,allow_empty=relative.endswith('ObjectModule.bsl'))
            if full.digest(raw)!=hashes['integrational_tests/launcher_1c/'+relative]:raise full.FullError('invalid_input')
            target=src/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        (src/FORM_PATH).parent.mkdir(parents=True,exist_ok=True)
        (src/FORM_PATH).write_bytes(route.form_xml())
        (src/MODULE).parent.mkdir(parents=True,exist_ok=True);(src/MODULE).write_bytes(module)
        try:route.validate_redump(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        phase='build';epf=root/'ManagedFormProbe.epf'
        full.run_process(platform.command('DESIGNER')+[
            '/LoadExternalDataProcessorOrReportFromFiles',str(src/'Launcher.xml'),str(epf),
            '/Out',str(root/'build.log'),'/DumpResult',str(root/'build.result')],
            root,root/'build-console.log',120,require_clean_tree=True)
        full.require_epf(epf)
        phase='redump';dumped=root/'roundtrip';dumped.mkdir()
        full.run_process(platform.command('DESIGNER')+[
            '/DumpExternalDataProcessorOrReportToFiles',str(dumped/'Launcher.xml'),str(epf),
            '/Out',str(root/'dump.log'),'/DumpResult',str(root/'dump.result')],
            root,root/'dump-console.log',120,require_clean_tree=True)
        dumped_files=_dump_files(dumped)
        try:route.validate_redump(dumped_files)
        except ValueError:raise full.FullError('module_mismatch') from None
        actual=full.generated_module(dumped_files[MODULE])
        if actual!=module:raise full.FullError('module_mismatch')
        report['roundtrip_sha256']=full.digest(actual)
        entered,completed,request=root/'entered.json',root/'completed.json',root/'request.json'
        full.absent(entered,completed,request)
        request_value={'nonce':nonce,'entered':str(entered),'completed':str(completed)}
        with request.open('x',encoding='utf-8') as stream:json.dump(request_value,stream)
        # Read back the exact owned request before handing its only path to1C.
        if full.strict_json(full.secure_bytes(request,4096))!=request_value:raise full.FullError('invalid_input')
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
        output=root/'managed-form.out';full.absent(output)
        with output.open('xb') as stream:stream.write(raw)
        phase='final'
        try:route.validate_redump(_dump_files(src))
        except ValueError:raise full.FullError('module_mismatch') from None
        if input_hashes(inputs)!=hashes or full.secure_bytes(src/MODULE,route.MAX_SOURCE+3)!=module:
            raise full.FullError('module_mismatch')
        report.update(status='ok',failure_kind='none',failure_phase='final',witness_verified=True,
                      output_sha256=full.digest(raw),output_size=len(raw),record_count=40)
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
            raw=full.secure_bytes(root/'managed-form.out',MAX_OUTPUT)
            require_available(parse_records(raw))
            if suite['output_sha256']!=full.digest(raw) or suite['output_size']!=len(raw):raise full.FullError('invalid_result')
            outputs=[{'name':'managed-form.out','size':len(raw),'sha256':full.digest(raw),'data_b64':base64.b64encode(raw).decode('ascii')}]
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
