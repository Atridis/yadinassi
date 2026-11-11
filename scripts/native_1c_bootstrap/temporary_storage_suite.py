"""Owned global temporary-storage observation; no schema changes or database-file reads."""
from pathlib import Path
import base64
import json
import os
import stat
import shutil
import sys
import re
import inject_modules
import evidence_gates
import full_suite as full
import run_stage
import diagnostics
from temporary_storage_behavior import fixture, route


def empty_report(nonce):
    return dict(schema=route.STAGE_SCHEMA,profile=route.PROFILE,nonce=nonce,status='failed',
        failure_kind='prerequisites_failed',failure_phase='prerequisites',input_sha256={},
        source_sha256=None,module_sha256=None,module_verified_sha256=None,
        output_sha256=None,output_size=None,record_count=None,
        partial_observations=[],case_diagnostics=[],install_diagnostics=[],incomplete=True,native_error_details=None,native_error_category="none",configuration_validation=fixture.VALIDATION_MODE,redump_diagnostic=[],process_diagnostics=full.empty_process_diagnostics(),
        **{k:False for k in ('entered','completed','process_exited','quiet','witness_verified','config_verified')})


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
    fixture._files(result)
    return result


def input_hashes(inputs):
    # Manifest is supplied by the source-pinned host and contains paths only.
    value=full.strict_json(full.secure_bytes(inputs/'temporary_storage-inputs.json',32768))
    if type(value) is not dict or not 1<=len(value)<=64:raise full.FullError('invalid_input')
    result={}
    for source,target in value.items():
        if (type(source) is not str or not source.startswith('scripts/') and not source.startswith('integrational_tests/')
            or type(target) is not str or target.startswith('/') or any(p in ('','..','.') for p in target.split('/'))):
            raise full.FullError('invalid_input')
        result[source]=full.digest(full.secure_bytes(inputs/target,full.MAX_OUTPUT))
    return result


def run_owned_case(launcher,platform,script,launcher_epf,directory,output,expected_module):
    """Explicit small launcher adapter; shared launcher globals stay untouched."""
    full.absent(directory);directory.mkdir(mode=0o700)
    sources=directory/'src';shutil.copytree(launcher.TEMPLATES,sources)
    module=sources/'TestModule/Ext/ObjectModule.bsl'
    source=full.secure_bytes(script,route.MAX_OUTPUT)
    if full.generated_module(source)!=expected_module:raise full.FullError('module_mismatch')
    module.write_bytes(expected_module)
    epf=directory/'TestModule.epf';result=epf.with_suffix('.build-result.txt')
    command=platform.command('DESIGNER')+['/LoadExternalDataProcessorOrReportFromFiles',str(sources/'TestModule.xml'),str(epf),'/Out',str(epf.with_suffix('.designer.log')),'/DumpResult',str(result)]
    full.run_process(command,directory,epf.with_suffix('.designer-console.log'),platform.timeout,require_clean_tree=True)
    full.require_zero_result(result,0);full.require_epf(epf)
    if full.secure_bytes(module,route.MAX_OUTPUT+3)!=expected_module:raise full.FullError('module_mismatch')
    result=directory/'result.json';request=directory/'request.json'
    with request.open('xb') as stream:
        stream.write(json.dumps({'module':str(epf),'result':str(result),'post_create':False},ensure_ascii=False).encode('utf-8'))
    command=platform.command('ENTERPRISE')+['/RunModeManagedApplication','/VL','ru_RU','/Execute',str(launcher_epf),'/C',str(request),'/Out',str(directory/'enterprise.log')]
    full.validate_case_request(command,directory,False)
    full.run_process(command,directory,directory/'enterprise-console.log',platform.timeout,require_clean_tree=True)
    messages,error=full.read_native_result(result)
    with output.open('xb') as stream:stream.write(full.serialize_messages(messages))
    if error:raise full.FullError('invalid_result')


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


