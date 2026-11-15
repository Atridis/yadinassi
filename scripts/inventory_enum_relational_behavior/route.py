"""Exactly twelve bounded raw scalar observations, no expected behavior."""
from pathlib import Path
import hashlib
import json
import re
PROFILE='inventory-enum-relational-observation-v1'
SCHEMA='native-1c-inventory-enum-relational-v1'
STAGE_SCHEMA='native-1c-inventory-enum-relational-stage-v1'
COUNT=12
MAX_OUTPUT=131072
SOURCE_SHA256='71f1709cec2c9f1b8eba46698eae93195af779ec389c60c6a34b6c04f28fd4f8'
def source():
    p=Path(__file__).with_name('observe.bsl')
    if p.is_symlink():raise ValueError('source symlink')
    raw=p.read_bytes()
    if not 0<len(raw)<=MAX_OUTPUT or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:raise ValueError('source changed')
    return raw

def program(setup,nonce):
    if type(nonce) is not str or re.fullmatch('[0-9a-f]{32}',nonce) is None:raise ValueError('nonce')
    prefix=('Procedure AccumulationEmit(N,V)\nMessage("ERQ|'+nonce+'|"+String(N)+"|"+V);\nEndProcedure\n').encode()
    prefix+=('Procedure AccumulationDiagnostic(N,Stage,Details)\n'
        'If StrLen(Details)>4096 Then Details=Left(Details,2048)+Right(Details,2048); EndIf;\n'
        'Writer=New JSONWriter; Writer.SetString(); WriteJSON(Writer,Details); Encoded=Writer.Close();\n'
        'Message("ERQ|'+nonce+'|error|"+String(N)+"|"+Stage+"|"+Encoded);\nEndProcedure\n').encode()
    body=source();marker=b'For CaseNo = 1 To 12 Do'
    if body.count(marker)!=1:raise ValueError('source body boundary')
    declarations,statements=body.split(marker)
    entered=('Message("ERQ|'+nonce+'|entered");\n').encode()
    return prefix+declarations+entered+marker+statements+('Message("ERQ|'+nonce+'|completed");\n').encode()

def canonical(values):
    if type(values) is not list or len(values)!=COUNT or any(type(v) is not str or len(v)>4096 or re.fullmatch(r'[A-Za-z0-9,;:| .-]+',v) is None for v in values):raise ValueError('observations')
    return (json.dumps(values,separators=(',',':'))+'\n').encode('ascii')

def parse_wire(raw,nonce):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT or re.fullmatch('[0-9a-f]{32}',nonce) is None:raise ValueError('wire')
    lines=raw.decode('ascii').splitlines();prefix='ERQ|'+nonce+'|'
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
    text=result['error'];messages=result['messages'];prefix='ERQ|'+nonce+'|'
    if type(messages) is not list or len(messages)>COUNT+2 or any(type(m) is not str or len(m)>8192 for m in messages):
        raise ValueError('invalid failure messages')
    entered=bool(messages and messages[0]==prefix+'entered');cases=0
    for n,message in enumerate(messages[1:],1):
        if n>COUNT or not message.startswith(prefix+str(n)+'|'):break
        cases=n
    frames=[]
    for match in re.finditer(r'\{([^{}\r\n]{1,200})\(([0-9]{1,3})(?:,\s*[0-9]{1,3})?\)\}',text):
        module=next((name for name in ('TestModule','Receipt','Issue') if name in match[1]),None)
        if module is not None and 1<=int(match[2])<=512 and len(frames)<4:frames.append([module,int(match[2])])
    apis=sorted({value for key,value in ERROR_APIS.items() if re.search(r'\('+re.escape(key)+r'\)',text)})
    return dict(entered=entered,cases=cases,frames=frames,apis=apis,
                codes=sorted(key for key,value in ERROR_CODES.items() if value in text.casefold()))

def valid_failure_details(value):
    return (type(value) is dict and set(value)=={'entered','cases','frames','apis','codes'} and
        type(value['entered']) is bool and type(value['cases']) is int and 0<=value['cases']<=COUNT and
        type(value['frames']) is list and len(value['frames'])<=4 and all(type(f) is list and len(f)==2 and
            f[0] in ('TestModule','Receipt','Issue') and type(f[1]) is int and 1<=f[1]<=512 for f in value['frames']) and
        type(value['apis']) is list and len(value['apis'])<=len(ERROR_APIS) and all(type(a) is str and a in ERROR_APIS.values() for a in value['apis']) and
        type(value['codes']) is list and len(value['codes'])<=len(ERROR_CODES) and all(type(c) is str and c in ERROR_CODES for c in value['codes']))


