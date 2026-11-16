"""Owner-bound isolated XML experiment. Collection is not visual UI acceptance."""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_1c_main_demo_designer as base
import native_1c_xml_order_ci_policy as policy
from xml_order_packet import packet
ROOT=Path(__file__).resolve().parents[1]
IMAGE,VERSION=base.IMAGE,base.VERSION
SCHEMA='native-xml-order-v1'
MAX_REPORT=32768
MAX_HOST_REPORT=262144
OWN=('scripts/native_1c_xml_order.py','scripts/native_1c_xml_order.sh',
     'scripts/native_1c_xml_order_ci_policy.py','.github/workflows/native-1c-xml-order.yml',
     *('scripts/xml_order_packet/'+n for n in ('__init__.py','mutations.py','packet.py','startup.bsl','observer.bsl')))
INPUTS=tuple(dict.fromkeys((*base.INPUTS,*OWN)))
PHASES=('create','load','check','update','redump','enterprise')
FAILURES=('none','input','process','timeout','result','witness','native_rejected')

def inventory(root):return {n:base.digest(base.read_regular(root/n)) for n in INPUTS}
def stage(root,target):
    base.source_files(root);hashes=inventory(root);target.mkdir(mode=0o755)
    for n in INPUTS:
        path=target/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(base.read_regular(root/n));path.chmod(0o644)
    for directory in target.rglob('*'):
        if directory.is_dir():directory.chmod(0o755)
    base.require(inventory(target)==hashes)
    return hashes

def command(staged,nonce,case):
    base.require(case in packet.CASES)
    cmd=base.container_command(staged,nonce)
    cmd[cmd.index('--name')+1]='onec-xml-order-'+nonce
    cmd[cmd.index('/smoke/scripts/native_1c_main_demo_designer.sh')]='/smoke/scripts/native_1c_xml_order.sh'
    return cmd+[case]

def operations(root):
    return base.operations(root)+[('redump',[base.ONEC,'DESIGNER','/F',str(root/'db'),
        '/AppAutoCheckVersion-','/DisableStartupDialogs','/DisableStartupMessages','/L','ru',
        '/DumpConfigToFiles',str(root/'redump'),'-Format','Hierarchical',
        '/Out',str(root/'redump.log'),'/DumpResult',str(root/'redump.result')]),
      ('enterprise',[base.ONEC,'ENTERPRISE','/F',str(root/'db'),'/L','ru',
        '/AppAutoCheckVersion-','/DisableStartupDialogs','/DisableStartupMessages',
        '/Out',str(root/'enterprise.log')])]

def designer_result(path):
    raw=base.read_regular(path,128)
    text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig').strip()
    base.require(re.fullmatch('0|[1-9][0-9]{0,8}',text) is not None)
    return int(text)

def empty(nonce,case,hashes,source):
    return dict(schema=SCHEMA,nonce=nonce,case=case,inputs=hashes,source=source,
        completed=[],phase='inputs',failure='input',redump=None,lifecycle='NOT RUN',
        runtime_items_order='NOT RUN',visual_ui='NOT RUN',status='failed')

def native(nonce,case):
    base.require(re.fullmatch('[0-9a-f]{32}',nonce) and case in packet.CASES and os.getuid()==1000)
    files=packet.case_files(base.source_files(ROOT),case)
    report=empty(nonce,case,inventory(ROOT),packet.digest_files(files))
    root=Path('/tmp/xml-order')
    try:
        root.mkdir(mode=0o700);(root/'source').mkdir();(root/'redump').mkdir()
        for n,raw in files.items():
            target=root/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        (root/'trace.json').write_text(json.dumps(dict(nonce=nonce,events=[])))
        for phase,cmd in operations(root):
            report['phase']=phase;report['failure']='process'
            with (root/(phase+'.stdout')).open('xb') as out, (root/(phase+'.stderr')).open('xb') as err:
                code=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','120s',*cmd],
                    stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=135).returncode
            if code in (124,137):report['failure']='timeout'
            base.require(code==0)
            base.native_quiet()
            if phase!='enterprise':
                report['failure']='result'
                result_code=designer_result(root/(phase+'.result'))
                if result_code and phase in ('load','check'):report['failure']='native_rejected'
                base.require(result_code==0)
            if phase=='create':base.require((root/'db/1Cv8.1CD').is_file())
            if phase=='redump':
                actual=base.dump_files(root/'redump')
                try:report['redump']=packet.redump_digest(actual)
                except ValueError:report['redump']=None
            if phase=='enterprise':
                report['failure']='witness'
                report['runtime_items_order']=packet.witness(base.read_regular(root/'trace.json',4096),nonce,case)
                report['lifecycle']='observed'
            report['completed'].append(phase)
        base.require(inventory(ROOT)==report['inputs'] and base.dump_files(root/'source')==files)
        report.update(status='collected',phase='complete',failure='none')
    except subprocess.TimeoutExpired:report['failure']='timeout'
    except Exception:pass
    print(json.dumps(report,sort_keys=True))
    return 0 if report['status']=='collected' else 1

