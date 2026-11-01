"""Saved, closed InformationRegister+Catalog inputs; physical layout remains unbound."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.parsers import expat

from information_register_packet import register_packet as packet
from linked_card_packet import linked
from linked_card_packet.base import probe, scalar_wire
from protocol import require, unique

BLOCKS = packet.BLOCKS
STATES = packet.STATES
ROOT = Path(__file__).with_name('information_register_packet')
MD = 'http://v8.1c.ru/8.3/MDClasses'


def load(repeat):
    require(type(repeat) is int and repeat in (1, 2), 'invalid_input')
    from inputs import read_source
    root = ROOT/'generated'/('repeat-'+str(repeat))
    manifest = json.loads(read_source(root/'manifest.json'), object_pairs_hook=unique)
    require(type(manifest) is dict and set(manifest) == {'profile', 'names',
        'metadata_ids', 'record_ids', 'product_rows', 'attribute_names',
        'attribute_ids', 'order', 'cases', 'files'}, 'provenance_mismatch')
    s = linked.Setup(probe.Setup(*(tuple(manifest[k]) for k in
        ('names', 'metadata_ids', 'record_ids'))), *(tuple(manifest[k]) for k in
        ('product_rows', 'attribute_names', 'attribute_ids', 'order'))).validate()
    request = manifest['profile']
    packet.validate(s, request)
    expected = {f'InformationRegisters/{request["register"]}.xml',
        f'Catalogs/{request["catalog"]}.xml', *(b+'.bsl' for b in BLOCKS),
        *(f'setup-{state}.bsl' for state in STATES)}
    require(type(manifest['files']) is dict and set(manifest['files']) == expected,
            'provenance_mismatch')
    files = {name: read_source(root/name) for name in sorted(expected)}
    require(all(hashlib.sha256(raw).hexdigest() == manifest['files'][name]
                for name, raw in files.items()), 'provenance_mismatch')
    packet.validate_xml(s, request, {n: b for n, b in files.items() if n.endswith('.xml')})
    require(type(manifest['cases']) is dict and set(manifest['cases']) == set(BLOCKS),
            'provenance_mismatch')
    for block in BLOCKS:
        require(manifest['cases'][block] == [list(row) for row in packet.cases(s, request, block)],
                'provenance_mismatch')
        require(files[block+'.bsl'] == packet.render(s, request, block).encode(),
                'provenance_mismatch')
    for state in STATES:
        require(files['setup-'+state+'.bsl'] == packet.setup(s, request, state).encode(),
                'provenance_mismatch')
    return s, manifest, files


def profile(s):
    s.validate()
    for repeat in (1, 2):
        saved, manifest, _ = load(repeat)
        if saved == s:
            return manifest['profile']
    raise ValueError('information register saved identity not found')


def validate_capture(raw, s, block):
    require(type(block) is str and block in BLOCKS, 'invalid_input')
    request = profile(s)
    rows = scalar_wire.validate_output(raw)
    require(not any(row['status'] == 'observer-error' for row in rows), 'invalid_marker')
    try:
        packet.capture(raw, s, request)
    except ValueError as error:
        if str(error) != 'register-control':
            raise
        return {'availability': 'unavailable'}
    return {'availability': 'available'}


def require_setup_evidence(raw, s, state):
    return packet.require_setup(raw, s, profile(s), state)


def _configuration(raw, s, request):
    packet.validate(s, request)
    if type(raw) is not bytes or len(raw) > 1048576 or b'<!' in raw:
        raise ValueError('configuration-bound')
    root = ET.fromstring(raw)
    children = root.find('{'+MD+'}Configuration/{'+MD+'}ChildObjects')
    if (children is None or [n.text for n in children if n.tag == '{'+MD+'}Catalog']
            != ['NativeOracleItems'] or any(n.tag in ('{'+MD+'}Document', '{'+MD+'}InformationRegister') for n in children)):
        raise ValueError('baseline-register-catalog-inventory')
    parser, stack, spans = expat.ParserCreate(), [], []
    def start(name, attrs):
        stack.append(name.split(':')[-1])
        if stack == ['MetaDataObject', 'Configuration', 'ChildObjects']:
            if attrs:
                raise ValueError('configuration-children')
            index = parser.CurrentByteIndex
            spans.append((index, raw.find(b'>', index)+1, name))
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _: stack.pop()
    parser.Parse(raw, True)
    if len(spans) != 1:
        raise ValueError('configuration-span')
    start_at, end, name = spans[0]
    if raw[start_at:end].rstrip().endswith(b'/>'):
        raise ValueError('baseline-children')
    prefix = name.rsplit(':', 1)[0]+':' if ':' in name else ''
    additions = (f'<{prefix}InformationRegister>{request["register"]}</{prefix}InformationRegister>'
                 f'<{prefix}Catalog>{request["catalog"]}</{prefix}Catalog>').encode()
    return raw[:end]+additions+raw[end:]


def extend_sources(s, request, saved_fragments, configuration, rights):
    packet.validate_xml(s, request, saved_fragments)
    return {**saved_fragments, 'Configuration.xml': _configuration(configuration, s, request),
        'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml': packet.rights(s, request, rights)}


def verify_redump(s, request, saved, redumped):
    packet.validate_xml(s, request, saved)
    if type(redumped) is not dict or set(redumped) != set(saved):
        raise ValueError('register-redump-inventory')
    for name, raw in saved.items():
        # Full tree/attributes/text equality with used QName semantics. No
        # stripping StandardAttributes, GeneratedTypes, defaults or privileges.
        # !todo Designer default expansion requires actual native review first.
        if linked._redump_signature(raw) != linked._redump_signature(redumped[name]):
            raise ValueError('register-redump-profile')
    return True


def actual_mapping(s, request, redumped):
    """Only extract identities after exact whole-tree/QName verification."""
    saved = packet.xml(s, request)
    verify_redump(s, request, saved, redumped)
    ns = {'md': MD, 'xr': 'http://v8.1c.ru/8.3/xcf/readable'}
    reg = ET.fromstring(redumped['InformationRegisters/'+request['register']+'.xml']).find('md:InformationRegister', ns)
    cat = ET.fromstring(redumped['Catalogs/'+request['catalog']+'.xml']).find('md:Catalog', ns)
    generated = {}
    for node in reg.findall('md:InternalInfo/xr:GeneratedType', ns):
        family = node.get('category')
        require(family in packet.FAMILIES and family not in generated and
                node.get('name') == 'InformationRegister'+family+'.'+request['register'], 'metadata_rejected')
        generated[family] = dict(type_uuid=node.findtext('xr:TypeId', namespaces=ns),
                                 value_uuid=node.findtext('xr:ValueId', namespaces=ns))
    require(generated == {family: dict(type_uuid=request['ids'][family+'.TypeId'],
        value_uuid=request['ids'][family+'.ValueId']) for family in packet.FAMILIES}, 'metadata_rejected')
    refs = [n for n in cat.findall('md:InternalInfo/xr:GeneratedType', ns)
            if n.get('category') == 'Ref' and n.get('name') == 'CatalogRef.'+request['catalog']]
    require(len(refs) == 1, 'metadata_rejected')
    catalog = dict(name=cat.findtext('md:Properties/md:Name', namespaces=ns),
        metadata_uuid=cat.get('uuid'), ref_type_uuid=refs[0].findtext('xr:TypeId', namespaces=ns))
    require(catalog == dict(name=request['catalog'], metadata_uuid=s.base.metadata_ids[1],
        ref_type_uuid=request['catalog_schema']['generated_ids'][request['catalog']]['REF_TYPE_UUID']), 'metadata_rejected')
    fields = []
    for node in reg.find('md:ChildObjects', ns):
        kind = node.tag.removeprefix('{'+MD+'}')
        name = node.findtext('md:Properties/md:Name', namespaces=ns)
        require(kind in ('Dimension', 'Resource', 'Attribute') and name in packet.FIELDS and
                node.get('uuid') == request['ids'][name], 'metadata_rejected')
        fields.append(dict(name=name, metadata_uuid=node.get('uuid'), kind=kind))
    require(len(fields) == len(packet.FIELDS) and {f['name'] for f in fields} == set(packet.FIELDS), 'metadata_rejected')
    return dict(register=dict(name=reg.findtext('md:Properties/md:Name', namespaces=ns),
        metadata_uuid=reg.get('uuid'), generated_types=generated), catalog=catalog, fields=fields)
