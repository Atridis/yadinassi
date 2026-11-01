"""Raw register observations and guarded readonly runtime comparison."""
from information_register_fixture import BLOCKS,load,validate_capture
from linked_card_packet.base import scalar_wire


_STAGES=('physical-observe','runtime-execute','compare')
_CATEGORIES=('catalog_error','value_error','type_error','import_error','resource_limit','unsupported_sharing')
_CODES=('descriptor_shape','descriptor_section','recordlock_shape','files_shape',
    'field_shape','field_attributes','descriptor_token','descriptor_utf8',
    'descriptor_unclosed_list','descriptor_unclosed_string')
_LOCATIONS={
    'information_register_physical': 'information_register_physical.py',
    'document_read_physical': 'document_read_physical.py',
    'linked_card_physical': 'linked_card_physical.py',
    'yadinassi.storage.filedb_catalog': 'filedb_catalog.py',
    'yadinassi.storage.config_catalog_transport': 'config_catalog_transport.py',
    'yadinassi.storage.filedb_dbnames': 'filedb_dbnames.py',
}
_SKIP_FRAMES=('_check','_exact','_integer','_uuid','_digest')


def validate_failure(value):
    if type(value) is not dict or set(value)!={'stage','category','code','location'}:
        raise ValueError('offline-failure-profile')
    if (type(value['stage']) is not str or value['stage'] not in _STAGES
            or type(value['category']) is not str or value['category'] not in _CATEGORIES):
        raise ValueError('offline-failure-profile')
    code=value['code']
    if code is not None and (type(code) is not str or code not in _CODES or value['category']!='catalog_error'):
        raise ValueError('offline-failure-profile')
    location=value['location']
    if location is not None:
        if (type(location) is not dict or set(location)!={'filename','line'}
                or type(location['filename']) is not str or location['filename'] not in _LOCATIONS.values()
                or type(location['line']) is not int or not 1<=location['line']<=5000):
            raise ValueError('offline-failure-profile')
    return value


class OfflineFailure(Exception):
    def __init__(self,diagnostic):
        validate_failure(diagnostic)
        self.diagnostic=dict(diagnostic)
        if diagnostic['location'] is not None:self.diagnostic['location']=dict(diagnostic['location'])
        super().__init__('offline-measurement-failed')


def _location(error):
    from pathlib import Path
    result=None;tb=error.__traceback__
    while tb is not None:
        frame=tb.tb_frame;module=frame.f_globals.get('__name__');filename=_LOCATIONS.get(module)
        if (filename is not None and Path(frame.f_code.co_filename).name==filename
                and frame.f_code.co_name not in _SKIP_FRAMES and 1<=tb.tb_lineno<=5000):
            result=dict(filename=filename,line=tb.tb_lineno)
        tb=tb.tb_next
    return result


def _attempt(stage,operation):
    from yadinassi.storage import filedb_catalog as c
    # OracleError and source-integrity CatalogError families deliberately
    # propagate. Diagnostics never turn an integrity failure into success.
    try:return operation()
    except (c.InvalidStructure,c.UnsupportedLayout,c.ResourceLimit,c.UnsupportedSharing,ValueError,TypeError,ImportError) as error:
        if isinstance(error,(c.InvalidStructure,c.UnsupportedLayout)):
            category='catalog_error';code=error.code if type(error.code) is str and error.code in _CODES else None
        elif isinstance(error,(c.ResourceLimit,c.UnsupportedSharing)):
            category='resource_limit' if isinstance(error,c.ResourceLimit) else 'unsupported_sharing';code=None
        else:
            category='value_error' if isinstance(error,ValueError) else 'type_error' if isinstance(error,TypeError) else 'import_error'
            code=None
        raise OfflineFailure(dict(stage=stage,category=category,code=code,location=_location(error))) from None


def compare(actual,native,s,block):
    left=scalar_wire.validate_output(actual);right=scalar_wire.validate_output(native)
    available=validate_capture(native,s,block)['availability']=='available'
    matched=[i for i,(a,b) in enumerate(zip(left,right),1) if a==b]
    missing=[i for i in range(1,25) if i not in matched]
    return dict(mode='deterministic',matched=not missing and available,
        matched_ids=matched,mismatched_ids=missing)


def execute(database,s):
    from yadinassi import Interpreter
    from yadinassi.database_context import FileDBContext
    from yadinassi.native_targets import LINUX_8_3_27_1508
    files=next(files for repeat in (1,2) for setup,_,files in (load(repeat),) if setup==s)
    output={}
    for block in BLOCKS:
        lines=[];interpreter=Interpreter(output=lines.append,database_context=FileDBContext(database),native_target=LINUX_8_3_27_1508)
        try:interpreter.execute(files[block+'.bsl'].decode('utf-8'),source='information-register-'+block+'.bsl')
        finally:interpreter.close()
        raw=('\n'.join(lines)+'\n').encode('ascii');validate_capture(raw,s,block);output[block]=raw.decode('ascii')
    return output


def readback(read_at,size,database,s,native,mapping):
    from information_register_physical import observe
    _,manifest,_=next(x for repeat in (1,2) for x in (load(repeat),) if x[0]==s)
    physical=_attempt('physical-observe',lambda:observe(read_at,size,manifest['profile'],mapping))
    actual=_attempt('runtime-execute',lambda:execute(database,s))
    comparisons=_attempt('compare',lambda:{block:compare(actual[block].encode('ascii'),native[block].encode('ascii'),s,block) for block in BLOCKS})
    return dict(physical=physical,outputs=actual,comparison=comparisons)
