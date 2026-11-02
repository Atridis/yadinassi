"""Bounded owned InformationRegister measurement, never storage admission.

InfoRg-to-_InfoRg naming is an explicitly unmeasured candidate hypothesis.
The caller verifies complete source/native XML and one immutable postimage.
CONFIG membership, keys, ordering, stride, slots and liveness remain unresolved.
"""
from dataclasses import asdict, fields
import hashlib
import re
import document_read_physical as base
c=base.c;common=base.common;root_projection=base.root_projection;dbnames=base.dbnames
MAX_READ_BYTES=base.MAX_READ_BYTES
MAX_READ_CALLS=base.MAX_READ_CALLS
MAX_CONFIG_BYTES=base.MAX_CONFIG_BYTES
MAX_TABLE_BYTES=base.MAX_TABLE_BYTES
MAX_FIELDS=base.MAX_FIELDS
_check=base._check;_exact=base._exact;_integer=base._integer;_hex=base._hex;_json=base._json
def _config_payloads(handle,specs):
    # Transport/baseline helpers only: never call the Document request checker
    # or admit the register through a Catalog/Document membership projector.
    result=base._config_payloads(handle,specs)
    result.pop('document_membership')
    result['register_membership']='unresolved'
    return result
MAX_OWNED_ENTRIES=128
MAX_UUID_ENTRIES=16
_physical=base._physical
_baseline_key=base._baseline_key
_baseline_profile=base._baseline_profile
_COLUMNS=('Product','Variant','Price','Available','ValidUntil','Note')
_FAMILIES=('Manager','Selection','List','RecordSet','RecordManager','RecordKey','Record')
_ROLES=(('Resource',('Price','Available','ValidUntil')),('Attribute',('Note',)),('Dimension',('Product','Variant')))


def _request(request,mapping):
    _exact(request,('register','catalog','metadata_uuid','periodicity','write_mode','columns','catalog_schema','ids','status'))
    _exact(mapping,('register','catalog','fields'))
    _check(request['periodicity']=='Nonperiodical' and request['write_mode']=='Independent'
        and request['status']=='v2-prospective-not-native-applied')
    schema=request['catalog_schema']
    _check(type(schema) is dict and type(schema.get('catalogs')) is list and len(schema['catalogs'])==2)
    originals=schema['catalogs']
    _check(type(schema.get('generated_ids')) is dict)
    # This is the saved identity-container blueprint, NOT a native Catalog
    # identity for the register. Actual native generated types are bound below.
    blueprint=[]
    for spec in originals:
        _check(type(spec) is dict and type(spec.get('name')) is str)
        generated=schema['generated_ids'].get(spec['name'])
        _check(type(generated) is dict)
        blueprint.append(dict(name=spec['name'],metadata_uuid=spec.get('metadata_uuid'),ref_type_uuid=generated.get('REF_TYPE_UUID')))
    common._request(schema,blueprint)
    _check(type(request['register']) is str and re.fullmatch('I[0-9a-f]{8}',request['register']) is not None
        and request['register']=='I'+originals[0]['name'][1:] and request['metadata_uuid']==originals[0]['metadata_uuid']
        and request['catalog']==originals[1]['name'])
    columns=request['columns'];_check(type(columns) is list and columns in (list(_COLUMNS),list(reversed(_COLUMNS))))
    ids=request['ids'];_exact(ids,(*_COLUMNS,'product2',*(f'{f}.{k}' for f in _FAMILIES for k in ('TypeId','ValueId'))))
    for value in ids.values():common._uuid(value)
    _check(len(set(ids.values()))==len(ids))
    prior=_json(schema).decode('ascii');_check(not any(value in prior for value in ids.values()))
    actual_register=mapping['register'];_exact(actual_register,('name','metadata_uuid','generated_types'))
    expected_register=dict(name=request['register'],metadata_uuid=request['metadata_uuid'],generated_types={
        f:dict(type_uuid=ids[f+'.TypeId'],value_uuid=ids[f+'.ValueId']) for f in _FAMILIES})
    _check(_json(actual_register)==_json(expected_register))
    _exact(mapping['catalog'],('name','metadata_uuid','ref_type_uuid'))
    _check(mapping['catalog']==blueprint[1])
    expected_fields=[dict(name=name,metadata_uuid=ids[name],kind=kind)
                     for kind,names in _ROLES for name in columns if name in names]
    _check(type(mapping['fields']) is list and _json(mapping['fields'])==_json(expected_fields))
    specs=[dict(name=request['register'],metadata_uuid=request['metadata_uuid'],attributes=expected_fields),originals[1]]
    return specs,hashlib.sha256(_json(request)).hexdigest()


