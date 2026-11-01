"""Read-only document identities scoped to one interpreter metadata snapshot.

Metadata UUID identifies the document; record UUID identifies an item in it. No
native type GUID or codec representation is inferred from either identifier.
Cross-snapshot identity/transport is deliberately outside this offline profile.
"""
from dataclasses import dataclass, field
from uuid import UUID

from .unique_identifiers import BSLUUID
from .values import BSLObject, HostFunction


@dataclass(frozen=True, slots=True, eq=False)
class BSLDocumentType(BSLObject):
    metadata_uuid: UUID
    name: str
    snapshot: object = field(repr=False)
    family: str = "ref"

    def __post_init__(self):
        if type(self.family) is not str or self.family not in ("ref", "manager", "selection"):
            raise ValueError("unsupported document type family")
        if type(self.metadata_uuid) is not UUID:
            raise TypeError('document metadata identity requires UUID')
        if type(self.name) is not str or not self.name or len(self.name) > 256:
            raise ValueError('document type requires a bounded metadata name')

    def __eq__(self, other):
        return (type(other) is BSLDocumentType and self.snapshot is other.snapshot
                and self.metadata_uuid == other.metadata_uuid and self.family == other.family)

    def __hash__(self):
        return hash((id(self.snapshot), self.metadata_uuid, self.family))

    def __str__(self):
        # Native41256261065: presentation is not the Type lookup name.
        return {'ref': self.name, 'manager': 'Документ менеджер: ' + self.name,
                'selection': 'Документ выборка: ' + self.name}[self.family]


@dataclass(frozen=True, slots=True)
class BSLDocumentReference(BSLObject):
    value_type: BSLDocumentType
    reference_uuid: UUID
    metadata: object = field(default=None, compare=False, hash=False, repr=False)
    read_member: object = field(default=None, compare=False, hash=False, repr=False)

    def __post_init__(self):
        if type(self.value_type) is not BSLDocumentType or type(self.reference_uuid) is not UUID:
            raise TypeError('document reference requires document type and record UUID')
        if self.value_type.family != 'ref':
            raise TypeError('document reference requires reference type family')
        if self.read_member is not None and not callable(self.read_member):
            raise TypeError('document reference reader must be callable')

    def is_empty(self):
        return self.reference_uuid.int == 0

    def unique_identifier(self):
        return BSLUUID(str(self.reference_uuid))

    def get_metadata(self):
        if self.metadata is None:
            raise ValueError('document reference metadata is unavailable')
        return self.metadata

    def get_member(self, name):
        key = name.casefold()
        if key in ('ref', 'ссылка'):
            return self
        if key in ('isempty', 'пустая'):
            return HostFunction(name, self.is_empty)
        if key in ('uuid', 'уникальныйидентификатор'):
            return HostFunction(name, self.unique_identifier)
        if key in ('metadata', 'метаданные'):
            return HostFunction(name, self.get_metadata)
        if self.read_member is not None:
            return self.read_member(self, name)
        return super(BSLDocumentReference, self).get_member(name)

    def __str__(self):
        if self.is_empty():
            return ''
        # !todo Native document presentation depends on configuration; measure
        # before exposing anything, never leak a Python repr or invent a format.
        raise ValueError('document reference presentation is unsupported')
