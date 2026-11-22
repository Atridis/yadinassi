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
            'schema_changed', 'duplicate_code', 'duplicate_identity', 'code_exhausted',
            'duplicate_number', 'number_exhausted',
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
    target_enum_id: UUID | None = None


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
    numbering: str = 'explicit'
    hierarchy: str = 'none'  # none or groups_v1; appended for flat-port compatibility.


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
    parent: CatalogKey | None = None
    is_folder: bool = False


@dataclass(frozen=True, slots=True)
class CatalogScalarRow:
    """Validated owner scalars, deliberately not a partially loaded card."""
    key: CatalogKey
    revision: Revision
    code: str
    description: str
    deletion_mark: bool
    values: tuple
    parent: CatalogKey | None = None
    is_folder: bool = False


@dataclass(frozen=True, slots=True)
class CatalogValueRow:
    key: CatalogKey
    values: tuple


@dataclass(frozen=True, slots=True)
class CatalogValuePage:
    rows: tuple[CatalogValueRow, ...]
    continuation: str | None


@dataclass(frozen=True, slots=True)
class _TabularSectionChanges:
    """Internal SQLite edit buffer intent: replace only explicitly dirty sections."""
    sections: tuple[TabularSectionRows, ...]


@dataclass(frozen=True, slots=True)
class CatalogDraft:
    key: CatalogKey
    code: str
    description: str
    deletion_mark: bool
    values: tuple
    # None preserves existing contents. An explicit tuple replaces all sections;
    # omitted sections, including all sections when (), become empty.
    tabular_sections: tuple[TabularSectionRows, ...] | _TabularSectionChanges | None = None
    auto_number: bool = False
    parent: CatalogKey | None = None
    is_folder: bool = False


@dataclass(frozen=True, slots=True)
class CatalogWriteOutcome:
    revision: Revision
    code: str


@dataclass(frozen=True, slots=True)
class CatalogWriteRequest:
    """One requested catalog write in transaction order.

    None means create; updates retain the exact submitted expected revision.
    This is an intent, not permission to replay or a transaction executor.
    """
    draft: CatalogDraft
    expected_revision: Revision | None = None


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
class CatalogFieldComparison:
    """A comparison between two exact fields of the same physical source."""
    field: str | UUID
    operator: str
    other_field: str | UUID


