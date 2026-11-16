"""Two independent A/A databases; two consecutive dumps each; no ENTERPRISE."""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_1c_xml_order as parent
from native_1c_xml_order import base,policy,packet
from xml_order_packet import measurement as measure
ROOT=Path(__file__).resolve().parents[1]
SCHEMA='native-xml-order-aa-v1'
PHASES=('create','load','check','update','dump1','dump2')
CASES=('aa1','aa2')
MAX_REPORT=196608
MAX_HOST_REPORT=524288
INPUTS=tuple(dict.fromkeys((*parent.INPUTS,'scripts/native_1c_xml_order_aa.py',
    'scripts/native_1c_xml_order_aa.sh','scripts/xml_order_packet/measurement.py')))

def inventory(root):return {n:base.digest(base.read_regular(root/n)) for n in INPUTS}
def stage(target):
    base.source_files(ROOT);hashes=inventory(ROOT);target.mkdir(mode=0o755)
    for n in INPUTS:
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base.read_regular(ROOT/n));p.chmod(0o644)
    for p in target.rglob('*'):
        if p.is_dir():p.chmod(0o755)
    base.require(inventory(target)==hashes)
    return hashes

def command(staged,nonce,case):
    base.require(case in CASES)
    cmd=parent.command(staged,nonce,'baseline')
    cmd[cmd.index('--name')+1]='onec-xml-order-aa-'+nonce
    cmd[cmd.index('/smoke/scripts/native_1c_xml_order.sh')]='/smoke/scripts/native_1c_xml_order_aa.sh'
    cmd[-1]=case
    return cmd

def operations(root):
    ops=base.operations(root)
    for phase in ('dump1','dump2'):
        ops.append((phase,[base.ONEC,'DESIGNER','/F',str(root/'db'),'/AppAutoCheckVersion-',
            '/DisableStartupDialogs','/DisableStartupMessages','/L','ru',
            '/DumpConfigToFiles',str(root/phase),'-Format','Hierarchical',
            '/Out',str(root/(phase+'.log')),'/DumpResult',str(root/(phase+'.result'))]))
    return ops

def empty(nonce,case,hashes,source):
    return dict(schema=SCHEMA,nonce=nonce,case=case,inputs=hashes,source=source,
        completed=[],phase='inputs',failure='input',status='failed',dumps=[],enterprise_executed=False)

def native(nonce,case):
    base.require(re.fullmatch('[0-9a-f]{32}',nonce) and case in CASES and os.getuid()==1000)
    files=packet.baseline(base.source_files(ROOT));report=empty(nonce,case,inventory(ROOT),packet.digest_files(files))
    root=Path('/tmp/xml-order-aa')
    try:
        root.mkdir(mode=0o700)
        for d in ('source','dump1','dump2'):(root/d).mkdir()
        for n,raw in files.items():
            p=root/'source'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        for phase,cmd in operations(root):
            report['phase']=phase;report['failure']='process'
            with (root/(phase+'.stdout')).open('xb') as out,(root/(phase+'.stderr')).open('xb') as err:
                code=subprocess.run(['timeout','--signal=TERM','--kill-after=5s','120s',*cmd],
                    stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=135).returncode
            if code in (124,137):report['failure']='timeout'
            base.require(code==0);base.native_quiet()
            report['failure']='result';base.require(parent.designer_result(root/(phase+'.result'))==0)
            if phase=='create':base.require((root/'db/1Cv8.1CD').is_file())
            if phase.startswith('dump'):
                report['failure']='diagnostic'
                fp=measure.fingerprint(base.dump_files(root/phase),known_names=files)
                measure.validate(fp,known_names=files);report['dumps'].append(fp)
            report['completed'].append(phase)
        base.require(inventory(ROOT)==report['inputs'] and base.dump_files(root/'source')==files)
        report.update(status='collected',phase='complete',failure='none')
    except subprocess.TimeoutExpired:report['failure']='timeout'
    except Exception:pass
    encoded=json.dumps(report,sort_keys=True);base.require(len(encoded.encode())<=MAX_REPORT)
    print(encoded)
    return 0 if report['status']=='collected' else 1

