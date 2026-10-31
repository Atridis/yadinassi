"""One bounded read-only compile check after a failed owned session stops.

Reuses the existing finite compiler projection; never exports native log text.
Marker inventory is captured before launch cleanup and never weakens admission.
"""
import re
from protocol import require, exact
from snapshots import OracleError
from metadata_catalog_runtime_inputs import _read
from catalog_zero_code_measurement import compile_log_projection, COMPILE_CATEGORIES, COMPILE_MODULES, COMPILE_STATES

MARKERS=('control','result','completion','completion.pending')
PHASES=('authorize','identity','metadata','observe','setup','serialize','complete',
        'setup-calibration-one','setup-calibration-two','setup-query-build',
        'setup-query-execute','setup-query-row','setup-manager','setup-mutate',
        *(f'setup-witness-{i:02}' for i in range(1,13)))


def read(path, maximum):
    try:
        path.lstat()
    except FileNotFoundError:
        return 'absent',None
    try:
        raw=_read(path,maximum)
        return ('nonempty' if raw else 'empty'),raw
    except BaseException:
        return 'unavailable',None


def collect(backend,database,previous):
    value=(dict(previous) if previous is not None else
           dict(site='process',phase=None,status=None,operation_matches=None))
    value['markers']={name:read(backend.evidence/(name+'.json'),98304 if name=='result' else 4096)[0] for name in MARKERS}
    compile=dict(state='unavailable',result_code=None,log_state='unavailable',issues=[],truncated=False)
    value['compile']=compile
    try:
        require(backend.quiescent(),'snapshot_not_quiescent')
        backend.remaining();backend.budgets()
        log=backend.evidence/f'{backend.counter+1:03}-catalog-compile.log'
        result=backend.evidence/f'{backend.counter+1:03}-catalog-compile.result'
        from run import absent,SETUP_USER
        absent(log,result)
        args=backend.command('DESIGNER',database,SETUP_USER)+['/CheckConfig','-ThickClientManagedApplication','-Server','/Out',str(log),'/DumpResult',str(result)]
        compile['state']='completed'
        try:backend.process(args,'catalog-compile')
        except OracleError as error:
            if error.kind not in ('process_failed','timeout'):raise
            compile['state']=error.kind
        require(backend.quiescent(),'snapshot_not_quiescent');backend.budgets()
        _,raw=read(result,64)
        if raw is not None:
            text=raw.decode('utf-8-sig').strip()
            if re.fullmatch('-?[0-9]{1,3}',text) and -1<=int(text)<=255:compile['result_code']=int(text)
        state,raw=read(log,32768)
        compile.update(compile_log_projection(raw) if raw is not None else dict(log_state=state,issues=[],truncated=False))
        backend.budgets();require(backend.quiescent(),'snapshot_not_quiescent')
    except BaseException:
        # Failure of optional diagnostics never replaces the primary failure.
        compile.update(state='unavailable')
    validate(value)
    return value


def validate(value):
    exact(value,('site','phase','status','operation_matches','markers','compile'))
    require(value['site'] in ('process','completion','output'))
    if value['site']=='process':require(value['phase'] is None and value['status'] is None and value['operation_matches'] is None)
    else:require(value['phase'] in PHASES and value['status'] in ('ok','error') and type(value['operation_matches']) is bool)
    exact(value['markers'],MARKERS)
    require(all(v in ('absent','empty','nonempty','unavailable') for v in value['markers'].values()))
    item=value['compile'];exact(item,('state','result_code','log_state','issues','truncated'))
    require(item['state'] in COMPILE_STATES and item['log_state'] in ('absent','empty','nonempty','unavailable'))
    require(item['result_code'] is None or type(item['result_code']) is int and -1<=item['result_code']<=255)
    require(type(item['issues']) is list and len(item['issues'])<=8 and type(item['truncated']) is bool)
    require(not item['truncated'] or len(item['issues'])==8)
    require(item['log_state']=='nonempty' or item['issues']==[] and item['truncated'] is False)
    for issue in item['issues']:
        exact(issue,('module','line','column','category'))
        require(issue['module'] in COMPILE_MODULES and issue['category'] in COMPILE_CATEGORIES)
        require(all(type(issue[k]) is int and 0<=issue[k]<=65535 for k in ('line','column')))
        require((issue['line']==issue['column']==0) if issue['module']=='other' else issue['line']>0 and issue['column']>0)
    require(len({tuple(i[k] for k in ('module','line','column','category')) for i in item['issues']})==len(item['issues']))
    return value
