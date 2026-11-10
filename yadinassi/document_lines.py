"""Document section buffers and explicit snapshot-scoped type identities."""
from dataclasses import dataclass
from uuid import UUID
from .values import BSLObject
from .catalog_backend import BackendError

@dataclass(frozen=True,slots=True,eq=False)
class BSLDocumentLinesType(BSLObject):
    document_uuid: UUID
    section_uuid: UUID
    generated_type_uuid: UUID
    document_name: str
    section_name: str
    snapshot: object
    family: str

    def __post_init__(self):
        if (type(self.family) is not str or self.family not in ('section','row')
                or any(type(v) is not UUID or not v.int for v in (self.document_uuid,self.section_uuid,self.generated_type_uuid))
                or any(type(v) is not str or not 1<=len(v)<=256 for v in (self.document_name,self.section_name))):
            raise ValueError('invalid document tabular-section type')
    def __eq__(self,other):
        return (type(other) is BSLDocumentLinesType and self.snapshot is other.snapshot
                and self.document_uuid==other.document_uuid and self.section_uuid==other.section_uuid
                and self.generated_type_uuid==other.generated_type_uuid and self.family==other.family)
    def __hash__(self):
        return hash((id(self.snapshot),self.document_uuid,self.section_uuid,self.generated_type_uuid,self.family))
    def __str__(self):
        return ('Документ табличная часть: ' if self.family=='section' else 'Документ табличная часть строка: ')+self.section_name


@dataclass(frozen=True, slots=True, eq=False)
class BSLDocumentSectionType(BSLObject):
    """Local snapshot identity; deliberately has no invented generated GUID."""
    document_uuid: UUID
    section_uuid: UUID
    section_name: str
    snapshot: object
    family: str

    def __post_init__(self):
        if (type(self.family) is not str or self.family not in ('section','row')
                or any(type(value) is not UUID or not value.int for value in (self.document_uuid,self.section_uuid))
                or type(self.section_name) is not str or not 1 <= len(self.section_name) <= 128):
            raise ValueError('invalid local document section type')

    def __eq__(self, other):
        return (type(other) is BSLDocumentSectionType and self.snapshot is other.snapshot
                and (self.document_uuid,self.section_uuid,self.family) ==
                    (other.document_uuid,other.section_uuid,other.family))
    def __hash__(self): return hash((id(self.snapshot),self.document_uuid,self.section_uuid,self.family))
    def __str__(self):
        raise ValueError('local document section type presentation is unsupported')


from .catalog_sections import BSLCatalogSection, BSLCatalogSectionRow


class BSLDocumentLine(BSLCatalogSectionRow):
    pass


class BSLDocumentLines(BSLCatalogSection):
    _row_class = BSLDocumentLine

    def __init__(self, owner, schema, rows=()):
        super().__init__(owner,schema,rows)
        manager = owner._manager
        self._value_type = manager._section_type(schema,'section')
        self._row_type = manager._section_type(schema,'row')

    def _mutable(self):
        if self._owner._pending_write is not None: raise BackendError('uncertain_commit')
        if not self._owner._manager._writable(): raise BackendError('unsupported')
