"""Separate, source-bound DESIGNER-only demo acquisition. No ENTERPRISE route."""
from __future__ import annotations
import base64
import binascii
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

SCHEMA = 'native-demo-designer-v5'
VERSION = '8.3.27.1508'
IMAGE = 'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728'
ONEC = '/opt/1cv8t/x86_64/' + VERSION + '/1cv8t'
CHECK_FLAGS = ('-ConfigLogIntegrity', '-IncorrectReferences', '-ThinClient', '-Server',
               '-ThickClientManagedApplication', '-HandlersExistence', '-ExtendedModulesCheck')
# Retired historical acquisition: offline comparison still uses exact old bytes.
SOURCE_ROOT = 'examples/demo'
HISTORICAL_ROOT = 'tests/fixtures/legacy_demo_root.xml'
SOURCE_FILES = (
    'Catalogs/ВидыНоменклатуры.xml',
    'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента.xml',
    'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form.xml',
    'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form/Module.bsl',
    'Catalogs/Номенклатура.xml',
    'Catalogs/Номенклатура/Ext/ObjectModule.bsl',
    'Catalogs/Номенклатура/Forms/ФормаСписка.xml',
    'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form.xml',
    'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form/Module.bsl',
    'Catalogs/Номенклатура/Forms/ФормаЭлемента.xml',
    'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form.xml',
    'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form/Module.bsl',
    'Catalogs/Склады.xml',
    'Configuration.xml',
    'Ext/ClientApplicationInterface.xml',
    'Ext/CommandInterface.xml',
    'Ext/HomePageWorkArea.xml',
    'Languages/Русский.xml',
    'Subsystems/НормативнаяИнформация.xml',
)
INPUTS = ('scripts/native_1c_demo_designer.py', 'scripts/native_1c_demo_designer.sh',
          'tests/legacy_demo_fixture.py', HISTORICAL_ROOT,
          *(SOURCE_ROOT + '/' + name for name in SOURCE_FILES if name != 'Configuration.xml'))
PHASES = ('inputs', 'create', 'load', 'check', 'update', 'redump', 'witness', 'complete')
FAILURES = ('none', 'invalid_input', 'process_failed', 'timeout', 'invalid_result', 'witness_mismatch')

class DemoError(ValueError):
    pass


def require(condition, reason='invalid_input'):
    if not condition:
        raise DemoError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=1048576):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit)
    with path.open('rb') as source:
        data = source.read(limit + 1)
    require(len(data) <= limit)
    return data


def inventory(root):
    return {name: digest(read_regular(root / name)) for name in INPUTS}


def stage_inputs(root, target):
    source_files(root)  # Reject unexpected/missing source paths before staging.
    require(not target.exists() and not target.is_symlink())
    hashes = inventory(root)
    target.mkdir(mode=0o755)
    for name in INPUTS:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(read_regular(root / name))
        path.chmod(0o644)
    for path in target.rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
    require(inventory(target) == hashes)
    return hashes


def dump_files(root):
    require(root.is_dir() and not root.is_symlink())
    result, pending, count, total = {}, [root], 0, 0
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                count += 1
                require(count <= 512)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    pending.append(Path(entry.path))
                else:
                    path = Path(entry.path)
                    raw = read_regular(path)
                    total += len(raw)
                    require(total <= 8 * 1048576 and len(result) < 256)
                    result[path.relative_to(root).as_posix()] = raw
    return result


