"""Закрытая проекция ошибки запуска; не содержит текста или путей."""
import re

MAX_LOG = 65536
CATEGORIES = frozenset({'none','unknown','compile_error','runtime_error','unsupported_api',
    'permission_denied','authentication_failed','license_unavailable','training_restriction',
    'startup_failed','evidence_invalid','conflicting_evidence'})
# Exact reviewed packet limits, including inserted/appended owned source.
LIMITS = {'SessionModule':287,'ManagedApplicationModule':180,
          'ClientProbe':82,'ServerProbe':91,'DualProbe':91}
ALIASES = {'МодульСеанса':'SessionModule','SessionModule':'SessionModule',
           'МодульУправляемогоПриложения':'ManagedApplicationModule',
           'ManagedApplicationModule':'ManagedApplicationModule'}
for _name in ('ClientProbe','ServerProbe','DualProbe'):
    for _prefix, _suffix in (('ОбщийМодуль.','.Модуль'),('CommonModule.','.Module')):
        ALIASES[_prefix+_name+_suffix]=_name
LOCATION = re.compile(r'\{('+ '|'.join(map(re.escape,ALIASES))+r')\(([0-9]{1,4})(?:,\s*[0-9]{1,4})?\)\}')
OWNED_IDENTIFIERS = frozenset({'Client','Server','AtClient','AtServer',
    'MobileAppClient','MobileAppServer','Клиент','Сервер','НаКлиенте','НаСервере',
    'МобильноеПриложениеКлиент','МобильноеПриложениеСервер','CPState','CPStartup',
    'CPMaskEN','CPMaskRU','CPMobileEN','CPMobileRU','ClientProbe','ServerProbe','DualProbe',
    'ClientExport','ServerExport'})
COMPILE_PHRASES = ('неизвестная инструкция препроцессора', 'неизвестный оператор',
    'неизвестная директива препроцессора', 'unknown preprocessor instruction',
    'unknown preprocessor directive', 'ожидается ключевое слово', 'expected keyword')

def summarize(text, sanitizer):
    summary=sanitizer.summarize_text(text)
    value={key:summary[key] for key in empty()}
    extra=any(phrase in text.casefold() for phrase in COMPILE_PHRASES)
    if extra:
        value['category']='compile_error' if value['category'] in ('unknown','compile_error','runtime_error','startup_failed') else 'conflicting_evidence'
    if value['category'] in ('none','evidence_invalid','conflicting_evidence'):
        return {**empty(),'category':value['category']}
    phrases=tuple(sanitizer.PHRASES.get(value['category'],())) + (COMPILE_PHRASES if value['category']=='compile_error' else ())
    details=set()
    for record in text.splitlines():
        if value['category']!='unknown' and not any(p in record.casefold() for p in phrases):continue
        matches=list(LOCATION.finditer(record))
        frames=re.findall(r'\{[^{}\r\n]{1,200}\([0-9]{1,4}(?:,\s*[0-9]{1,4})?\)\}',record)
        module=line=None
        if len(matches)==len(frames)==1:
            candidate=ALIASES[matches[0][1]];number=int(matches[0][2])
            if 1<=number<=LIMITS[candidate]:module,line=candidate,number
        candidates={m[1].strip() for pattern in sanitizer.IDENTIFIER_PATTERNS for m in re.finditer(pattern,record,re.I)}
        identifier=next(iter(candidates)) if len(candidates)==1 and candidates <= (sanitizer.IDENTIFIERS|OWNED_IDENTIFIERS) else None
        details.add((module,line,identifier))
    module,line,identifier=next(iter(details)) if len(details)==1 else (None,None,None)
    return {'category':value['category'],'module':module,'line':line,'identifier':identifier}


def empty():
    return {'category':'none','module':None,'line':None,'identifier':None}

def validate(value, identifiers):
    if type(value) is not dict or set(value) != set(empty()): raise ValueError('diagnostic keys')
    if type(value['category']) is not str or value['category'] not in CATEGORIES: raise ValueError('diagnostic category')
    module,line,identifier=value['module'],value['line'],value['identifier']
    if module is None:
        if line is not None: raise ValueError('diagnostic line')
    elif type(module) is not str or module not in LIMITS or type(line) is not int or not 1 <= line <= LIMITS[module]:
        raise ValueError('diagnostic location')
    if identifier is not None and (type(identifier) is not str or identifier not in (identifiers | OWNED_IDENTIFIERS)): raise ValueError('diagnostic identifier')
    if value['category'] in ('none','evidence_invalid','conflicting_evidence') and any(x is not None for x in (module,line,identifier)):
        raise ValueError('diagnostic detail')
    return value

def collect(root, full, sanitizer, *, label="enterprise"):
    if label not in ("enterprise","check"): raise ValueError("diagnostic origin")
    # Caller supplies its exclusive TemporaryDirectory root, never a path from1C.
    # secure_bytes rejects links/nonregular files and enforces read/stat bounds.
    try:
        raw=full.secure_bytes(root/(label+'.log'),MAX_LOG)
        summary=summarize(sanitizer.native_text(raw),sanitizer)
        value={key:summary[key] for key in empty()}
        return validate(value,sanitizer.IDENTIFIERS)
    except (OSError,ValueError,full.FullError):
        return {**empty(),'category':'evidence_invalid'}
