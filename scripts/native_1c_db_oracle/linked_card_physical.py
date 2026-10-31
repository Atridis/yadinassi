"""Owned linked-card raw measurement, never mixed-schema storage admission.

Only requested catalog CONFIG payloads, selected DBNames triples and their own
physical table bytes leave the reader. Unknown widths/nullability stay unresolved.
The caller supplies a quiescent immutable positioned source and verified redump
mapping; this module performs no path access, writes or native session work.
"""
from dataclasses import asdict, fields
import hashlib
import json
import re
from types import SimpleNamespace
from uuid import UUID
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage import config_catalog_transport as config
from yadinassi.storage import config_catalog_name as names
from yadinassi.storage import config_root_projection as root_projection
from yadinassi.storage import config_catalog_references as catalog_refs
from yadinassi.storage import filedb_named_file as named
from yadinassi.storage import filedb_dbnames as dbnames

MAX_READ_BYTES = 64 * 1024 * 1024
MAX_READ_CALLS = 100000
MAX_CONFIG_BYTES = 65536
MAX_TABLE_BYTES = 8192
MAX_SLOTS = 16
MAX_FIELDS = 32
MAX_REPORT_BYTES = 512 * 1024


def _check(value):
    if not value: raise ValueError('invalid linked measurement')


def _exact(value, keys):
    _check(type(value) is dict and set(value) == set(keys))


def _integer(value, maximum):
    _check(type(value) is int and 0 <= value <= maximum)


def _uuid(value):
    _check(type(value) is str and len(value) == 36)
    _check(str(UUID(value)) == value and UUID(value).int != 0)


def _digest(value):
    _check(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None)


def _json(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                     allow_nan=False).encode('ascii')
    _check(len(raw) <= MAX_REPORT_BYTES)
    return raw


def _request(request, mapping):
    """Host additionally verifies full saved packet/request and native redump."""
    _exact(request, ('status', 'generated_ids', 'catalogs', 'pending'))
    _check(type(request['catalogs']) is list and len(request['catalogs']) == 2)
    _check(type(mapping) is list and len(mapping) == 2)
    _check(type(request['generated_ids']) is dict)
    used = set(); selected = []
    for index, (spec, actual) in enumerate(zip(request['catalogs'], mapping)):
        _exact(spec, ('name','metadata_uuid','code_length','code_type','description_length','hierarchical','attributes'))
        _check(type(spec['name']) is str and re.fullmatch('C[0-9a-f]{8}', spec['name']) is not None)
        _uuid(spec['metadata_uuid'])
        _check(spec['metadata_uuid'] not in used); used.add(spec['metadata_uuid'])
        _check(type(spec['code_length']) is int and spec['code_length'] == 2
               and spec['code_type'] == 'String' and type(spec['description_length']) is int
               and spec['description_length'] == 8 and spec['hierarchical'] is False)
        _check(type(spec['attributes']) is list and len(spec['attributes']) == (5 if index == 0 else 0))
        attr_names = set()
        for attr in spec['attributes']:
            _check(type(attr) is dict and {'name','metadata_uuid','type'} <= set(attr))
            _check(type(attr['name']) is str and re.fullmatch('A[0-9a-f]{8}', attr['name']) is not None)
            _uuid(attr['metadata_uuid']); _check(attr['metadata_uuid'] not in used)
            used.add(attr['metadata_uuid']); _check(attr['name'] not in attr_names); attr_names.add(attr['name'])
        _exact(actual, ('name','metadata_uuid','ref_type_uuid'))
        _check(actual['name'] == spec['name'] and actual['metadata_uuid'] == spec['metadata_uuid'])
        _uuid(actual['ref_type_uuid'])
        generated = request['generated_ids'].get(spec['name'])
        _check(type(generated) is dict and generated.get('CATALOG_UUID') == spec['metadata_uuid']
               and generated.get('REF_TYPE_UUID') == actual['ref_type_uuid'])
        selected.append(spec)
    _check(len({s['name'] for s in selected}) == 2)
    _check(set(request['generated_ids']) == {s['name'] for s in selected})
    _check(len({m['ref_type_uuid'] for m in mapping}) == 2 and not used.intersection(m['ref_type_uuid'] for m in mapping))
    # Bind the whole externally verified request, not just a name selector.
    return selected, hashlib.sha256(_json(request)).hexdigest()


