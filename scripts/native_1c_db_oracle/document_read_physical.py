"""Closed Document raw measurement; no Document CONFIG/record admission.

The caller verifies saved request/redump identities and owns one immutable
postimage. Document UUID-to-_Document naming is only a labeled measurement
hypothesis. CONFIG collection membership, stride, offsets and slots stay raw.
Production Catalog graph/reference guards are never relaxed or impersonated.
"""
from dataclasses import asdict, fields
import hashlib
import re
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage import config_catalog_transport as config
from yadinassi.storage import config_root_projection as root_projection
from yadinassi.storage import filedb_named_file as named
from yadinassi.storage import filedb_dbnames as dbnames
import linked_card_physical as common

MAX_READ_BYTES=64*1024*1024
MAX_READ_CALLS=100000
MAX_CONFIG_BYTES=65536
MAX_TABLE_BYTES=8192
MAX_FIELDS=32
_check=common._check
_exact=common._exact
_integer=common._integer
_hex=common._hex
_json=common._json


def _request(request,mapping):
    _exact(request,('source','status','document_name','catalog_name','document_uuid','catalog_uuid',
                    'posting','number_type','number_length','number_periodicity','attributes','linked_schema'))
    _check(type(mapping) is list and len(mapping)==2)
    schema=request['linked_schema'];_check(type(schema) is dict and type(schema.get('catalogs')) is list and len(schema['catalogs'])==2)
    original=schema['catalogs']
    _check(type(request['document_name']) is str and re.fullmatch('D[0-9a-f]{8}',request['document_name']) is not None)
    _check(request['document_name']=='D'+original[0]['name'][1:]
        and request['catalog_name']==original[1]['name'] and request['document_uuid']==original[0]['metadata_uuid']
        and request['catalog_uuid']==original[1]['metadata_uuid'])
    _check(request['posting']=='Allow' and request['number_type']=='String'
        and type(request['number_length']) is int and request['number_length']==8
        and request['number_periodicity']=='Nonperiodical' and type(request['attributes']) is int and request['attributes']==5)
    for m,name,uid in zip(mapping,(request['document_name'],request['catalog_name']),(request['document_uuid'],request['catalog_uuid'])):
        _exact(m,('name','metadata_uuid','ref_type_uuid'));_check(m['name']==name and m['metadata_uuid']==uid)
    # Reuse only closed identity-container validation, never catalog routing.
    aliases=[dict(m,name=s['name']) for m,s in zip(mapping,original)]
    common._request(schema,aliases)
    specs=[dict(original[0],name=request['document_name']),original[1]]
    return specs,hashlib.sha256(_json(request)).hexdigest()

def _config_payloads(handle, specs):
    """Existing closed CONFIG transport; no S/N attribute projector or AST guess."""
    reader = handle._graph.reader; table = handle.table; budget = reader._budget
    p = config.ConfigContentDecodeProfile(config.DECLARATIONS, '0', 0)
    if (type(table.format_item) is not int or table.format_item != 0 or table.recordlock != '0'
            or tuple(f.raw for f in table.fields) != config.DECLARATIONS):
        raise c.UnsupportedLayout('linked_config_profile')
    data = handle._open_table_data(table); blob = handle._open_table_blob(table)
    length = data.info.logical_length
    if not length or length % p.candidate_stride:
        raise c.InvalidStructure('linked_config_length')
    slots = length // p.candidate_stride
    if slots > config.ConfigFramingLimits().max_slots: raise c.ResourceLimit('linked_config_slots')
    chains = config._ConfigBlobChains(blob, config.ConfigBlobChainLimits())
    decoder = config._ConfigContentDecoder(chains, config.ConfigContentDecodeLimits())
    refs = {}; keys = set()
    for slot in range(slots):
        base = slot * p.candidate_stride; marker = data._read_range(base, 1)
        if slot == 0:
            if marker != b'\1': raise c.UnsupportedLayout('linked_config_reserved')
            continue
        if marker != b'\0': continue  # Existing CONFIG selection policy, not catalog liveness.
        units = int.from_bytes(data._read_range(base+p.filename_offset, 2), 'little')
        if units > 128: raise c.InvalidStructure('linked_config_name_length')
        raw_name = data._read_range(base+p.filename_offset+2, units*2)
        name = raw_name.decode('utf-16le')
        raw_ref = data._read_range(base+p.binarydata_offset, p.binarydata_width)
        start, size = int.from_bytes(raw_ref[:4], 'little'), int.from_bytes(raw_ref[4:], 'little')
        if not start or not size or not units: continue
        if start >= chains.blocks or size > 250 * (chains.blocks-1):
            raise c.InvalidStructure('linked_config_reference')
        if config._config_partno(data._read_range(base+p.partno_offset, p.partno_width)) != 0:
            raise c.UnsupportedLayout('linked_config_part')
        kind = config._config_content_name(name, units, budget, keys)
        budget.charge('output_bytes', 512 + len(raw_name)*2)
        refs[name.lower()] = (start, size, kind)
    def decode(key):
        if key not in refs: raise c.InvalidStructure('linked_config_missing')
        start, size, kind = refs[key]
        stored, _, _ = chains.read(start, size)
        return decoder.decode(stored, kind)
    raw_root = decode('root')
    rp = root_projection.RootProjectionProfile(root_projection.PROFILE_IDENTIFIER)
    rl = root_projection.RootProjectionLimits()
    reserve = root_projection.reserve_root_projection(raw_root, profile=rp, limits=rl)
    budget.charge('output_bytes', reserve.output_bytes); budget.charge('bytes_processed', reserve.bytes_processed)
    target = root_projection.project_root_reference_prefix(raw_root, profile=rp, limits=rl).reference
    if target in ('root', *(s['metadata_uuid'] for s in specs)):
        raise c.InvalidStructure('document_config_self_reference')
    result=[]
    for key in ('root',target,*(s['metadata_uuid'] for s in specs)):
        raw=raw_root if key=='root' else decode(key)
        if len(raw)>MAX_CONFIG_BYTES: raise c.ResourceLimit('document_config_payload')
        budget.charge('output_bytes',4*len(raw));budget.charge('bytes_processed',len(raw))
        result.append(dict(filename=key,raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest()))
    return dict(root_target=target,document_membership='unresolved',files=result)

