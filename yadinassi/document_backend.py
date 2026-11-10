"""Logical non-posting document persistence, independent of catalog identities.

Revisions are private optimistic-lock tokens, not native DataVersion. A write
atomically replaces one document and its explicitly supplied tabular sections.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .catalog_backend import (FieldSchema, TabularSectionSchema, TabularSectionRows,
                              CatalogSchema, CatalogScanRequest, CatalogValuePage, CatalogSectionPage)


@dataclass(frozen=True, slots=True)
class DocumentSchema:
    identity: UUID
    name: str
    number_length: int
    fields: tuple[FieldSchema, ...] = ()
    tabular_sections: tuple[TabularSectionSchema, ...] = ()
    numbering: str = 'explicit'


@dataclass(frozen=True, slots=True)
class DocumentKey:
    database_id: UUID
    document_id: UUID
    record_id: UUID


@dataclass(frozen=True, slots=True)
class DocumentRevision:
    database_id: UUID
    configuration_generation: int
    document_id: UUID
    record_id: UUID
    token: str


@dataclass(frozen=True, slots=True)
class DocumentCard:
    key: DocumentKey
    revision: DocumentRevision
    number: str
    date: datetime
    deletion_mark: bool
    values: tuple
    tabular_sections: tuple[TabularSectionRows, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentDraft:
    key: DocumentKey
    number: str
    date: datetime
    deletion_mark: bool
    values: tuple
    # None preserves sections on updates; a tuple replaces all sections.
    tabular_sections: tuple[TabularSectionRows, ...] | None = None
    auto_number: bool = False


@dataclass(frozen=True, slots=True)
class DocumentWriteOutcome:
    revision: DocumentRevision
    number: str


@dataclass(frozen=True, slots=True)
class DocumentSelection:
    start: datetime | None = None
    end: datetime | None = None
    limit: int = 1000


@dataclass(frozen=True, slots=True)
class DocumentScanRequest:
    """Bounded report scan; continuation belongs to one live read snapshot."""
    page_size: int = 1000
    continuation: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentPage:
    rows: tuple[DocumentCard, ...]
    continuation: str | None


class DocumentReadView(Protocol):
    database_id: UUID
    configuration_generation: int
    def documents(self) -> tuple[DocumentSchema, ...]: ...
    def document_schema(self, document_id: UUID) -> DocumentSchema: ...
    def read_document(self, key: DocumentKey) -> DocumentCard | None: ...
    def find_document_number(self, document_id: UUID, number: str) -> DocumentKey | None: ...
    def select_documents(self, document_id: UUID, request: DocumentSelection) -> tuple[DocumentCard, ...]: ...
    def scan_documents(self, document_id: UUID, request: DocumentScanRequest) -> DocumentPage: ...
    def close(self) -> None: ...


class QueryReadView(DocumentReadView, Protocol):
    """Catalog and document sources sharing one pinned query snapshot."""
    def catalog_schema(self, catalog_id: UUID) -> CatalogSchema: ...
    def scan_catalog_values(self, catalog_id: UUID, request: CatalogScanRequest, fields: tuple[str | UUID, ...]) -> CatalogValuePage: ...
    def scan_catalog_section(self, catalog_id: UUID, section_id: UUID, request: CatalogScanRequest) -> CatalogSectionPage: ...


class DocumentWriteView(DocumentReadView, Protocol):
    def create(self, draft: DocumentDraft) -> None: ...
    def update(self, draft: DocumentDraft, expected: DocumentRevision) -> None: ...
    def commit(self) -> DocumentWriteOutcome: ...
    def rollback(self) -> None: ...