def validate(raw,nonce,case,hashes,source):
    base.require(type(raw) is bytes and len(raw)<=MAX_REPORT)
    value=json.loads(raw,object_pairs_hook=policy.unique)
    expected=empty(nonce,case,hashes,source)
    base.require(type(value) is dict and set(value)==set(expected))
    for key in ('schema','nonce','case','inputs','source','visual_ui'):
        base.require(value[key]==expected[key])
    base.require(value['completed'] in [list(PHASES[:i]) for i in range(7)])
    base.require(value['failure'] in FAILURES and value['lifecycle'] in ('NOT RUN','observed')
        and value['runtime_items_order'] in ('NOT RUN','baseline','changed'))
    base.require(value['redump'] is None or type(value['redump']) is str and re.fullmatch('[0-9a-f]{64}',value['redump']))
    count=len(value['completed'])
    if value['failure']=='native_rejected':base.require(value['phase'] in ('load','check'))
    if value['status']=='collected':
        base.require(count==6 and value['phase']=='complete' and value['failure']=='none'
            and value['lifecycle']=='observed' and value['runtime_items_order']==('changed' if case=='ui_childitems' else 'baseline'))
    else:
        base.require(value['status']=='failed' and value['failure']!='none'
            and ((count==0 and value['phase']=='inputs') or count<6 and value['phase']==PHASES[count] or count==6 and value['phase']=='enterprise'))
        if count<5:base.require(value['lifecycle']=='NOT RUN' and value['runtime_items_order']=='NOT RUN')
    if count<4:base.require(value['redump'] is None)
    return value

def assessment(reports):
    baseline=reports['baseline']; result={}
    ready=baseline['status']=='collected' and baseline['redump'] is not None
    for case,r in reports.items():
        if not ready:result[case]='inconclusive_baseline'
        elif r['failure']=='timeout':result[case]='infrastructure_failed'
        elif case in ('duplicate_property','duplicate_event'):
            result[case]='rejected' if r['phase'] in ('load','check') and r['failure']=='native_rejected' else 'accepted_or_inconclusive_duplicate_never_equivalent'
        elif case=='handler_changed':
            result[case]='rejected' if r['phase'] in ('load','check') and r['failure']=='native_rejected' else 'not_equivalent'
        elif case=='ui_childitems':
            result[case]='runtime_order_distinguished' if r['status']=='collected' and r['runtime_items_order']=='changed' and r['redump'] not in (None,baseline['redump']) else 'inconclusive_ui_control'
        else:
            result[case]='runtime_and_redump_match_visual_pending' if r['status']=='collected' and r['redump']==baseline['redump'] else 'inconclusive_or_different'
    return result

def acquisition_complete(reports):
    if set(reports)!=set(packet.CASES):return False
    results=assessment(reports)
    if any(results[c]!='runtime_and_redump_match_visual_pending' for c in packet.POSITIVE):return False
    if results['ui_childitems']!='runtime_order_distinguished':return False
    for c in ('handler_changed','duplicate_property','duplicate_event'):
        r=reports[c]
        rejected=r['phase'] in ('load','check') and r['failure']=='native_rejected'
        observed=c in ('duplicate_property','duplicate_event') and r['status']=='collected'
        if not (rejected or observed):return False
    return True

def run_host():
    import native_1c_docker_lifecycle as lifecycle
    import native_1c_smoke as smoke
    source_sha,tree=base.revision();base.require(policy.check_environment()==source_sha)
    base.require(IMAGE==smoke.IMAGE and VERSION==smoke.EXPECTED_VERSION)
    run_id,attempt=os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT')
    base.require(all(type(x) is str and re.fullmatch('[1-9][0-9]{0,19}',x) for x in (run_id,attempt)))
    token,actor=os.environ.pop('GHCR_TOKEN',''),os.environ.pop('GHCR_USER','')
    base.require(token and re.fullmatch('[A-Za-z0-9-]{1,39}',actor))
    reports={}
    with tempfile.TemporaryDirectory(prefix='onec-xml-order-') as directory:
        work=Path(directory).resolve();staged=work/'staged';hashes=stage(ROOT,staged)
        auth=work/'auth';auth.mkdir(mode=0o700)
        try:
            env=smoke.docker_environment(auth)
            smoke.run_silent(['docker','login','ghcr.io','--username',actor,'--password-stdin'],env,60,token.encode());token=''
            smoke.run_silent(['docker','pull','--platform','linux/amd64',IMAGE],env,600)
        finally:token='';shutil.rmtree(auth)
        clean=work/'no-auth';clean.mkdir(mode=0o700)
        files=base.source_files(ROOT)
        for case in packet.CASES:
            nonce=uuid.uuid4().hex
            code,raw=lifecycle.run_owned(command(staged,nonce,case),smoke.docker_environment(clean),
                name='onec-xml-order-'+nonce,nonce=nonce,image=IMAGE,seconds=850,output_limit=MAX_REPORT)
            report=validate(raw,nonce,case,hashes,packet.digest_files(packet.case_files(files,case)))
            base.require(code==(0 if report['status']=='collected' else 1))
            report.pop('nonce');reports[case]=report
            # Baseline failure cannot justify seven more native runs.
            if case=='baseline' and report['status']!='collected':break
        base.require(inventory(ROOT)==hashes and inventory(staged)==hashes and base.revision()==(source_sha,tree))
    return dict(schema=SCHEMA+'-host',source_sha=source_sha,source_tree=tree,
        github_run_id=run_id,github_run_attempt=attempt,image=IMAGE,expected_version=VERSION,
        cases=reports,assessment=assessment(reports),acquisition_complete=acquisition_complete(reports),visual_ui='NOT RUN',semantic_acceptance='NOT PROVEN',
        container_cleanup_verified=True,docker_cli_reap_verified=True,private_payloads_removed=True)

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--inside-container':raise SystemExit(native(sys.argv[2],sys.argv[3]))
    if sys.argv[1:]!=['--execute-approved-image']:raise SystemExit('Exact owner-reviewed source required.')
    try:
        result=run_host();encoded=json.dumps(result,sort_keys=True)
        base.require(len(encoded.encode())<=MAX_HOST_REPORT)
        print(encoded)
        raise SystemExit(0 if result['acquisition_complete'] else 1)
    except Exception as error:
        value=base.failure_report(error);value['schema']=SCHEMA+'-host';print(json.dumps(value));raise SystemExit(1)
