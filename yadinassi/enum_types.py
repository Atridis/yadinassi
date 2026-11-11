"""Application-scoped enumeration identity, not native UUID serialization."""
from dataclasses import dataclass, field
from uuid import UUID
from .values import BSLObject, HostFunction


@dataclass(frozen=True, slots=True, eq=False)
class BSLEnumType(BSLObject):
    metadata_uuid: UUID
    name: str
    snapshot: object = field(repr=False)
    family: str = 'ref'

    def __post_init__(self):
        if type(self.metadata_uuid) is not UUID or type(self.name) is not str or not self.name or len(self.name)>256:
            raise TypeError('invalid enumeration type identity')
        if type(self.family) is not str or self.family not in ('ref','manager'): raise ValueError('unsupported enumeration type family')

    def __eq__(self,other):
        return (type(other) is BSLEnumType and self.snapshot is other.snapshot
                and self.metadata_uuid==other.metadata_uuid and self.family==other.family)

    def __hash__(self):
        return hash((id(self.snapshot),self.metadata_uuid,self.family))

    def __str__(self):
        if self.family=='manager': return 'Перечисление менеджер: '+self.name
        raise ValueError('enumeration reference type presentation awaits native evidence')


@dataclass(frozen=True, slots=True)
class BSLEnumReference(BSLObject):
    value_type: BSLEnumType
    reference_uuid: UUID
    metadata: object = field(compare=False,hash=False,repr=False)
    presentation: str | None = field(default=None,compare=False,hash=False,repr=False)

    def __post_init__(self):
        if type(self.value_type) is not BSLEnumType or self.value_type.family!='ref' or type(self.reference_uuid) is not UUID:
            raise TypeError('invalid enumeration reference')

    def is_empty(self):
        return self.reference_uuid.int==0

    def get_member(self,name):
        key=name.casefold()
        if key in ('ref','ссылка'): return self
        if key in ('isempty','пустая'): return HostFunction(name,self.is_empty)
        if key in ('metadata','метаданные'): return HostFunction(name,lambda:self.metadata)
        return super(BSLEnumReference,self).get_member(name)

    def __str__(self):
        if self.is_empty(): return ''
        # Native43035110558 ru_RU ignores the authored English synonym.
        # Russian synonyms and other UI languages remain outside this profile.
        if type(self.presentation) is str: return self.presentation
        raise ValueError('enumeration synonym presentation awaits native evidence')