def _dbnames(handle,specs):
    # Owned registers may give a selected metadata UUID several DBNames roles. Retain
    # evidence, never choose the first row or broaden production binding.
    reader=handle._graph.reader
    extracted=base.named._read_dbnames_from_catalog(reader,handle._graph.catalog,
        profile=base.named.DBNamesProfile(base.config.DECLARATIONS,'0',0,slot_policy='closed_marker1_chain_v1'),_binding_handle=handle)
    profile=dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER);limits=dbnames.DBNamesParseLimits()
    reserve=dbnames.reserve_dbnames_parse(extracted.data,profile=profile,limits=limits)
    reader._budget.charge('output_bytes',reserve.output_bytes);reader._budget.charge('bytes_processed',reserve.bytes_processed)
    reader._budget.charge('tokens',min(len(extracted.data),limits.max_tokens+1))
    parsed=dbnames.parse_dbnames(extracted.data,profile=profile,limits=limits)
    groups=[];total=0
    for spec in specs:
        entries=[];missing=[]
        for uid in [spec['metadata_uuid']]+[a['metadata_uuid'] for a in spec['attributes']]:
            found=[e for e in parsed.entries if e.uuid==uid]
            total+=len(found)
            if len(found)>MAX_UUID_ENTRIES or total>MAX_OWNED_ENTRIES:raise c.ResourceLimit('register_dbnames_entries')
            if not found:missing.append(uid)
            for e in found:
                if sum(x.kind==e.kind and x.id==e.id for x in parsed.entries)!=1:
                    raise c.UnsupportedSharing('document_dbnames_alias')
                entries.append(asdict(e))
        groups.append(dict(entries=entries,missing=missing))
    return dict(bytes=len(extracted.data),sha256=hashlib.sha256(extracted.data).hexdigest(),groups=groups)


def _candidate(group,spec,index):
    entries=[e for e in group['entries'] if e['uuid']==spec['metadata_uuid']]
    if not entries:return None,'dbnames_missing'
    # !todo Actual native kinds/names must be measured; this is not a decoder.
    expected=('InfoRg','Reference')[index]
    matched=[e for e in entries if e['kind']==expected]
    if not matched:return None,'dbnames_kind'
    if len(matched)!=1:return None,'dbnames_ambiguous'
    entry=matched[0]
    if not 1<=entry['id']<=2147483647:return None,'dbnames_id'
    return ('_InfoRg' if index==0 else '_Reference')+str(entry['id']),None

