"""Closed saved Document Items fixture; XML identities are not physical bindings."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from document_lines_packet import lines_packet as packet
from document_read_packet import document_packet as document
from linked_card_packet import linked
from linked_card_packet.base import probe,scalar_wire
import document_read_fixture as previous
from protocol import require,unique

ROOT=Path(__file__).with_name('document_lines_packet')
BLOCKS=packet.BLOCKS
STATES=packet.STATES
MD=previous.MD
NS={'md':MD,'xr':'http://v8.1c.ru/8.3/xcf/readable'}


def load(repeat):
    require(type(repeat) is int and repeat in (1,2),'invalid_input')
    from inputs import read_source
    root=ROOT/'generated'/('repeat-'+str(repeat))
    manifest=json.loads(read_source(root/'manifest.json'),object_pairs_hook=unique)
    require(type(manifest) is dict and set(manifest)=={'profile','names','metadata_ids',
        'record_ids','product_rows','attribute_names','attribute_ids','order','cases',
        'files','native_status'} and manifest['native_status']=='not-applied','provenance_mismatch')
    s=linked.Setup(probe.Setup(*(tuple(manifest[k]) for k in ('names','metadata_ids','record_ids'))),
        *(tuple(manifest[k]) for k in ('product_rows','attribute_names','attribute_ids','order'))).validate()
    request=manifest['profile'];packet.validate(s,request);base=request['base']
    expected={f'Documents/{base["document_name"]}.xml',f'Catalogs/{base["catalog_name"]}.xml',
              *(b+'.bsl' for b in BLOCKS),*(f'setup-{s}.bsl' for s in STATES),
              *(f'witness-{s}.bsl' for s in STATES)}
    require(type(manifest['files']) is dict and set(manifest['files'])==expected,'provenance_mismatch')
    files={name:read_source(root/name) for name in sorted(expected)}
    require(all(hashlib.sha256(raw).hexdigest()==manifest['files'][name]
                for name,raw in files.items()),'provenance_mismatch')
    packet.validate_xml(s,request,{n:b for n,b in files.items() if n.endswith('.xml')})
    require(type(manifest['cases']) is dict and set(manifest['cases'])==set(BLOCKS),'provenance_mismatch')
    for block in BLOCKS:
        require(manifest['cases'][block]==[list(row) for row in packet.cases(s,request,block)],'provenance_mismatch')
        require(files[block+'.bsl']==packet.render(s,request,block).encode(),'provenance_mismatch')
    for state in STATES:
        require(files['setup-'+state+'.bsl']==packet.setup(s,request,state).encode(),'provenance_mismatch')
        require(files['witness-'+state+'.bsl']==packet.witness(s,request,state).encode(),'provenance_mismatch')
    return s,manifest,files


def profile(s):
    s.validate()
    for repeat in (1,2):
        saved,manifest,_=load(repeat)
        if saved==s:return manifest['profile']
    raise ValueError('document lines saved identity not found')


def validate_capture(raw,s,block):
    require(type(block) is str and block in BLOCKS,'invalid_input')
    request=profile(s);rows=scalar_wire.validate_output(raw)
    require(not any(r['status']=='observer-error' for r in rows),'invalid_marker')
    try:packet.capture(raw,s,request)
    except ValueError as error:
        if str(error)!='document-availability-control':raise
        return {'availability':'unavailable'}
    return {'availability':'available'}


def require_setup_evidence(raw,s,state):
    require(type(state) is str and state in STATES,'invalid_input')
    request=profile(s)
    if state=='initial':return packet.require_initial_setup(raw,s,request)
    rows=packet.capture(raw,s,request)
    # Rewrite preconditions execute unguarded in the source-controlled setup.
    # Do not make unknown Type/row equality observations into invented goldens.
    # The separate persisted Query witness is REQUIRED as well by the host.
    for index,value in ((3,0),(4,1),(5,3)):
        require(rows[index-1]==dict(id=index,status='ok',kind='number',value=value),'invalid_marker')
    return rows


def require_witness(raw,s,state):
    require(type(state) is str and state in STATES,'invalid_input')
    return packet.require_witness(raw,s,profile(s),state)


def extend_sources(s,request,saved_fragments,configuration,rights):
    packet.validate_xml(s,request,saved_fragments)
    base=request['base']
    return {**saved_fragments,'Configuration.xml':previous._configuration(configuration,s,base),
        'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml':document.extend_rights(s,base,rights)}


def verify_redump(s,request,saved,redumped):
    packet.validate_xml(s,request,saved)
    if type(redumped) is not dict or set(redumped)!=set(saved):
        raise ValueError('document-lines-redump-inventory')
    for name,raw in saved.items():
        # Full used-QName/tree equality; not a defaults/GeneratedTypes filter.
        # !todo Any native defaults must first correct the reviewed inputs.
        if linked._redump_signature(raw)!=linked._redump_signature(redumped[name]):
            raise ValueError('document-lines-redump-profile')
    return True


def actual_mapping(s,request,redumped):
    saved=packet.xml(s,request);verify_redump(s,request,saved,redumped)
    base=request['base'];objects=[]
    for kind,name,metadata,input_name in (
        ('Document',base['document_name'],base['document_uuid'],s.base.names[0]),
        ('Catalog',base['catalog_name'],base['catalog_uuid'],s.base.names[1])):
        obj=ET.fromstring(redumped[kind+'s/'+name+'.xml']).find('md:'+kind,NS)
        refs=[n for n in obj.findall('md:InternalInfo/xr:GeneratedType',NS)
              if n.get('category')=='Ref' and n.get('name')==kind+'Ref.'+name]
        require(len(refs)==1,'metadata_rejected')
        value=dict(name=obj.findtext('md:Properties/md:Name',namespaces=NS),
                   metadata_uuid=obj.get('uuid'),ref_type_uuid=refs[0].findtext('xr:TypeId',namespaces=NS))
        require(value==dict(name=name,metadata_uuid=metadata,
            ref_type_uuid=base['linked_schema']['generated_ids'][input_name]['REF_TYPE_UUID']),'metadata_rejected')
        objects.append(value)
    doc=ET.fromstring(redumped['Documents/'+base['document_name']+'.xml']).find('md:Document',NS)
    sections=doc.findall('md:ChildObjects/md:TabularSection',NS)
    require(len(sections)==1,'metadata_rejected');section=sections[0];ids=request['ids']
    result=dict(name=section.findtext('md:Properties/md:Name',namespaces=NS),
        metadata_uuid=section.get('uuid'),document_metadata_uuid=doc.get('uuid'))
    require(result==dict(name=request['section'],metadata_uuid=ids['section'],
        document_metadata_uuid=base['document_uuid']),'metadata_rejected')
    generated=section.findall('md:InternalInfo/xr:GeneratedType',NS)
    require(len(generated)==2,'metadata_rejected')
    for category,key,out in (('TabularSection','section',''),('TabularSectionRow','row','row_')):
        items=[n for n in generated if n.get('category')==category and
               n.get('name')=='Document'+category+'.'+base['document_name']+'.'+request['section']]
        require(len(items)==1,'metadata_rejected')
        for tag,suffix in (('TypeId','type'),('ValueId','value')):
            value=items[0].findtext('xr:'+tag,namespaces=NS)
            require(value==ids[key+'_'+suffix],'metadata_rejected')
            result[out+suffix+'_uuid']=value
    result['columns']=[dict(name=a.findtext('md:Properties/md:Name',namespaces=NS),metadata_uuid=a.get('uuid'))
                       for a in section.findall('md:ChildObjects/md:Attribute',NS)]
    require(result['columns']==[dict(name=name,metadata_uuid=ids[name]) for name in request['columns']],
            'metadata_rejected')
    return {'objects':objects,'section':result}