def validate(raw,nonce,case,hashes,files):
    base.require(type(raw)==bytes and len(raw)<=MAX_REPORT)
    r=json.loads(raw,object_pairs_hook=policy.unique)
    expected=empty(nonce,case,hashes,packet.digest_files(files))
    base.require(type(r)==dict and set(r)==set(expected))
    for k in ('schema','nonce','case','inputs','source','enterprise_executed'):base.require(r[k]==expected[k] and (k!='enterprise_executed' or r[k] is False))
    base.require(r['completed'] in [list(PHASES[:n]) for n in range(7)])
    base.require(type(r['dumps'])==list and len(r['dumps'])==max(0,len(r['completed'])-4))
    for fp in r['dumps']:measure.validate(fp,known_names=files)
    if r['status']=='collected':base.require(r['completed']==list(PHASES) and r['phase']=='complete' and r['failure']=='none')
    else:
        n=len(r['completed'])
        base.require(r['status']=='failed' and r['failure'] in ('input','process','timeout','result','diagnostic'))
        base.require((n==0 and r['phase']=='inputs') or n<6 and r['phase']==PHASES[n] or n==6 and r['phase']=='dump2')
    return r

def comparisons(reports):
    result={}
    for case,r in reports.items():
        if len(r['dumps'])==2:result[case+'_repeat']=measure.compare(*r['dumps'])
    if all(c in reports and reports[c]['status']=='collected' for c in CASES):
        for i in range(2):result['cross_dump'+str(i+1)]=measure.compare(reports['aa1']['dumps'][i],reports['aa2']['dumps'][i])
    return result

def run_host():
    import native_1c_docker_lifecycle as lifecycle
    import native_1c_smoke as smoke
    source_sha,tree=base.revision();base.require(policy.check_environment()==source_sha)
    base.require(base.IMAGE==smoke.IMAGE and base.VERSION==smoke.EXPECTED_VERSION)
    run_id,attempt=os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT')
    base.require(all(type(x)==str and re.fullmatch('[1-9][0-9]{0,19}',x) for x in (run_id,attempt)))
    token,actor=os.environ.pop('GHCR_TOKEN',''),os.environ.pop('GHCR_USER','')
    base.require(token and re.fullmatch('[A-Za-z0-9-]{1,39}',actor))
    reports={}
    with tempfile.TemporaryDirectory(prefix='onec-xml-order-aa-') as directory:
        work=Path(directory).resolve();staged=work/'staged';hashes=stage(staged)
        auth=work/'auth';auth.mkdir(mode=0o700)
        try:
            env=smoke.docker_environment(auth)
            smoke.run_silent(['docker','login','ghcr.io','--username',actor,'--password-stdin'],env,60,token.encode());token=''
            smoke.run_silent(['docker','pull','--platform','linux/amd64',base.IMAGE],env,600)
        finally:token='';shutil.rmtree(auth)
        clean=work/'no-auth';clean.mkdir(mode=0o700);files=packet.baseline(base.source_files(ROOT))
        for case in CASES:
            nonce=uuid.uuid4().hex
            code,raw=lifecycle.run_owned(command(staged,nonce,case),smoke.docker_environment(clean),
                name='onec-xml-order-aa-'+nonce,nonce=nonce,image=base.IMAGE,seconds=850,output_limit=MAX_REPORT)
            report=validate(raw,nonce,case,hashes,files)
            base.require(code==(0 if report['status']=='collected' else 1));report.pop('nonce');reports[case]=report
            if report['status']!='collected':break
        base.require(inventory(ROOT)==hashes and inventory(staged)==hashes and base.revision()==(source_sha,tree))
    return dict(schema=SCHEMA+'-host',source_sha=source_sha,source_tree=tree,image=base.IMAGE,
        github_run_id=run_id,github_run_attempt=attempt,expected_version=base.VERSION,
        cases=reports,comparisons=comparisons(reports),acquisition_complete=len(reports)==2 and all(r['status']=='collected' for r in reports.values()),
        semantic_acceptance='NOT PROVEN',visual_ui='NOT RUN',enterprise_executed=False,
        container_cleanup_verified=True,docker_cli_reap_verified=True,private_payloads_removed=True)

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--inside-container':raise SystemExit(native(sys.argv[2],sys.argv[3]))
    if sys.argv[1:]!=['--execute-approved-image']:raise SystemExit('Exact owner-reviewed source required.')
    try:
        r=run_host();encoded=json.dumps(r,sort_keys=True);base.require(len(encoded.encode())<=MAX_HOST_REPORT)
        print(encoded);raise SystemExit(0 if r['acquisition_complete'] else 1)
    except Exception as error:
        r=base.failure_report(error);r['schema']=SCHEMA+'-host';print(json.dumps(r));raise SystemExit(1)
