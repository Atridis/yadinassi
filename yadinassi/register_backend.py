"""Logical independent, nonperiodic information-register persistence.

The dimension tuple is a typed key, not a catalog or document identity.
"""
from dataclasses import dataclass
from uuid import UUID
from .catalog_backend import FieldSchema


@dataclass(frozen=True, slots=True)
class InformationRegisterSchema:
    identity: UUID
    name: str
    dimensions: tuple[FieldSchema, ...]
    resources: tuple[FieldSchema, ...]
    attributes: tuple[FieldSchema, ...] = ()

    @property
    def fields(self): return self.dimensions + self.resources + self.attributes


@dataclass(frozen=True, slots=True)
class RegisterKey:
    database_id: UUID
    register_id: UUID
    dimensions: tuple


@dataclass(frozen=True, slots=True)
class RegisterRevision:
    database_id: UUID
    configuration_generation: int
    register_id: UUID
    key_digest: str
    token: str


@dataclass(frozen=True, slots=True)
class RegisterRecord:
    key: RegisterKey
    revision: RegisterRevision
    values: tuple  # Resources followed by attributes.


@dataclass(frozen=True, slots=True)
class RegisterDraft:
    key: RegisterKey
    values: tuple


@dataclass(frozen=True, slots=True)
class RegisterOutcome:
    revision: RegisterRevision
    deleted: bool


@dataclass(frozen=True, slots=True)
class RegisterScanRequest:
    page_size: int = 1000
    continuation: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterPage:
    rows: tuple[RegisterRecord, ...]
    continuation: str | None


@dataclass(frozen=True, slots=True)
class RegisterSetDraft:
    register_id: UUID
    filters: tuple  # (dimension UUID, logical scalar) pairs.
    rows: tuple[RegisterDraft, ...]
    replace: bool = True
    expected_snapshot: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterSetOutcome:
    register_id: UUID
    snapshot: str
    count: int


from typing import Protocol


class RegisterReadView(Protocol):
    database_id: UUID
    configuration_generation: int
    def registers(self) -> tuple[InformationRegisterSchema, ...]: ...
    def register_schema(self, identity: UUID) -> InformationRegisterSchema: ...
    def read_record(self, key: RegisterKey) -> RegisterRecord | None: ...
    def select_records(self, identity: UUID, filters: tuple = (), limit: int = 1000) -> tuple[RegisterRecord, ...]: ...
    def scan_register(self, identity: UUID, request: RegisterScanRequest) -> RegisterPage: ...
    def read_set(self, identity: UUID, filters: tuple = ()) -> tuple[tuple[RegisterRecord, ...], str]: ...
    def close(self) -> None: ...
