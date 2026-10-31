"""Measurement-only slot bytes for two owned catalogs, never production admission.

Every catalog traverses its own CONFIG/PARAMS/records revocable graph. Both use
one caller-owned immutable descriptor and a shared source-read budget. No marker
is interpreted as a free-list pointer or proof of liveness. Native Query/cursor
observations, not this helper, establish the meaning of the captured bytes.
"""
from dataclasses import asdict
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage import config_catalog_transport as config
from yadinassi.storage import filedb_named_file as named
from yadinassi.storage import filedb_dbnames as dbnames
from yadinassi.storage import config_catalog_binding as compiler
from yadinassi.storage import config_catalog_records as records

MAX_SLOTS = 16
MAX_RECORD_BYTES = 256
MAX_READ_BYTES = 64 * 1024 * 1024
MAX_READ_CALLS = 100000


def _slots(reader, handle, binding):
    """Keep reserved/free bytes opaque, separate from logical _MARKED bytes."""
    records._validate_binding(binding, reader._budget)
    table = handle.table
    if (table.name != binding.table_name or type(table.format_item) is not int
            or table.format_item != 0 or table.recordlock != binding.recordlock
            or tuple(f.raw for f in table.fields) != binding.declarations):
        raise c.UnsupportedLayout('measurement_declaration_mismatch')
    if binding.record_size > MAX_RECORD_BYTES:
        raise c.ResourceLimit('measurement_record_bytes')
    data = handle._open_table_data(table)
    length = data.info.logical_length
    if length % binding.record_size:
        raise c.InvalidStructure('record_file_length')
    count = length // binding.record_size
    if count > MAX_SLOTS:
        raise c.ResourceLimit('measurement_slots')
    placements = [{'name':p.declaration[0], 'offset':p.offset, 'width':p.width,
                   'declaration':list(p.declaration)} for p in binding.placements]
    marked = [p for p in binding.placements if p.declaration[0] == '_MARKED']
    if len(marked) != 1 or marked[0].width != 1:
        raise c.UnsupportedLayout('measurement_marked_role')
    reader._budget.charge('output_bytes', 8192 + count * (512 + 2 * binding.record_size))
    reader._budget.charge('bytes_processed', 8192 + count * 3 * binding.record_size)
    slots = []
    for index in range(count):
        raw = data._read_range(index * binding.record_size, binding.record_size)
        # Deliberately retain all marker values. Unknown is observation, not
        # successful row decode, active count, or production support.
        slots.append({'slot':index, 'logical_offset':index * binding.record_size,
                      'marker':raw[0], 'raw_hex':raw.hex(),
                      'logical_marked_hex':raw[marked[0].offset:marked[0].offset+1].hex()
                          if index > 0 and raw[0] == 0 else None})
    return {'table':table.name, 'data_header_page':data.info.physical_header_page,
            'record_size':binding.record_size, 'logical_length':length,
            'placements':placements, 'slots':slots}


def _catalog(read_at, size, name, expected_uuid):
    reader = c.CatalogReader(read_at, size)
    catalog = reader.read_catalog()
    graph = c._CatalogBindingGraph(reader, catalog)
    try:
        with graph.stage('config') as h:
            observed = config._observe_catalog_attributes_from_graph(h,
                profile=config.ConfigCatalogAttributeProfile(config.DECLARATIONS, '0', 0))
            reader._budget.charge('output_bytes', 65536)
            reader._budget.charge('bytes_processed', 2048 * len(observed.private_fields))
            matches = []
            identities = set()
            for key, identity, attributes in observed.private_fields:
                if key != identity.metadata_uuid or key in identities:
                    raise c.InvalidStructure('measurement_catalog_identity')
                identities.add(key)
                if identity.name == name: matches.append((identity, attributes))
            if len(matches) != 1:
                raise c.UnsupportedLayout('measurement_catalog_selector')
            identity, attributes = matches[0]
            if identity.metadata_uuid != expected_uuid:
                raise c.InvalidStructure('measurement_saved_identity')
        with graph.stage('params') as h:
            extracted = named._read_dbnames_from_catalog(reader, catalog,
                profile=named.DBNamesProfile(config.DECLARATIONS, '0', 0,
                    slot_policy='closed_marker1_chain_v1'), _binding_handle=h)
            profile = dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER)
            limits = dbnames.DBNamesParseLimits()
            reserve = dbnames.reserve_dbnames_parse(extracted.data, profile=profile, limits=limits)
            reader._budget.charge('output_bytes', reserve.output_bytes)
            reader._budget.charge('bytes_processed', reserve.bytes_processed)
            reader._budget.charge('tokens', min(len(extracted.data), limits.max_tokens + 1))
            parsed = dbnames.parse_dbnames(extracted.data, profile=profile, limits=limits)
            binding = compiler.compile_catalog_binding(identity, attributes, parsed,
                profile=compiler.CatalogBindingProfile(compiler.NUMERIC_PROFILE_IDENTIFIER), budget=reader._budget)
            # Only this owned fixture shape, not a new general physical profile.
            if (binding.code_type != 1 or binding.code_length != 2
                    or binding.description_length != 8
                    or tuple((a.name, a.type_token, a.qualifiers) for a in binding.attributes)
                    != (('Payload', 'S', (32, 1)), ('Amount', 'N', (9, 2, 0)))):
                raise c.UnsupportedLayout('measurement_owned_profile')
        with graph.stage('records', binding=binding) as h:
            result = _slots(reader, h, binding)
        return {'name':identity.name, 'metadata_uuid':identity.metadata_uuid,
                **result, 'usage':asdict(reader.usage)}
    except BaseException:
        graph.failed = True
        raise


