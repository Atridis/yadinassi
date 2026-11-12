"""Sequential official-XML AccumulationRegister observation; never reads database files."""
from pathlib import Path
import base64
import json
import os
import stat
import sys
import full_suite as full
import run_stage
import diagnostics
from inventory_enum_behavior import fixture, route


def empty_report(nonce):
    return dict(schema=route.STAGE_SCHEMA,profile=route.PROFILE,nonce=nonce,status='failed',
        failure_kind='prerequisites_failed',failure_phase='prerequisites',input_sha256={},
        source_sha256=None,module_sha256=None,module_verified_sha256=None,
        output_sha256=None,output_size=None,record_count=None,
        partial_observations=[],case_diagnostics=[],install_diagnostics=[],phases=[],incomplete=True,native_error_details=None,native_error_category="none",configuration_validation=fixture.VALIDATION_MODE,redump_diagnostic=[],process_diagnostics=full.empty_process_diagnostics(),
        **{k:False for k in ('entered','completed','process_exited','quiet','witness_verified','config_verified','restart_verified')})


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
    value=full.strict_json(full.secure_bytes(inputs/'inventory-inputs.json',32768))
    if type(value) is not dict or not 1<=len(value)<=64:raise full.FullError('invalid_input')
    result={}
    for source,target in value.items():
        if (type(source) is not str or not source.startswith('scripts/') and not source.startswith('integrational_tests/')
            or type(target) is not str or target.startswith('/') or any(p in ('','..','.') for p in target.split('/'))):
            raise full.FullError('invalid_input')
        result[source]=full.digest(full.secure_bytes(inputs/target,full.MAX_OUTPUT))
    return result


