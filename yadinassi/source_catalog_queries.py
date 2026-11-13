"""Read-only source catalog queries over one bounded v4 snapshot, never user SQL."""
from dataclasses import fields, is_dataclass, replace
from . import query_parser as syntax
from .queries import _Column
from .query_packages import _Table, _check_tables
from .source_constant_queries import _local_nodes, _private_name
from .source_catalog_store import SourceCatalogStore

_CONSTANTS = ('constants','константы')
_STANDARD = {'Code':'Код','Description':'Наименование','DeletionMark':'ПометкаУдаления'}


def has_catalog(statements):
    return any(type(n) in (syntax.Select,syntax.Source) and n.derived is None
               and not n.temporary and not n.external and n.family=='catalog'
               for n in syntax.walk_nodes(statements))


def read(query, caller, statements, *, batch=False):
    store=query._source_owner._store(caller)
    app=query._source_owner._application()
    if type(store) is not SourceCatalogStore:
        raise ValueError('source Catalog queries require explicit v4 scratch capability')
    if caller._scheduler.pending:
        raise ValueError('source Catalog query requires synchronous execution')
    if batch or len(statements)!=1 or query._temp_tables_manager is not None:
        raise ValueError('source Catalog query packages/temporary tables unsupported')
    nodes=tuple(syntax.walk_nodes(statements))
    if any(type(n) is syntax.Destroy or getattr(n,'into',None) is not None for n in nodes):
        raise ValueError('source Catalog query mutation/temporary tables unsupported')
    used={n.catalog.casefold() for n in nodes if type(n) in (syntax.Select,syntax.Source)}|set(query._parameters)
    mappings={};catalogs={};tables={};constant_names={}
    constant_parameter=None
    for node in nodes:
        if type(node) not in (syntax.Select,syntax.Source) or node.derived is not None:
            continue
        if node.section is not None or node.period_boundary is not None:
            raise ValueError('source Catalog virtual/tabular sources unsupported')
        if node.external:
            raise ValueError('source Catalog external-table mixing unsupported')
        if node.temporary:
            if node.catalog.casefold() not in _CONSTANTS:
                raise ValueError('unknown source query temporary table')
            key=('constant',node.catalog.casefold())
            if constant_parameter is None:
                constant_parameter=_private_name(used,'__source_constants');used.add(constant_parameter)
            mappings[key]=constant_parameter
        elif node.family=='catalog':
            definition=store.catalog(node.catalog)
            key=('catalog',definition.name.casefold())
            if key not in mappings:
                parameter=_private_name(used,'__source_catalog');used.add(parameter)
                mappings[key]=parameter;catalogs[parameter]=definition
        else:
            raise ValueError('source query persistent family unsupported: '+node.family)
    if len(catalogs)+(constant_parameter is not None)>16:
        raise ValueError('source query table bound')
    for arm in syntax.selects(statements):
        sources=(syntax.Source(arm.catalog,arm.source_alias,arm.section,arm.temporary,arm.external,arm.family,arm.period_boundary,arm.derived),*(j.source for j in arm.joins))
        aliases={s.alias.casefold() for s in sources if s.temporary and s.catalog.casefold() in _CONSTANTS}
        for node in _local_nodes(arm):
            if type(node) is not syntax.Field or not aliases:continue
            if len(node.parts)==2 and node.parts[0].casefold() not in aliases:continue
            if len(node.parts) not in (1,2):continue
            name=node.parts[-1]
            if len(node.parts)==1 and not store.has(name):continue
            definition=store._definition(name);constant_names[name.casefold()]=definition
    from .source_query_references import make_binding
    for parameter,definition in catalogs.items():
        binding=make_binding(app,query._catalogs,definition.name)
        columns=[_Column(n,None,'catalog_ref',(),explicit_alias=True,reference_identity=binding.identity,reference_binding=binding) for n in ('Ref','Ссылка')]
        for field in definition.fields:
            for name in (field.name, *([_STANDARD[field.name]] if field.name in _STANDARD else [])):
                if field.kind == 'object_ref' and field.qualifiers[0] == 'Catalog':
                    target = make_binding(app, query._catalogs, field.qualifiers[2])
                    columns.append(_Column(name,None,'catalog_ref',(),explicit_alias=True,
                                           reference_identity=target.identity,reference_binding=target))
                else:
                    columns.append(_Column(name,None,field.kind,field.qualifiers,explicit_alias=True))
        tables[parameter]=_Table(tuple(columns),())
    constant_definitions=tuple(constant_names.values())
    if constant_parameter is not None:
        columns=[]
        for d in constant_definitions:
            if d.kind in ('string','number','boolean','datetime'):
                columns.append(_Column(d.name,None,d.kind,d.qualifiers,explicit_alias=True))
            elif d.kind=='object_ref' and d.qualifiers[0]=='Catalog':
                binding=make_binding(app,query._catalogs,d.qualifiers[2])
                columns.append(_Column(d.name,None,'catalog_ref',(),explicit_alias=True,reference_identity=binding.identity,reference_binding=binding))
            else:raise ValueError('source query constant type unsupported: '+d.name)
        tables[constant_parameter]=_Table(tuple(columns),())
    translated=_translate(statements[0],mappings)
    from .relational_queries import _Plan, snapshot_parameters
    from .query_sources import _UnionPlan
    parameters=snapshot_parameters(dict(query._parameters))
    plan=(_UnionPlan if type(translated) is syntax.Union else _Plan)(translated,query._catalogs,parameters,external_tables=tables)
    owned=not store.transaction_active
    try:
        if owned:store.begin_transaction()
        store._open()
        for parameter,definition in catalogs.items():
            rows=[]
            for identity,_,values in store.read_records(definition.name):
                reference=app.references.ref('Catalog',definition.name,identity)
                row=[reference,reference]
                for field in definition.fields:
                    row.append(values[field.name.casefold()])
                    if field.name in _STANDARD:row.append(values[field.name.casefold()])
                rows.append(tuple(row))
            tables[parameter]=_Table(tables[parameter].columns,tuple(rows))
        if constant_parameter is not None:
            values=store.get_many(tuple(d.name for d in constant_definitions))
            tables[constant_parameter]=_Table(tables[constant_parameter].columns,(tuple(values[d.name.casefold()] for d in constant_definitions),))
        _check_tables(tables)
        query._source_owner._store(caller)
        if owned:store.rollback_transaction()
    except BaseException:
        if store.transaction_active:store.rollback_transaction()
        raise
    return plan.execute()


def _translate(node,mappings):
    if type(node) is tuple:return tuple(_translate(n,mappings) for n in node)
    if not is_dataclass(node):return node
    changes={field.name:_translate(getattr(node,field.name),mappings) for field in fields(node)}
    if type(node) in (syntax.Select,syntax.Source) and node.derived is None:
        kind='constant' if node.temporary else 'catalog'
        changes.update(catalog=mappings[(kind,node.catalog.casefold())],temporary=False,external=True)
    return replace(node,**changes)