def source_files(root=ROOT):
    # This is the historical 19-file projection, not current main-demo acceptance.
    import importlib.util
    spec = importlib.util.spec_from_file_location('legacy_demo_fixture', root / 'tests/legacy_demo_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        files = module.legacy_demo_files(root)
    except (ValueError, OSError):
        raise DemoError('invalid_input') from None
    require(set(files) == set(SOURCE_FILES))
    return files


def stage_source(destination, expected):
    require(set(expected) == set(SOURCE_FILES))
    destination.mkdir(mode=0o700, exist_ok=False)
    for name in SOURCE_FILES:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as target:
            target.write(expected[name])
    require(dump_files(destination) == expected)


def xml_signature(raw):
    # Conservative: preserve QName prefix bindings, significant leaf text and all
    # attributes. Prefix/default/schema rewrites need separate native evidence.
    try:
        text = raw.decode('utf-8-sig')
        require('\x00' not in text and '<!DOCTYPE' not in text.upper()
                and '<!ENTITY' not in text.upper(), 'witness_mismatch')
        body = re.sub(r'^<\?xml\s+[^?]*\?>', '', text, count=1)
        require('<?' not in body, 'witness_mismatch')
        namespaces = {}
        for _, (prefix, uri) in ET.iterparse(io.StringIO(text), events=('start-ns',)):
            require(prefix not in namespaces or namespaces[prefix] == uri, 'witness_mismatch')
            namespaces[prefix] = uri
        root = ET.fromstring(text)
        def visit(node, depth=0):
            require(depth < 128, 'witness_mismatch')
            value = node.text or ''
            if len(node) and not value.strip(' \t\r\n'):
                value = ''  # indentation between elements only
            return (node.tag, tuple(sorted(node.attrib.items())), value,
                    tuple((visit(child, depth + 1), '' if not (child.tail or '').strip(' \t\r\n')
                           else child.tail) for child in node))
        return tuple(sorted(namespaces.items())), visit(root)
    except (ET.ParseError, RecursionError, UnicodeError, ValueError):
        raise DemoError('witness_mismatch') from None


def redump_mismatches(expected, actual):
    failures = {}
    if set(actual) - {'ConfigDumpInfo.xml'} - set(expected):
        failures['$inventory'] = 'unexpected_file'
    for name, raw in expected.items():
        if name not in actual:
            failures[name] = 'missing_file'
            continue
        try:
            if name.endswith('.bsl'):
                normalize = lambda data: data.decode('utf-8-sig').replace('\r\n', '\n')
                if normalize(raw) != normalize(actual[name]):
                    failures[name] = 'module_changed'
            elif xml_signature(raw) != xml_signature(actual[name]):
                failures[name] = 'metadata_changed'
        except (DemoError, UnicodeError):
            failures[name] = 'invalid_encoding_or_xml'
    return failures


def verify_redump(expected, actual):
    require(not redump_mismatches(expected, actual), 'witness_mismatch')
    return {name: digest(actual[name]) for name in sorted(expected)}


# Diagnostic metadata never participates in acceptance. Counts are positional
# observations, not a claim that a native rewrite is semantically harmless.
XML_FILES = tuple(name for name in SOURCE_FILES if name.endswith('.xml'))
DIAGNOSTIC_MAX_BYTES = 1048576
DIAGNOSTIC_MAX_NODES = 4096
DIAGNOSTIC_MAX_DEPTH = 96
DIAGNOSTIC_MAX_STRING = 65536
DIAGNOSTIC_MAX_OUTPUT = 6144
DIAGNOSTIC_COUNTS = ('namespace_bindings', 'root_name', 'root_version',
                     'attributes', 'text', 'child_shape', 'element_names')
DIAGNOSTIC_COMPARISONS = ('equal', 'namespace_only', 'expanded_tree', 'namespace_and_tree',
                          'unavailable')
DIAGNOSTIC_REASONS = ('none', 'missing', 'input_limit', 'parse_rejected', 'analysis_limit')
# Records contain only source preorder IDs, finite kinds, source attribute slots,
# and bounded counts. Never serialize a name or value from the native dump.
ADDRESS_KINDS = ('attribute_changed', 'attribute_removed', 'attributes_added',
                 'text_changed', 'tail_changed', 'children_added', 'child_removed',
                 'child_order_changed', 'children_ambiguous', 'element_name_changed')
ADDRESS_MAX_RECORDS = 12
ADDRESS_MAX_TOTAL = 32768


def source_nodes(tree):
    """Deterministic preorder of the acceptance signature, not native paths."""
    result, pending = [], [tree]
    while pending:
        node = pending.pop()
        result.append(node)
        pending.extend(child for child, _ in reversed(node[3]))
    return result


def xml_addresses(left, right):
    """Align unique sibling QNames only; repeated names never imply identity."""
    nodes = source_nodes(left)
    identifiers = {id(node): index for index, node in enumerate(nodes)}
    records, total = [], 0

    def add(node, kind, slot=0, count=1):
        nonlocal total
        total += 1
        entry = [identifiers[id(node)], ADDRESS_KINDS.index(kind), slot, min(count, DIAGNOSTIC_MAX_NODES)]
        records.append(entry)
        # Structural changes first; common root-version churn must not crowd out
        # source-addressed observations deeper in Configuration and form XML.
        records.sort(key=lambda item: (9 if item[0] == 0 and item[1] in (0, 1) else
                                      3 if item[1] in (0, 1, 2) else
                                      2 if item[1] in (3, 4, 8) else 1))
        del records[ADDRESS_MAX_RECORDS:]

    pending = [(left, right)]
    while pending:
        before, after = pending.pop()
        if before == after:
            continue
        if before[0] != after[0]:
            add(before, 'element_name_changed')
            # No asserted descendant identity across an expanded-name change.
            continue
        attrs_before, attrs_after = dict(before[1]), dict(after[1])
        for slot, (name, value) in enumerate(before[1]):
            if name not in attrs_after:
                add(before, 'attribute_removed', slot)
            elif value != attrs_after[name]:
                add(before, 'attribute_changed', slot)
        extra = len(attrs_after.keys() - attrs_before.keys())
        if extra:
            add(before, 'attributes_added', count=extra)
        if before[2] != after[2]:
            add(before, 'text_changed')
        groups_before, groups_after = {}, {}
        for child, tail in before[3]:
            groups_before.setdefault(child[0], []).append((child, tail))
        for child, tail in after[3]:
            groups_after.setdefault(child[0], []).append((child, tail))
        added = sum(len(children) for name, children in groups_after.items() if name not in groups_before)
        if added:
            add(before, 'children_added', count=added)
        # Child-list order is an observation, never accepted as harmless.
        # Compare stable name multiplicities, including repeated groups, so an
        # unrelated insertion cannot hide movement of existing sibling groups.
        stable = {name for name in groups_before.keys() & groups_after.keys()
                  if len(groups_before[name]) == len(groups_after[name])}
        old_order = [child[0] for child, _ in before[3] if child[0] in stable]
        new_order = [child[0] for child, _ in after[3] if child[0] in stable]
        if old_order != new_order:
            add(before, 'child_order_changed')
        children_to_visit = []
        for name, group in groups_before.items():
            other = groups_after.get(name, [])
            if not other:
                for child, _ in group:
                    add(child, 'child_removed')
            elif len(group) != 1 or len(other) != 1:
                if group != other:
                    add(group[0][0], 'children_ambiguous', count=max(len(group), len(other)))
            else:
                (child, tail), (other_child, other_tail) = group[0], other[0]
                if tail != other_tail:
                    add(child, 'tail_changed')
                children_to_visit.append((child, other_child))
        pending.extend(reversed(children_to_visit))
    return records, total - len(records)


def diagnostic_signature(raw):
    """Bound work before using the unchanged acceptance signature."""
    if type(raw) is not bytes or len(raw) > DIAGNOSTIC_MAX_BYTES:
        return None, 'input_limit'
    try:
        text = raw.decode('utf-8-sig')
        if ('\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper()
                or '<?' in re.sub(r'^<\?xml\s+[^?]*\?>', '', text, count=1)):
            return None, 'parse_rejected'
        depth = nodes = attributes = declarations = 0
        for event, node in ET.iterparse(io.StringIO(text), events=('start', 'end', 'start-ns')):
            if event == 'start-ns':
                declarations += 1
                if declarations > DIAGNOSTIC_MAX_NODES or any(len(v) > DIAGNOSTIC_MAX_STRING for v in node):
                    return None, 'analysis_limit'
            elif event == 'start':
                depth += 1
                nodes += 1
                attributes += len(node.attrib)
                if (depth > DIAGNOSTIC_MAX_DEPTH or nodes > DIAGNOSTIC_MAX_NODES
                        or attributes > DIAGNOSTIC_MAX_NODES or len(node.tag) > DIAGNOSTIC_MAX_STRING
                        or any(len(k) > DIAGNOSTIC_MAX_STRING or len(v) > DIAGNOSTIC_MAX_STRING
                               for k, v in node.attrib.items())):
                    return None, 'analysis_limit'
            else:
                if len(node.text or '') > DIAGNOSTIC_MAX_STRING or len(node.tail or '') > DIAGNOSTIC_MAX_STRING:
                    return None, 'analysis_limit'
                depth -= 1
        return xml_signature(raw), 'none'
    except (DemoError, UnicodeError, ET.ParseError, RecursionError, ValueError):
        return None, 'parse_rejected'


def xml_diagnostic(before, after):
    """Return only finite categories/counts and bounded-byte hashes; no XML text."""
    result = dict(comparison='unavailable', reason='missing', counts=[0] * len(DIAGNOSTIC_COUNTS),
                  before_sha256=None, after_sha256=None, addresses=[], omitted=0)
    for field, raw in (('before_sha256', before), ('after_sha256', after)):
        if type(raw) is bytes and len(raw) <= DIAGNOSTIC_MAX_BYTES:
            result[field] = digest(raw)
    if before is None or after is None:
        return result
    left, reason = diagnostic_signature(before)
    right, other = diagnostic_signature(after)
    if left is None or right is None:
        result['reason'] = reason if left is None else other
        return result
    ns_left, tree_left = left
    ns_right, tree_right = right
    bindings_left, bindings_right = dict(ns_left), dict(ns_right)
    counts = result['counts']
    counts[0] = sum(bindings_left.get(k) != bindings_right.get(k)
                    for k in bindings_left.keys() | bindings_right.keys())
    counts[1] = int(tree_left[0] != tree_right[0])
    counts[2] = int(dict(tree_left[1]).get('version') != dict(tree_right[1]).get('version'))
    pending = [(tree_left, tree_right)]
    while pending:
        first, second = pending.pop()
        counts[3] += int(first[1] != second[1])
        counts[4] += int(first[2] != second[2])
        counts[5] += int(len(first[3]) != len(second[3]))
        counts[6] += int(first[0] != second[0])
        for (child_a, tail_a), (child_b, tail_b) in zip(first[3], second[3]):
            counts[4] += int(tail_a != tail_b)
            pending.append((child_a, child_b))
    result['counts'] = [min(value, DIAGNOSTIC_MAX_NODES) for value in counts]
    changed_ns, changed_tree = ns_left != ns_right, tree_left != tree_right
    result.update(comparison=('namespace_and_tree' if changed_ns and changed_tree else
                              'namespace_only' if changed_ns else 'expanded_tree' if changed_tree else 'equal'),
                  reason='none')
    result['addresses'], result['omitted'] = xml_addresses(tree_left, tree_right)
    return result


def xml_diagnostics(expected, actual, mismatches):
    files = []
    for index, name in enumerate(XML_FILES):
        if name in mismatches:
            files.append(dict(file=index, **xml_diagnostic(expected.get(name), actual.get(name))))
    result = dict(state='available', files=files)
    # Preserve all file summaries. Remove details round-robin from the largest
    # lists first, with an explicit per-file omission count.
    while len(json.dumps(result, separators=(',', ':')).encode()) > DIAGNOSTIC_MAX_OUTPUT:
        candidates = [item for item in files if item['addresses']]
        if not candidates:
            return dict(state='budget_limit', files=[])
        item = max(candidates, key=lambda entry: len(entry['addresses']))
        item['addresses'].pop()
        item['omitted'] += 1
    return result


def validate_xml_diagnostics(value, mismatches, expected=None):
    require(type(value) is dict and set(value) == {'state', 'files'}
            and value['state'] in ('available', 'not_reached', 'budget_limit')
            and type(value['files']) is list and len(value['files']) <= len(XML_FILES), 'invalid_result')
    require(len(json.dumps(value, separators=(',', ':')).encode()) <= DIAGNOSTIC_MAX_OUTPUT, 'invalid_result')
    if value['state'] != 'available':
        require(value['files'] == [], 'invalid_result')
        return
    seen = set()
    expected = source_files() if expected is None else expected
    for item in value['files']:
        require(type(item) is dict and set(item) == {'file', 'comparison', 'reason', 'counts',
                'before_sha256', 'after_sha256', 'addresses', 'omitted'}, 'invalid_result')
        index = item['file']
        require(type(index) is int and 0 <= index < len(XML_FILES) and index not in seen
                and XML_FILES[index] in mismatches, 'invalid_result')
        seen.add(index)
        require(item['comparison'] in DIAGNOSTIC_COMPARISONS and item['comparison'] != 'equal'
                and item['reason'] in DIAGNOSTIC_REASONS, 'invalid_result')
        counts = item['counts']
        require(type(counts) is list and len(counts) == len(DIAGNOSTIC_COUNTS)
                and all(type(n) is int and 0 <= n <= DIAGNOSTIC_MAX_NODES for n in counts)
                and counts[1] <= 1 and counts[2] <= 1, 'invalid_result')
        for field in ('before_sha256', 'after_sha256'):
            require(item[field] is None or type(item[field]) is str
                    and re.fullmatch('[0-9a-f]{64}', item[field]) is not None, 'invalid_result')
        addresses, omitted = item['addresses'], item['omitted']
        require(type(addresses) is list and len(addresses) <= ADDRESS_MAX_RECORDS
                and type(omitted) is int and 0 <= omitted <= ADDRESS_MAX_TOTAL, 'invalid_result')
        if addresses or omitted:
            signature, reason = diagnostic_signature(expected.get(XML_FILES[index]))
            require(signature is not None and reason == 'none', 'invalid_result')
            nodes = source_nodes(signature[1])
            seen_addresses = set()
            for entry in addresses:
                require(type(entry) is list and len(entry) == 4
                        and all(type(n) is int for n in entry), 'invalid_result')
                node, kind, slot, count = entry
                require(0 <= node < len(nodes) and 0 <= kind < len(ADDRESS_KINDS)
                        and 1 <= count <= DIAGNOSTIC_MAX_NODES, 'invalid_result')
                require((kind in (0, 1) and 0 <= slot < len(nodes[node][1]))
                        or (kind not in (0, 1) and slot == 0), 'invalid_result')
                require(kind in (2, 5, 8) or count == 1, 'invalid_result')
                key = tuple(entry[:3])
                require(key not in seen_addresses, 'invalid_result')
                seen_addresses.add(key)
        require(len(addresses) + omitted <= ADDRESS_MAX_TOTAL, 'invalid_result')
        if item['comparison'] in ('unavailable', 'namespace_only'):
            require(not addresses and omitted == 0, 'invalid_result')
        else:
            require(addresses or omitted > 0, 'invalid_result')
        if item['comparison'] == 'unavailable':
            require(item['reason'] != 'none' and not any(counts), 'invalid_result')
        else:
            require(item['reason'] == 'none' and item['before_sha256'] is not None
                    and item['after_sha256'] is not None, 'invalid_result')
            ns, tree = counts[0] > 0, any(counts[1:])
            require((item['comparison'], ns, tree) in (('namespace_only', True, False),
                    ('expanded_tree', False, True), ('namespace_and_tree', True, True)), 'invalid_result')
    require(seen == {i for i, name in enumerate(XML_FILES) if name in mismatches}, 'invalid_result')


def operations(root):
    db = root / 'db'
    common = ['/AppAutoCheckVersion-', '/DisableStartupDialogs', '/DisableStartupMessages', '/L', 'ru']
    result = [('create', [ONEC, 'CREATEINFOBASE', f'File="{db}";', '/Lru'])]
    for phase, flags in (
        ('load', ['/LoadConfigFromFiles', str(root / 'source')]),
        ('check', ['/CheckConfig', *CHECK_FLAGS]),
        ('update', ['/UpdateDBCfg']),
        ('redump', ['/DumpConfigToFiles', str(root / 'redump'), '-Format', 'Hierarchical'])):
        result.append((phase, [ONEC, 'DESIGNER', '/F', str(db), *common, *flags]))
    return [(phase, command + ['/Out', str(root / (phase + '.log')),
                               '/DumpResult', str(root / (phase + '.result'))])
            for phase, command in result]


def zero_result(path):
    raw = read_regular(path, 128)
    try:
        text = raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig').strip()
    except UnicodeError:
        raise DemoError('invalid_result') from None
    require(text == '0', 'invalid_result')


def native_quiet():
    # Container PID namespace only. Refuse overlap with surviving native children.
    for item in Path('/proc').iterdir():
        if item.name.isdigit():
            try:
                executable = os.readlink(item / 'exe')
            except FileNotFoundError:
                continue
            except PermissionError:
                raise DemoError('process_failed') from None
            require(not Path(executable).name.startswith('1cv8'), 'process_failed')


EXPORT_SCHEMA = 'native-demo-xml-export-v1'
WIRE_SCHEMA = 'native-demo-designer-wire-v1'
EXPORT_MAX_FILE = 256 * 1024
EXPORT_MAX_TOTAL = 1024 * 1024
WIRE_MAX_BYTES = 1536 * 1024
EXPORT_REASONS = ('none', 'not_reached', 'invalid_inventory', 'invalid_xml', 'export_limit')


def xml_export(actual):
    """Only the fixed public-demo XML inventory; no other dump bytes escape."""
    result = dict(state='unavailable', reason='not_reached', files=[])
    if actual is None:
        return result
    if (type(actual) is not dict or set(actual) - {'ConfigDumpInfo.xml'} != set(SOURCE_FILES)):
        result['reason'] = 'invalid_inventory'
        return result
    files, total = [], 0
    for index, name in enumerate(XML_FILES):
        raw = actual[name]
        if type(raw) is not bytes or not 0 < len(raw) <= EXPORT_MAX_FILE:
            result['reason'] = 'export_limit'
            return result
        total += len(raw)
        if total > EXPORT_MAX_TOTAL:
            result['reason'] = 'export_limit'
            return result
        signature, reason = diagnostic_signature(raw)
        if signature is None or reason != 'none':
            result['reason'] = 'invalid_xml'
            return result
        files.append(dict(file=index, size=len(raw), sha256=digest(raw),
                          base64=base64.b64encode(raw).decode('ascii')))
    return dict(state='available', reason='none', files=files)


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def validate_wire(raw, nonce, hashes, expected):
    """Treat all native bytes as untrusted, including the indexed export."""
    require(type(raw) is bytes and 0 < len(raw) <= WIRE_MAX_BYTES, 'invalid_result')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'invalid_result')
            result[key] = value
        return result
    try:
        wire = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise DemoError('invalid_result') from None
    require(type(wire) is dict and set(wire) == {'schema', 'report', 'export'}
            and wire['schema'] == WIRE_SCHEMA, 'invalid_result')
    report = validate_report(json_bytes(wire['report']), nonce, hashes)
    export = wire['export']
    require(type(export) is dict and set(export) == {'state', 'reason', 'files'}
            and export['state'] in ('available', 'unavailable') and export['reason'] in EXPORT_REASONS
            and type(export['files']) is list, 'invalid_result')
    if export['state'] == 'unavailable':
        require(export['reason'] != 'none' and export['files'] == [], 'invalid_result')
        require((export['reason'] == 'not_reached') == (report['phase'] not in ('witness', 'complete')),
                'invalid_result')
        return report, export, {}
    require(export['reason'] == 'none' and report['phase'] in ('witness', 'complete')
            and len(export['files']) == len(XML_FILES), 'invalid_result')
    require('$inventory' not in report['mismatches']
            and not any(value == 'missing_file' for value in report['mismatches'].values()), 'invalid_result')
    result, total = {}, 0
    for index, item in enumerate(export['files']):
        require(type(item) is dict and set(item) == {'file', 'size', 'sha256', 'base64'}
                and type(item['file']) is int and item['file'] == index
                and type(item['size']) is int and 0 < item['size'] <= EXPORT_MAX_FILE
                and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']) is not None
                and type(item['base64']) is str and len(item['base64']) <= 4 * ((EXPORT_MAX_FILE + 2) // 3),
                'invalid_result')
        total += item['size']
        require(total <= EXPORT_MAX_TOTAL, 'invalid_result')
        try:
            decoded = base64.b64decode(item['base64'], validate=True)
        except (ValueError, binascii.Error):
            raise DemoError('invalid_result') from None
        require(len(decoded) == item['size'] and digest(decoded) == item['sha256']
                and base64.b64encode(decoded).decode('ascii') == item['base64'], 'invalid_result')
        signature, reason = diagnostic_signature(decoded)
        require(signature is not None and reason == 'none', 'invalid_result')
        result[XML_FILES[index]] = decoded
    expected_xml = {name: expected[name] for name in XML_FILES}
    mismatches = redump_mismatches(expected_xml, result)
    require(mismatches == {name: value for name, value in report['mismatches'].items() if name in XML_FILES},
            'invalid_result')
    require(xml_diagnostics(expected_xml, result, mismatches) == report['xml_diagnostics'], 'invalid_result')
    for name, raw_xml in result.items():
        if name in report['redump_sha256']:
            require(report['redump_sha256'][name] == digest(raw_xml), 'invalid_result')
    return report, export, result


def publish_xml_evidence(destination, summary, exported):
    """Exclusive output root; only a complete atomic payload is uploadable."""
    require(summary.get('container_cleanup_verified') is True
            and summary.get('docker_cli_reap_verified') is True
            and summary.get('enterprise_executed') is False
            and summary.get('security_settings_changed') is False, 'invalid_result')
    require(set(exported) == set(XML_FILES), 'invalid_result')
    # Recheck the exact byte inventory before creating any output artifact.
    rows, total = [], 0
    for index, name in enumerate(XML_FILES):
        raw = exported[name]
        require(type(raw) is bytes and 0 < len(raw) <= EXPORT_MAX_FILE, 'invalid_result')
        total += len(raw)
        require(total <= EXPORT_MAX_TOTAL and diagnostic_signature(raw)[0] is not None, 'invalid_result')
        rows.append(dict(file=index, source=name, path=f'xml/{index:02d}.xml', size=len(raw), sha256=digest(raw)))
    report_bytes = json_bytes(summary)
    manifest = dict(schema=EXPORT_SCHEMA, source_sha=summary['source_sha'], nonce=summary['native']['nonce'],
                    input_sha256=summary['native']['input_sha256'], report_sha256=digest(report_bytes), files=rows)
    # The parent is the trusted checkout. A preexisting directory/file/symlink is
    # never reused or removed. The newly reserved private root is ours alone.
    require(destination.parent.is_dir() and not destination.parent.is_symlink(), 'invalid_result')
    destination.mkdir(mode=0o700, exist_ok=False)
    committed = False
    try:
        staging = destination / '.staging'
        staging.mkdir(mode=0o700)
        (staging / 'xml').mkdir(mode=0o700)
        files = {'report.json': report_bytes, 'manifest.json': json_bytes(manifest),
                 **{row['path']: exported[XML_FILES[row['file']]] for row in rows}}
        for name, raw in files.items():
            with (staging / name).open('xb') as target:
                target.write(raw)
            (staging / name).chmod(0o600)
        # Publish all seventeen files together; the final path did not exist in
        # this exclusively created directory. Workflow never uploads staging.
        staging.rename(destination / 'payload')
        committed = True
    finally:
        if not committed:
            shutil.rmtree(destination)


def native_run(nonce):
    report = dict(schema=SCHEMA, nonce=nonce, status='failed', phase='inputs', failure='invalid_input',
                  input_sha256={}, redump_sha256={}, mismatches={},
                  xml_diagnostics=dict(state='not_reached', files=[]))
    actual = None
    try:
        require(re.fullmatch('[0-9a-f]{32}', nonce) is not None and os.getuid() == 1000)
        report['input_sha256'] = inventory(ROOT)
        root = Path('/tmp/demo-designer')
        root.mkdir(mode=0o700)
        expected = source_files()
        stage_source(root / 'source', expected)
        (root / 'redump').mkdir()
        for phase, command in operations(root):
            report['phase'] = phase
            require(not (root / (phase + '.result')).exists())
            # Outer owned-container deadline/removal is the hard process-tree bound.
            code = subprocess.run(['timeout', '--signal=TERM', '--kill-after=5s', '120s', *command],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=135).returncode
            require(code == 0, 'timeout' if code in (124, 137) else 'process_failed')
            native_quiet()
            zero_result(root / (phase + '.result'))
            if phase == 'create':
                require((root / 'db/1Cv8.1CD').is_file(), 'invalid_result')
        report['phase'] = 'witness'
        actual = dump_files(root / 'redump')
        report['mismatches'] = redump_mismatches(expected, actual)
        report['xml_diagnostics'] = xml_diagnostics(expected, actual, report['mismatches'])
        report['redump_sha256'] = verify_redump(expected, actual)
        require(inventory(ROOT) == report['input_sha256'])
        report.update(status='ok', phase='complete', failure='none')
    except subprocess.TimeoutExpired:
        report['failure'] = 'timeout'
    except Exception as error:
        report['failure'] = str(error) if isinstance(error, DemoError) and str(error) in FAILURES else 'invalid_input'
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode()) > 16384:
        report['xml_diagnostics'] = dict(state='budget_limit', files=[])
        encoded = json.dumps(report, sort_keys=True, separators=(',', ':'))
    require(len(encoded.encode()) <= 16384, 'invalid_result')
    export = xml_export(actual)
    if actual is None and report['phase'] in ('witness', 'complete'):
        export['reason'] = 'invalid_inventory'
    # Preserve the finite strict summary even when export qualification fails.
    wire = json_bytes(dict(schema=WIRE_SCHEMA, report=report, export=export))
    require(len(wire) <= WIRE_MAX_BYTES, 'invalid_result')
    print(wire.decode('utf-8'))
    return 0 if report['status'] == 'ok' else 1


