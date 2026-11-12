"""Конечные свидетельства загруженных модулей и проверки файлового клиента."""
import hashlib
import re
from . import route
PATHS=('Ext/ManagedApplicationModule.bsl','Ext/SessionModule.bsl',
       'CommonModules/ClientProbe/Ext/Module.bsl','CommonModules/ServerProbe/Ext/Module.bsl',
       'CommonModules/DualProbe/Ext/Module.bsl')
MAX_MODULE=65536

def empty_sources():
    return {p:{'expected_sha256':None,'actual_sha256':None,'matched':None} for p in PATHS}

def empty_check():
    return {'status':'not_checked','result':'not_checked','process_success':False}

def inspect_sources(directory, expected, full):
    result=empty_sources()
    for path in PATHS:
        wanted=expected[path]
        if type(wanted) is not bytes or not 0<len(wanted)<=MAX_MODULE: raise ValueError('source budget')
        result[path]['expected_sha256']=hashlib.sha256(route.normalized(wanted)).hexdigest()
        try:
            actual=full.secure_bytes(directory/path,MAX_MODULE)
            result[path]['actual_sha256']=hashlib.sha256(route.normalized(actual)).hexdigest()
            result[path]['matched']=result[path]['actual_sha256']==result[path]['expected_sha256']
        except (OSError,ValueError,full.FullError):
            result[path]['matched']=False
    return result

def result_state(path,full):
    try:
        raw=full.secure_bytes(path,128)
        text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig').strip()
        if not re.fullmatch(r'[+-]?[0-9]{1,10}',text):return 'invalid'
        return 'zero' if int(text)==0 else 'nonzero'
    except (OSError,ValueError,full.FullError):return 'invalid'

def validate(sources,check):
    if type(sources) is not dict or set(sources)!=set(PATHS):raise ValueError('source keys')
    for item in sources.values():
        if type(item) is not dict or set(item)!={'expected_sha256','actual_sha256','matched'}:raise ValueError('source shape')
        for key in ('expected_sha256','actual_sha256'):
            value=item[key]
            if value is not None and (type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value)):raise ValueError('source digest')
        matched=item['matched']
        if matched is not None and type(matched) is not bool:raise ValueError('source flag')
        if matched is None and any(item[k] is not None for k in ('expected_sha256','actual_sha256')):raise ValueError('unmeasured source')
        if matched is not None and item['expected_sha256'] is None:raise ValueError('unbound source')
        if matched is not None and matched != (item['actual_sha256'] is not None and item['actual_sha256']==item['expected_sha256']):raise ValueError('source disagreement')
    if type(check) is not dict or set(check)!=set(empty_check()):raise ValueError('check keys')
    if type(check['status']) is not str or check['status'] not in ('not_checked','passed','failed'):raise ValueError('check status')
    if type(check['result']) is not str or check['result'] not in ('not_checked','zero','nonzero','invalid'):raise ValueError('check result')
    if type(check['process_success']) is not bool:raise ValueError('check process')
    if check['status']=='not_checked' and check!=empty_check():raise ValueError('unmeasured check')
    if check['status']=='passed' and (check['result']!='zero' or not check['process_success']):raise ValueError('check acceptance')
    if check['status']!='not_checked' and check['result']=='not_checked':raise ValueError('missing check result')
    if check['status']!='not_checked' and not all(item['matched'] is True for item in sources.values()):raise ValueError('check before source admission')

def accepted(sources,check):
    validate(sources,check)
    return all(item['matched'] is True for item in sources.values()) and check['status']=='passed'
