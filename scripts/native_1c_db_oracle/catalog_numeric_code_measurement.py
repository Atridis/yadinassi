"""Standalone Numeric Code fixture; no runtime/runner registration.

Requested assignments are not expected readback values or reader selectors.
The owned metadata matrix previously exercised XML Number (length2, empty).
This does not claim native row acceptance for this new experiment.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from uuid import UUID

CASES = MappingProxyType({'number3': (3, 987, 12), 'number6': (6, 654321, 42)})
ROOT = Path(__file__).parent
WITNESS_LIMIT = 2048
MAX_NUMBER_TEXT = 80  # Private transport bound, NOT a native numeric maximum.
MAX_DESCRIPTION_UNITS = 128
PINS = MappingProxyType({
 'metadata/Catalog.xml': '612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5',
 'modules/NativeOracleServer.bsl': '5700a4f2f44574e47afdcea4d3ecb136436715a1391e945a8de31d5f45cfe69b'})
HOOK_SHA256 = '67eb08e54336c3258b83d70943349a5da05214c7bd6592a8fa05aaddc1f2b5a0'


def _case(case):
    if type(case) is not str or case not in CASES:
        raise ValueError('numeric_code_case_invalid')
    return CASES[case]


def _changes(case, name):
    length, create, update = _case(case)
    if name == 'metadata/Catalog.xml':
        return (('<CodeLength>2</CodeLength>', f'<CodeLength>{length}</CodeLength>'),
                ('<DescriptionLength>0</DescriptionLength>', '<DescriptionLength>8</DescriptionLength>'),
                ('<CodeType>String</CodeType>', '<CodeType>Number</CodeType>'))
    if name != 'modules/NativeOracleServer.bsl':
        raise ValueError('numeric_code_template_invalid')
    return (
        ('NativeИзмерить(Контроль.operation, Результат, Корень, Контекст);',
         'NativeИзмерить(Контроль.operation, Результат, Корень, Контекст, ТокенЗапуска);'),
        ('Процедура NativeИзмерить(Операция, Результат, Корень, Контекст)',
         'Процедура NativeИзмерить(Операция, Результат, Корень, Контекст, ТокенЗапуска)'),
        ('Каталог.ДлинаКода <> 2 Или Каталог.ДлинаНаименования <> 0',
         f'Каталог.ДлинаКода <> {length} Или Каталог.ДлинаНаименования <> 8 Или Каталог.Автонумерация'),
        ('            Объект.Код = "K1";', f'            Объект.Код = {create};\n            Объект.Наименование = "Name  ";'),
        ('                Объект.Payload = "beta";',
         f'                Объект.Код = {update};\n                Объект.Наименование = "Я ";\n                Объект.Payload = "beta";'),
        ('Выборка.Код <> "K1"', 'ТипЗнч(Выборка.Код) <> Тип("Число")'),
        # Closed logical tag, NOT actual Code. A future lane needs an explicit
        # mapped-core protocol; this standalone module is not runnable today.
        ('Результат.code = "K1";', 'Результат.code = "observed_number";'),
        ('    Для Каждого Поле Из После Цикл\n        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;',
         '    Для Каждого Поле Из После Цикл\n        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;\n'
         '    Если Операция = "create" Или Операция = "update" Или Операция = "observe" Тогда\n'
         '        NativeNumericCodeObserve(Корень, ТокенЗапуска, Операция);\n    КонецЕсли;'))


def _hook(case):
    length, _, _ = _case(case)
    raw = (ROOT/'modules/CatalogNumericCodeObservation.bsl').read_bytes()
    if hashlib.sha256(raw).hexdigest() != HOOK_SHA256:
        raise ValueError('numeric_code_template_invalid')
    text = raw.decode('utf-8')
    for old, new in (('@@NUMERIC_LENGTH@@', str(length)), ('@@NUMERIC_CASE@@', case)):
        if text.count(old) != 1:
            raise ValueError('numeric_code_template_invalid')
        text = text.replace(old, new)
    return '\n'+text


def transform(raw, *, name, case):
    _case(case)
    if type(raw) is not bytes or type(name) is not str or name not in PINS or hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise ValueError('numeric_code_template_invalid')
    text = raw.decode('utf-8')
    for old, new in _changes(case, name):
        if text.count(old) != 1 or new in text:
            raise ValueError('numeric_code_template_invalid')
        text = text.replace(old, new)
    if name.endswith('.bsl'):
        text += _hook(case)
    out = text.encode('utf-8')
    if inverse(out, name=name, case=case) != raw:
        raise ValueError('numeric_code_template_invalid')
    return out


def inverse(raw, *, name, case):
    _case(case)
    if type(raw) is not bytes or type(name) is not str or name not in PINS:
        raise ValueError('numeric_code_template_invalid')
    text = raw.decode('utf-8')
    if name.endswith('.bsl'):
        hook = _hook(case)
        if not text.endswith(hook):
            raise ValueError('numeric_code_template_invalid')
        text = text[:-len(hook)]
    for old, new in reversed(_changes(case, name)):
        if text.count(new) != 1:
            raise ValueError('numeric_code_template_invalid')
        text = text.replace(new, old)
    out = text.encode('utf-8')
    if hashlib.sha256(out).hexdigest() != PINS[name]:
        raise ValueError('numeric_code_template_invalid')
    return out


@dataclass(frozen=True)
class NumericCodeWitness:
    actual_code: object  # PRIVATE Decimal or None; never report this object.
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
        raise ValueError('numeric_code_witness_invalid')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail()
            result[key] = value
        return result
    _case(case)
    if (type(raw) is not bytes or not 1 <= len(raw) <= WITNESS_LIMIT
            or type(operation) is not str or operation not in ('create','update','observe')
            or any(type(x) is not str or re.fullmatch('[0-9a-f]{32}', x) is None for x in (nonce,token))):
        fail()
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=lambda _: fail())
    except (ValueError, UnicodeError, RecursionError):
        fail()
    keys = {'schema','nonce','token','case','operation','present','actual_number','actual_code',
            'actual_uuid','actual_description','code_length','description_length','payload_length','autonumbering'}
    if (type(data) is not dict or set(data) != keys or type(data['schema']) is not int or data['schema'] != 1
            or any(type(data[k]) is not str or data[k] != v for k,v in [('nonce',nonce),('token',token),('case',case),('operation',operation)])
            or type(data['present']) is not bool or type(data['actual_number']) is not bool
            or type(data['autonumbering']) is not bool
            or any(type(data[k]) is not int or not 0 <= data[k] <= 2047 for k in ('code_length','description_length','payload_length'))
            or any(type(data[k]) is not str for k in ('actual_code','actual_uuid','actual_description'))
            or (operation in ('create','update') and not data['present'])):
        fail()
    code, identifier = None, None
    if not data['present']:
        if data['actual_number'] or any(data[k] for k in ('actual_code','actual_uuid','actual_description')):
            fail()
    else:
        value = data['actual_code']
        if not data['actual_number'] or len(value) > MAX_NUMBER_TEXT or re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value) is None:
            fail()
        code = Decimal(value)  # bounded lexical grammar; independent of context precision
        try:
            identifier = UUID(data['actual_uuid'])
        except ValueError:
            fail()
        if str(identifier) != data['actual_uuid'] or identifier.int == 0:
            fail()
    try:
        if len(data['actual_description'].encode('utf-16-le'))//2 > MAX_DESCRIPTION_UNITS:
            fail()
    except UnicodeError:
        fail()
    return NumericCodeWitness(code, identifier, data['actual_description'], data['code_length'],
        data['description_length'], data['payload_length'], data['autonumbering'], hashlib.sha256(raw).hexdigest(),
        case, operation, data['present'], nonce, token)


def compare_readback(observation, witness, *, case):
    """Only after independent physical admission; NOT postimage provenance itself."""
    from catalog_numeric_code_physical import NumericCodeObservation, public_observation
    length, _, _ = _case(case)
    if type(observation) is not NumericCodeObservation or type(witness) is not NumericCodeWitness or witness.case != case or not witness.present:
        raise ValueError('numeric_code_comparison_invalid')
    identity = observation.identity
    metadata = (identity.code_type == 0 and identity.code_length == witness.code_length == length
        and identity.description_length == witness.description_length == 8
        and observation.attributes.attributes[0].qualifiers[0] == witness.payload_length
        and not witness.autonumbering)
    result = dict(status='layout_unresolved', metadata_matches=metadata,
        code_verdict='not_compared', uuid_verdict='not_compared', description_verdict='not_compared',
        physical=public_observation(observation), witness_sha256=witness.raw_sha256,
        runtime_support='not_claimed')
    if not metadata:
        result['status'] = 'case_metadata_mismatch'
    elif observation.status == 'layout_observed':
        fields = observation.records.rows[0].fields
        for key, equal in (('code',fields[4].value == witness.actual_code),
                           ('uuid',observation.typed_uuid == witness.actual_uuid),
                           ('description',fields[5].value == witness.actual_description)):
            result[key+'_verdict'] = 'matches' if equal else 'differs'
        result['status'] = 'readback_matches' if all(result[k+'_verdict']=='matches' for k in ('code','uuid','description')) else 'readback_differs'
    return result