def container_command(staged, nonce):
    require(staged.is_absolute() and ',' not in str(staged) and re.fullmatch('[0-9a-f]{32}', nonce))
    return ['docker', 'create', '--name', 'onec-demo-designer-' + nonce,
            '--label', 'org.yadinassi.native.invocation=' + nonce, '--hostname', 'onec-smoke',
            '--pull', 'never', '--platform', 'linux/amd64', '--network', 'none',
            '--user', '1000:1000', '--read-only', '--no-healthcheck', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--pids-limit', '256',
            '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
            '--ulimit', 'nofile=1024:1024', '--ulimit', 'fsize=67108864:67108864',
            '--ipc', 'private', '--shm-size', '128m', '--log-driver', 'none',
            '--stop-timeout', '10', '--init',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777',
            '--mount', f'type=bind,src={staged},dst=/smoke,readonly',
            '--workdir', '/tmp', '--entrypoint', '/usr/bin/env', IMAGE, '-i',
            'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME=/tmp/home', 'XDG_RUNTIME_DIR=/tmp/runtime', 'DISPLAY=:99',
            'LANG=ru_RU.UTF-8', 'LC_ALL=ru_RU.UTF-8', 'TZ=Etc/UTC',
            '/bin/bash', '--noprofile', '--norc', '/smoke/scripts/native_1c_demo_designer.sh', nonce]


