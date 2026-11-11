"""Exactly twelve bounded raw scalar observations, no expected behavior."""
from pathlib import Path
import hashlib
import json
import re
PROFILE='document-posting-observation-v1'
SCHEMA='native-1c-document-posting-v1'
STAGE_SCHEMA='native-1c-document-posting-stage-v1'
COUNT=12
MAX_OUTPUT=16384
SOURCE_SHA256='405c94d686297f96488673f8d6bd8f7279b891d6ef6c0829744c4f316db0850d'
def source():
    p=Path(__file__).with_name('observe.bsl')
    if p.is_symlink():raise ValueError('source symlink')
    raw=p.read_bytes()
    if not 0<len(raw)<=MAX_OUTPUT or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:raise ValueError('source changed')
    return raw

def program(setup,nonce):
    if type(nonce) is not str or re.fullmatch('[0-9a-f]{32}',nonce) is None:raise ValueError('nonce')
    prefix=('Procedure PostingEmit(N,V)\nMessage("POST|'+nonce+'|"+String(N)+"|"+V);\nEndProcedure\n').encode()
    body=source();marker=b'For CaseNo = 1 To 12 Do'
    if body.count(marker)!=1:raise ValueError('source body boundary')
    declarations,statements=body.split(marker)
    entered=('Message("POST|'+nonce+'|entered");\n').encode()
    return prefix+declarations+entered+marker+statements+('Message("POST|'+nonce+'|completed");\n').encode()

def canonical(values):
    if type(values) is not list or len(values)!=COUNT or any(type(v) is not str or len(v)>512 or re.fullmatch(r'[A-Za-z0-9,;:| .-]+',v) is None for v in values):raise ValueError('observations')
    return (json.dumps(values,separators=(',',':'))+'\n').encode('ascii')

def parse_wire(raw,nonce):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT or re.fullmatch('[0-9a-f]{32}',nonce) is None:raise ValueError('wire')
    lines=raw.decode('ascii').splitlines();prefix='POST|'+nonce+'|'
    if len(lines)!=COUNT+2 or lines[0]!=prefix+'entered' or lines[-1]!=prefix+'completed':raise ValueError('markers')
    values=[]
    for n,line in enumerate(lines[1:-1],1):
        expected=prefix+str(n)+'|'
        if not line.startswith(expected):raise ValueError('order')
        values.append(line[len(expected):])
    canonical(values);return values

ERROR_APIS={'Write':'write','Записать':'write','Execute':'execute','Выполнить':'execute',
    'GetObject':'get_object','ПолучитьОбъект':'get_object','Select':'select','Выбрать':'select',
    'Next':'next','Следующий':'next','Number':'number','Число':'number',
    'RegisterRecords':'movements','Движения':'movements','Active':'active','Активность':'active'}
ERROR_CODES={'query':'ошибка в запросе','field_not_found':'поле объекта не обнаружено',
    'method_not_found':'метод объекта не обнаружен','not_object':'не является значением объектного типа',
    'permission':'недостаточно прав','conversion':'преобразование значения',
    'invalid_argument':'недопустимое значение параметра','object_absent':'объект не найден',
    'transaction':'транзакц','module':'модул','compile':'синтаксическ'}

def failure_details(result,nonce):
    """Finite error vocabulary and trusted source locations, no native text."""
    if type(result) is not dict or set(result)!={'messages','error'} or type(result['error']) is not str or len(result['error'])>16384:
        raise ValueError('invalid failure envelope')
    text=result['error'];messages=result['messages'];prefix='POST|'+nonce+'|'
    if type(messages) is not list or len(messages)>14 or any(type(m) is not str or len(m)>1024 for m in messages):
        raise ValueError('invalid failure messages')
    entered=bool(messages and messages[0]==prefix+'entered');cases=0
    for n,message in enumerate(messages[1:],1):
        if n>12 or not message.startswith(prefix+str(n)+'|'):break
        cases=n
    frames=[]
    for match in re.finditer(r'\{([^{}\r\n]{1,200})\(([0-9]{1,3})(?:,\s*[0-9]{1,3})?\)\}',text):
        module=next((name for name in ('TestModule','OwnedPostingDoc') if name in match[1]),None)
        if module is not None and 1<=int(match[2])<=512 and len(frames)<4:frames.append([module,int(match[2])])
    apis=sorted({value for key,value in ERROR_APIS.items() if re.search(r'\('+re.escape(key)+r'\)',text)})
    return dict(entered=entered,cases=cases,frames=frames,apis=apis,
                codes=sorted(key for key,value in ERROR_CODES.items() if value in text.casefold()))

def valid_failure_details(value):
    return (type(value) is dict and set(value)=={'entered','cases','frames','apis','codes'} and
        type(value['entered']) is bool and type(value['cases']) is int and 0<=value['cases']<=12 and
        type(value['frames']) is list and len(value['frames'])<=4 and all(type(f) is list and len(f)==2 and
            f[0] in ('TestModule','OwnedPostingDoc') and type(f[1]) is int and 1<=f[1]<=512 for f in value['frames']) and
        type(value['apis']) is list and len(value['apis'])<=len(ERROR_APIS) and all(type(a) is str and a in ERROR_APIS.values() for a in value['apis']) and
        type(value['codes']) is list and len(value['codes'])<=len(ERROR_CODES) and all(type(c) is str and c in ERROR_CODES for c in value['codes']))