STAGES=('setup','seed','write','readback','query')
def parse_attempt(raw,nonce):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT:raise ValueError('wire')
    lines=raw.decode('utf-8').splitlines();prefix='ERQ|'+nonce+'|'
    if len(lines)>50 or not lines or lines[0]!=prefix+'entered' or lines[-1]!=prefix+'completed':raise ValueError('markers')
    observations=[];errors=[];last=0
    for line in lines[1:-1]:
        if line.startswith(prefix+'error|'):
            parts=line[len(prefix+'error|'):].split('|',2)
            if len(parts)!=3 or not parts[0].isdigit() or not 1<=int(parts[0])<=COUNT or parts[1] not in STAGES:raise ValueError('diagnostic')
            text=json.loads(parts[2])
            if type(text) is not str or len(text)>4096 or len(errors)>=24:raise ValueError('diagnostic')
            errors.append((int(parts[0]),parts[1],text))
        else:
            parts=line[len(prefix):].split('|',1) if line.startswith(prefix) else []
            if len(parts)!=2 or not parts[0].isdigit() or not last<int(parts[0])<=COUNT:raise ValueError('order')
            canonical([parts[1]]*COUNT);last=int(parts[0]);observations.append([last,parts[1]])
    return observations,errors

# Designer failures occur before the observer and cannot use its error marker.
# Keep only this fixed vocabulary and source-owned identifiers, never log text,
# paths, arbitrary tokens, numeric values, credentials or quoted user data.
INSTALL_LABELS=('before','load','update','after')
INSTALL_WORDS={
    'error':('error','ошибка','ошибки'), 'invalid':('invalid','недопустимый','недопустимое','недопустимая','неверное','неверный'),
    'unknown':('unknown','неизвестный','неизвестное','неизвестная'),
    'not':('not','не'),
    'must':('must','должен','должна','должно'), 'required':('required','требуется','необходимо'),
    'cannot':('cannot','невозможно','нельзя'), 'only':('only','только'),
    'field':('field','поле','поля'),
    'attribute':('attribute','атрибут','атрибута','реквизит','реквизита'),
    'element':('element','элемент','элемента'), 'type':('type','тип','типа'),
    'value':('value','значение','значения'), 'property':('property','свойство','свойства'),
    'register':('register','регистр','регистра'), 'resource':('resource','ресурс','ресурса'),
    'dimension':('dimension','измерение','измерения'), 'document':('document','документ','документа'),
    'accumulation':('accumulation','накопления'), 'information':('information','сведений'),
    'configuration':('configuration','конфигурация','конфигурации'),
    'duplicate':('duplicate','дублируется','дублирование'), 'reserved':('reserved','зарезервировано','зарезервированное'),
    'syntax':('syntax','синтаксическая','синтаксические'), 'expected':('expected','ожидается'),
    'identifier':('identifier','идентификатор','идентификатора'), 'module':('module','модуль','модуля'),
    'rights':('rights','право','права','прав'), 'role':('role','роль','роли'),
    'read':('read','чтение'), 'write':('write','запись'), 'update':('update','изменение','обновление'),
    'load':('load','loading','загрузка','загрузки','загрузке'), 'failed':('failed','failure','ошибкой'),
    'xml':('xml','xdto','хдто'), 'conversion':('conversion','convert','преобразование','преобразования'),
    'mapping':('mapping','отображение','отображения'), 'namespace':('namespace','пространство','пространства'),
    'metadata':('metadata','метаданные','метаданных'), 'object':('object','объект','объекта'),
    'setting':('setting','settings','настройка','настройки'), 'enum':('enum','enumeration','перечисление','перечисления'),
    'absent':('absent','missing','отсутствует','отсутствуют'), 'defined':('defined','определен','определено','определена'),
    'exists':('exists','exist','существует','существуют'), 'unique':('unique','уникальный','уникальное','уникально','уникальным'),
    'correct':('correct','корректный','корректное'), 'unsupported':('unsupported','поддерживается','поддерживаются'),
    'while':('while','при'), 'operation':('operation','операция','операции'),
    'opening':('open','opening','открытие','открытия','открыть'), 'reading':('reading','чтения','читать'),
    'file':('file','files','файл','файла','файлы','файлов'), 'directory':('directory','folder','каталог','каталога','каталогов'),
    'path':('path','путь','пути'), 'format':('format','формат','формата'), 'encoding':('encoding','кодировка','кодировки'),
    'parse':('parse','parser','parsing','разбор','разбора'), 'end':('end','конец','конца'),
    'unexpected':('unexpected','неожиданный','неожиданное'), 'symbol':('symbol','символ','символа'),
    'line':('line','строка','строки'), 'column':('column','колонка','колонки'),
    'invalid_name':('badname',), 'display':('display','дисплей','дисплея'), 'font':('font','fonts','шрифт','шрифта'),
    'color':('color','цвет','цвета'), 'request':('request','запрос','запроса'),
    'connection':('connection','соединение','соединения'), 'protocol':('protocol','protocols','протокол','протокола'),
    'authentication':('authentication','аутентификация','аутентификации'), 'session':('session','сессия','сеанса'),
    'library':('library','libraries','библиотека','библиотеки'), 'plugin':('plugin','плагин'),
    'application':('application','приложение','приложения'), 'platform':('platform','платформа','платформы'),
    'terminate':('terminate','terminated','termination','завершение'), 'exception':('exception','исключение','исключения'),
    'system':('system','система','системы'), 'memory':('memory','память','памяти'),
    'sequence':('sequence','последовательность','последовательности'),
    'found':('found','найден','найдена','найдено','обнаружено','обнаружен','обнаружена'),
    'name':('name','names','имя','имени','имен','наименование'),

}
INSTALL_IDENTIFIERS=frozenset(('Receipt','Issue','Stock','Products','Warehouses','Product','Lines','Catalog','AccumulationRegister',
    'Record','Manager','Selection','List','RecordSet','RecordKey','RegisterType','Balance',
    'RegisterRecords','EnableTotalsSplitting','DataLockControlMode','UseInTotals',
    'Amount','Quantity','Item','Warehouse','Note','Period','Active','RecordType',
    'AppendRows','Input','Set','Rows','First','Replacement','PersistedCount','Posting','Cancel','PostingMode',
    'Name','MetaDataObject','Configuration','InternalInfo','Properties','ChildObjects','GeneratedType',
    'TypeId','ValueId','NumberQualifiers','StringQualifiers','Digits','FractionDigits','AllowedSign',
    'Length','AllowedLength','Resource','Dimension','Attribute','Update','Read'))
