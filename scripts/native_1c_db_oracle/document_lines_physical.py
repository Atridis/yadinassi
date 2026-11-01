"""Bounded Items raw acquisition; table naming is a measurement hypothesis only.

Section/columns are retained in the full owned Document CONFIG payload. No
separate CONFIG filename, row stride, owner join, ordering or liveness is inferred.
The caller independently verifies the complete saved/native XML identities.
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
_config_payloads=base._config_payloads
_dbnames=base._dbnames
_physical=base._physical
_baseline_key=base._baseline_key
_baseline_profile=base._baseline_profile
_COLUMNS=('Product','Quantity','Price','Amount','Note')


def _request(request,mapping):
    _exact(request,('source','base','section','columns','ids'))
    _exact(mapping,('objects','section'))
    specs,_=base._request(request['base'],mapping['objects'])
    _check(request['source']=='9be9d601e4598de21c87098161928e827341973c' and request['section']=='Items')
    columns=request['columns'];_check(type(columns) is list and columns in (list(_COLUMNS),list(reversed(_COLUMNS))))
    ids=request['ids'];_exact(ids,('section',*_COLUMNS,'section_type','section_value','row_type','row_value','product2','lookup_absent'))
    for value in ids.values():common._uuid(value)
    _check(len(set(ids.values()))==len(ids))
    prior=_json(request['base']).decode('ascii')
    _check(not any(value in prior for value in ids.values()))
    section=mapping['section']
    _exact(section,('name','metadata_uuid','document_metadata_uuid','type_uuid','value_uuid','row_type_uuid','row_value_uuid','columns'))
    expected=dict(name='Items',metadata_uuid=ids['section'],document_metadata_uuid=specs[0]['metadata_uuid'],
        type_uuid=ids['section_type'],value_uuid=ids['section_value'],row_type_uuid=ids['row_type'],row_value_uuid=ids['row_value'],
        columns=[dict(name=name,metadata_uuid=ids[name]) for name in columns])
    _check(section==expected)
    specs.append(dict(name='Items',metadata_uuid=ids['section'],attributes=expected['columns']))
    return specs,hashlib.sha256(_json(request)).hexdigest()


def _candidate(group,spec,index,groups=None,specs=None):
    if index<2:return base._candidate(group,spec,index)
    doc,reason=base._candidate(groups[0],specs[0],0)
    if doc is None:return None,reason
    entries=[e for e in group['entries'] if e['uuid']==spec['metadata_uuid']]
    if not entries:return None,'dbnames_missing'
    entry=entries[0]
    if entry['kind']!='VT':return None,'dbnames_kind'
    if not 1<=entry['id']<=2147483647:return None,'dbnames_id'
    return doc+'_VT'+str(entry['id']),None

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
        with graph.stage('config') as h:configs=_config_payloads(h,specs[:2])
        with graph.stage('params') as h:db=_dbnames(h,specs)
        # CONFIG/PARAMS views have been revoked. The legacy raw reader is used
        # separately without expanding production record graph admission.
        forbidden={p for p,role in reader._source.roles.items() if role in ('table_data_data','table_data_fat','table_blob_data','table_blob_fat')}
        forbidden.update(p for t in graph._tables for p in t.files if p)
        usages=[asdict(reader.usage)];objects=[];pending=[]
        for index,(spec,group) in enumerate(zip(specs,db['groups'])):
            candidate,reason=_candidate(group,spec,index,db['groups'],specs)
            physical,raw_reader,owned,data=_physical(bounded,size,candidate,reason,set(forbidden))
            pending.append((physical,raw_reader,data))
            forbidden.update(owned)
            objects.append(dict(name=spec['name'],metadata_uuid=spec['metadata_uuid'],
                binding='dbnames_table_name_hypothesis_not_production',physical=physical))
        # Map all three owned candidates before reading any raw payload;
        # cross-table aliases must fail before raw capture.
        for physical,raw_reader,data in pending:
            if data is not None:
                physical['raw_hex']=data._read_range(0,physical['logical_length']).hex()
            if raw_reader is not None:usages.append(asdict(raw_reader.usage))
        result=dict(schema=1,capability='owned_document_lines_raw_measurement_only',request_sha256=request_sha,
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
    _check(type(value['schema']) is int and value['schema']==1 and value['capability']=='owned_document_lines_raw_measurement_only'
        and value['request_sha256']==request_sha and value['actual_mapping']==actual_mapping)
    config_value=value['config'];_exact(config_value,('root_target','document_membership','baseline','files'))
    _check(config_value['document_membership']=='unresolved');common._uuid(config_value['root_target'])
    baseline=config_value['baseline']
    _exact(baseline,('metadata_uuid','name','code_type','code_length','description_length','attributes'))
    common._uuid(baseline['metadata_uuid'])
    names=['root',config_value['root_target'],*(s['metadata_uuid'] for s in specs[:2]),baseline['metadata_uuid']];_check(len(set(names))==5)
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
    _check(type(db['groups']) is list and len(db['groups'])==3)
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
    _check(type(value['objects']) is list and len(value['objects'])==3)
    headers=set()
    for index,(spec,group,obj) in enumerate(zip(specs,db['groups'],value['objects'])):
        _exact(obj,('name','metadata_uuid','binding','physical'))
        _check(obj['name']==spec['name'] and obj['metadata_uuid']==spec['metadata_uuid'] and obj['binding']=='dbnames_table_name_hypothesis_not_production')
        p=obj['physical'];_exact(p,('status','reason','candidate','descriptor_hex','declarations','data_header_page','logical_length','raw_hex','layout','record_size','slots','offsets'))
        candidate,reason=_candidate(group,spec,index,db['groups'],specs);_check(p['candidate']==candidate)
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
    usages=value['reader_usage'];_check(type(usages) is list and 1<=len(usages)<=4)
    for usage in usages:
        _exact(usage,[f.name for f in fields(c.CatalogUsage)])
        for key,n in usage.items():_integer(n,getattr(c.CatalogLimits(),'max_'+key))
    totals=value['source_reads'];_exact(totals,('calls','bytes'));_integer(totals['calls'],MAX_READ_CALLS);_integer(totals['bytes'],MAX_READ_BYTES)
    _check(totals['calls']>0 and totals['bytes']>0 and sum(u['read_bytes'] for u in usages)==totals['bytes'])
    _json(value)
    return value