def _config_payload(handle, metadata_uuid):
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
    if target in ('root', metadata_uuid): raise c.InvalidStructure('linked_config_self_reference')
    declared = catalog_refs.project_catalog_references(decode(target), budget=budget).references
    if metadata_uuid not in declared: raise c.InvalidStructure('linked_config_not_catalog')
    raw = decode(metadata_uuid)
    if len(raw) > MAX_CONFIG_BYTES: raise c.ResourceLimit('linked_config_payload')
    budget.charge('output_bytes', len(raw)*4); budget.charge('bytes_processed', len(raw))
    raw.decode('utf-8-sig')  # Explicit closed output encoding, no replacement.
    return raw


def _selected_dbnames(handle, spec):
    reader = handle._graph.reader
    extracted = named._read_dbnames_from_catalog(reader, handle._graph.catalog,
        profile=named.DBNamesProfile(config.DECLARATIONS, '0', 0, slot_policy='closed_marker1_chain_v1'),
        _binding_handle=handle)
    p = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER); limits = dbnames.DBNamesParseLimits()
    reserve = dbnames.reserve_dbnames_parse(extracted.data, profile=p, limits=limits)
    reader._budget.charge('output_bytes', reserve.output_bytes)
    reader._budget.charge('bytes_processed', reserve.bytes_processed)
    reader._budget.charge('tokens', min(len(extracted.data), limits.max_tokens+1))
    parsed = dbnames.parse_dbnames(extracted.data, profile=p, limits=limits)
    wanted = [spec['metadata_uuid']] + [a['metadata_uuid'] for a in spec['attributes']]
    chosen = []
    for index, uid in enumerate(wanted):
        matches = [e for e in parsed.entries if e.uuid == uid]
        if len(matches) != 1: raise c.InvalidStructure('linked_dbnames_identity')
        e = matches[0]
        if e.kind != ('Reference' if index == 0 else 'Fld') or not 1 <= e.id <= 2147483647:
            raise c.UnsupportedLayout('linked_dbnames_kind')
        if sum(x.kind == e.kind and x.id == e.id for x in parsed.entries) != 1:
            raise c.UnsupportedSharing('linked_dbnames_alias')
        chosen.append(asdict(e))
    return {'bytes':len(extracted.data), 'sha256':hashlib.sha256(extracted.data).hexdigest(), 'entries':chosen}


def _placements(declarations):
    """Only already measured baseline primitive placements; DT/nullable unresolved.

    !todo After native descriptor/slot comparison establish linked DT/ref widths.
    Unknown kinds must not inherit a guessed Date or reference value decoder.
    """
    widths = []
    for name, kind, nullable, length, precision, case in declarations:
        width = None
        if nullable == 0 and case in ('CS','CI'):
            if (kind,length,precision) in (('RV',0,0),('B',16,0)): width = 16
            elif (kind,length,precision) == ('L',0,0): width = 1
            elif kind == 'NVC' and precision == 0 and length in (2,8,32): width = 2+2*length
            elif (kind,length,precision) == ('N',9,2): width = 5
        widths.append(width)
    # RV-first placement has only been established for a single version field.
    versions = [i for i,d in enumerate(declarations) if d[1] == 'RV']
    if any(w is None for w in widths) or len(versions) != 1:
        return None, [{'declaration':list(d),'offset':None,'width':w} for d,w in zip(declarations,widths)]
    offsets = [0]*len(widths); cursor = 1
    for i in versions+[i for i in range(len(widths)) if i not in versions]:
        offsets[i] = cursor; cursor += widths[i]
    return cursor, [{'declaration':list(d),'offset':o,'width':w} for d,o,w in zip(declarations,offsets,widths)]


