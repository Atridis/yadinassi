"""One deterministic reduction of the source-owned accumulation fixture.

Retain every declaration byte except register fields and the document handler.
The original bootstrap and owned-object rights are unchanged, never broadened.
"""
import hashlib
import json
from accumulation_register_behavior import fixture as source

original = source.original
MAX_FILE = source.MAX_FILE
MAX_TOTAL = source.MAX_TOTAL
_files = source._files
DOCUMENT = 'Documents/OwnedAccumulationDoc.xml'
REGISTER = 'AccumulationRegisters/OwnedAccumulationRows.xml'
MODULE = 'Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl'
VALIDATION_MODE = 'declaration-only-strict-semantic-redump-v1'


def declarations():
    _, assets = source.load_saved()
    raw = assets['AccumulationRegister.xml']
    # The parent fixture's byte pins admit one exact source, not arbitrary XML.
    original._require(raw.count(b'<ChildObjects>') == raw.count(b'</ChildObjects>') == 1)
    left, tail = raw.split(b'<ChildObjects>')
    children, right = tail.split(b'</ChildObjects>')
    tree, _ = original._xml(raw)
    md = '{' + original.MD + '}'
    fields = original._one(original._one(tree, md + 'AccumulationRegister'), md + 'ChildObjects')
    original._require([child.tag for child in fields] ==
                      [md + name for name in ('Resource', 'Resource', 'Attribute', 'Dimension', 'Dimension')])
    original._require(bool(children))
    return {DOCUMENT: assets['Document.xml'],
            REGISTER: left + b'<ChildObjects></ChildObjects>' + right}


def prepare(files):
    setup, expected = source.prepare(files)
    del expected[MODULE]
    expected.update(declarations())
    _files(expected)
    original._require(set(expected) == set(files) | {DOCUMENT, REGISTER})
    return setup, expected


def verify_redump(expected, actual):
    """Fail closed on changed identities, generated types, properties or files.

    XML namespace spelling, insignificant whitespace and set ordering use the
    existing semantic signature. No UI/default-property relaxation is added.
    Only ConfigDumpInfo.xml export bookkeeping follows the bootstrap exception.
    """
    owned = declarations()
    original._require(MODULE not in expected and MODULE not in actual)
    original._require(all(expected.get(name) == raw for name, raw in owned.items()))
    return original.verify_redump(expected, actual)


def inventory_digest(files):
    _files(files)
    value = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


redump_diagnostic = source.redump_diagnostic
valid_diagnostic = source.valid_diagnostic
