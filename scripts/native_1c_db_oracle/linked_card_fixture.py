"""Exact saved mixed-schema packet, never caller source or generated identities."""
import hashlib
import json
from pathlib import Path
from linked_card_packet import linked
from linked_card_packet.base import probe, scalar_wire
from protocol import require, unique
BLOCKS=linked.BLOCKS
STATES=linked.STATES
ROOT=Path(__file__).with_name('linked_card_packet')


def load(repeat):
    require(type(repeat) is int and repeat in (1,2), 'invalid_input')
    from inputs import read_source
    root=ROOT/'generated'/('repeat-'+str(repeat))
    manifest=json.loads(read_source(root/'manifest.json'),object_pairs_hook=unique)
    s=linked.Setup(probe.Setup(*(tuple(manifest[k]) for k in ('names','metadata_ids','record_ids'))),
        *(tuple(manifest[k]) for k in ('product_rows','attribute_names','attribute_ids','order'))).validate()
    request=manifest['schema'];linked.validate_request(s,request)
    require(manifest['schema_evidence']==linked.SCHEMA_EVIDENCE,'provenance_mismatch')
    expected={*(f'Catalogs/{n}.xml' for n in s.base.names),*(n+'.bsl' for n in BLOCKS),*(f'setup-{n}.bsl' for n in STATES)}
    require(type(manifest['source_hashes']) is dict and set(manifest['source_hashes'])==expected,'provenance_mismatch')
    files={n:read_source(root/n) for n in sorted(expected)}
    require(all(hashlib.sha256(raw).hexdigest()==manifest['source_hashes'][n] for n,raw in files.items()),'provenance_mismatch')
    linked.validate_fragments(s,request,{n:raw for n,raw in files.items() if n.endswith('.xml')})
    for block in BLOCKS:
        require(manifest['cases'][block]==[list(row) for row in linked.cases(s,block)],'provenance_mismatch')
        require(files[block+'.bsl']==linked.render_block(s,block).encode('utf-8'),'provenance_mismatch')
    for state in STATES:require(files['setup-'+state+'.bsl']==linked.render_setup(s,state)[0].encode('utf-8'),'provenance_mismatch')
    return s,manifest,files


def validate_capture(raw,s,block):
    require(block in BLOCKS,'invalid_input')
    rows=scalar_wire.validate_output(raw)
    require(not any(row['status']=='observer-error' for row in rows),'invalid_marker')
    try:linked.read_capture(raw,s)
    except ValueError as error:
        if str(error)!='availability-control':raise
        return {'availability':'unavailable'}
    return {'availability':'available'}


def actual_mapping(s,request,redumped):
    # Complete request/redump equality established first; no UUID name guessing.
    linked.validate_fragments(s,request,redumped)
    import xml.etree.ElementTree as ET
    ns={'md':'http://v8.1c.ru/8.3/MDClasses','xr':'http://v8.1c.ru/8.3/xcf/readable'}
    result=[]
    for c in request['catalogs']:
        root=ET.fromstring(redumped['Catalogs/'+c['name']+'.xml'])
        catalog=root.find('md:Catalog',ns)
        refs=[node for node in catalog.findall('md:InternalInfo/xr:GeneratedType',ns)
              if node.get('category')=='Ref' and node.get('name')=='CatalogRef.'+c['name']]
        require(len(refs)==1,'metadata_rejected')
        item=dict(name=catalog.find('md:Properties/md:Name',ns).text,
                  metadata_uuid=catalog.get('uuid'),ref_type_uuid=refs[0].find('xr:TypeId',ns).text)
        require(item==dict(name=c['name'],metadata_uuid=c['metadata_uuid'],
            ref_type_uuid=request['generated_ids'][c['name']]['REF_TYPE_UUID']),'metadata_rejected')
        result.append(item)
    return result
