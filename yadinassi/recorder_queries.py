"""Closed read-only recorder sources on the owning document query snapshot."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
from .catalog_backend import BackendError
from .document_backend import DocumentKey

class RecorderQueryManager:
    def __init__(self, documents, schema):
        self.documents=documents;self.recorder_schema=schema
        self._catalogs=documents._catalogs
        self._schema=SimpleNamespace(identity=schema.identity,name=schema.name,fields=schema.fields,
            dimensions=schema.fields[:schema.dimension_count],periodic=False)
        self._documents_by_id={d.identity:documents.get_index(d.name)
            for d in documents._context.backend.posting_configuration.documents}
    def _logical(self, field, value):
        return self._documents_by_id[self.recorder_schema.recorder_documents[0]]._logical(field,value)

def manager(documents,name):
    if documents is None:return None
    from .sqlite_catalog import SQLiteCatalogBackend
    from .configuration_posting import PostingConfiguration
    context=documents._context
    if context is None:return None
    backend=context.backend
    if type(backend) is not SQLiteCatalogBackend:return None
    config=backend.posting_configuration
    if type(config) is not PostingConfiguration:return None
    matches=[s for s in config.registers if s.name.casefold()==name.casefold()]
    if len(matches)!=1:raise ValueError('Unknown recorder information-register source')
    return RecorderQueryManager(documents,matches[0])

def field(manager,expression,alias):
    from .queries import _Column
    if len(expression.parts)==2 and expression.parts[0].casefold()!=alias.casefold():
        raise ValueError('Unknown query source qualifier')
    name=expression.parts[-1].casefold()
    standard={'recorder':'recorder','регистратор':'recorder','active':'active',
        'активность':'active','linenumber':'line_number','номерстроки':'line_number'}.get(name)
    if standard=='recorder':
        owners=manager.recorder_schema.recorder_documents
        if len(owners)!=1:raise ValueError('Recorder reference query requires one declared document type')
        return _Column('',standard,'document_ref',(),
            reference_identity=(manager.documents._metadata,owners[0]))
    if standard=='active':return _Column('',standard,'boolean',())
    if standard=='line_number':return _Column('',standard,'number',(10,0,'Nonnegative'))
    matches=[f for f in manager._schema.fields if f.name.casefold()==name]
    if len(matches)!=1:raise ValueError('Unknown recorder query field')
    f=matches[0]
    return _Column('',f.identity,f.kind,f.qualifiers,f)

def load(manager,columns,view,budget):
    from .sqlite_documents import DocumentView
    from .sqlite_transactions import _recorder_port
    from .queries import _section_value,_MAX_CELLS,_MAX_RESULT_TEXT
    from .query_parser import MAX_ROWS
    if type(view) is not DocumentView:raise BackendError('unsupported')
    owner=view._view;owner._require()
    config=owner._backend.posting_configuration
    if (config is None or manager.recorder_schema not in config.registers or
            manager.documents._context.backend is not owner._backend):
        raise BackendError('schema_changed')
    port=_recorder_port(owner)
    rows=[]
    for key,partition in port.scan(manager.recorder_schema.identity):
        for row in partition.rows:
            values={f.identity:_section_value(manager,f,v)
                for f,v in zip(manager._schema.fields,row.values)}
            values.update(active=row.active,line_number=Decimal(row.line_number))
            # Validate and charge all source cells, not only projected/residual fields.
            budget[0]+=len(values)+1
            budget[1]+=sum(len(v) for v in values.values() if type(v) is str)
            if budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT:raise ValueError('Query input resource limit exceeded')
            if any(c.field=='recorder' for c in columns):
                values['recorder']=manager._documents_by_id[key.document_id]._ref(key.record_id)
            rows.append(tuple(values[c.field] for c in columns))
            if len(rows)>MAX_ROWS:raise ValueError('Query input row limit exceeded')
    return rows
