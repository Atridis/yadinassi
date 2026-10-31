"""Standalone disabled-Code fixture; no runner/runtime registration.

Metadata availability and physical omission are hypotheses until native evidence.
Actual native Code access is observed without expected seed values.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from uuid import UUID

CASES = MappingProxyType({'zero0': 0, 'zero8': 8})
ROOT = Path(__file__).parent
WITNESS_LIMIT = 2048
MAX_NUMBER_TEXT = 80  # Private transport bound, NOT a native numeric maximum.
MAX_DESCRIPTION_UNITS = 128
PINS = MappingProxyType({
 'metadata/Catalog.xml': '612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5',
 'modules/NativeOracleServer.bsl': '5700a4f2f44574e47afdcea4d3ecb136436715a1391e945a8de31d5f45cfe69b'})
HOOK_SHA256 = 'e26b456ac4a642f047e89872822f2cc622bfd86a27f1061b38c7723ea7da9306'


def _case(case):
    if type(case) is not str or case not in CASES:
        raise ValueError('zero_code_case_invalid')
    return CASES[case]


def _changes(case, name):
    description = _case(case)
    if name == 'metadata/Catalog.xml':
        changes = (('<CodeLength>2</CodeLength>', '<CodeLength>0</CodeLength>'),)
        if description:
            changes += (('<DescriptionLength>0</DescriptionLength>', '<DescriptionLength>8</DescriptionLength>'),)
        return changes
    if name != 'modules/NativeOracleServer.bsl':
        raise ValueError('zero_code_template_invalid')
    return (
        ('NativeИзмерить(Контроль.operation, Результат, Корень, Контекст);',
         'NativeИзмерить(Контроль.operation, Результат, Корень, Контекст, ТокенЗапуска);'),
        ('Процедура NativeИзмерить(Операция, Результат, Корень, Контекст)',
         'Процедура NativeИзмерить(Операция, Результат, Корень, Контекст, ТокенЗапуска)'),
        ('Каталог.ДлинаКода <> 2 Или Каталог.ДлинаНаименования <> 0',
         f'Каталог.ДлинаКода <> 0 Или Каталог.ДлинаНаименования <> {description} Или Каталог.Автонумерация'),
        ('            Объект.Код = "K1";', ('            Объект.Наименование = "Name  ";' if description else '            // Code disabled: no Code assignment.')),
        ('                Объект.Payload = "beta";',
         ('                Объект.Наименование = "Я ";\n' if description else '                // Description disabled.\n') + '                Объект.Payload = "beta";'),
        ('Результат.count > 1 Или Выборка.Код <> "K1" Или Выборка.ПометкаУдаления', 'Результат.count > 1 Или Выборка.ПометкаУдаления'),
        # Closed logical tag, NOT actual Code. A future lane needs an explicit
        # mapped-core protocol; this standalone module is not runnable today.
        ('Результат.code = "K1";', 'Результат.code = "observed_no_code";'),
        ('    Для Каждого Поле Из После Цикл\n        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;',
         '    Для Каждого Поле Из После Цикл\n        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;\n'
         '    Если Операция = "create" Или Операция = "update" Или Операция = "observe" Тогда\n'
         '        NativeZeroCodeObserve(Корень, ТокенЗапуска, Операция);\n    КонецЕсли;'))


def _hook(case):
    description = _case(case)
    raw = (ROOT/'modules/CatalogZeroCodeObservation.bsl').read_bytes()
    if hashlib.sha256(raw).hexdigest() != HOOK_SHA256:
        raise ValueError('zero_code_template_invalid')
    text = raw.decode('utf-8')
    for old, new in (('@@ZERO_DESCRIPTION@@', str(description)), ('@@ZERO_CASE@@', case)):
        if text.count(old) != 1:
            raise ValueError('zero_code_template_invalid')
        text = text.replace(old, new)
    return '\n'+text


def transform(raw, *, name, case):
    _case(case)
    if type(raw) is not bytes or type(name) is not str or name not in PINS or hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise ValueError('zero_code_template_invalid')
    text = raw.decode('utf-8')
    for old, new in _changes(case, name):
        if text.count(old) != 1 or new in text:
            raise ValueError('zero_code_template_invalid')
        text = text.replace(old, new)
    if name.endswith('.bsl'):
        text += _hook(case)
    out = text.encode('utf-8')
    if inverse(out, name=name, case=case) != raw:
        raise ValueError('zero_code_template_invalid')
    return out


def inverse(raw, *, name, case):
    _case(case)
    if type(raw) is not bytes or type(name) is not str or name not in PINS:
        raise ValueError('zero_code_template_invalid')
    text = raw.decode('utf-8')
    if name.endswith('.bsl'):
        hook = _hook(case)
        if not text.endswith(hook):
            raise ValueError('zero_code_template_invalid')
        text = text[:-len(hook)]
    for old, new in reversed(_changes(case, name)):
        if text.count(new) != 1:
            raise ValueError('zero_code_template_invalid')
        text = text.replace(new, old)
    out = text.encode('utf-8')
    if hashlib.sha256(out).hexdigest() != PINS[name]:
        raise ValueError('zero_code_template_invalid')
    return out


@dataclass(frozen=True)
class ZeroCodeWitness:
    code_type: str
    code_state: str
    actual_code: object
    actual_uuid: object
    actual_description: str
    code_length: int
    description_length: int
    payload_length: int
    autonumbering: bool
    raw_sha256: str
    case: str
    operation: str
    present: bool
    nonce: str
    token: str


def validate_witness(raw, *, nonce, token, case, operation):
    def fail():
        raise ValueError('zero_code_witness_invalid')
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail()
            out[key] = value
        return out
    _case(case)
    if (type(raw) is not bytes or not 1 <= len(raw) <= WITNESS_LIMIT
            or type(operation) is not str or operation not in ('create','update','observe')
            or any(type(x) is not str or re.fullmatch('[0-9a-f]{32}', x) is None for x in (nonce,token))):
        fail()
    try:
        d=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda _:fail())
    except (ValueError,UnicodeError,RecursionError):
        fail()
    keys={'schema','nonce','token','case','operation','present','code_type','code_state','actual_code','actual_uuid',
          'actual_description','code_length','description_length','payload_length','autonumbering'}
    if (type(d) is not dict or set(d)!=keys or type(d['schema']) is not int or d['schema']!=1
            or any(type(d[k]) is not str or d[k]!=v for k,v in (('nonce',nonce),('token',token),('case',case),('operation',operation)))
            or type(d['present']) is not bool or type(d['autonumbering']) is not bool
            or any(type(d[k]) is not int or not 0<=d[k]<=2047 for k in ('code_length','description_length','payload_length'))
            or any(type(d[k]) is not str for k in ('code_type','code_state','actual_code','actual_uuid','actual_description'))
            or d['code_type'] not in ('string','number','other')
            or d['code_state'] not in ('absent','unavailable','string','number','other')
            or (operation in ('create','update') and not d['present'])):
        fail()
    state=d['code_state'];code=None;identifier=None
    if not d['present']:
        if state!='absent' or any(d[k] for k in ('actual_code','actual_uuid','actual_description')):fail()
    else:
        if state=='absent':fail()
        if state in ('unavailable','other'):
            if d['actual_code']:fail()
        elif state=='number':
            if len(d['actual_code'])>80 or re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',d['actual_code']) is None:fail()
            code=Decimal(d['actual_code'])
        else:code=d['actual_code']
        try:identifier=UUID(d['actual_uuid'])
        except ValueError:fail()
        if str(identifier)!=d['actual_uuid'] or identifier.int==0:fail()
    try:
        if len(d['actual_code'].encode('utf-16-le'))//2>128 or len(d['actual_description'].encode('utf-16-le'))//2>128:fail()
    except UnicodeError:fail()
    if d['description_length']==0 and d['actual_description']:fail()
    return ZeroCodeWitness(d['code_type'],state,code,identifier,d['actual_description'],d['code_length'],d['description_length'],
        d['payload_length'],d['autonumbering'],hashlib.sha256(raw).hexdigest(),case,operation,d['present'],nonce,token)


def compare_readback(observation,witness,*,case):
    from catalog_zero_code_physical import ZeroCodeObservation, public_observation
    description=_case(case)
    if type(observation) is not ZeroCodeObservation or type(witness) is not ZeroCodeWitness or not witness.present or witness.case!=case:
        raise ValueError('zero_code_comparison_invalid')
    public=public_observation(observation)
    metadata=(witness.code_type=='string' and observation.identity.code_type==1 and observation.identity.code_length==witness.code_length==0
        and observation.identity.description_length==witness.description_length==description
        and observation.attributes.attributes[0].qualifiers[0]==witness.payload_length
        and witness.autonumbering is False)
    uuid='unresolved';name='unresolved'
    if observation.status=='layout_observed':
        uuid='matches' if observation.typed_uuid==witness.actual_uuid else 'differs'
        if not description:name='not_applicable'
        else:name='matches' if observation.records.rows[0].fields[4].value==witness.actual_description else 'differs'
    return dict(schema=1,metadata_matches=metadata,code_availability=witness.code_state,
        uuid_verdict=uuid,description_verdict=name,physical=public,witness_sha256=witness.raw_sha256)


FRONTIER_POINTS = ('client_before_call', 'server_enter', 'server_return', 'client_after_call')
CLIENT_TEMPLATE_SHA256 = '18a04341b78ea0e7d3ed9d3fcaa7b18ac9fa2585f793bf398054f88094c8ac59'
FRONTIER_HELPER = '''
// Failure-only bootstrap frontier. Diagnostic errors never change dispatch.
Процедура NativeZeroFrontier(Точка, ТокенЗапуска, Статус, Фаза)
    Попытка
        КореньДиагностики = @@EVIDENCE@@;
        ЧтениеДиагностики = Новый ЧтениеJSON;
        ЧтениеДиагностики.ОткрытьФайл(КореньДиагностики + "/control.json");
        КонтрольДиагностики = ПрочитатьJSON(ЧтениеДиагностики);
        ЧтениеДиагностики.Закрыть();
        Если ТипЗнч(КонтрольДиагностики) <> Тип("Структура") Тогда
            Возврат;
        КонецЕсли;
        Если КонтрольДиагностики.Количество() <> 4 Или КонтрольДиагностики.schema <> 1
            Или КонтрольДиагностики.nonce <> @@NONCE@@ Или КонтрольДиагностики.token <> ТокенЗапуска
            Или КонтрольДиагностики.operation <> "bootstrap" Тогда
            Возврат;
        КонецЕсли;
        ПутьДиагностики = КореньДиагностики + "/zero-frontier-" + Точка + ".json";
        ФайлДиагностики = Новый Файл(ПутьДиагностики);
        Если ФайлДиагностики.Существует() Тогда
            Возврат;
        КонецЕсли;
        ДанныеДиагностики = Новый Структура("schema,nonce,token,point,status,phase", 1, @@NONCE@@, ТокенЗапуска, Точка, Статус, Фаза);
        ЗаписьДиагностики = Новый ЗаписьJSON;
        ЗаписьДиагностики.ОткрытьФайл(ПутьДиагностики);
        ЗаписатьJSON(ЗаписьДиагностики, ДанныеДиагностики);
        ЗаписьДиагностики.Закрыть();
    Исключение
        // Missing or malformed diagnostic is not proof that this point was not reached.
    КонецПопытки;
КонецПроцедуры
'''


def _frontier_changes(name):
    if name == 'ManagedApplicationModule.bsl':
        call = '            Ответ = NativeOracleServer.NativeВыполнить(ПараметрЗапуска);'
        return ((call, '            NativeZeroFrontier("client_before_call", ПараметрЗапуска, "entered", "dispatch");\n' + call +
            '\n            NativeZeroFrontier("client_after_call", ПараметрЗапуска, "returned", "dispatch");'),)
    if name == 'NativeOracleServer.bsl':
        entry = 'Функция NativeВыполнить(ТокенЗапуска) Экспорт'
        ret = '    Возврат Контекст;'
        return ((entry, entry+'\n    NativeZeroFrontier("server_enter", ТокенЗапуска, "entered", "dispatch");'),
                (ret, '    NativeZeroFrontier("server_return", ТокенЗапуска, Контекст.status, Контекст.phase);\n'+ret))
    raise ValueError('zero_frontier_module_invalid')


def instrument_module(raw, *, name, case):
    """Closed zero-only source transformation; legacy templates stay byte-exact."""
    _case(case)
    if name == 'NativeOracleServer.bsl':
        baseline = transform(raw, name='modules/'+name, case=case)
    elif name == 'ManagedApplicationModule.bsl' and type(raw) is bytes and hashlib.sha256(raw).hexdigest() == CLIENT_TEMPLATE_SHA256:
        baseline = raw
    else:
        raise ValueError('zero_frontier_module_invalid')
    text = baseline.decode('utf-8')
    for old, new in _frontier_changes(name):
        if text.count(old) != 1 or new in text:
            raise ValueError('zero_frontier_module_invalid')
        text = text.replace(old, new)
    result = (text + FRONTIER_HELPER).encode('utf-8')
    # Exact invertibility ensures no incidental transformation of the underlying module.
    inverse = result.decode('utf-8')[:-len(FRONTIER_HELPER)]
    for old, new in reversed(_frontier_changes(name)):
        if inverse.count(new) != 1:
            raise ValueError('zero_frontier_module_invalid')
        inverse = inverse.replace(new, old)
    if inverse.encode('utf-8') != baseline:
        raise ValueError('zero_frontier_module_invalid')
    return result


COMPILE_CATEGORIES = ('undefined_symbol','syntax_error','undefined_method','unknown_type','other')
COMPILE_MODULES = ('server','client','session','other')
COMPILE_STATES = ('completed','process_failed','timeout','unavailable')


def compile_log_projection(raw):
    """Read-only projection of owned compiler output; never return any log text."""
    if type(raw)is not bytes or len(raw)>32768:
        raise ValueError('compile_log_invalid')
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text=raw.decode('utf-16')
    else:
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:text=raw.decode('cp1251')
    modules={'ОбщийМодуль.NativeOracleServer.Модуль':'server','CommonModule.NativeOracleServer.Module':'server',
             'МодульУправляемогоПриложения':'client','ManagedApplicationModule':'client',
             'МодульСеанса':'session','SessionModule':'session'}
    categories=(('undefined_symbol',('Переменная не определена','Variable is not defined')),
                ('syntax_error',('Синтаксическая ошибка','Syntax error')),
                ('undefined_method',('Процедура или функция с указанным именем не определена','Procedure or function with the specified name is not defined')),
                ('unknown_type',('Тип не определен','Type is not defined')))
    issues=[];truncated=False
    for match in re.finditer(r'\{([^{}\r\n]{1,200})\((\d{1,5}),(\d{1,5})\)\}[ \t]*:[ \t]*([^\r\n]{0,500})',text):
        module=modules.get(match[1],'other');line=int(match[2]);column=int(match[3])
        if not 1<=line<=65535 or not 1<=column<=65535:
            continue
        category=next((name for name,phrases in categories if any(phrase in match[4]for phrase in phrases)),'other')
        item={'module':module,'line':line if module!='other'else 0,'column':column if module!='other'else 0,'category':category}
        if item in issues:continue
        if len(issues)==8:truncated=True;break
        issues.append(item)
    return {'log_state':'nonempty'if raw else 'empty','issues':issues,'truncated':truncated}
