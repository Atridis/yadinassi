"""Закрытая проекция ошибки запуска; не содержит текста или путей."""
MAX_LOG = 65536
CATEGORIES = frozenset({'none','unknown','compile_error','runtime_error','unsupported_api',
    'permission_denied','authentication_failed','license_unavailable','training_restriction',
    'startup_failed','evidence_invalid','conflicting_evidence'})
LIMITS = {'SessionModule':202,'ManagedApplicationModule':89}

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
    if identifier is not None and (type(identifier) is not str or identifier not in identifiers): raise ValueError('diagnostic identifier')
    if value['category'] in ('none','evidence_invalid','conflicting_evidence') and any(x is not None for x in (module,line,identifier)):
        raise ValueError('diagnostic detail')
    return value

def collect(root, full, sanitizer):
    # Caller supplies its exclusive TemporaryDirectory root, never a path from1C.
    # secure_bytes rejects links/nonregular files and enforces read/stat bounds.
    try:
        raw=full.secure_bytes(root/'enterprise.log',MAX_LOG)
        summary=sanitizer.summarize_text(sanitizer.native_text(raw))
        value={key:summary[key] for key in empty()}
        return validate(value,sanitizer.IDENTIFIERS)
    except (OSError,ValueError,full.FullError):
        return {**empty(),'category':'evidence_invalid'}