def validate_report(raw, nonce, hashes):
    require(type(raw) is bytes and len(raw) <= 16384, 'invalid_result')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'invalid_result')
            value[key] = item
        return value
    try:
        report = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise DemoError('invalid_result') from None
    require(type(report) is dict and set(report) == {'schema', 'nonce', 'status', 'phase', 'failure',
            'input_sha256', 'redump_sha256', 'mismatches', 'xml_diagnostics'}, 'invalid_result')
    require(report['schema'] == SCHEMA and report['nonce'] == nonce
            and report['input_sha256'] == hashes and report['phase'] in PHASES
            and report['failure'] in FAILURES and report['status'] in ('ok', 'failed'), 'invalid_result')
    failures = report['mismatches']
    require(type(failures) is dict and set(failures) <= set(SOURCE_FILES) | {'$inventory'}
            and all(type(value) is str and value in ('unexpected_file', 'missing_file', 'module_changed',
                    'metadata_changed', 'invalid_encoding_or_xml') for value in failures.values()), 'invalid_result')
    validate_xml_diagnostics(report['xml_diagnostics'], failures)
    if report['xml_diagnostics']['state'] != 'not_reached':
        require(report['phase'] in ('witness', 'complete'), 'invalid_result')
    witness = report['redump_sha256']
    require(type(witness) is dict, 'invalid_result')
    require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) for value in witness.values()), 'invalid_result')
    if report['status'] == 'ok':
        require(not failures and report['phase'] == 'complete' and report['failure'] == 'none'
                and set(witness) == set(SOURCE_FILES), 'invalid_result')
    else:
        require(report['failure'] != 'none' and set(witness) <= set(SOURCE_FILES), 'invalid_result')
    return report


