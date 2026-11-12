"""Immutable UI projections of the logical catalog backend port.

No SQL, filesystem paths, storage bindings, BSL handlers or write route.
The host supplies an owned backend; this repository owns its read-view lifetime.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ..catalog_backend import (BackendError, Capabilities, CatalogCard, CatalogKey,
                               CatalogSchema, CatalogSelection, FieldSchema, Revision)
from ..dates import BSLDate, TICKS_PER_SECOND
from .protocol import CatalogRef, MAX_PAGE, UIError, bounded_text, encode_value, uuid_text


@dataclass(frozen=True, slots=True)
class CatalogInfo:
    identity: str
    name: str


@dataclass(frozen=True, slots=True)
class CatalogField:
    name: str
    kind: str
    qualifiers: tuple
    target_catalog: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogCardSnapshot:
    reference: CatalogRef
    catalog_name: str
    fields: tuple[CatalogField, ...]
    values: tuple[object, ...]

    def value(self, name):
        if type(name) is not str:
            raise UIError('invalid_value')
        matches = [value for field, value in zip(self.fields, self.values)
                   if field.name.casefold() == name.casefold()]
        if len(matches) != 1:
            raise UIError('reference_field')
        return matches[0]

    def wire(self):
        return {'reference': encode_value(self.reference), 'catalogName': self.catalog_name,
                'fields': [{'name': field.name, 'kind': field.kind,
                            'qualifiers': list(field.qualifiers),
                            'targetCatalog': field.target_catalog, 'readOnly': True,
                            'value': encode_value(value)}
                           for field, value in zip(self.fields, self.values)]}


@dataclass(frozen=True, slots=True)
class CatalogView:
    catalog: CatalogInfo
    cards: tuple[CatalogCardSnapshot, ...]

    def card(self, reference):
        if type(reference) is not CatalogRef or reference.catalog != self.catalog.identity:
            raise UIError('catalog_identity')
        if reference.record == '00000000-0000-0000-0000-000000000000':
            raise UIError('empty_reference')
        matches = [card for card in self.cards if card.reference == reference]
        if len(matches) != 1:
            # Unlike BSL reference scalar defaults, a UI card must be a real row.
            raise UIError('record_not_found')
        return matches[0]

    def page(self, offset=0, limit=8):
        if (type(offset) is not int or type(limit) is not int or
                not 0 <= offset <= len(self.cards) or not 1 <= limit <= MAX_PAGE):
            raise UIError('page')
        return {'catalog': self.catalog.identity, 'catalogName': self.catalog.name,
                'offset': offset, 'limit': limit, 'total': len(self.cards),
                'rows': [{'reference': encode_value(card.reference),
                          'code': encode_value(card.values[0]),
                          'description': encode_value(card.values[1]),
                          'deletionMark': encode_value(card.values[2])}
                         for card in self.cards[offset:offset + limit]]}


class CatalogRepository:
    """Host-owned logical backend and one pinned read view; always read-only UI.

    The backend chooses its storage/transport. This facade never opens a database,
    sends SQL or exposes backend revisions. Closing it releases the owned backend.
    """
    def __init__(self, backend, *, own_backend=True):
        if not all(callable(getattr(backend, name, None))
                   for name in ('capabilities', 'begin_read', 'close')):
            raise TypeError('catalog UI requires logical catalog backend')
        if type(own_backend) is not bool:
            raise TypeError('catalog UI ownership requires Boolean')
        self._own_backend = own_backend
        self._backend = backend
        self._view = None
        self._identity = None
        self._schemas = None
        self._closed = False

    @staticmethod
    def _uuid(value, *, empty=False):
        if type(value) is not UUID or not empty and not value.int:
            raise UIError('catalog_identity')
        return str(value)

    def _read(self):
        if self._closed:
            raise UIError('catalog_unavailable')
        try:
            capability = self._backend.capabilities()
            if (type(capability) is not Capabilities or capability.catalog_read is not True
                    or capability.read_consistency != 'transaction_snapshot'):
                raise UIError('catalog_unavailable')
            if self._view is None:
                self._view = self._backend.begin_read()
                identity = (self._view.database_id, self._view.configuration_generation)
                self._uuid(identity[0])
                if type(identity[1]) is not int or identity[1] <= 0:
                    raise UIError('metadata_unavailable')
                self._identity = identity
            if (self._view.database_id, self._view.configuration_generation) != self._identity:
                raise UIError('catalog_unavailable')
            return self._view
        except BackendError:
            raise UIError('catalog_unavailable') from None

    def check_source(self):
        """Validate the pinned view, not filesystem stat or latest-write visibility."""
        view = self._read()
        try:
            schemas = view.catalogs()  # Also checks the declared view lifetime.
            if type(schemas) is not tuple or len(schemas) > 128:
                raise UIError('message_limit')
            if self._schemas is not None and schemas != self._schemas:
                raise UIError('metadata_unavailable')
            return schemas
        except BackendError:
            raise UIError('catalog_unavailable') from None

    def inventory(self):
        schemas = self.check_source()
        inventory, names, identities = [], set(), set()
        for schema in schemas:
            if type(schema) is not CatalogSchema:
                raise UIError('metadata_unavailable')
            identity = self._uuid(schema.identity)
            name = bounded_text(schema.name, 1024)
            if not name or name.casefold() in names or identity in identities:
                raise UIError('metadata_unavailable')
            names.add(name.casefold()); identities.add(identity)
            inventory.append(CatalogInfo(identity, name))
        self._schemas = schemas
        return tuple(inventory)

    @staticmethod
    def _summary_fields(schema):
        if (type(schema.fields) is not tuple or len(schema.fields) > 64 or
                any(type(n) is not int or not 0 <= n <= 1024
                    for n in (schema.code_length, schema.description_length))):
            raise UIError('metadata_unavailable')
        return (CatalogField('Code', 'string', (schema.code_length,)),
                CatalogField('Description', 'string', (schema.description_length,)),
                CatalogField('DeletionMark', 'boolean', ()))

    def _fields(self, schema):
        fields = list(self._summary_fields(schema))
        names, identities = {'code', 'description', 'deletionmark', 'ref'}, set()
        catalog_ids = {item.identity for item in self._schemas}
        for field in schema.fields:
            if type(field) is not FieldSchema:
                raise UIError('metadata_unavailable')
            identity = self._uuid(field.identity)
            name = bounded_text(field.name, 1024)
            if (not name or identity in identities or name.casefold() in names
                    or field.kind not in ('string', 'number', 'boolean', 'datetime', 'catalog_ref')
                    or type(field.qualifiers) is not tuple or len(field.qualifiers) > 4):
                raise UIError('metadata_unavailable')
            for value in field.qualifiers:
                if type(value) is str:
                    bounded_text(value, 1024)
                elif type(value) is not int or not 0 <= value <= 4096:
                    raise UIError('metadata_unavailable')
            names.add(name.casefold()); identities.add(identity)
            target = None
            if field.kind == 'catalog_ref':
                target = self._uuid(field.target_catalog_id)
                if field.target_catalog_id not in catalog_ids:
                    raise UIError('metadata_unavailable')
            elif field.target_catalog_id is not None:
                raise UIError('metadata_unavailable')
            fields.append(CatalogField(name, field.kind, field.qualifiers, target))
        return tuple(fields)

    def _value(self, value, field):
        kind = field.kind
        if kind == 'catalog_ref':
            if (type(value) is not CatalogKey or value.database_id != self._identity[0]
                    or value.catalog_id != field.target_catalog_id):
                raise UIError('catalog_identity')
            value = CatalogRef(self._uuid(value.catalog_id), self._uuid(value.record_id, empty=True))
        elif kind == 'datetime':
            if type(value) is not datetime or value.tzinfo is not None or value.microsecond:
                raise UIError('unsupported_value')
            delta = value - datetime(1, 1, 1)
            value = BSLDate((delta.days * 86400 + delta.seconds) * TICKS_PER_SECOND)
        elif type(value) is not {'string': str, 'number': Decimal, 'boolean': bool}.get(kind):
            raise UIError('unsupported_value')
        encode_value(value)
        return value

    def load(self, identity, *, summary_only=False):
        if type(summary_only) is not bool: raise TypeError("explicit summary projection required")
        uuid_text(identity, nonzero=True)
        info = next((item for item in self.inventory() if item.identity == identity), None)
        if info is None:
            raise UIError('catalog_not_found')
        try:
            schema = self._view.catalog_schema(UUID(identity))
            if (type(schema) is not CatalogSchema or schema.identity != UUID(identity)
                    or schema not in self._schemas):
                raise UIError('metadata_unavailable')
            fields = self._summary_fields(schema) if summary_only else self._fields(schema)
            # The port refuses overflow rather than returning a misleading total.
            rows = self._view.select_catalog(schema.identity, CatalogSelection(limit=1000))
            if type(rows) is not tuple or len(rows) > 1000:
                raise UIError('message_limit')
            cards, seen = [], set()
            for row in rows:
                if (type(row) is not CatalogCard or type(row.key) is not CatalogKey
                        or row.key.database_id != self._identity[0]
                        or row.key.catalog_id != schema.identity):
                    raise UIError('catalog_identity')
                record = self._uuid(row.key.record_id)
                if record in seen or type(row.values) is not tuple or len(row.values) != len(schema.fields):
                    raise UIError('catalog_unavailable')
                seen.add(record)
                revision = row.revision
                if (type(revision) is not Revision or revision.database_id != row.key.database_id
                        or revision.configuration_generation != self._identity[1]
                        or revision.catalog_id != row.key.catalog_id or revision.record_id != row.key.record_id):
                    raise UIError('catalog_identity')
                if type(row.code) is not str or type(row.description) is not str or type(row.deletion_mark) is not bool:
                    raise UIError('unsupported_value')
                values = (row.code, row.description, row.deletion_mark) + (() if summary_only else tuple(
                    self._value(value, field) for field, value in zip(schema.fields, row.values)))
                for value in values:
                    encode_value(value)
                cards.append(CatalogCardSnapshot(CatalogRef(identity, record), info.name, fields, values))
            self.check_source()
            return CatalogView(info, tuple(cards))
        except BackendError as error:
            raise UIError('catalog_not_found' if error.code == 'not_found' else 'catalog_unavailable') from None

    def capabilities(self):
        return {'mode': 'read-only', 'canWrite': False, 'canEdit': False,
                'formRuntime': False, 'actual1CForms': False, 'maxPage': MAX_PAGE,
                'rowSupport': 'checked-on-selection', 'consistency': 'transaction-snapshot'}

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                if self._view is not None:
                    self._view.close()
            finally:
                if self._own_backend:
                    self._backend.close()

    def commit(self, *args, **kwargs):
        raise UIError('write_unsupported')