def observe(read_at,size,request,actual_mapping):
    specs,request_sha=_request(request,actual_mapping)
    _check(callable(read_at));_integer(size,MAX_READ_BYTES)
    totals=dict(calls=0,bytes=0);active=True
    def bounded(offset,length):
        if (not active or type(offset) is not int or type(length) is not int or offset<0 or length<0
                or offset>size or length>size-offset):raise c.InvalidStructure('register_source_range')
        totals['calls']+=1;totals['bytes']+=length
        if totals['calls']>MAX_READ_CALLS or totals['bytes']>MAX_READ_BYTES:raise c.ResourceLimit('register_source_budget')
        return read_at(offset,length)
    reader=c.CatalogReader(bounded,size);catalog=reader.read_catalog();graph=c._CatalogBindingGraph(reader,catalog)
    try:
        with graph.stage('config') as h:configs=_config_payloads(h,specs)
        with graph.stage('params') as h:db=_dbnames(h,specs)
        # CONFIG/PARAMS views have been revoked. The legacy raw reader is used
        # separately without expanding production record graph admission.
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
        # Map both owned candidates before reading any raw payload;
        # cross-table aliases must fail before raw capture.
        for physical,raw_reader,data in pending:
            if data is not None:
                physical['raw_hex']=data._read_range(0,physical['logical_length']).hex()
            if raw_reader is not None:usages.append(asdict(raw_reader.usage))
        result=dict(schema=1,capability='owned_information_register_raw_measurement_only',request_sha256=request_sha,
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
    _check(type(value['schema']) is int and value['schema']==1 and value['capability']=='owned_information_register_raw_measurement_only'
        and value['request_sha256']==request_sha and value['actual_mapping']==actual_mapping)
    config_value=value['config'];_exact(config_value,('root_target','register_membership','baseline','files'))
    _check(config_value['register_membership']=='unresolved');common._uuid(config_value['root_target'])
    baseline=config_value['baseline']
    _exact(baseline,('metadata_uuid','name','code_type','code_length','description_length','attributes'))
    common._uuid(baseline['metadata_uuid'])
    names=['root',config_value['root_target'],*(s['metadata_uuid'] for s in specs),baseline['metadata_uuid']];_check(len(set(names))==5)
    files=config_value['files'];_check(type(files) is list and len(files)==5)
    for item,name in zip(files,names):
        _exact(item,('filename','raw_hex','sha256'));_check(item['filename']==name)
        raw=_hex(item['raw_hex'],MAX_CONFIG_BYTES);_check(bool(raw))
        _check(hashlib.sha256(raw).hexdigest()==item['sha256'])
    rp=root_projection.RootProjectionProfile(root_projection.PROFILE_IDENTIFIER);rl=root_projection.RootProjectionLimits()
    _check(root_projection.project_root_reference_prefix(bytes.fromhex(files[0]['raw_hex']),profile=rp,limits=rl).reference==config_value['root_target'])
    validation_budget=c._Budget(c.CatalogLimits())
    _check(_baseline_key(bytes.fromhex(files[1]['raw_hex']),specs,config_value['root_target'],validation_budget)==baseline['metadata_uuid'])
    expected_baseline=_baseline_profile(bytes.fromhex(files[4]['raw_hex']),baseline['metadata_uuid'],validation_budget)
    _check(_json(baseline)==_json(expected_baseline))
    db=value['dbnames'];_exact(db,('bytes','sha256','groups'));_integer(db['bytes'],dbnames.DBNamesParseLimits().max_input_bytes);common._digest(db['sha256'])
    _check(type(db['groups']) is list and len(db['groups'])==2)
    physical_ids=set();ordinals=set();total_entries=0
    for spec,group in zip(specs,db['groups']):
        _exact(group,('entries','missing'));wanted=[spec['metadata_uuid']]+[a['metadata_uuid'] for a in spec['attributes']]
        _check(type(group['entries']) is list and len(group['entries'])<=MAX_OWNED_ENTRIES and type(group['missing']) is list)
        found=[];counts={u:0 for u in wanted};order=[]
        total_entries+=len(group['entries']);_check(total_entries<=MAX_OWNED_ENTRIES)
        for e in group['entries']:
            _exact(e,('uuid','raw_uuid','kind','raw_kind','id','raw_id','ordinal'))
            _check(e['uuid'] in wanted and e['raw_uuid']==e['uuid']);found.append(e['uuid'])
            counts[e['uuid']]+=1;_check(counts[e['uuid']]<=MAX_UUID_ENTRIES)
            _check(type(e['kind']) is str and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,31}',e['kind']) is not None and e['raw_kind']=='"'+e['kind']+'"')
            _integer(e['id'],2147483647);_check(e['raw_id']==str(e['id']));_integer(e['ordinal'],4095)
            _check(e['ordinal'] not in ordinals);ordinals.add(e['ordinal']);order.append((wanted.index(e['uuid']),e['ordinal']))
            key=(e['kind'],e['id']);_check(key not in physical_ids);physical_ids.add(key)
        _check(order==sorted(order) and group['missing']==[u for u in wanted if u not in found])
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
