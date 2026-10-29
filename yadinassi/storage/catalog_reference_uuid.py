"""Pure UUID conversion for the measured Catalog row-reference byte order.

This is not a database reader or writer. The caller must independently admit
its row layout. In particular, conversion of zero bytes does not establish
that a persisted empty-reference field uses this layout. No interpreter or
native-oracle dependency belongs at this boundary.
"""
from uuid import UUID

# canonical[i] = physical[_CANONICAL_FROM_PHYSICAL[i]], NOT the inverse.
_CANONICAL_FROM_PHYSICAL = (12, 13, 14, 15, 10, 11, 8, 9,
                            0, 1, 2, 3, 4, 5, 6, 7)
_PHYSICAL_FROM_CANONICAL = (8, 9, 10, 11, 12, 13, 14, 15,
                            6, 7, 4, 5, 0, 1, 2, 3)


class CatalogUUIDError(ValueError):
    """Finite diagnostics; never include a private UUID or physical bytes."""

    codes = frozenset(('bytes_type', 'bytes_length', 'uuid_type', 'uuid_value'))

    def __init__(self, code):
        if type(code) is not str or code not in self.codes:
            raise ValueError('invalid catalog UUID diagnostic')
        self.code = code
        super().__init__(code)


def decode_catalog_reference_uuid(physical: bytes) -> UUID:
    """Decode exactly 16 immutable bytes, without version/variant rewriting."""
    if type(physical) is not bytes:
        raise CatalogUUIDError('bytes_type')
    if len(physical) != 16:
        raise CatalogUUIDError('bytes_length')
    return UUID(bytes=bytes(physical[i] for i in _CANONICAL_FROM_PHYSICAL))


def encode_catalog_reference_uuid(value: UUID) -> bytes:
    """Encode an exact stdlib UUID, without coercion or database writes."""
    if type(value) is not UUID:
        raise CatalogUUIDError('uuid_type')
    # Even a malformed UUID made with object.__new__/object.__setattr__ must
    # not leak a dynamic error or invoke a user-defined conversion hook.
    integer = getattr(value, 'int', None)
    if type(integer) is not int or not 0 <= integer < (1 << 128):
        raise CatalogUUIDError('uuid_value')
    canonical = integer.to_bytes(16, 'big')
    return bytes(canonical[i] for i in _PHYSICAL_FROM_CANONICAL)