def _point_predicate(predicate, keys):
    """Prove one positive key equality necessary for the complete predicate.

    A true conjunction requires every child; a true disjunction requires only
    one. Keep only equalities common to all disjuncts. SQL UNKNOWN, like a
    false result, is not selected. Never extract or discard a filter.
    """
    from yadinassi.db.document.document_backend import DocumentKey

    def atom(term):
        if type(term) is CatalogFieldComparison:
            return set()
        if type(term) is not CatalogComparison:
            return None
        if (type(term.field) is not str or term.field not in keys
                or type(term.operator) is not str or term.operator != 'eq'):
            return set()
        value = term.value
        if term.field == 'code' and type(value) is str:
            return {(term.field,value)}
        if term.field == 'ref':
            if type(value) is CatalogKey:
                identity = value.database_id,value.catalog_id,value.record_id
            elif type(value) is DocumentKey:
                identity = value.database_id,value.document_id,value.record_id
            else:
                return set()
            if all(type(item) is UUID and type(item.int) is int for item in identity):
                return {(term.field,type(value),*(item.int for item in identity))}
        return set()

    # Do not impose extra expression limits on the proof. The calling provider
    # validates supported physical clauses separately. A raw cyclic DTO cannot
    # be a predicate, even if one of its reachable leaves has a point.
    pending = [(predicate,False)]
    active, proved = set(), {}
    while pending:
        term, exit_node = pending.pop()
        identity = id(term)
        if identity in proved:
            continue
        if type(term) is not CatalogPredicate:
            result = atom(term)
            if result is None: return False
            proved[identity] = result
        elif exit_node:
            children = iter(term.terms)
            required = proved[id(next(children))].copy()
            combine = required.update if term.kind == 'and' else required.intersection_update
            for child in children: combine(proved[id(child)])
            active.remove(identity)
            proved[identity] = required
        else:
            if (identity in active or type(term.kind) is not str or term.kind not in ('and','or')
                    or type(term.terms) is not tuple or not term.terms):
                return False
            active.add(identity)
            pending.append((term,True))
            pending.extend((child,False) for child in reversed(term.terms))
    return bool(proved[id(predicate)])


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

    The section scan uses the same request shape. Its only standard field is
    'ref' (the owner key); UUID fields belong to the chosen section. Its source
    identity also includes the section UUID. Catalog and section scans share
    the one active traversal, so starting either invalidates the other.
    """
    predicate: CatalogComparison | CatalogPredicate | None = None
    order: tuple[CatalogOrder, ...] = ()
    page_size: int = 1000
    continuation: str | None = None
    string_comparison: str = 'codepoint'


@dataclass(frozen=True, slots=True)
class CatalogAggregateRequest:
    """Closed logical aggregate capability; never SQL or physical identifiers.

    Version 1 permits only COUNT(*) of one complete catalog. Backends may return
    None to decline this shape; accepted results prove complete row validation
    and uniqueness of normalized logical record identities in the same view.
    """
    operation: str = 'count_all_v1'


@dataclass(frozen=True, slots=True)
class CatalogAggregateResult:
    count: int


@dataclass(frozen=True, slots=True)
class CatalogNumericAggregateRequest:
    """Ordered (operation, logical field UUID) pairs; never SQL fragments."""
    operations: tuple


@dataclass(frozen=True, slots=True)
class CatalogNumericAggregateResult:
    count: int
    values: tuple


@dataclass(frozen=True, slots=True)
class CatalogPage:
    cards: tuple[CatalogCard, ...]
    continuation: str | None


@dataclass(frozen=True, slots=True)
class CatalogSectionRecord:
    """Detached section row; identity is (owner, section_id, row.identity).

    The owner key is the section query's Ref. Internal row UUIDs are not BSL
    references, and this result deliberately exposes no native line number.
    """
    owner: CatalogKey
    section_id: UUID
    row: TabularRow


@dataclass(frozen=True, slots=True)
class CatalogSectionPage:
    rows: tuple[CatalogSectionRecord, ...]
    continuation: str | None


@dataclass(frozen=True, slots=True)
class Capabilities:
    catalog_read: bool = True
    catalog_create: bool = False
    catalog_update: bool = False
    atomic_transactions: bool = False
    read_consistency: str = 'transaction_snapshot'
    catalog_tabular_sections: bool = False
    catalog_write_outcomes: bool = False
    document_read: bool = False
    document_create: bool = False
    document_update: bool = False
    document_tabular_sections: bool = False
    register_read: bool = False
    register_write: bool = False


class CatalogReadView(Protocol):
    database_id: UUID
    configuration_generation: int
    def catalogs(self) -> tuple[CatalogSchema, ...]: ...
    def catalog_schema(self, catalog_id: UUID) -> CatalogSchema: ...
    def select_catalog(self, catalog_id: UUID, request: CatalogSelection) -> tuple[CatalogCard, ...]: ...
    def scan_catalog(self, catalog_id: UUID, request: CatalogScanRequest) -> CatalogPage: ...
    def scan_catalog_section(self, catalog_id: UUID, section_id: UUID, request: CatalogScanRequest) -> CatalogSectionPage: ...
    def scan_catalog_values(self, catalog_id: UUID, request: CatalogScanRequest, fields: tuple[str | UUID, ...]) -> CatalogValuePage: ...
    def read_catalog(self, key: CatalogKey) -> CatalogCard | None: ...
    def close(self) -> None: ...


class CatalogWriteTransaction(CatalogReadView, Protocol):
    def create(self, draft: CatalogDraft) -> None: ...
    def update(self, draft: CatalogDraft, expected_revision: Revision) -> None: ...
    def commit(self) -> tuple[Revision, ...]: ...
    def commit_outcomes(self) -> tuple[CatalogWriteOutcome, ...]: ...
    def rollback(self) -> None: ...


class CatalogBackend(Protocol):
    def read_catalog_editor_source(self, catalog_id: UUID, *, expected=None):
        """Optional coherent source-pair capability; never synthesize two reads."""
        raise BackendError('unsupported')

    def catalog_write_preparation(self, catalog_id: UUID, *, expected=None) -> str | None:
        """Optional bounded host write policy; ordinary adapters have none."""
        return None

    def capabilities(self) -> Capabilities: ...
    def begin_read(self) -> CatalogReadView: ...
    def begin_write(self, operation_id: UUID) -> CatalogWriteTransaction: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ConfigurationSourceIdentity:
    database_id: UUID
    configuration_id: UUID
    generation: int
    manifest_sha256: str
    catalog_id: UUID
    form_id: UUID


@dataclass(frozen=True, slots=True)
class CatalogFormSource:
    identity: ConfigurationSourceIdentity
    catalog_name: str
    form_name: str
    default_object_form: str
    catalog_path: str
    form_path: str
    definition_path: str
    module_path: str
    configuration_xml: bytes
    catalog_xml: bytes
    form_xml: bytes
    definition_xml: bytes
    module_source: bytes
    module_present: bool

# Definition-time ABI for the direct live movement ownership traversal.
_DIRECT_MOVEMENT_PARENT_CLASSES=tuple((cls,cls.__mro__,tuple(vars(cls).items()))
    for cls in dict.fromkeys(base for receiver in (FieldSchema,) for base in receiver.__mro__))

_DIRECT_LIVE_METADATA_SCHEMA_ABI=tuple((cls,cls.__mro__,tuple(vars(cls).items())) for cls in (FieldSchema,TabularSectionSchema,CatalogSchema,))
