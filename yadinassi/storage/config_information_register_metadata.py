"""Measured independent/nonperiodic InformationRegister CONFIG, native41353896285.

Only the observed six-field scalar/reference profile is admitted. No XML, oracle
mapping, fixture names or physical offsets are inputs to this projector.
"""
from dataclasses import dataclass, field
from . import config_catalog_attributes as a
from . import config_catalog_references as refs
from .config_catalog_name import _IdentityCursor, CatalogNameError

COLLECTION_UUID = '13134201-f60b-11d5-a3c7-0050bae0a776'
FAMILIES = ('Record', 'Manager', 'Selection', 'List', 'RecordSet', 'RecordKey', 'RecordManager')
COLLECTIONS = {3: ('resources', '13134202-f60b-11d5-a3c7-0050bae0a776', 3),
               4: ('dimensions', '13134203-f60b-11d5-a3c7-0050bae0a776', 2),
               7: ('attributes', 'a2207540-1400-11d6-a3c7-0050bae0a776', 1)}
EMPTY = {5: '13134204-f60b-11d5-a3c7-0050bae0a776',
         6: '3daea016-69b7-4ed4-9453-127911372fe6',
         8: 'b44ba719-945c-445c-8aab-1088fa4df16e'}
ZERO = '00000000-0000-0000-0000-000000000000'
HEADER = {(0,): '1', (1, 0): '33', (2,): '6',
          **{(1, i): ZERO for i in (16, 17, 27, 28)},
          **{(1, i): '0' for i in (*range(18, 26), *range(34, 39))},
          **{(1, i, 0): '0' for i in range(29, 34)}}


@dataclass(frozen=True, slots=True)
class InformationRegisterIdentityPrefix:
    metadata_uuid: str
    name: str
    periodicity: int = 0
    write_mode: int = 0
    generated_types: tuple = field(default=(), kw_only=True)


@dataclass(frozen=True, slots=True)
class InformationRegisterConfigSnapshot:
    register_fields: tuple
    catalog_fields: tuple


class _References(refs._Walk):
    collection_type = COLLECTION_UUID

    def run(self):
        try:
            return super().run()
        except refs.CatalogReferenceError as error:
            if error.code == 'no_positive' and self.catalog_count:
                return refs.CatalogReferences(self.catalog_count, ())
            raise


def project_information_register_references(data, *, budget, limits=None):
    if type(data) is not bytes:
        raise refs.CatalogReferenceError('input_type')
    limits = refs.CatalogReferenceLimits() if limits is None else limits
    if type(limits) is not refs.CatalogReferenceLimits:
        raise refs.CatalogReferenceError('limits_type')
    limits.__post_init__()
    if len(data) > limits.max_input_bytes:
        raise refs.CatalogReferenceError('input_bytes')
    budget.charge('bytes_processed', 3 * len(data))
    budget.charge('output_bytes', refs.OUTPUT_RESERVATION)
    return _References(data, budget, limits).run()


