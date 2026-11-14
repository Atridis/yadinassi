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


def _field(section,name):
    if type(name) is not str or not 1<=len(name)<=128:raise TypeError('source section column requires bounded field name')
    key=name.casefold()
    if key not in section.fields:raise ValueError('unknown source section column')
    return key


def _selection(section,names):
    if names is None or (type(names) is str and names==''):return tuple(section.fields)
    if type(names) is not str or len(names)>16384:raise TypeError('source section column list requires bounded String')
    parts=names.split(',')
    if len(parts)>len(section.fields):raise ValueError('source section column count bound')
    if any(not p or p!=p.strip() for p in parts):raise ValueError('source section columns require explicit names without whitespace')
    keys=tuple(_field(section,p) for p in parts)
    if len(set(keys))!=len(keys):raise ValueError('duplicate source section column')
    return keys


def _replace_values(caller,section,candidate):
    """Validate the whole owner buffer before changing any live row dictionary."""
    total=0;count=0
    for other in section.owner.sections.values():
        rows=candidate if other is section else [r.values for r in other.rows]
        count+=len(rows)
        for values in rows:
            total+=32+sum(len(_encode(v,other.fields[k]).encode())+len(k.encode()) for k,v in values.items())
            if total>_MAX_DOCUMENT_BYTES:raise ValueError('document section buffer bound')
    if count>_MAX_ROWS:raise ValueError('document section buffer bound')
    section.authorize(caller)
    for row,values in zip(section.rows,candidate):row.values=values


def column_operation(caller,section,operation,arguments):
    from .values import BSLArray
    section.authorize(caller);section.buffer_bound()
    if operation=='unloadcolumn':
        if len(arguments)!=1:raise TypeError('source UnloadColumn requires one field name')
        key=_field(section,arguments[0]);values=[]
        for row in section.rows:
            if key not in row.values:raise ValueError('source section column requires explicit values')
            value=row.values[key];_encode(value,section.fields[key]);values.append(value)
        result=BSLArray();result.items=values;return result
    if operation=='loadcolumn':
        if len(arguments)!=2:raise TypeError('source LoadColumn requires Array and field name')
        array,name=arguments;key=_field(section,name)
        if type(array) is not BSLArray or type(array.items) is not list:raise TypeError('source LoadColumn requires exact Array')
        if len(array.items)!=len(section.rows) or len(array.items)>_MAX_ROWS:raise ValueError('source LoadColumn requires exact row count')
        values=tuple(array.items)
        for value in values:_encode(value,section.fields[key])
        candidate=[dict(row.values,**{key:value}) for row,value in zip(section.rows,values)]
    elif operation=='fillvalues':
        if len(arguments) not in (1,2):raise TypeError('source FillValues requires value and optional column list')
        value=arguments[0];keys=_selection(section,arguments[1] if len(arguments)==2 else None)
        for key in keys:_encode(value,section.fields[key])
        candidate=[dict(row.values,**{key:value for key in keys}) for row in section.rows]
    else:raise ValueError('unsupported source column operation')
    _replace_values(caller,section,candidate)


def search(caller,section,operation,args):
    """Explicit typed predicates over the owned bounded buffer, no persistence."""
    from .structures import BSLStructure
    from .values import BSLArray,equal
    section.authorize(caller);section.buffer_bound()
    if operation=='find':
        if len(args)!=2:raise TypeError('source section Find requires value and one field')
        field=section.fields[_field(section,args[1])];selected=[(field,args[0])]
    else:
        if len(args)!=1 or type(args[0]) is not BSLStructure:raise TypeError('source section FindRows requires Structure')
        filters=args[0]
        if type(filters._items) is not dict:raise TypeError('source section filter shape')
        if len(filters._items)>len(section.fields):raise ValueError('source section filter bound')
        selected=[];seen=set()
        for entry in filters._items.values():
            if type(entry) is not tuple or len(entry)!=2:raise TypeError('source section filter entry')
            name,value=entry;key=_field(section,name);field=section.fields[key]
            if key in seen:raise ValueError('duplicate source section filter')
            seen.add(key);selected.append((field,value))
    for field,value in selected:_encode(value,field)
    found=[]
    if selected:
        for row in section.rows:
            matches=[]
            for field,value in selected:
                key=field.name.casefold()
                if key not in row.values:raise ValueError('section search requires assigned fields')
                actual=row.values[key];_encode(actual,field);matches.append(equal(actual,value))
            if all(matches):
                if operation=='find':return row
                found.append(row)
    section.authorize(caller)
    if operation=='find':return None
    result=BSLArray();result.items=found;return result