def _dbnames(handle,specs):
    reader=handle._graph.reader
    extracted=named._read_dbnames_from_catalog(reader,handle._graph.catalog,
        profile=named.DBNamesProfile(config.DECLARATIONS,'0',0,slot_policy='closed_marker1_chain_v1'),_binding_handle=handle)
    profile=dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER);limits=dbnames.DBNamesParseLimits()
    reserve=dbnames.reserve_dbnames_parse(extracted.data,profile=profile,limits=limits)
    reader._budget.charge('output_bytes',reserve.output_bytes);reader._budget.charge('bytes_processed',reserve.bytes_processed)
    reader._budget.charge('tokens',min(len(extracted.data),limits.max_tokens+1))
    parsed=dbnames.parse_dbnames(extracted.data,profile=profile,limits=limits)
    groups=[]
    for spec in specs:
        entries=[];missing=[]
        for uid in [spec['metadata_uuid']]+[a['metadata_uuid'] for a in spec['attributes']]:
            found=[e for e in parsed.entries if e.uuid==uid]
            if len(found)>1:raise c.InvalidStructure('document_dbnames_ambiguous')
            if not found:missing.append(uid);continue
            e=found[0]
            if sum(x.kind==e.kind and x.id==e.id for x in parsed.entries)!=1:
                raise c.UnsupportedSharing('document_dbnames_alias')
            entries.append(asdict(e))
        groups.append(dict(entries=entries,missing=missing))
    return dict(bytes=len(extracted.data),sha256=hashlib.sha256(extracted.data).hexdigest(),groups=groups)


def _candidate(group,spec,index):
    found=[e for e in group['entries'] if e['uuid']==spec['metadata_uuid']]
    if not found:return None,'dbnames_missing'
    e=found[0]
    if e['kind']!=('Document' if index==0 else 'Reference'):return None,'dbnames_kind'
    if not 1<=e['id']<=2147483647:return None,'dbnames_id'
    return ('_Document' if index==0 else '_Reference')+str(e['id']),None