class _Register(a._Walk):
    def __init__(self, data, budget, limits):
        super().__init__(data, budget, limits, linked=True)
        self.identity = {}; self.generated = {}; self.header = set()
        self.collections = {}; self.indexed = {}

    def kind(self, path):
        if path in HEADER:
            return 'header'
        if len(path) == 2 and path[0] == 1 and 1 <= path[1] <= 14:
            return 'generated'
        if path == (1, 15, 1, 1, 2): return 'identity_uuid'
        if path == (1, 15, 1, 2): return 'identity_name'
        if path and path[0] in EMPTY:
            if len(path) == 1: return 'object'
            if path[1:] == (0,): return 'empty_uuid'
            if path[1:] == (1,): return 'empty_count'
            raise a.CatalogAttributeError('collection_count')
        if path and path[0] in COLLECTIONS:
            if len(path) == 1:
                self.rows = []; self.count = None
            if len(path) == 4 and path[0] == 4 and path[1] >= 2 and path[2:] == (0, 4):
                return 'indexed'
            return super().kind((6,) + path[1:])
        return 'opaque'

    def value(self, path, kind):
        if kind == 'header':
            if self.peek() == 34 or self.scalar(True) != HEADER[path]:
                raise a.CatalogAttributeError('type_unsupported')
            self.header.add(path)
        elif kind == 'generated': self.generated[path[1]] = _IdentityCursor.uuid(self)
        elif kind == 'identity_uuid': self.identity['metadata_uuid'] = _IdentityCursor.uuid(self)
        elif kind == 'identity_name':
            if self.peek() != 34: raise a.CatalogAttributeError('expected_scalar')
            self.identity['name'] = self.scalar(True)
        elif kind == 'collection_uuid':
            if _IdentityCursor.uuid(self) != COLLECTIONS[path[0]][1]:
                raise a.CatalogAttributeError('collection_uuid')
        elif kind == 'empty_uuid':
            if _IdentityCursor.uuid(self) != EMPTY[path[0]]:
                raise a.CatalogAttributeError('collection_uuid')
        elif kind == 'empty_count':
            if self.integer(0) != 0: raise a.CatalogAttributeError('collection_count')
        elif kind == 'indexed': self.indexed[path[1]-2] = self.integer(1)
        else: super().value(path, kind)

    def close(self, path, children):
        if path and path[0] in COLLECTIONS:
            done = super().close((6,) + path[1:], children)
            if done:
                role, _, count = COLLECTIONS[path[0]]
                if len(self.rows) != count: raise a.CatalogAttributeError('attribute_limit')
                self.collections[role] = a.CatalogAttributes(tuple(self.rows))
            return False
        if path and path[0] in EMPTY and len(path) == 1:
            if children != 2: raise a.CatalogAttributeError('collection_count')
            if path == (8,): return True
        if path == (1,) and children != 39:
            raise a.CatalogAttributeError('type_unsupported')
        if len(path) == 2 and path[0] == 1 and 29 <= path[1] <= 33 and children != 1:
            raise a.CatalogAttributeError('type_unsupported')
        if path == ():
            if children != 9: raise a.CatalogAttributeError('collection_count')
            return True
        return False


def project_information_register_metadata(data, *, budget):
    if type(data) is not bytes: raise a.CatalogAttributeError('input_type')
    limits = a.CatalogAttributeLimits()
    if len(data) > limits.max_input_bytes: raise a.CatalogAttributeError('input_bytes')
    budget.charge('bytes_processed', 8 * len(data)); budget.charge('output_bytes', a.OUTPUT_RESERVATION)
    try:
        walk = _Register(data, budget, limits); walk.run()
        if walk.peek() != 125: raise a.CatalogAttributeError('syntax')
        walk.event(); walk.character(); walk.spaces()
        if walk.peek() is not None: raise a.CatalogAttributeError('syntax')
        if (walk.header != set(HEADER) or set(walk.identity) != {'metadata_uuid', 'name'}
                or not walk.identity['name'] or len(walk.generated) != 14
                or set(walk.collections) != {'dimensions', 'resources', 'attributes'}):
            raise a.CatalogAttributeError('missing_field')
        dims, resources, attributes = (walk.collections[k] for k in ('dimensions', 'resources', 'attributes'))
        kinds = lambda c: tuple((v.type_token, v.qualifiers) for v in c.attributes)
        d = (('#', ()), ('N', (9, 0, 0)))
        r = (('N', (9, 2, 0)), ('B', ()), ('D', ()))
        if (kinds(dims) not in (d, d[::-1]) or kinds(resources) not in (r, r[::-1])
                or kinds(attributes) != (('S', (32, 1)),)
                or walk.indexed != {i: int(v.type_token == '#') for i, v in enumerate(dims.attributes)}):
            raise a.CatalogAttributeError('type_unsupported')
        all_fields = dims.attributes + resources.attributes + attributes.attributes
        identities = [walk.identity['metadata_uuid'], *walk.generated.values(), *(x.metadata_uuid for x in all_fields)]
        if len(set(identities)) != len(identities): raise a.CatalogAttributeError('duplicate_uuid')
        if len({x.name.casefold() for x in all_fields}) != 6: raise a.CatalogAttributeError('duplicate_name')
        generated = tuple((name, walk.generated[2*i+1], walk.generated[2*i+2]) for i, name in enumerate(FAMILIES))
        return InformationRegisterIdentityPrefix(**walk.identity, generated_types=generated), dims, resources, attributes
    except CatalogNameError as error:
        raise a.CatalogAttributeError(error.code) from None
    # !todo Periodic/recorder-bound registers, other field profiles and extensions
    # need independent native CONFIG/physical evidence; never infer their layout.
