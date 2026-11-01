"""Saved, closed Document+Catalog fixture; no guessed CONFIG or row layout."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.parsers import expat

from document_read_packet import document_packet as packet
from linked_card_packet import linked
from linked_card_packet.base import probe, scalar_wire
from protocol import require, unique

BLOCKS = packet.BLOCKS
STATES = packet.STATES
ROOT = Path(__file__).with_name('document_read_packet')
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
    packet.validate_profile(s, request)
    expected = {f'Documents/{request["document_name"]}.xml',
        f'Catalogs/{request["catalog_name"]}.xml', *(b+'.bsl' for b in BLOCKS),
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
        require(files[block+'.bsl'] == packet.render_block(s, request, block).encode(),
                'provenance_mismatch')
    for state in STATES:
        require(files['setup-'+state+'.bsl'] == packet.render_setup(s, request, state)[0].encode(),
                'provenance_mismatch')
    return s, manifest, files


def profile(s):
    s.validate()
    for repeat in (1, 2):
        saved, manifest, _ = load(repeat)
        if saved == s:
            return manifest['profile']
    raise ValueError('document saved identity not found')


def validate_capture(raw, s, block):
    require(type(block) is str and block in BLOCKS, 'invalid_input')
    request = profile(s)
    rows = scalar_wire.validate_output(raw)
    require(not any(row['status'] == 'observer-error' for row in rows), 'invalid_marker')
    try:
        packet.require_capture(raw, s, request)
    except ValueError as error:
        if str(error) != 'document-availability-control':
            raise
        return {'availability': 'unavailable'}
    return {'availability': 'available'}


def require_setup_evidence(raw, s, state):
    return packet.require_setup_evidence(raw, s, profile(s), state)


def _configuration(raw, s, request):
    packet.validate_profile(s, request)
    if type(raw) is not bytes or len(raw) > 1048576 or b'<!' in raw:
        raise ValueError('configuration-bound')
    root = ET.fromstring(raw)
    children = root.find('{'+MD+'}Configuration/{'+MD+'}ChildObjects')
    if (children is None or [n.text for n in children if n.tag == '{'+MD+'}Catalog']
            != ['NativeOracleItems'] or any(n.tag == '{'+MD+'}Document' for n in children)):
        raise ValueError('baseline-document-catalog-inventory')
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
    additions = (f'<{prefix}Document>{request["document_name"]}</{prefix}Document>'
                 f'<{prefix}Catalog>{request["catalog_name"]}</{prefix}Catalog>').encode()
    return raw[:end]+additions+raw[end:]


def extend_sources(s, request, saved_fragments, configuration, rights):
    packet.validate_xml(s, request, saved_fragments)
    return {**saved_fragments, 'Configuration.xml': _configuration(configuration, s, request),
        'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml': packet.extend_rights(s, request, rights)}


def verify_redump(s, request, saved, redumped):
    packet.validate_xml(s, request, saved)
    if type(redumped) is not dict or set(redumped) != set(saved):
        raise ValueError('document-redump-inventory')
    for name, raw in saved.items():
        # Full tree/attributes/text equality with used QName semantics. No
        # stripping StandardAttributes, GeneratedTypes, defaults or privileges.
        # !todo Designer default expansion requires actual native review first.
        if linked._redump_signature(raw) != linked._redump_signature(redumped[name]):
            raise ValueError('document-redump-profile')
    return True


def actual_mapping(s, request, redumped):
    saved = packet.document_xml(s, request)
    verify_redump(s, request, saved, redumped)
    ns = {'md': MD, 'xr': 'http://v8.1c.ru/8.3/xcf/readable'}
    specs = [('Document', request['document_name'], request['document_uuid'], s.base.names[0]),
             ('Catalog', request['catalog_name'], request['catalog_uuid'], s.base.names[1])]
    result = []
    for kind, name, metadata, input_name in specs:
        root = ET.fromstring(redumped[kind+'s/'+name+'.xml'])
        obj = root.find('md:'+kind, ns)
        refs = [n for n in obj.findall('md:InternalInfo/xr:GeneratedType', ns)
                if n.get('category') == 'Ref' and n.get('name') == kind+'Ref.'+name]
        require(len(refs) == 1, 'metadata_rejected')
        item = dict(name=obj.find('md:Properties/md:Name', ns).text,
            metadata_uuid=obj.get('uuid'), ref_type_uuid=refs[0].find('xr:TypeId', ns).text)
        require(item == dict(name=name, metadata_uuid=metadata,
            ref_type_uuid=request['linked_schema']['generated_ids'][input_name]['REF_TYPE_UUID']),
            'metadata_rejected')
        result.append(item)
    return result