def observe(read_at, size, b):
    """No path access, writes, runtime admission, or unbounded raw database export."""
    from catalog_read_packet.batch import Batch
    if type(b) is not Batch or not callable(read_at):
        raise ValueError('closed measurement inputs required')
    b.validate()
    totals = {'calls':0, 'bytes':0}
    def bounded(offset, length):
        # CatalogReader validates ranges; do not forward an invalid callback
        # argument even if a future internal caller changes its own validation.
        if (type(offset) is not int or type(length) is not int or offset < 0
                or length < 0 or type(size) is not int or offset > size or length > size-offset):
            raise c.InvalidStructure('measurement_source_range')
        totals['calls'] += 1; totals['bytes'] += length
        if totals['calls'] > MAX_READ_CALLS or totals['bytes'] > MAX_READ_BYTES:
            raise c.ResourceLimit('measurement_source_budget')
        return read_at(offset, length)
    catalogs = [_catalog(bounded, size, name, uuid)
                for name, uuid in zip(b.setup.names, b.setup.metadata_ids)]
    if (len({v['table'] for v in catalogs}) != 2
            or len({v['data_header_page'] for v in catalogs}) != 2):
        raise c.UnsupportedSharing('measurement_catalog_alias')
    value = {'schema':1, 'capability':'owned_raw_slot_measurement_only',
             'catalogs':catalogs, 'source_reads':totals}
    validate_observation(value, b)
    return value


def validate_observation(value, b):
    """Strict bounded JSON replay, not a second physical read or liveness claim."""
    import re
    from dataclasses import fields
    def check(condition):
        if not condition: raise ValueError('invalid physical observation')
    def exact(item, keys): check(type(item) is dict and set(item) == set(keys))
    def integer(item, high): check(type(item) is int and 0 <= item <= high)
    from catalog_read_packet.batch import Batch
    check(type(b) is Batch); b.validate()
    exact(value, ('schema','capability','catalogs','source_reads'))
    check(type(value['schema']) is int and value['schema'] == 1)
    check(value['capability'] == 'owned_raw_slot_measurement_only')
    exact(value['source_reads'], ('calls','bytes'))
    integer(value['source_reads']['calls'], MAX_READ_CALLS)
    integer(value['source_reads']['bytes'], MAX_READ_BYTES)
    check(value['source_reads']['calls'] > 0 and value['source_reads']['bytes'] > 0)
    check(type(value['catalogs']) is list and len(value['catalogs']) == 2)
    tables = set(); headers = set()
    for item, name, uuid in zip(value['catalogs'], b.setup.names, b.setup.metadata_ids):
        exact(item, ('name','metadata_uuid','table','data_header_page','record_size',
                     'logical_length','placements','slots','usage'))
        check(item['name'] == name and item['metadata_uuid'] == uuid)
        check(type(item['table']) is str and re.fullmatch(r'_Reference[1-9][0-9]{0,9}', item['table']) is not None)
        check(int(item['table'][10:]) <= 2147483647)
        integer(item['data_header_page'], 8191); check(item['data_header_page'] > 0)
        check(item['table'] not in tables and item['data_header_page'] not in headers)
        tables.add(item['table']); headers.add(item['data_header_page'])
        check(type(item['record_size']) is int and item['record_size'] == 145)
        check(type(item['slots']) is list and len(item['slots']) <= MAX_SLOTS)
        integer(item['logical_length'], MAX_SLOTS * 145)
        check(item['logical_length'] == len(item['slots']) * 145)
        check(type(item['placements']) is list and len(item['placements']) == 8)
        dynamic=[]
        for p in item['placements'][6:]:
            check(type(p) is dict and type(p.get('name')) is str and re.fullmatch(r'_FLD[1-9][0-9]{0,9}', p['name']) is not None)
            check(int(p['name'][4:]) <= 2147483647); dynamic.append(p['name'])
        check(len(set(dynamic)) == 2)
        decls=(('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
               ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),
               ('_CODE','NVC',0,2,0,'CI'),('_DESCRIPTION','NVC',0,8,0,'CI'),
               (dynamic[0],'NVC',0,32,0,'CI'),(dynamic[1],'N',0,9,2,'CS'))
        for p,d,offset,width in zip(item['placements'],decls,(17,1,33,34,50,56,74,140),(16,16,1,16,6,18,66,5)):
            exact(p, ('name','offset','width','declaration'))
            check(p['name']==d[0]); integer(p['offset'],145);integer(p['width'],145)
            check(p['offset']==offset and p['width']==width)
            check(type(p['declaration']) is list and len(p['declaration'])==6)
            check(all(type(a) is type(z) and a==z for a,z in zip(p['declaration'],d)))
        for i, slot in enumerate(item['slots']):
            exact(slot, ('slot','logical_offset','marker','raw_hex','logical_marked_hex'))
            integer(slot['slot'],15);integer(slot['logical_offset'],15*145);integer(slot['marker'],255)
            check(slot['slot']==i and slot['logical_offset']==i*145)
            check(type(slot['raw_hex']) is str and re.fullmatch('[0-9a-f]{290}',slot['raw_hex']) is not None)
            raw=bytes.fromhex(slot['raw_hex']);check(raw[0]==slot['marker'])
            expected=raw[33:34].hex() if i>0 and raw[0]==0 else None
            check(slot['logical_marked_hex']==expected and type(slot['logical_marked_hex']) is type(expected))
        usage_keys=tuple(f.name for f in fields(c.CatalogUsage))
        exact(item['usage'],usage_keys)
        limits=c.CatalogLimits()
        for key,n in item['usage'].items(): integer(n,getattr(limits,'max_'+key))
    check(sum(item['usage']['read_bytes'] for item in value['catalogs']) == value['source_reads']['bytes'])
    return value