def run_suite(launcher,platform,launcher_epf,root,inputs,nonce):
    report=empty_report(nonce);phase='inputs'

    try:
        if not full.valid_nonce(nonce) or platform.user!='NativeSmoke' or platform.password is not None or platform.timeout!=120:
            raise full.FullError('invalid_input')
        hashes=input_hashes(inputs);report['input_sha256']=hashes
        setup,assets=fixture.load_saved();source=route.program(setup,nonce);module=full.generated_module(source)
        report.update(source_sha256=full.digest(assets['generated/observe.bsl']),module_sha256=full.digest(module))
        full.absent(root);root.mkdir(mode=0o700)
        baseline=full.client_process_baseline(nonce)
        def designer(label,args):
            source_root=Path(args[1]) if label=='load' else None
            facts=dict(source_root_present=None if source_root is None else source_root.is_dir() and not source_root.is_symlink(),
                configuration_present=None if source_root is None else (source_root/'Configuration.xml').is_file() and not (source_root/'Configuration.xml').is_symlink())
            try:
                full.run_process(platform.command('DESIGNER')+args+['/Out',str(root/(label+'.log')),
                    '/DumpResult',str(root/(label+'.result'))],root,root/(label+'-console.log'),120,require_clean_tree=True)
            except Exception as error:
                code=getattr(error,'exit_code',None)
                facts['exit_code']=code if type(code) is int and -255<=code<=255 else None
                for name in (label+'.log',label+'-console.log'):
                    try:
                        raw=full.secure_bytes(root/name,65536,allow_empty=True)
                        report['install_diagnostics'].append(route.install_diagnostic(diagnostics.native_text(raw),label,**facts))
                    except Exception:pass
                if not report['install_diagnostics']:
                    report['install_diagnostics'].append(route.install_diagnostic('',label,**facts))
                raise
            if not full.native_processes_quiet(platform.executable):raise full.FullError('process_failed')
        before=root/'before';before.mkdir()
        designer('before',['/DumpConfigToFiles',str(before),'-Format','Hierarchical'])
        setup,expected=fixture.prepare(dump_files(before),bootstrap_module=bootstrap_session_source(launcher_epf))
        # No metadata changes are needed for global temporary-storage APIs.
        # Verify the owned bootstrap once; do not re-import or polish XML.
        fixture.verify_redump(expected,dump_files(before));report['config_verified']=True
        program_path=root/'observe.bsl';program_path.write_bytes(source)
        case=root/'case';output=root/'wire.out'
        phase='enterprise'
        try:
            run_owned_case(launcher,platform,program_path,launcher_epf,case,output,module)
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
        raw=full.secure_bytes(output,route.MAX_OUTPUT)
        if raw!=full.serialize_messages(messages):raise full.FullError('output_mismatch')
        observations,errors=route.parse_attempt(raw,nonce)
        report['entered']=True;report['partial_observations']=observations
        for number,stage,text in errors:
            details=route.failure_details({'messages':[],'error':text},nonce)
            category=diagnostics.summarize_text(text)['category']
            context=diagnostics.rendered_context(text,'managed_marker')
            report['case_diagnostics'].append(dict(case=number,stage=stage,category=category,details=details,context=context))
        report['incomplete']=len(observations)!=route.COUNT
        if report['incomplete'] or errors:raise full.FullError('invalid_result')
        values=[v for _,v in observations];report['completed']=True
        if not report['quiet'] or report['process_diagnostics']['reason']!='none':raise full.FullError('process_failed')
        if full.secure_bytes(case/'src/TestModule/Ext/ObjectModule.bsl',route.MAX_OUTPUT+3)!=module:raise full.FullError('module_mismatch')
        report['module_verified_sha256']=full.digest(module)
        phase='final'
        if input_hashes(inputs)!=hashes:raise full.FullError('module_mismatch')
        fixture.verify_redump(expected,dump_files(before))
        canonical=route.canonical(values)
        with (root/'temporary_storage.out').open('xb') as stream:stream.write(canonical)
        report.update(status='ok',failure_kind='none',failure_phase='final',witness_verified=True,
            output_sha256=full.digest(canonical),output_size=len(canonical),record_count=route.COUNT)
    except Exception as error:
        if phase=='enterprise':
            try:
                result=full.strict_json(full.secure_bytes(root/'case/result.json',full.MAX_RESULT))
                if type(result) is dict and type(result.get('error')) is str and len(result['error'])<=16384:
                    report['native_error_category']=diagnostics.summarize_text(result['error'])['category']
                    report['native_error_details']=route.failure_details(result,nonce)
                    report['entered']=report['native_error_details']['entered']
                    report['partial_observations']=route.partial_values(result['messages'],nonce)
                    details=report['native_error_details']
                    report['case_diagnostics'].append(dict(case=min(details['cases']+1,route.COUNT),
                        stage='read',category=report['native_error_category'],details=details,
                        context=diagnostics.rendered_context(result['error'],'managed_marker')))
            except Exception:pass
        report['failure_kind']=error.kind if isinstance(error,full.FullError) else 'unexpected_failure'
        report['failure_phase']=phase
        if isinstance(error,full.ClientProcessError):report['process_diagnostics']=error.diagnostics
    return report


def finish_report(report,nonce,root,*,quiet,bus_cleanup_failed):
    suite=empty_report(nonce);outputs=[]
    try:
        suite=full.strict_json(full.secure_bytes(root.parent/'stage3-report.json',32768))
        if type(suite) is not dict or suite.get('schema')!=route.STAGE_SCHEMA or suite.get('profile')!=route.PROFILE or suite.get('nonce')!=nonce:
            raise full.FullError('invalid_result')
        if not quiet or bus_cleanup_failed:raise full.FullError('process_failed')
        full.final_client_process_census(nonce)
        if report['status']=='ok' and suite['status']=='ok':
            raw=full.secure_bytes(root/'temporary_storage.out',route.MAX_OUTPUT)
            if route.canonical(full.strict_json(raw))!=raw or suite['output_sha256']!=full.digest(raw) or suite['output_size']!=len(raw):
                raise full.FullError('invalid_result')
            outputs=[dict(name='temporary_storage.out',size=len(raw),sha256=full.digest(raw),data_b64=base64.b64encode(raw).decode('ascii'))]
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
    if len(raw)>32768:return 1
    with (run_stage.ROOT/'stage3-report.json').open('xb') as stream:stream.write(raw)
    return 0 if report['status']=='ok' else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
