"""Bounded Document CONFIG projection measured in native 41256261065.

No fixture identities, XML, physical offsets or host observations are inputs.
Document collection and attribute routes are separate from Catalog routes.
"""
from dataclasses import dataclass

from . import config_catalog_attributes as attrs
from . import config_catalog_references as refs
from .config_catalog_name import CatalogNameError, _IdentityCursor

DOCUMENT_COLLECTION_UUID = '061d872a-5787-460e-95ac-ed74ea3a3e84'
ATTRIBUTE_COLLECTION_UUID = '45e46cbc-3e24-4165-8b7b-cc98a6f80211'


@dataclass(frozen=True, slots=True)
class DocumentIdentityPrefix:
    metadata_uuid: str
    name: str
    number_type: int = 1
    number_length: int = 8
    number_periodicity: int = 0


@dataclass(frozen=True, slots=True)
class DocumentConfigSnapshot:
    document_fields: tuple
    catalog_fields: tuple


class _DocumentReferences(refs._Walk):
    collection_type = DOCUMENT_COLLECTION_UUID

    def run(self):
        try:
            return super().run()
        except refs.CatalogReferenceError as error:
            # The complete declared prefix may contain an empty Documents list.
            if error.code == 'no_positive' and self.catalog_count:
                return refs.CatalogReferences(self.catalog_count, ())
            raise


def project_document_references(data, *, budget, limits=None):
    if type(data) is not bytes:
        raise refs.CatalogReferenceError('input_type')
    limits = refs.CatalogReferenceLimits() if limits is None else limits
    if type(limits) is not refs.CatalogReferenceLimits:
        raise refs.CatalogReferenceError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise refs.CatalogReferenceError('input_bytes')
    budget.charge('bytes_processed', 3*len(data))
    budget.charge('output_bytes', refs.OUTPUT_RESERVATION)
    return _DocumentReferences(data, budget, limits).run()


# Exact observed header prefix for String8, variable-length, unique,
# non-autonumbered/nonperiodical Document with regular posting enabled.
# This is a bounded profile, not an interpretation of every header field.
_HEADER = {(0,): '1', (1, 0): '40', (2,): '5',
    **{(1, i): value for i, value in ((11,'1'),(12,'8'),(13,'0'),(14,'1'),
        (15,'0'),(19,'0'),(20,'1'),(21,'1'))},
    **{(1, i): '00000000-0000-0000-0000-000000000000' for i in (10,16,17,18)}}


class _DocumentAttributes(attrs._Walk):
    def __init__(self, data, budget, limits):
        super().__init__(data, budget, limits, linked=True)
        self.identity = {}
        self.header = set()

    def kind(self, path):
        if path in _HEADER:
            return 'document_header'
        if path == (1, 9, 1, 1, 2):
            return 'document_uuid'
        if path == (1, 9, 1, 2):
            return 'document_name'
        if path and path[0] == 5:
            return super().kind((6,)+path[1:])
        if path and path[0] == 6:
            return 'opaque'
        return super().kind(path)

    def value(self, path, kind):
        if kind == 'document_header':
            if self.peek() == 34 or self.scalar(True) != _HEADER[path]:
                raise attrs.CatalogAttributeError('type_unsupported')
            self.header.add(path)
        elif kind == 'document_uuid':
            self.identity['metadata_uuid'] = _IdentityCursor.uuid(self)
        elif kind == 'document_name':
            if self.peek() != 34:
                raise attrs.CatalogAttributeError('expected_scalar')
            self.identity['name'] = self.scalar(True)
        elif kind == 'collection_uuid':
            if _IdentityCursor.uuid(self) != ATTRIBUTE_COLLECTION_UUID:
                raise attrs.CatalogAttributeError('collection_uuid')
        else:
            super().value(path, kind)

    def close(self, path, children):
        if path and path[0] == 5:
            return super().close((6,)+path[1:], children)
        if path and path[0] == 6:
            return False
        return super().close(path, children)


def project_document_metadata(data, *, budget):
    if type(data) is not bytes:
        raise attrs.CatalogAttributeError('input_type')
    limits = attrs.CatalogAttributeLimits()
    if len(data) > limits.max_input_bytes:
        raise attrs.CatalogAttributeError('input_bytes')
    budget.charge('bytes_processed', 8*len(data))
    budget.charge('output_bytes', attrs.OUTPUT_RESERVATION)
    try:
        walk = _DocumentAttributes(data, budget, limits)
        collection = walk.run()
        if (walk.header != set(_HEADER) or set(walk.identity) != {'metadata_uuid', 'name'}
                or not walk.identity['name'] or collection.reference_type_uuid is None):
            raise attrs.CatalogAttributeError('missing_field')
        # !todo Numeric/periodic numbering and other Document headers require
        # their own native layout/API evidence; no Catalog header fallback.
        return DocumentIdentityPrefix(**walk.identity), collection
    except CatalogNameError as error:
        raise attrs.CatalogAttributeError(error.code) from None