_INSTALL_TOKENS=frozenset(INSTALL_WORDS)|frozenset('owned:'+v for v in INSTALL_IDENTIFIERS)|{'redacted','line_break'}

def install_diagnostic(text,label,*,exit_code=None,source_root_present=None,configuration_present=None):
    if type(text) is not str or len(text)>65536 or label not in INSTALL_LABELS:
        raise ValueError('install diagnostic input')
    aliases={word:token for token,words in INSTALL_WORDS.items() for word in words}
    identities={word.casefold():'owned:'+word for word in INSTALL_IDENTIFIERS}
    # Remove credential-bearing lines before matching even fixed vocabulary.
    text=re.sub(r'^.*(?:password|passwd|token|secret|authorization|cookie|пароль|токен|секрет)\s*[:=].*$',
                ' ',text,flags=re.I|re.M)
    if (exit_code is not None and (type(exit_code) is not int or not -255<=exit_code<=255)
            or any(v is not None and type(v) is not bool for v in (source_root_present,configuration_present))):
        raise ValueError('install diagnostic facts')
    tokens=[]
    for word in re.findall(r'\r\n|\r|\n|[^\W\d_]+(?:_[^\W\d_]+)*',text,re.UNICODE):
        token='line_break' if word in ('\r','\n','\r\n') else identities.get(word.casefold(),aliases.get(word.casefold(),'redacted'))
        if token not in ('redacted','line_break') or not tokens or tokens[-1]!=token:tokens.append(token)
    return {'step':label,'exit_code':exit_code,'source_root_present':source_root_present,
            'configuration_present':configuration_present,'tokens':tokens[:96] if len(tokens)<=96 else tokens[:48]+tokens[-48:],
            'truncated':len(tokens)>96}

def valid_install_diagnostic(value):
    return (type(value) is dict and set(value)=={'step','tokens','truncated','exit_code','source_root_present','configuration_present'}
        and type(value['step']) is str and value['step'] in INSTALL_LABELS
        and (value['exit_code'] is None or type(value['exit_code']) is int and -255<=value['exit_code']<=255)
        and all(value[k] is None or type(value[k]) is bool for k in ('source_root_present','configuration_present'))
        and type(value['truncated']) is bool and type(value['tokens']) is list
        and len(value['tokens'])<=96 and (not value['truncated'] or len(value['tokens'])==96)
        and all(type(v) is str and v in _INSTALL_TOKENS for v in value['tokens']))
