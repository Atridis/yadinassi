"""Read-only source record queries over one bounded v4/v5/v6 snapshot, never user SQL."""
from dataclasses import fields, is_dataclass, replace
from decimal import Decimal
from . import query_parser as syntax
from .queries import _Column
from .query_packages import _Table, _check_tables, MAX_ROWS, MAX_CELLS, MAX_TEXT
from .source_constant_queries import _local_nodes, _private_name
from .source_catalog_store import SourceCatalogStore
from .source_document_store import SourceDocumentStore
from .source_document_section_store import SourceDocumentSectionStore

_CONSTANTS = ('constants','константы')
_STANDARD = {'catalog': {'Code':'Код','Description':'Наименование','DeletionMark':'ПометкаУдаления'},
             'document': {'Number':'Номер','Date':'Дата','DeletionMark':'ПометкаУдаления','Posted':'Проведен'}}


def has_catalog(statements):
    return any(type(n) in (syntax.Select,syntax.Source) and n.derived is None
               and not n.temporary and not n.external and n.family in ('catalog','document')
               for n in syntax.walk_nodes(statements))


def read(query, caller, statements, *, batch=False):
    store=query._source_owner._store(caller)
    app=query._source_owner._application()
    if type(store) not in (SourceCatalogStore, SourceDocumentStore, SourceDocumentSectionStore):
        raise ValueError('source Catalog queries require explicit v4 scratch capability')
    if caller._scheduler.pending:
        raise ValueError('source Catalog query requires synchronous execution')
    package_mode = batch or len(statements)!=1 or query._temp_tables_manager is not None
    nodes=tuple(syntax.walk_nodes(statements))
    if any(type(n) is syntax.Destroy or getattr(n,'into',None) is not None for n in nodes):
        package_mode = True
    for n in nodes:
        target=n.name if type(n) is syntax.Destroy else getattr(n,'into',None)
        if target is not None and target.casefold() in _CONSTANTS:
            raise ValueError('source Constants table name is reserved')
    if any(m.family == 'CommonAttribute' for m in app.source.metadata):
        raise ValueError('source query data separation unsupported')
    used={n.catalog.casefold() for n in nodes if type(n) in (syntax.Select,syntax.Source)}|set(query._parameters)|{n.name.casefold() for n in nodes if type(n) is syntax.Parameter}
    mappings={};catalogs={};tables={};constant_names={}
    constant_parameter=None
    for node in nodes:
        if type(node) not in (syntax.Select,syntax.Source) or node.derived is not None:
            continue
        if node.period_boundary is not None or (node.section is not None and
                (node.family!='document' or node.external or node.temporary or type(store) is not SourceDocumentSectionStore)):
            raise ValueError('source Catalog virtual/tabular sources unsupported')
        if node.external:
            package_mode=True
            continue
        if node.temporary:
            if node.catalog.casefold() not in _CONSTANTS:
                package_mode=True
                continue
            key=('constant',node.catalog.casefold(),None)
            if constant_parameter is None:
                constant_parameter=_private_name(used,'__source_constants');used.add(constant_parameter)
            mappings[key]=constant_parameter
        elif node.family in ('catalog','document'):
            if node.family=='document' and type(store) not in (SourceDocumentStore, SourceDocumentSectionStore):
                raise ValueError('source Document query requires v5 scratch capability')
            definition=(store.catalog if node.family=='catalog' else store.document)(node.catalog)
            section=None
            if node.section is not None:
                section=next((item for item in definition.sections if item.name.casefold()==node.section.casefold()),None)
                if section is None:raise ValueError('unknown source document section: '+node.section)
            key=(node.family,definition.name.casefold(),section.name.casefold() if section else None)
            if key not in mappings:
                parameter=_private_name(used,'__source_catalog');used.add(parameter)
                mappings[key]=parameter;catalogs[parameter]=(node.family,definition,section)
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
    for parameter,(family,definition,section) in catalogs.items():
        binding=make_binding(app,query._catalogs,definition.name,family.title())
        columns=[_Column(n,None,binding.kind,(),explicit_alias=True,reference_identity=binding.identity,reference_binding=binding) for n in ('Ref','Ссылка')]
        if section is not None:
            columns.extend(_Column(n,None,'number',(10,0,'Nonnegative'),explicit_alias=True) for n in ('LineNumber','НомерСтроки'))
        selected_fields=section.fields if section is not None else definition.fields
        aliases={} if section is not None else _STANDARD[family]
        for field in selected_fields:
            for name in (field.name, *([aliases[field.name]] if field.name in aliases else [])):
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
            elif d.kind=='object_ref' and d.qualifiers[0] in ('Catalog','Document'):
                binding=make_binding(app,query._catalogs,d.qualifiers[2],d.qualifiers[0])
                columns.append(_Column(d.name,None,binding.kind,(),explicit_alias=True,reference_identity=binding.identity,reference_binding=binding))
            else:raise ValueError('source query constant type unsupported: '+d.name)
        tables[constant_parameter]=_Table(tuple(columns),())
    translated=_translate(statements if package_mode else statements[0],mappings)
    from .relational_queries import _Plan, snapshot_parameters
    from .query_sources import _UnionPlan
    parameters=snapshot_parameters(dict(query._parameters))
    plan = None if package_mode else (_UnionPlan if type(translated) is syntax.Union else _Plan)(translated,query._catalogs,parameters,external_tables=tables)
    owned=not store.transaction_active
    try:
        if owned:store.begin_transaction()
        store._open()
        record_cache={};section_cache={};cells=0;text=0
        for parameter,(family,definition,section) in catalogs.items():
            rows=[];cache_key=(family,definition.name.casefold())
            if cache_key not in record_cache:
                record_cache[cache_key]=(store.read_records if family=='catalog' else store.read_documents)(definition.name)
            for identity,_,values in record_cache[cache_key]:
                reference=app.references.ref(family.title(),definition.name,identity)
                if section is None:
                    entries=((None,values),);selected_fields=definition.fields;aliases=_STANDARD[family]
                else:
                    section_key=(definition.identity,identity)
                    if section_key not in section_cache:
                        section_cache[section_key]=store._sections(definition,identity)
                    entries=enumerate(section_cache[section_key][section.name.casefold()],1)
                    selected_fields=section.fields;aliases={}
                for line,entry in entries:
                    row=[reference,reference]
                    if section is not None:row.extend((Decimal(line),Decimal(line)))
                    for field in selected_fields:
                        row.append(entry[field.name.casefold()])
                        if field.name in aliases:row.append(entry[field.name.casefold()])
                    cells+=len(row);text+=sum(len(v) for v in row if type(v) is str)
                    if len(rows)>=MAX_ROWS or cells>MAX_CELLS or text>MAX_TEXT:
                        raise ValueError('source query snapshot resource limit')
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
    if package_mode:
        import weakref
        from .source_query_references import SourcePackageScope
        from .query_packages import execute_package
        scope=SourcePackageScope(weakref.ref(app),query._catalogs,translated,tuple(tables.items()))
        result=execute_package(translated,query._catalogs,parameters,query._temp_tables_manager,_source_scope=scope)
        return result if batch else result.items[-1]
    return plan.execute()


