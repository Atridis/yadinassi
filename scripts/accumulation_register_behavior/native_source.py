"""Reproduce the owned acquisition XML from exactly pinned public native XML.

Developer/offline source tooling only: not staged, imported by the native route,
or used to expand a runtime source grant. No arbitrary XML importer is exposed.
Keep native wrappers verbatim; make only the reviewed substitutions below.
"""
import hashlib
from pathlib import Path
import re

PUBLIC = Path(__file__).parent / 'public_source' / 'vanessa_add'
BALANCE = 'РегистрНакопленияОстатки.xml'
ATTRIBUTE = 'РегистрНакопления2.xml'
SOURCE_HASHES = {
    BALANCE: '19f0e833301d68843e0dddb921a678def1c0e819037a501200bab3fce3a6e227',
    ATTRIBUTE: '31e8e0fa9d9ef01965da39eeb41ffd85c1f7663be2f19be0e978121eb290aeb2',
}
REGISTER_UUID = '53f5be52-f6c4-5f55-a904-2315026fbcdb'
REGISTER_NAME = 'OwnedAccumulationRows'
GENERATED_IDS = {
    'Record': ('d782356a-9cef-5a95-bcb4-b0a023d9e836', '2304697b-3424-5372-9808-46eb18bb5d4f'),
    'Manager': ('653a8f41-551b-5958-b02f-bd2b92d2b69b', '39ed6dd6-e775-5147-a5cc-b488fae77cdd'),
    'Selection': ('8268781d-8014-5f2d-9641-4c5d18f9e696', '13bd901b-2fa2-5324-be3a-58031a22c05f'),
    'List': ('1ad8a538-cbea-51c0-8e0e-3d6d43a88e1c', '7865a44f-fb94-5fba-b4c8-f854aee4e607'),
    'RecordSet': ('68487e52-a354-58f4-8e5e-3c0585112bfd', 'f0da1f92-37c0-5331-8fa1-21524a4c4a90'),
    'RecordKey': ('81f3bc3b-61e6-5b2b-ba6d-b61324e4dfef', '26da58a6-f818-5ac2-bf22-b16c671a1d21'),
}
FIELDS = (
    ('Resource', 'Amount', 'bacfca9e-c9bc-5116-aaf9-23373023a45f', 'Number', 10, 2),
    ('Resource', 'Quantity', '18281200-85cf-5f3e-97c7-034f3eaffd9b', 'Number', 10, 3),
    ('Attribute', 'Note', '77b1bc03-3518-5dca-b33e-d00a5c9f1943', 'String', 32, None),
    ('Dimension', 'Item', '7669a9dd-957b-5575-b334-a9a893d4ed32', 'String', 32, None),
    ('Dimension', 'Warehouse', 'ce426a7f-dd8d-5df2-bcdd-c177f05bd8cf', 'Number', 4, 0),
)
NOTICE = ('<!-- Derived from vanessa-opensource/add native XML; modified for the\n'
          '     owned accumulation acquisition fixture. SPDX-License-Identifier: MPL-2.0\n'
          '     See public_source/vanessa_add/NOTICE.md, SOURCE.json and LICENSE.\n'
          '     This Source Code Form is subject to the Mozilla Public License, v. 2.0.\n'
          '     https://mozilla.org/MPL/2.0/ -->\n')


def _replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('native source substitution is not unique')
    return text.replace(before, after, 1)


def _element(text, tag):
    matches = re.findall(r'<' + re.escape(tag) + r'(?:/>|>.*?</' + re.escape(tag) + r'>)', text, re.S)
    if len(matches) != 1:
        raise ValueError('native source element is not unique')
    return matches[0]


def _set_element(text, tag, value):
    return _replace_once(text, _element(text, tag), '<' + tag + '>' + value + '</' + tag + '>')


def _block(text, tag, depth):
    tabs = '\t' * depth
    matches = re.findall(r'^' + tabs + '<' + tag + r'(?: [^>\n]+)?>.*?^' + tabs + '</' + tag + '>', text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError('native source block is not unique')
    return matches[0]


def _uuid(block, kind, value):
    matches = re.findall('<' + kind + r' uuid="[a-f0-9-]+">', block)
    if len(matches) != 1:
        raise ValueError('native source identity is not unique')
    return _replace_once(block, matches[0], '<' + kind + ' uuid="' + value + '">')


def derive():
    """Return UTF-8/BOM XML using only the two immutable checked-in sources."""
    sources = {}
    for name, digest in SOURCE_HASHES.items():
        path = PUBLIC / name
        if path.is_symlink():
            raise ValueError('native source symlink')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('native source changed')
        sources[name] = raw.decode('utf-8-sig')
    text = sources[BALANCE]
    # Keep all native namespace declarations and the truthful input version 2.4.
    text = _uuid(text, 'AccumulationRegister', REGISTER_UUID)
    info = _block(text, 'InternalInfo', 2)
    updated = info.replace('РегистрНакопленияОстатки', REGISTER_NAME)
    for category, (type_id, value_id) in GENERATED_IDS.items():
        matches = re.findall(r'<xr:GeneratedType [^>]*category="' + category + r'">.*?</xr:GeneratedType>', updated, re.S)
        if len(matches) != 1:
            raise ValueError('native generated type is not unique')
        block = _set_element(matches[0], 'xr:TypeId', type_id)
        block = _set_element(block, 'xr:ValueId', value_id)
        updated = _replace_once(updated, matches[0], block)
    text = _replace_once(text, info, updated)
    properties = _block(text, 'Properties', 2)
    updated = _set_element(properties, 'Name', REGISTER_NAME)
    updated = _replace_once(updated, _element(updated, 'Synonym'), '<Synonym/>')
    updated = _set_element(updated, 'UseStandardCommands', 'false')
    updated = _set_element(updated, 'EnableTotalsSplitting', 'false')
    text = _replace_once(text, properties, updated)

    templates = {kind: _block(sources[BALANCE], kind, 3) for kind in ('Resource', 'Dimension')}
    templates['Attribute'] = _block(sources[ATTRIBUTE], 'Attribute', 3)
    number_type = _element(templates['Resource'], 'Type')
    string_type = _element(templates['Dimension'], 'Type')
    fields = []
    for kind, name, uuid, scalar, digits, fraction in FIELDS:
        block = _uuid(templates[kind], kind, uuid)
        block = _set_element(block, 'Name', name)
        block = _replace_once(block, _element(block, 'Synonym'), '<Synonym/>')
        if scalar == 'Number':
            field_type = _set_element(number_type, 'v8:Digits', str(digits))
            field_type = _set_element(field_type, 'v8:FractionDigits', str(fraction))
        else:
            field_type = _set_element(string_type, 'v8:Length', str(digits))
        block = _replace_once(block, _element(block, 'Type'), field_type)
        fields.append(block)
    text = _replace_once(text, _block(text, 'ChildObjects', 2),
                         '\t\t<ChildObjects>\n' + '\n'.join(fields) + '\n\t\t</ChildObjects>')
    text = _replace_once(text, '<?xml version="1.0" encoding="UTF-8"?>\n',
                         '<?xml version="1.0" encoding="UTF-8"?>\n' + NOTICE)
    return text.encode('utf-8-sig')