def run_suite(launcher,platform,launcher_epf,root,inputs,nonce):
    report=empty_report(nonce);phase='inputs'
    old_reader,old_process,old_build=launcher.read_result,launcher.run_process,launcher.build_epf
    try:
        if not full.valid_nonce(nonce) or platform.user!='NativeSmoke' or platform.password is not None or platform.timeout!=120:
            raise full.FullError('invalid_input')
        hashes=input_hashes(inputs);report['input_sha256']=hashes
        setup,assets=fixture.load_saved()
        sources=tuple(route.program(setup,nonce,p) for p in (1,2))
        modules=tuple(full.generated_module(source) for source in sources)
        report.update(source_sha256=full.digest(assets['generated/observe.bsl']),
            module_sha256=full.digest(b'\0'.join(modules)))
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
        setup,expected=fixture.prepare(dump_files(before))
        prepared=root/'prepared';prepared.mkdir()
        for name,raw in expected.items():
            path=prepared/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(raw)
        phase='install'
        designer('load',['/LoadConfigFromFiles',str(prepared)])
        designer('update',['/UpdateDBCfg'])
        phase='redump';after=root/'after';after.mkdir()
        designer('after',['/DumpConfigToFiles',str(after),'-Format','Hierarchical'])
        actual=dump_files(after)
        report['redump_diagnostic']=fixture.redump_diagnostic(expected,actual)
        fixture.verify_redump(expected,actual);report['config_verified']=True
        case=None;module=None;current_phase=1
        launcher.read_result=full.read_native_result
        def process(command,directory,log,timeout):
            if command[1]=='ENTERPRISE':
                if directory!=case:raise full.FullError('invalid_input')
                full.validate_case_request(command,case,False)
            full.run_process(command,directory,log,timeout,require_clean_tree=True)
        launcher.run_process=process
        def build(p,xml,destination):
            if full.secure_bytes(xml.parent/'TestModule/Ext/ObjectModule.bsl',route.MAX_OUTPUT+3)!=module:
                raise full.FullError('module_mismatch')
            old_build(p,xml,destination)
        launcher.build_epf=build
        verified=[]
        for current_phase in (1,2):
            # run_case waits for exit. This additional census must pass before
            # the second invocation can start against the same owned database.
            if current_phase==2 and (not report['phases'][0]['process_exited']
                    or not report['phases'][0]['quiet']):
                raise full.FullError('process_failed')
            source=sources[current_phase-1];module=modules[current_phase-1]
            program_path=root/('observe-'+str(current_phase)+'.bsl');program_path.write_bytes(source)
            case=root/('case-'+str(current_phase));output=root/('wire-'+str(current_phase)+'.out')
            fact=dict(phase=current_phase,entered=False,completed=False,
                process_exited=False,quiet=False,record_count=0,
                module_sha256=full.digest(module),module_verified_sha256=None)
            report['phases'].append(fact)
            phase='enterprise'
            try:
                launcher.run_case(platform,program_path,launcher_epf,case,output)
                fact['process_exited']=True
            finally:
                survivors=full.client_process_snapshot()-baseline
                if survivors:
                    report['process_diagnostics']=full.unexpected_process_diagnostics(survivors,'after_exit')
                else:
                    full.require_session_bus(run_stage.ROOT,nonce)
                    fact['quiet']=full.native_processes_quiet(platform.executable)
                    report['process_diagnostics']={**full.empty_process_diagnostics(),'stage':'after_exit',
                        'reason':'none' if fact['quiet'] else 'native_not_quiet'}
            if not fact['quiet'] or report['process_diagnostics']['reason']!='none':
                raise full.FullError('process_failed')
            phase='markers'
            messages,_=full.read_native_result(case/'result.json')
            raw=full.secure_bytes(output,route.MAX_OUTPUT)
            if raw!=full.serialize_messages(messages):raise full.FullError('output_mismatch')
            observations,errors=route.parse_attempt(raw,nonce,current_phase)
            fact['entered']=True;fact['record_count']=len(observations)
            report['entered']=True;report['partial_observations'].extend(observations)
            for number,stage,text in errors:
                details=route.failure_details({'messages':[],'error':text},nonce,current_phase)
                category=diagnostics.summarize_text(text)['category']
                context=diagnostics.rendered_context(text,'managed_marker')
                report['case_diagnostics'].append(dict(case=number,stage=stage,category=category,details=details,context=context))
            if errors or [n for n,_ in observations]!=list(route.case_range(current_phase)):
                raise full.FullError('invalid_result')
            actual_module=full.secure_bytes(case/'src/TestModule/Ext/ObjectModule.bsl',route.MAX_OUTPUT+3)
            if actual_module!=module:raise full.FullError('module_mismatch')
            verified.append(actual_module);fact['module_verified_sha256']=full.digest(actual_module)
            fact['completed']=True
        report.update(incomplete=False,completed=True,process_exited=True,quiet=True,restart_verified=True)
        values=[v for _,v in report['partial_observations']]
        report['module_verified_sha256']=full.digest(b'\0'.join(verified))
        phase='final'
        if input_hashes(inputs)!=hashes:raise full.FullError('module_mismatch')
        fixture.verify_redump(expected,dump_files(prepared))
        canonical=route.canonical(values)
        with (root/'inventory-enum.out').open('xb') as stream:stream.write(canonical)
        report.update(status='ok',failure_kind='none',failure_phase='final',witness_verified=True,
            output_sha256=full.digest(canonical),output_size=len(canonical),record_count=route.COUNT)
    except Exception as error:
        if phase=='enterprise':
            try:
                result=full.strict_json(full.secure_bytes(case/'result.json',full.MAX_RESULT))
                if type(result) is dict and type(result.get('error')) is str and len(result['error'])<=16384:
                    report['native_error_category']=diagnostics.summarize_text(result['error'])['category']
                    report['native_error_details']=route.failure_details(result,nonce,current_phase)
            except Exception:pass
        report['failure_kind']=error.kind if isinstance(error,full.FullError) else 'unexpected_failure'
        report['failure_phase']=phase
        if isinstance(error,full.ClientProcessError):report['process_diagnostics']=error.diagnostics
    finally:launcher.read_result,launcher.run_process,launcher.build_epf=old_reader,old_process,old_build
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
            raw=full.secure_bytes(root/'inventory-enum.out',route.MAX_OUTPUT)
            if route.canonical(full.strict_json(raw))!=raw or suite['output_sha256']!=full.digest(raw) or suite['output_size']!=len(raw):
                raise full.FullError('invalid_result')
            outputs=[dict(name='inventory-enum.out',size=len(raw),sha256=full.digest(raw),data_b64=base64.b64encode(raw).decode('ascii'))]
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