def _translate(node,mappings):
    if type(node) is tuple:return tuple(_translate(n,mappings) for n in node)
    if not is_dataclass(node):return node
    changes={field.name:_translate(getattr(node,field.name),mappings) for field in fields(node)}
    if type(node) in (syntax.Select,syntax.Source) and node.derived is None:
        kind='constant' if node.temporary else node.family
        key=(kind,node.catalog.casefold(),node.section.casefold() if node.section is not None else None)
        if not node.external and key in mappings:
            # The rewritten node is a private external carrier, not a persistent
            # Document source. Reference kind/identity live in its typed columns.
            # Normalize the lexical family so legacy package metadata discovery
            # cannot open a separate document backend for this frozen snapshot.
            changes.update(catalog=mappings[key],temporary=False,external=True,family='catalog',section=None)
    return replace(node,**changes)


def has_source_inputs(query):
    """Route detached source reports back to their authorized source adapter."""
    from .source_query_references import SourceBinding
    from .value_tables import BSLValueTable
    from .query_packages import BSLTempTablesManager
    for value in query._parameters.values():
        if type(value) is BSLValueTable:
            for column in value.columns.items:
                if type(getattr(column.value_type, '_query_reference', None)) is SourceBinding:
                    return True
    manager=query._temp_tables_manager
    if type(manager) is BSLTempTablesManager:
        if getattr(manager, '_source_owner', None) is not None:
            return True
        if any(type(c.reference_binding) is SourceBinding for t in manager._tables.values() for c in t.columns):
            return True
    return False
