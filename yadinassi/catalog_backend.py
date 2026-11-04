"""Logical catalog persistence contract; no SQL, paths or engine handles.

Backend revisions and database identities are internal, not native DataVersion.
Only an admitted backend can provide write capabilities. Values use exact Python
str/Decimal/bool/datetime or CatalogKey; runtime adapters own BSL conversion.
Writes apply bounded String/Decimal metadata qualifiers before canonical intent
encoding; reads validate persisted values strictly without conversion.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class BackendError(ValueError):
    """Closed public category; never raw SQL or filesystem exception text."""
    def __init__(self, code: str):
        if type(code) is not str or code not in {
            'unsupported', 'invalid_input', 'not_found', 'conflict', 'busy',
            'closed', 'integrity', 'storage_error', 'uncertain_commit',
            'schema_changed', 'duplicate_code', 'duplicate_identity',
        }:
            raise ValueError('invalid backend error')
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class FieldSchema:
    identity: UUID
    name: str
    kind: str
    qualifiers: tuple = ()
    target_catalog_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TabularSectionSchema:
    identity: UUID
    name: str
    fields: tuple[FieldSchema, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogSchema:
    identity: UUID
    name: str
    code_length: int
    description_length: int
    fields: tuple[FieldSchema, ...] = ()
    tabular_sections: tuple[TabularSectionSchema, ...] = ()


@dataclass(frozen=True, slots=True)
class TabularRow:
    """Backend row identity, scoped to its owner and section; not a line number."""
    identity: UUID
    values: tuple


@dataclass(frozen=True, slots=True)
class TabularSectionRows:
    section_id: UUID
    rows: tuple[TabularRow, ...]


@dataclass(frozen=True, slots=True)
class CatalogKey:
    database_id: UUID
    catalog_id: UUID
    record_id: UUID


@dataclass(frozen=True, slots=True)
class Revision:
    database_id: UUID
    configuration_generation: int
    catalog_id: UUID
    record_id: UUID
    token: str


@dataclass(frozen=True, slots=True)
class CatalogCard:
    key: CatalogKey
    revision: Revision
    code: str
    description: str
    deletion_mark: bool
    values: tuple
    tabular_sections: tuple[TabularSectionRows, ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogDraft:
    key: CatalogKey
    code: str
    description: str
    deletion_mark: bool
    values: tuple
    # None preserves existing contents. An explicit tuple replaces all sections;
    # omitted sections, including all sections when (), become empty.
    tabular_sections: tuple[TabularSectionRows, ...] | None = None


@dataclass(frozen=True, slots=True)
class CatalogSelection:
    """Initial finite order, no implicit native collation or arbitrary query."""
    limit: int = 1000
    order: str = 'code_then_identity'
    # Future bounded typed filters/page cursors require explicit capabilities.


@dataclass(frozen=True, slots=True)
class CatalogComparison:
    field: str | UUID
    operator: str
    value: object


@dataclass(frozen=True, slots=True)
class CatalogPredicate:
    kind: str
    terms: tuple


@dataclass(frozen=True, slots=True)
class CatalogOrder:
    field: str | UUID
    descending: bool = False


@dataclass(frozen=True, slots=True)
class CatalogScanRequest:
    """Typed object scan; no SQL text or connection-shaped authority.

    Continue on the same open read view with the same request. Each view admits
    one active traversal; starting another invalidates its previous continuation.
    Equal order keys use record identity as a stable backend-only tie breaker.
    String policy is explicit: codepoint or casefold_v1. Neither claims full
    native regional collation. Exact lookup keeps the codepoint default.
    """
    predicate: CatalogComparison | CatalogPredicate | None = None
    order: tuple[CatalogOrder, ...] = ()
    page_size: int = 1000
    continuation: str | None = None
    string_comparison: str = 'codepoint'


@dataclass(frozen=True, slots=True)
class CatalogPage:
    cards: tuple[CatalogCard, ...]
    continuation: str | None


@dataclass(frozen=True, slots=True)
class Capabilities:
    catalog_read: bool = True
    catalog_create: bool = False
    catalog_update: bool = False
    atomic_transactions: bool = False
    read_consistency: str = 'transaction_snapshot'
    catalog_tabular_sections: bool = False


class CatalogReadView(Protocol):
    database_id: UUID
    configuration_generation: int
    def catalogs(self) -> tuple[CatalogSchema, ...]: ...
    def catalog_schema(self, catalog_id: UUID) -> CatalogSchema: ...
    def select_catalog(self, catalog_id: UUID, request: CatalogSelection) -> tuple[CatalogCard, ...]: ...
    def scan_catalog(self, catalog_id: UUID, request: CatalogScanRequest) -> CatalogPage: ...
    def read_catalog(self, key: CatalogKey) -> CatalogCard | None: ...
    def close(self) -> None: ...


class CatalogWriteTransaction(CatalogReadView, Protocol):
    def create(self, draft: CatalogDraft) -> None: ...
    def update(self, draft: CatalogDraft, expected_revision: Revision) -> None: ...
    def commit(self) -> tuple[Revision, ...]: ...
    def rollback(self) -> None: ...


class CatalogBackend(Protocol):
    def capabilities(self) -> Capabilities: ...
    def begin_read(self) -> CatalogReadView: ...
    def begin_write(self, operation_id: UUID) -> CatalogWriteTransaction: ...
    def resolve_write(self, operation_id: UUID, draft: CatalogDraft, expected_revision: Revision | None = None) -> Revision | None: ...
    def close(self) -> None: ...
