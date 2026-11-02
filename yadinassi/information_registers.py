"""Neutral register type identity; SQLite register data operations unsupported."""
from dataclasses import dataclass, field
from uuid import UUID
from .values import BSLObject
from .catalog_backend import BackendError

@dataclass(frozen=True, slots=True, eq=False)
class BSLInformationRegisterType(BSLObject):
    metadata_uuid: UUID
    type_uuid: UUID
    name: str
    snapshot: object = field(repr=False)
    family: str

    def __post_init__(self):
        if (type(self.metadata_uuid) is not UUID or not self.metadata_uuid.int
                or type(self.type_uuid) is not UUID or not self.type_uuid.int
                or type(self.name) is not str or not 1 <= len(self.name) <= 256
                or type(self.family) is not str or self.family not in ('Manager', 'Selection')):
            raise ValueError('invalid information-register type')

    def __eq__(self, other):
        return (type(other) is BSLInformationRegisterType and self.snapshot is other.snapshot
                and self.metadata_uuid == other.metadata_uuid and self.type_uuid == other.type_uuid
                and self.family == other.family)

    def __hash__(self):
        return hash((id(self.snapshot), self.metadata_uuid, self.type_uuid, self.family))

    def __str__(self):
        return ('Регистр сведений менеджер: ' if self.family == 'Manager'
                else 'Регистр сведений выборка: ') + self.name


class BSLInformationRegisters(BSLObject):
    def __init__(self, metadata, context, catalogs, documents):
        self._documents=documents
    def get_member(self, name):
        raise BackendError('unsupported')
    get_index = get_member
    def type_by_name(self, name):
        if type(name) is str and name.partition('.')[0].casefold() in ('informationregistermanager','регистрсведенийменеджер','informationregisterselection','регистрсведенийвыборка'):
            raise BackendError('unsupported')
        return self._documents.type_by_name(name)
    def __str__(self):
        return 'Регистры сведений менеджер'

class BSLInformationRegisterManager(BSLObject):
    def __init__(self, *args, **kwargs):
        raise BackendError('unsupported')

class BSLInformationRegisterSelection(BSLInformationRegisterManager):
    pass