def run_host():
    import native_1c_docker_lifecycle as lifecycle
    import native_1c_smoke as smoke
    require(IMAGE == smoke.IMAGE and VERSION == smoke.EXPECTED_VERSION)
    def revision():
        value = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                        stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        require(re.fullmatch('[0-9a-f]{40}', value) is not None)
        subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', 'HEAD'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True)
        return value
    source_sha = revision()
    require(os.environ.get('GITHUB_SHA') == source_sha)
    nonce = uuid.uuid4().hex
    token, actor = os.environ.pop('GHCR_TOKEN', ''), os.environ.pop('GHCR_USER', '')
    require(token and re.fullmatch('[A-Za-z0-9-]{1,39}', actor))
    with tempfile.TemporaryDirectory(prefix='onec-demo-designer-') as directory:
        work = Path(directory).resolve()
        staged = work / 'staged'
        hashes = stage_inputs(ROOT, staged)
        expected = source_files()  # Exact public-source bytes for export validation.
        auth = work / 'auth'
        auth.mkdir(mode=0o700)
        try:
            env = smoke.docker_environment(auth)
            smoke.run_silent(['docker', 'login', 'ghcr.io', '--username', actor, '--password-stdin'], env, 60, token.encode())
            token = ''
            smoke.run_silent(['docker', 'pull', '--platform', 'linux/amd64', IMAGE], env, 600)
        finally:
            token = ''
            shutil.rmtree(auth)
        clean = work / 'no-auth'
        clean.mkdir(mode=0o700)
        code, raw = lifecycle.run_owned(container_command(staged, nonce), smoke.docker_environment(clean),
                                       name='onec-demo-designer-' + nonce, nonce=nonce, image=IMAGE,
                                       seconds=900, output_limit=WIRE_MAX_BYTES)
        report, export, exported = validate_wire(raw, nonce, hashes, expected)
        require(code == (0 if report['status'] == 'ok' else 1), 'invalid_result')
        require(inventory(ROOT) == hashes and inventory(staged) == hashes and revision() == source_sha)
    # Only after verified owned-container removal and private directory cleanup.
    summary = dict(schema=SCHEMA + '-host', source_sha=source_sha, image=IMAGE, expected_version=VERSION,
                   native=report, container_cleanup_verified=True, docker_cli_reap_verified=True,
                   enterprise_executed=False, security_settings_changed=False,
                   xml_export=dict(state=export['state'], reason=export['reason'], files=len(exported)))
    if exported:
        publish_xml_evidence(ROOT / 'demo-native-evidence', summary, exported)
    return summary


def failure_report(error):
    import native_1c_docker_lifecycle as lifecycle
    failure = dict(schema=SCHEMA + '-host', status='failed', failure='host_failed',
                   container_cleanup_verified=None, docker_cli_reap_verified=None)
    if isinstance(error, lifecycle.LifecycleError):
        failure.update(failure=str(error), container_cleanup_verified=error.container_cleanup_verified,
                       docker_cli_reap_verified=error.cli_reap_verified)
    return failure


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--inside-container':
        raise SystemExit(native_run(sys.argv[2]))
    if sys.argv[1:] != ['--execute-approved-image']:
        raise SystemExit('Use --execute-approved-image only after exact-source review and CI admission.')
    try:
        value = run_host()
        print(json.dumps(value, sort_keys=True))
        raise SystemExit(0 if value['native']['status'] == 'ok' else 1)
    except Exception as error:
        # Never serialize exception text, native logs, credentials or unvalidated bytes.
        print(json.dumps(failure_report(error)))
        raise SystemExit(1)
