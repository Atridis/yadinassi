"""Immutable host views of the existing bounded read-only catalog API.

No form metadata, business object, BSL API, authentication or write semantics
are introduced. An offline source remains the caller's responsibility.
"""
from dataclasses import dataclass
import os
import stat

from ..catalogs import BSLCatalogs, BSLCatalogSelection, _bound_card
from ..catalog_types import BSLCatalogReference
from ..database_context import FileDBContext
from ..metadata import BSLCatalogMetadataCollection
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
    """One host-selected offline path; renderer input can never select a path.

    Descriptor checks are inherited from FileDBContext. Session stat stamps also
    reject detectable replacement/modification between reads, but are NOT a lock,
    transaction or proof that a live source is consistent. No file is written.
    """
    def __init__(self, context):
        if type(context) is not FileDBContext:
            raise TypeError('catalog UI requires FileDBContext')
        self._context = context
        self._metadata = BSLCatalogMetadataCollection(context)
        self._catalogs = BSLCatalogs(self._metadata, context)
        self._inventory = None
        self._source_stamp = None

    def _stamp(self):
        if self._context._unsupported:
            # Preserve FileDBContext's pre-I/O spelling boundary, notably UNC
            # and device-like paths. Even stat must not touch such a target.
            raise UIError('catalog_unavailable')
        try:
            value = os.stat(os.path.join(self._context.directory, '1Cv8.1CD'))
            if not stat.S_ISREG(value.st_mode):
                raise UIError('catalog_unavailable')
        except OSError:
            raise UIError('catalog_unavailable') from None
        return (value.st_dev, value.st_ino, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns)

    def check_source(self):
        current = self._stamp()
        if self._source_stamp is not None and current != self._source_stamp:
            raise UIError('catalog_unavailable')
        return current

    def inventory(self):
        before = self.check_source()
        if self._inventory is None:
            # Pin even a failed initial read: a later replacement must never
            # reuse the metadata collection's earlier lazy cache.
            self._source_stamp = before
            try:
                items = self._metadata._snapshot()
                if len(items) > 128:
                    raise UIError('message_limit')
                inventory = tuple(CatalogInfo(uuid_text(item._metadata_uuid, nonzero=True),
                                              bounded_text(item._name, 1024))
                                  for item in items.values())
                if self._stamp() != before:
                    raise UIError('catalog_unavailable')
            except (ValueError, TypeError) as error:
                if type(error) is UIError:
                    raise
                raise UIError('metadata_unavailable') from None
            self._inventory, self._source_stamp = inventory, before
        return self._inventory

    def load(self, identity):
        uuid_text(identity, nonzero=True)
        info = next((item for item in self.inventory() if item.identity == identity), None)
        if info is None:
            raise UIError('catalog_not_found')
        try:
            manager = self._catalogs.get_index(info.name)
            result = manager._rows()
            # Reuse the BSL reader's ordering admission, never physical row order
            # or a new UI-specific approximation to native collation.
            selection = BSLCatalogSelection(manager, result)
            fields = (CatalogField('Code', 'number' if result.binding.code_type == 0 else 'string',
                                   (result.binding.code_length,)),
                      CatalogField('Description', 'string', (result.binding.description_length,)),
                      CatalogField('DeletionMark', 'boolean', ()))
            fields += tuple(CatalogField(bounded_text(item.name, 1024), _bound_card(item).kind,
                                         item.qualifiers, item.reference_catalog_uuid)
                            for item in result.binding.attributes)
            cards = []
            for row in selection._rows:
                logical = manager._fields(result, row)
                values = tuple(self._value(logical[field.name.casefold()]) for field in fields)
                # Validate the narrow value envelope before retaining a snapshot.
                for value in values:
                    encode_value(value)
                cards.append(CatalogCardSnapshot(CatalogRef(identity, str(row.reference_uuid)),
                                                  info.name, fields, values))
            self.check_source()
            return CatalogView(info, tuple(cards))
        except (ValueError, TypeError, KeyError) as error:
            if type(error) is UIError:
                raise
            raise UIError('catalog_unavailable') from None

    @staticmethod
    def _value(value):
        if type(value) is BSLCatalogReference:
            return CatalogRef(str(value.value_type.metadata_uuid), str(value.reference_uuid))
        return value

    @staticmethod
    def capabilities():
        return {'mode': 'offline-read-only', 'canWrite': False, 'canEdit': False,
                'formRuntime': False, 'actual1CForms': False, 'maxPage': MAX_PAGE,
                'rowSupport': 'checked-on-selection', 'consistency': 'caller-owned-offline-copy'}

    def commit(self, *args, **kwargs):
        # Intentionally no success stub, sidecar, overlay or file write fallback.
        raise UIError('write_unsupported')
