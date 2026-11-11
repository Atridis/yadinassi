"""One complete, byte-pinned public native register in the owned scaffold.

Only three target references change. Preserve the native input's schema, names,
UUIDs and declaration bytes; retain the owned document except its recorder link
and omit its handler. Existing bootstrap and owned-object rights never broaden.
"""
import hashlib
import json
from pathlib import Path
from accumulation_register_behavior import fixture as source

original = source.original
MAX_FILE = source.MAX_FILE
MAX_TOTAL = source.MAX_TOTAL
_files = source._files
DOCUMENT = 'Documents/OwnedAccumulationDoc.xml'
SOURCE_REGISTER = 'AccumulationRegisters/OwnedAccumulationRows.xml'
REGISTER_NAME = 'РегистрНакопленияОстатки'
REGISTER = 'AccumulationRegisters/' + REGISTER_NAME + '.xml'
MODULE = 'Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl'
VALIDATION_MODE = 'full-native-declaration-strict-semantic-redump-v2'
PUBLIC_ROOT = Path(__file__).parent / 'public_source' / 'vanessa_add'
NATIVE_SHA256 = '19f0e833301d68843e0dddb921a678def1c0e819037a501200bab3fce3a6e227'
NATIVE_GIT_BLOB = '154bb545aa8f71b63559e1fb123f401c4c245b58'
NATIVE_SIZE = 10303
INPUT_SCHEMA_VERSION = '2.4'
SCHEMA_VERSIONS = (None, '2.4', '2.20', 'other')
OLD_TARGET = b'AccumulationRegister.OwnedAccumulationRows'
NEW_TARGET = ('AccumulationRegister.' + REGISTER_NAME).encode('utf-8')


def native_declaration():
    path = PUBLIC_ROOT / (REGISTER_NAME + '.xml')
    original._require(not path.is_symlink() and path.is_file() and path.stat().st_size == NATIVE_SIZE)
    raw = path.read_bytes()
    original._require(len(raw) == NATIVE_SIZE and raw.startswith(b'\xef\xbb\xbf')
                      and hashlib.sha256(raw).hexdigest() == NATIVE_SHA256
                      and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == NATIVE_GIT_BLOB)
    return raw


def _replace_once(raw, before, after):
    original._require(raw.count(before) == 1)
    return raw.replace(before, after, 1)


def declarations():
    _, assets = source.load_saved()
    return {DOCUMENT: _replace_once(assets['Document.xml'], OLD_TARGET, NEW_TARGET),
            REGISTER: native_declaration()}


def prepare(files):
    setup, expected = source.prepare(files)
    del expected[MODULE]
    del expected[SOURCE_REGISTER]
    expected['Configuration.xml'] = _replace_once(expected['Configuration.xml'],
        b'>OwnedAccumulationRows<', ('>' + REGISTER_NAME + '<').encode('utf-8'))
    role = original.ROLE_FILES[1]
    expected[role] = _replace_once(expected[role], b'>' + OLD_TARGET + b'<', b'>' + NEW_TARGET + b'<')
    expected.update(declarations())
    _files(expected)
    original._require(set(expected) == set(files) | {DOCUMENT, REGISTER})
    return setup, expected


def verify_redump(expected, actual):
    """Strict signatures include the original 2.4 schema and all native defaults.

    No schema upgrade, generated type, property, field, grant or file relaxation.
    Only ConfigDumpInfo.xml export bookkeeping follows the bootstrap exception.
    """
    owned = declarations()
    original._require(all(path not in files for path in (MODULE, SOURCE_REGISTER) for files in (expected, actual)))
    original._require(all(expected.get(name) == raw for name, raw in owned.items()))
    return original.verify_redump(expected, actual)


def target_schema_version(files):
    """Finite version fact only; never export arbitrary native XML attribute text."""
    raw = files.get(REGISTER)
    if raw is None:
        return None
    root, _ = original._xml(raw)
    version = root.attrib.get('version')
    return version if version in ('2.4', '2.20') else 'other'


def inventory_digest(files):
    _files(files)
    value = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


# The existing bounded diagnostic hashes unknown filenames, including the public
# native register's Cyrillic filename. It never expands to arbitrary XML text.
redump_diagnostic = source.redump_diagnostic
valid_diagnostic = source.valid_diagnostic