def _physical(handle):
    table = handle.table; reader = handle._graph.reader
    if type(table.format_item) is not int or table.format_item != 0 or table.recordlock != '0':
        raise c.UnsupportedLayout('linked_table_format')
    if not 1 <= len(table.fields) <= MAX_FIELDS or len(table.raw_descriptor) > MAX_CONFIG_BYTES:
        raise c.ResourceLimit('linked_declarations')
    declarations = [f.raw for f in table.fields]
    for d in declarations:
        if any(len(s) > 128 for s in (d[0],d[1],d[5])):
            raise c.ResourceLimit('linked_declaration_text')
    stride, placements = _placements(declarations)
    data = handle._open_table_data(table); length = data.info.logical_length
    if length > MAX_TABLE_BYTES: raise c.ResourceLimit('linked_table_bytes')
    if stride is not None and (stride > 4096 or length % stride or length // stride > MAX_SLOTS):
        raise c.UnsupportedLayout('linked_slot_shape')
    reader._budget.charge('output_bytes', 4*(length+len(table.raw_descriptor))+8192)
    reader._budget.charge('bytes_processed', length*2+8192)
    raw = data._read_range(0, length)
    slots = None if stride is None else [raw[i:i+stride].hex() for i in range(0,length,stride)]
    return dict(table=table.name, data_header_page=data.info.physical_header_page,
        descriptor_hex=table.raw_descriptor.hex(), declarations=[list(d) for d in declarations],
        layout='unresolved' if stride is None else 'existing_primitive_placement_only',
        record_size=stride, placements=placements, logical_length=length, raw_hex=raw.hex(), slots=slots)


def _catalog(read_at, size, spec):
    reader = c.CatalogReader(read_at, size); catalog = reader.read_catalog()
    graph = c._CatalogBindingGraph(reader, catalog)
    try:
        with graph.stage('config') as h:
            raw = _config_payload(h, spec['metadata_uuid'])
            identity = names.project_catalog_identity_prefix(raw, budget=reader._budget)
            if (identity.metadata_uuid != spec['metadata_uuid'] or identity.name != spec['name']
                    or identity.code_type != 1 or identity.code_length != 2 or identity.description_length != 8):
                raise c.InvalidStructure('linked_config_identity')
        with graph.stage('params') as h:
            db = _selected_dbnames(h, spec)
        table_name = '_Reference'+str(db['entries'][0]['id'])
        with graph.stage('records', binding=SimpleNamespace(table_name=table_name)) as h:
            physical = _physical(h)
        return dict(name=spec['name'],metadata_uuid=spec['metadata_uuid'],config_hex=raw.hex(),
            config_sha256=hashlib.sha256(raw).hexdigest(),dbnames=db,physical=physical,usage=asdict(reader.usage))
    except BaseException:
        graph.failed = True
        raise


def observe(read_at, size, request, actual_mapping):
    specs, request_sha = _request(request, actual_mapping)
    _check(callable(read_at)); _integer(size, MAX_READ_BYTES)
    totals = {'calls':0,'bytes':0}
    def bounded(offset, length):
        if (type(offset) is not int or type(length) is not int or offset < 0 or length < 0
                or offset > size or length > size-offset):
            raise c.InvalidStructure('linked_source_range')
        totals['calls'] += 1; totals['bytes'] += length
        if totals['calls'] > MAX_READ_CALLS or totals['bytes'] > MAX_READ_BYTES:
            raise c.ResourceLimit('linked_source_budget')
        return read_at(offset,length)
    catalogs = [_catalog(bounded,size,spec) for spec in specs]
    value = dict(schema=1,capability='owned_linked_raw_measurement_only',request_sha256=request_sha,
        actual_mapping=actual_mapping,catalogs=catalogs,source_reads=totals)
    validate_observation(value,request,actual_mapping)
    return value


def _hex(value, maximum):
    _check(type(value) is str and len(value) <= maximum*2 and len(value)%2 == 0
           and re.fullmatch('[0-9a-f]*',value) is not None)
    return bytes.fromhex(value)


def validate_observation(value, request, actual_mapping):
    specs, digest = _request(request, actual_mapping)
    _exact(value, ('schema','capability','request_sha256','actual_mapping','catalogs','source_reads'))
    _check(type(value['schema']) is int and value['schema']==1
           and value['capability']=='owned_linked_raw_measurement_only'
           and value['request_sha256']==digest and value['actual_mapping']==actual_mapping)
    _exact(value['source_reads'],('calls','bytes'))
    _integer(value['source_reads']['calls'],MAX_READ_CALLS); _integer(value['source_reads']['bytes'],MAX_READ_BYTES)
    _check(value['source_reads']['calls'] > 0 and value['source_reads']['bytes'] > 0)
    _check(type(value['catalogs']) is list and len(value['catalogs'])==2)
    tables=set(); headers=set()
    for item,spec in zip(value['catalogs'],specs):
        _exact(item,('name','metadata_uuid','config_hex','config_sha256','dbnames','physical','usage'))
        _check(item['name']==spec['name'] and item['metadata_uuid']==spec['metadata_uuid'])
        raw=_hex(item['config_hex'],MAX_CONFIG_BYTES); _check(bool(raw))
        _check(hashlib.sha256(raw).hexdigest()==item['config_sha256'])
        identity=names.project_catalog_identity_prefix(raw,budget=c._Budget(c.CatalogLimits()))
        _check(identity.name==spec['name'] and identity.metadata_uuid==spec['metadata_uuid']
               and identity.code_type==1 and identity.code_length==2 and identity.description_length==8)
        raw.decode('utf-8-sig')
        db=item['dbnames']; _exact(db,('bytes','sha256','entries'))
        _integer(db['bytes'],dbnames.DBNamesParseLimits().max_input_bytes); _digest(db['sha256'])
        expected=[spec['metadata_uuid']]+[a['metadata_uuid'] for a in spec['attributes']]
        _check(type(db['entries']) is list and len(db['entries'])==len(expected))
        ids=set()
        for index,(e,uid) in enumerate(zip(db['entries'],expected)):
            _exact(e,('uuid','raw_uuid','kind','raw_kind','id','raw_id','ordinal'))
            _check(e['uuid']==uid and e['raw_uuid']==uid)
            _check(e['kind']==('Reference' if index==0 else 'Fld') and e['raw_kind']=='"'+e['kind']+'"')
            _integer(e['id'],2147483647); _check(e['id']>0 and e['raw_id']==str(e['id']))
            _integer(e['ordinal'],4095); _check(e['id'] not in ids);ids.add(e['id'])
        p=item['physical']; _exact(p,('table','data_header_page','descriptor_hex','declarations',
            'layout','record_size','placements','logical_length','raw_hex','slots'))
        _check(p['table']=='_Reference'+str(db['entries'][0]['id']) and p['table'] not in tables);tables.add(p['table'])
        _integer(p['data_header_page'],8191);_check(p['data_header_page']>0 and p['data_header_page'] not in headers);headers.add(p['data_header_page'])
        descriptor=_hex(p['descriptor_hex'],MAX_CONFIG_BYTES)
        tree=c._Parser(descriptor,c._Budget(c.CatalogLimits())).value()
        _check(type(tree) is tuple and len(tree)==6 and tree[0]==p['table']
               and type(tree[1]) is int and tree[1]==0
               and type(tree[2]) is tuple and tree[2][0]=='Fields'
               and type(tree[4]) is tuple and tree[4]==('Recordlock','0')
               and type(tree[5]) is tuple and len(tree[5])==4 and tree[5][0]=='Files'
               and type(tree[5][1]) is int and tree[5][1]==p['data_header_page'])
        _check([list(d) for d in tree[2][1:]]==p['declarations'])
        ds=p['declarations'];_check(type(ds) is list and 1<=len(ds)<=MAX_FIELDS)
        for d in ds:
            _check(type(d) is list and len(d)==6 and all(type(x) is t for x,t in zip(d,(str,str,int,int,int,str))))
            _check(all(len(d[i])<=128 for i in (0,1,5)))
            for i in (2,3,4):_integer(d[i],2147483647)
        stride,placements=_placements(ds)
        _check(type(p['record_size']) is type(stride) and p['record_size']==stride and _json(p['placements'])==_json(placements))
        _check(p['layout']==('unresolved' if stride is None else 'existing_primitive_placement_only'))
        _integer(p['logical_length'],MAX_TABLE_BYTES); raw=_hex(p['raw_hex'],MAX_TABLE_BYTES)
        _check(len(raw)==p['logical_length'])
        if stride is None:_check(p['slots'] is None)
        else:
            _check(stride<=4096 and len(raw)%stride==0 and len(raw)//stride<=MAX_SLOTS)
            _check(p['slots']==[raw[i:i+stride].hex() for i in range(0,len(raw),stride)])
        usage=item['usage'];_exact(usage,[f.name for f in fields(c.CatalogUsage)])
        for k,n in usage.items():_integer(n,getattr(c.CatalogLimits(),'max_'+k))
    _check(sum(x['usage']['read_bytes'] for x in value['catalogs'])==value['source_reads']['bytes'])
    _json(value)
    return value