def _physical(read_at,size,candidate,reason,forbidden):
    result=dict(status='unresolved',reason=reason,candidate=candidate,descriptor_hex=None,
        declarations=None,data_header_page=None,logical_length=None,raw_hex=None,
        layout='unresolved',record_size=None,slots=None,offsets=None)
    if candidate is None:return result,None,set(),None
    def protected(offset,length):
        if length and any(page in forbidden for page in range(offset//c.PAGE_SIZE,(offset+length-1)//c.PAGE_SIZE+1)):
            raise c.UnsupportedSharing('document_cross_reader_alias')
        return read_at(offset,length)
    reader=c.CatalogReader(protected,size);catalog=reader.read_catalog()
    tables=[t for t in catalog.tables if t.name==candidate]
    if len(tables)>1:raise c.UnsupportedSharing('document_table_ambiguous')
    if not tables:result['reason']='table_missing';return result,reader,set(),None
    table=tables[0]
    if len(table.raw_descriptor)>MAX_CONFIG_BYTES or not 1<=len(table.fields)<=MAX_FIELDS:
        raise c.ResourceLimit('document_descriptor_bound')
    ds=[list(f.raw) for f in table.fields]
    if any(any(len(d[i])>128 for i in (0,1,5)) for d in ds):raise c.ResourceLimit('document_declaration_text')
    reader._budget.charge('output_bytes',len(table.raw_descriptor)*4+8192)
    result.update(descriptor_hex=table.raw_descriptor.hex(),declarations=ds,data_header_page=table.files[0])
    if not table.files[0]:result['reason']='data_header_missing';return result,reader,set(),None
    try:data=reader._open_table_data(table)
    except c.UnsupportedLayout as error:
        if error.code not in ('free_object_header','fat_level'):raise
        result['reason']='data_layout_unmeasured';return result,reader,set(),None
    owned={page for page,role in reader._source.roles.items() if role in ('table_data_data','table_data_fat')}
    owned.add(table.files[0])
    if owned.intersection(forbidden):raise c.UnsupportedSharing('document_cross_reader_alias')
    length=data.info.logical_length
    if length>MAX_TABLE_BYTES:raise c.ResourceLimit('document_table_bytes')
    reader._budget.charge('output_bytes',length*4);reader._budget.charge('bytes_processed',length*2)
    result.update(status='captured',reason=None,logical_length=length)
    return result,reader,owned,data


def observe(read_at,size,request,actual_mapping):
    specs,request_sha=_request(request,actual_mapping)
    _check(callable(read_at));_integer(size,MAX_READ_BYTES)
    totals=dict(calls=0,bytes=0);active=True
    def bounded(offset,length):
        if (not active or type(offset) is not int or type(length) is not int or offset<0 or length<0
                or offset>size or length>size-offset):raise c.InvalidStructure('document_source_range')
        totals['calls']+=1;totals['bytes']+=length
        if totals['calls']>MAX_READ_CALLS or totals['bytes']>MAX_READ_BYTES:raise c.ResourceLimit('document_source_budget')
        return read_at(offset,length)
    reader=c.CatalogReader(bounded,size);catalog=reader.read_catalog();graph=c._CatalogBindingGraph(reader,catalog)
    try:
        with graph.stage('config') as h:configs=_config_payloads(h,specs)
        with graph.stage('params') as h:db=_dbnames(h,specs)
        # CONFIG/PARAMS views have been revoked. The legacy raw reader is used
        # separately because production records graph only admits References.
        forbidden={p for p,role in reader._source.roles.items() if role in ('table_data_data','table_data_fat','table_blob_data','table_blob_fat')}
        forbidden.update(p for t in graph._tables for p in t.files if p)
        usages=[asdict(reader.usage)];objects=[];pending=[]
        for index,(spec,group) in enumerate(zip(specs,db['groups'])):
            candidate,reason=_candidate(group,spec,index)
            physical,raw_reader,owned,data=_physical(bounded,size,candidate,reason,set(forbidden))
            pending.append((physical,raw_reader,data))
            forbidden.update(owned)
            objects.append(dict(name=spec['name'],metadata_uuid=spec['metadata_uuid'],
                binding='dbnames_table_name_hypothesis_not_production',physical=physical))
        # Map both owned tables before reading either raw payload, so aliases
        # between the two target tables fail before any raw capture.
        for physical,raw_reader,data in pending:
            if data is not None:
                physical['raw_hex']=data._read_range(0,physical['logical_length']).hex()
            if raw_reader is not None:usages.append(asdict(raw_reader.usage))
        result=dict(schema=1,capability='owned_document_raw_measurement_only',request_sha256=request_sha,
            actual_mapping=actual_mapping,config=configs,dbnames=db,objects=objects,reader_usage=usages,source_reads=totals)
        validate_observation(result,request,actual_mapping)
        return result
    except BaseException:
        graph.failed=True
        raise
    finally:active=False


def validate_observation(value,request,actual_mapping):
    specs,request_sha=_request(request,actual_mapping)
    _exact(value,('schema','capability','request_sha256','actual_mapping','config','dbnames','objects','reader_usage','source_reads'))
    _check(type(value['schema']) is int and value['schema']==1 and value['capability']=='owned_document_raw_measurement_only'
        and value['request_sha256']==request_sha and value['actual_mapping']==actual_mapping)
    config_value=value['config'];_exact(config_value,('root_target','document_membership','files'))
    _check(config_value['document_membership']=='unresolved');common._uuid(config_value['root_target'])
    names=['root',config_value['root_target'],*(s['metadata_uuid'] for s in specs)];_check(len(set(names))==4)
    files=config_value['files'];_check(type(files) is list and len(files)==4)
    for item,name in zip(files,names):
        _exact(item,('filename','raw_hex','sha256'));_check(item['filename']==name)
        raw=_hex(item['raw_hex'],MAX_CONFIG_BYTES);_check(bool(raw))
        _check(hashlib.sha256(raw).hexdigest()==item['sha256'])
    rp=root_projection.RootProjectionProfile(root_projection.PROFILE_IDENTIFIER);rl=root_projection.RootProjectionLimits()
    _check(root_projection.project_root_reference_prefix(bytes.fromhex(files[0]['raw_hex']),profile=rp,limits=rl).reference==config_value['root_target'])
    db=value['dbnames'];_exact(db,('bytes','sha256','groups'));_integer(db['bytes'],dbnames.DBNamesParseLimits().max_input_bytes);common._digest(db['sha256'])
    _check(type(db['groups']) is list and len(db['groups'])==2)
    physical_ids=set()
    for spec,group in zip(specs,db['groups']):
        _exact(group,('entries','missing'));wanted=[spec['metadata_uuid']]+[a['metadata_uuid'] for a in spec['attributes']]
        _check(type(group['entries']) is list and len(group['entries'])<=len(wanted) and type(group['missing']) is list)
        found=[]
        for e in group['entries']:
            _exact(e,('uuid','raw_uuid','kind','raw_kind','id','raw_id','ordinal'))
            _check(e['uuid'] in wanted and e['uuid'] not in found and e['raw_uuid']==e['uuid']);found.append(e['uuid'])
            _check(type(e['kind']) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,31}',e['kind']) is not None and e['raw_kind']=='"'+e['kind']+'"')
            _integer(e['id'],2147483647);_check(e['raw_id']==str(e['id']));_integer(e['ordinal'],4095)
            key=(e['kind'],e['id']);_check(key not in physical_ids);physical_ids.add(key)
        _check(found==[u for u in wanted if u in found] and group['missing']==[u for u in wanted if u not in found])
    _check(type(value['objects']) is list and len(value['objects'])==2)
    headers=set()
    for index,(spec,group,obj) in enumerate(zip(specs,db['groups'],value['objects'])):
        _exact(obj,('name','metadata_uuid','binding','physical'))
        _check(obj['name']==spec['name'] and obj['metadata_uuid']==spec['metadata_uuid'] and obj['binding']=='dbnames_table_name_hypothesis_not_production')
        p=obj['physical'];_exact(p,('status','reason','candidate','descriptor_hex','declarations','data_header_page','logical_length','raw_hex','layout','record_size','slots','offsets'))
        candidate,reason=_candidate(group,spec,index);_check(p['candidate']==candidate)
        _check(p['layout']=='unresolved' and p['record_size'] is None and p['slots'] is None and p['offsets'] is None)
        if p['descriptor_hex'] is None:
            _check(p['status']=='unresolved' and p['reason']==(reason if candidate is None else 'table_missing')
                and all(p[k] is None for k in ('declarations','data_header_page','logical_length','raw_hex')))
            continue
        _check(candidate is not None)
        raw=_hex(p['descriptor_hex'],MAX_CONFIG_BYTES);tree=c._Parser(raw,c._Budget(c.CatalogLimits())).value()
        _check(type(tree) is tuple and len(tree)==6 and tree[0]==candidate and type(tree[2]) is tuple and tree[2][0]=='Fields'
            and type(tree[5]) is tuple and len(tree[5])==4 and tree[5][0]=='Files' and tree[5][1]==p['data_header_page'])
        ds=p['declarations'];_check(type(ds) is list and 1<=len(ds)<=MAX_FIELDS and ds==[list(d) for d in tree[2][1:]])
        for d in ds:
            _check(type(d) is list and len(d)==6 and all(type(x) is t for x,t in zip(d,(str,str,int,int,int,str))) and all(len(d[i])<=128 for i in (0,1,5)))
            for i in (2,3,4):_integer(d[i],2147483647)
        _integer(p['data_header_page'],8191)
        if p['data_header_page']:
            _check(p['data_header_page'] not in headers);headers.add(p['data_header_page'])
        if p['status']=='captured':
            _check(p['reason'] is None and p['data_header_page']>0);_integer(p['logical_length'],MAX_TABLE_BYTES)
            _check(len(_hex(p['raw_hex'],MAX_TABLE_BYTES))==p['logical_length'])
        else:
            _check(p['status']=='unresolved' and p['reason'] in ('data_header_missing','data_layout_unmeasured') and p['logical_length'] is None and p['raw_hex'] is None)
            _check((p['data_header_page']==0)==(p['reason']=='data_header_missing'))
    usages=value['reader_usage'];_check(type(usages) is list and 1<=len(usages)<=3)
    for usage in usages:
        _exact(usage,[f.name for f in fields(c.CatalogUsage)])
        for key,n in usage.items():_integer(n,getattr(c.CatalogLimits(),'max_'+key))
    totals=value['source_reads'];_exact(totals,('calls','bytes'));_integer(totals['calls'],MAX_READ_CALLS);_integer(totals['bytes'],MAX_READ_BYTES)
    _check(totals['calls']>0 and totals['bytes']>0 and sum(u['read_bytes'] for u in usages)==totals['bytes'])
    _json(value)
    return value
