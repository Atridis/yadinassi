"""Standalone source-bound Description experiment. Not registered in any runner.

Seeds are assignments, never expected readback or physical-reader inputs.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

CASES = MappingProxyType({'description8': (8, 'AБ😀xy  ', 'Я '),
                          'description17': (17, 'AbВгДеЖзИйКл😀x  ', 'Qя ')})
WITNESS_LIMIT = 2048
MAX_ACTUAL_UNITS = 128  # Observation transport ceiling, NOT native capacity.
CAPTURE_LIMIT = 8192
REPORT_LIMIT = 32768
ROOT = Path(__file__).parent
HOOK_SHA256 = '32f5f6c4f13e2f07674c2fd79639697c11de46e4f2dfc06865627cb72b071f3f'
PINS = MappingProxyType({
 'metadata/Catalog.xml': '612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5',
 'modules/NativeOracleServer.bsl': '5700a4f2f44574e47afdcea4d3ecb136436715a1391e945a8de31d5f45cfe69b'})


def _case(case):
    if type(case) is not str or case not in CASES:
        raise ValueError('description_case_invalid')
    return CASES[case]


def _replace(raw, changes):
    for old, new in changes:
        if raw.count(old) != 1 or new in raw:
            raise ValueError('description_template_invalid')
        raw = raw.replace(old, new)
    return raw


def _changes(case, name):
    length, create, update = _case(case)
    if name == 'metadata/Catalog.xml':
        return (('<DescriptionLength>0</DescriptionLength>',
                 f'<DescriptionLength>{length}</DescriptionLength>'),)
    if name != 'modules/NativeOracleServer.bsl':
        raise ValueError('description_template_invalid')
    return (
        ('NativeИзмерить(Контроль.operation, Результат, Корень, Контекст);',
         'NativeИзмерить(Контроль.operation, Результат, Корень, Контекст, ТокенЗапуска);'),
        ('Процедура NativeИзмерить(Операция, Результат, Корень, Контекст)',
         'Процедура NativeИзмерить(Операция, Результат, Корень, Контекст, ТокенЗапуска)'),
        ('Каталог.ДлинаНаименования <> 0', f'Каталог.ДлинаНаименования <> {length}'),
        ('            Объект.Payload = "alpha";',
         f'            Объект.Наименование = "{create}";\n            Объект.Payload = "alpha";'),
        ('                Объект.Payload = "beta";',
         f'                Объект.Наименование = "{update}";\n                Объект.Payload = "beta";'),
        ('    Для Каждого Поле Из После Цикл\n        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;',
         '    Для Каждого Поле Из После Цикл\n        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;\n'
         '    Если Операция = "create" Или Операция = "update" Или Операция = "observe" Тогда\n'
         '        NativeDescriptionObserve(Корень, ТокенЗапуска, Операция);\n    КонецЕсли;'))


def _hook(case):
    raw = (ROOT / 'modules/CatalogDescriptionObservation.bsl').read_bytes()
    if hashlib.sha256(raw).hexdigest() != HOOK_SHA256 or raw.count(b'@@DESCRIPTION_CASE@@') != 1:
        raise ValueError('description_template_invalid')
    return '\n' + raw.decode('utf-8').replace('@@DESCRIPTION_CASE@@', case)


def transform(raw, *, name, case):
    """Transform exact ORIGINAL template bytes, before normal literal rendering.

    Not an injector replacement: executable staging/redump integration is deferred.
    Every accepted output has a byte-exact inverse back to the pinned baseline.
    """
    _case(case)
    if type(raw) is not bytes or name not in PINS or hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise ValueError('description_template_invalid')
    text = _replace(raw.decode('utf-8'), _changes(case, name))
    if name.endswith('.bsl'):
        text += _hook(case)
    result = text.encode('utf-8')
    if inverse(result, name=name, case=case) != raw:
        raise ValueError('description_template_invalid')
    return result


def inverse(raw, *, name, case):
    _case(case)
    if type(raw) is not bytes or name not in PINS:
        raise ValueError('description_template_invalid')
    text = raw.decode('utf-8')
    if name.endswith('.bsl'):
        hook = _hook(case)
        if not text.endswith(hook):
            raise ValueError('description_template_invalid')
        text = text[:-len(hook)]
    for old, new in reversed(_changes(case, name)):
        if text.count(new) != 1:
            raise ValueError('description_template_invalid')
        text = text.replace(new, old)
    result = text.encode('utf-8')
    if hashlib.sha256(result).hexdigest() != PINS[name]:
        raise ValueError('description_template_invalid')
    return result


@dataclass(frozen=True)
class DescriptionWitness:
    actual_description: str  # PRIVATE; do not serialize this object publicly.
    utf16_units: int
    scalar_count: int
    trailing_spaces: int
    raw_sha256: str
    case: str
    operation: str
    present: bool
    nonce: str
    token: str


def validate_witness(raw, *, nonce, token, case, operation):
    def fail():
        raise ValueError('description_witness_invalid')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail()
            result[key] = value
        return result
    _case(case)
    if (type(raw) is not bytes or not 1 <= len(raw) <= WITNESS_LIMIT
        or type(operation) is not str or operation not in ('create', 'update', 'observe')
        or any(type(x) is not str or re.fullmatch('[0-9a-f]{32}', x) is None for x in (nonce, token))):
        fail()
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=lambda _: fail())
    except (ValueError, UnicodeError, RecursionError):
        fail()
    if (type(data) is not dict or set(data) != {'schema','nonce','token','case','operation','present','actual_description'}
        or type(data['schema']) is not int or data['schema'] != 2
        or any(data[k] != v for k,v in [('nonce',nonce),('token',token),('case',case),('operation',operation)])
        or type(data['present']) is not bool
        or type(data['actual_description']) is not str
        or (not data['present'] and data['actual_description'] != '')
        or (operation in ('create','update') and not data['present'])):
        fail()
    value = data['actual_description']
    try:
        units = len(value.encode('utf-16-le')) // 2
    except UnicodeError:
        fail()
    if units > MAX_ACTUAL_UNITS:
        fail()
    return DescriptionWitness(value, units, len(value), len(value)-len(value.rstrip(' ')), hashlib.sha256(raw).hexdigest(), case, operation, data['present'], nonce, token)


def verify_case_metadata(case, description_length):
    """Separate comparison AFTER independent CONFIG/physical observation."""
    return type(description_length) is int and description_length == _case(case)[0]


def compare_readback(observation, witness, *, case):
    """Compare only AFTER independent observation, not a physical reader input.

    Pure comparison is not provenance proof: caller must bind both inputs to
    the same source-bound operation/postimage before publishing any conclusion.
    """
    from catalog_description_physical import DescriptionObservation, public_observation
    if type(observation) is not DescriptionObservation or type(witness) is not DescriptionWitness:
        raise ValueError('description_comparison_invalid')
    _case(case)
    if witness.case != case or not witness.present:
        raise ValueError('description_comparison_invalid')
    metadata_matches = verify_case_metadata(case, observation.identity.description_length)
    physical = public_observation(observation)
    result = dict(status='not_compared', metadata_matches=metadata_matches,
                  physical=physical, witness_sha256=witness.raw_sha256,
                  native_utf16_units=witness.utf16_units,
                  native_unicode_scalars=witness.scalar_count,
                  native_trailing_spaces=witness.trailing_spaces,
                  count_evidence='not_distinguished', native_compatibility='not_claimed')
    if not metadata_matches:
        result['status'] = 'case_metadata_mismatch'
    elif observation.status == 'layout_unresolved':
        result['status'] = 'layout_unresolved'
    else:
        field = observation.records.rows[0].fields[5]
        equal = field.value == witness.actual_description
        result['status'] = 'readback_matches' if equal else 'readback_differs'
        if equal and witness.utf16_units > witness.scalar_count and physical['utf16_count_matches']:
            result['count_evidence'] = 'supplementary_utf16_units_observed'
    return result
