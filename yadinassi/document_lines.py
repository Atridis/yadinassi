"""Neutral tabular-section type identity; no SQLite document storage adapter."""
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


class BSLDocumentLines(BSLObject):
    def __init__(self, *args, **kwargs):
        raise BackendError('unsupported')

class BSLDocumentLine(BSLDocumentLines):
    pass
