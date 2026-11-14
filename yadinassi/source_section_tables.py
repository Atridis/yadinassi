"""Bounded complete-schema section snapshots and atomic typed buffer replacement."""
from uuid import UUID
from .source_constant_store import _encode
from .source_document_section_store import _MAX_ROWS,_MAX_DOCUMENT_BYTES


def _columns(caller,section):
    from .queries import _Column
    from .source_query_references import make_binding
    from .source_query_enums import SourceEnumScope
    app,_=section.owner.authorize(caller);scope=SourceEnumScope(app,app.interpreter._catalogs)
    result=[]
    try:
        for field in section.definition.fields:
            binding=None;kind=field.kind;qualifiers=field.qualifiers
            if kind=='enum_ref':binding=scope.domain(scope.descriptor(UUID(qualifiers[0])))
            elif kind=='object_ref':
                binding=make_binding(app,app.interpreter._catalogs,qualifiers[2],qualifiers[0]);kind=binding.kind
            result.append(_Column(field.name,None,kind,() if binding else qualifiers,explicit_alias=True,
                                  reference_binding=binding,reference_identity=binding.identity if binding else None))
        return tuple(result)
    finally:scope._retired=True


def unload(caller,section):
    from .query_reference_tables import unload as snapshot
    section.authorize(caller);section.buffer_bound()
    columns=_columns(caller,section);rows=[]
    for row in section.rows:
        if set(row.values)!=set(section.fields):raise ValueError('source section Unload requires all fields assigned')
        values=tuple(row.values[f.name.casefold()] for f in section.definition.fields)
        for field,value in zip(section.definition.fields,values):_encode(value,field)
        rows.append(values)
    return snapshot(columns,tuple(rows))


def load(caller,section,table):
    from .value_tables import BSLValueTable,BSLValueTableColumnCollection,BSLValueTableColumn,BSLValueTableRow
    from .type_descriptions import BSLTypeDescription,_reference_description_kind
    from .source_document_sections import SourceDocumentRow
    section.authorize(caller)
    if (type(table) is not BSLValueTable or type(table.rows) is not list
            or type(table.columns) is not BSLValueTableColumnCollection or table.columns.table is not table
            or type(table.columns.items) is not list):raise TypeError('source section Load requires exact ValueTable')
    if len(table.rows)>_MAX_ROWS or len(table.columns.items)!=len(section.fields):raise ValueError('source section Load shape bound')
    expected={c.name.casefold():c for c in _columns(caller,section)}
    columns={}
    for column in table.columns.items:
        if (type(column) is not BSLValueTableColumn or column.table is not table or column._deleted
                or type(column.name) is not str or not 1<=len(column.name)<=128
                or type(column.value_type) is not BSLTypeDescription):raise TypeError('source section Load invalid column')
        key=column.name.casefold()
        if key not in section.fields or key in columns:raise ValueError('source section Load requires every field exactly once')
        typ=_reference_description_kind(column.value_type)
        if typ is not None:
            binding=expected[key].reference_binding
            if binding is None or typ is not binding.value_type:raise TypeError('source section Load foreign reference column')
            binding.require_owner()
        columns[key]=column
    candidate=[];total=0
    for row in table.rows:
        if (type(row) is not BSLValueTableRow or row.table is not table or row._deleted
                or type(row.cells) is not dict or set(row.cells)!=set(table.columns.items)):
            raise TypeError('source section Load invalid row')
        values={key:row.cells[column] for key,column in columns.items()}
        size=32
        for key,value in values.items():size+=len(_encode(value,section.fields[key]).encode())+len(key.encode())
        total+=size
        if total>_MAX_DOCUMENT_BYTES:raise ValueError('document section buffer bound')
        candidate.append(values)
    count=len(candidate)
    for other in section.owner.sections.values():
        if other is section:continue
        count+=len(other.rows)
        for row in other.rows:
            total+=32+sum(len(_encode(v,other.fields[k]).encode())+len(k.encode()) for k,v in row.values.items())
    if count>_MAX_ROWS or total>_MAX_DOCUMENT_BYTES:raise ValueError('document section buffer bound')
    section.authorize(caller)
    replacement=[SourceDocumentRow(section,values) for values in candidate]
    for row in section.rows:row.live=False
    section.rows=replacement;section.version+=1
