"""Host-only enum codec contracts, not native storage/wire parity evidence."""
from dataclasses import FrozenInstanceError, replace
import unittest
from uuid import UUID

from yadinassi.catalog_backend import BackendError, CatalogKey
from yadinassi.configuration_enumerations import EnumDefinition, EnumValueDefinition
from yadinassi.enum_storage_values import EnumKey, EnumValueDomain
from yadinassi.enum_types import BSLEnumReference, BSLEnumType


DB, OTHER_DB = UUID(int=1), UUID(int=2)
UNITS, STATES = UUID(int=10), UUID(int=20)
PIECE, PACK, DRAFT = UUID(int=11), UUID(int=12), UUID(int=21)
ZERO = UUID(int=0)


def definitions():
    return (EnumDefinition(UNITS, 'Unit', (EnumValueDefinition(PIECE, 'Piece'),
                                        EnumValueDefinition(PACK, 'Pack'))),
            EnumDefinition(STATES, 'State', (EnumValueDefinition(DRAFT, 'Draft'),)))


class Hostile:
    touched = []

    def __getattribute__(self, name):
        Hostile.touched.append(('attribute', name))
        raise AssertionError('unexpected attribute hook')

    def __eq__(self, other):
        Hostile.touched.append('equality')
        raise AssertionError('unexpected equality hook')

    def __hash__(self):
        Hostile.touched.append('hash')
        raise AssertionError('unexpected hash hook')

    def __str__(self):
        Hostile.touched.append('string')
        raise AssertionError('unexpected string hook')


class EnumStorageValuesTests(unittest.TestCase):
    def setUp(self):
        self.definitions = definitions()
        self.domain = EnumValueDomain(DB, self.definitions)
        self.key = EnumKey(DB, UNITS, PIECE)
        Hostile.touched.clear()

    def invalid(self, function, *args, code='invalid_input'):
        with self.assertRaises(BackendError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_key_retains_all_three_identities(self):
        self.assertEqual((self.key.database_id, self.key.enum_id, self.key.value_id),
                         (DB, UNITS, PIECE))
        self.assertNotEqual(self.key, EnumKey(OTHER_DB, UNITS, PIECE))
        self.assertNotEqual(self.key, EnumKey(DB, STATES, PIECE))

    def test_typed_empty_keys_are_not_untyped_zero(self):
        self.assertNotEqual(self.domain.empty(UNITS), self.domain.empty(STATES))
        self.assertEqual(self.domain.empty(UNITS), EnumKey(DB, UNITS, ZERO))

    def test_key_is_frozen_and_has_no_ordering(self):
        with self.assertRaises(FrozenInstanceError): self.key.value_id = PACK
        with self.assertRaises(TypeError): self.key < EnumKey(DB, UNITS, PACK)

    def test_key_requires_exact_nonempty_database_and_enum(self):
        for parts in ((ZERO, UNITS, PIECE), (DB, ZERO, PIECE),
                      ('1', UNITS, PIECE), (DB, 'Unit', PIECE), (DB, UNITS, 'Piece')):
            self.invalid(EnumKey, *parts)

    def test_key_rejects_uuid_subclasses(self):
        class DerivedUUID(UUID): pass
        for index in range(3):
            parts = [DB, UNITS, PIECE]; parts[index] = DerivedUUID(int=1)
            self.invalid(EnumKey, *parts)

    def test_key_input_does_not_run_hostile_hooks(self):
        for index in range(3):
            parts = [DB, UNITS, PIECE]; parts[index] = Hostile()
            self.invalid(EnumKey, *parts)
        self.assertEqual(Hostile.touched, [])

    def test_key_rejects_forged_uuid_without_hooks(self):
        for integer in (Hostile(), True, -1, 2**128):
            identity = UUID(int=1)
            object.__setattr__(identity, 'int', integer)
            self.invalid(EnumKey, identity, UNITS, PIECE)
        self.invalid(EnumKey, object.__new__(UUID), UNITS, PIECE)
        self.assertEqual(Hostile.touched, [])

    def test_domain_rejects_invalid_database_without_hooks(self):
        for database in (ZERO, 'database', Hostile()):
            self.invalid(EnumValueDomain, database, self.definitions)
        self.assertEqual(Hostile.touched, [])

    def test_domain_projects_only_declared_identity_tuples(self):
        self.assertEqual(self.domain.declarations,
                         ((UNITS, (PIECE, PACK)), (STATES, (DRAFT,))))
        self.assertIs(type(self.domain.declarations), tuple)
        with self.assertRaises(FrozenInstanceError): self.domain.database_id = OTHER_DB

    def test_domain_does_not_retain_source_objects_or_runtime_values(self):
        object.__setattr__(self.definitions[0], 'values', ())
        self.assertIs(self.domain.require_key(self.key, UNITS), self.key)
        self.assertEqual(self.domain.declarations[0][1], (PIECE, PACK))

    def test_domain_rejects_foreign_definition_class_without_hooks(self):
        self.invalid(EnumValueDomain, DB, (Hostile(),))
        self.assertEqual(Hostile.touched, [])

    def test_domain_rejects_definition_subclasses(self):
        class Derived(EnumDefinition): pass
        self.invalid(EnumValueDomain, DB, (Derived(UNITS, 'Unit', ()),))

    def test_domain_requires_exact_definition_and_value_tuples(self):
        self.invalid(EnumValueDomain, DB, list(self.definitions))
        self.invalid(EnumValueDomain, DB, (replace(self.definitions[0], values=[]),))

    def test_domain_rejects_value_definition_subclasses(self):
        class Derived(EnumValueDefinition): pass
        self.invalid(EnumValueDomain, DB,
                     (EnumDefinition(UNITS, 'Unit', (Derived(PIECE, 'Piece'),)),))

    def test_domain_rejects_hostile_value_definition_without_hooks(self):
        self.invalid(EnumValueDomain, DB, (EnumDefinition(UNITS, 'Unit', (Hostile(),)),))
        self.assertEqual(Hostile.touched, [])

    def test_domain_rejects_zero_declaration_and_value_ids(self):
        self.invalid(EnumValueDomain, DB, (EnumDefinition(ZERO, 'Unit', ()),))
        self.invalid(EnumValueDomain, DB,
                     (EnumDefinition(UNITS, 'Unit', (EnumValueDefinition(ZERO, 'Empty'),)),))

    def test_domain_rejects_duplicate_enum_id(self):
        self.invalid(EnumValueDomain, DB, (self.definitions[0], self.definitions[0]))

    def test_domain_rejects_duplicate_value_id_across_enums(self):
        self.invalid(EnumValueDomain, DB, (self.definitions[0],
            EnumDefinition(STATES, 'State', (EnumValueDefinition(PIECE, 'Draft'),))))

    def test_domain_rejects_enum_and_value_identity_collisions(self):
        self.invalid(EnumValueDomain, DB, (self.definitions[0], EnumDefinition(PIECE, 'Other', ())))
        self.invalid(EnumValueDomain, DB,
                     (EnumDefinition(UNITS, 'Unit', (EnumValueDefinition(UNITS, 'Piece'),)),))

    def test_domain_rejects_hostile_declared_uuid_without_hooks(self):
        self.invalid(EnumValueDomain, DB, (EnumDefinition(Hostile(), 'Unit', ()),))
        self.invalid(EnumValueDomain, DB,
                     (EnumDefinition(UNITS, 'Unit', (EnumValueDefinition(Hostile(), 'Piece'),)),))
        self.assertEqual(Hostile.touched, [])

    def test_domain_rejects_constructor_bypassed_declarations(self):
        self.invalid(EnumValueDomain, DB, (object.__new__(EnumDefinition),))
        self.invalid(EnumValueDomain, DB,
                     (EnumDefinition(UNITS, 'Unit', (object.__new__(EnumValueDefinition),)),))

    def test_empty_domain_has_no_implicit_targets(self):
        domain = EnumValueDomain(DB, ())
        self.invalid(domain.empty, UNITS)
        self.invalid(domain.require_key, self.key, UNITS)

    def test_empty_enum_admits_only_typed_empty(self):
        domain = EnumValueDomain(DB, (EnumDefinition(UNITS, 'Unit', ()),))
        self.assertEqual(domain.empty(UNITS).value_id, ZERO)
        self.invalid(domain.require_key, self.key, UNITS)

    def test_enum_count_boundary(self):
        declared = tuple(EnumDefinition(UUID(int=1000+i), 'E'+str(i), ()) for i in range(129))
        self.assertEqual(len(EnumValueDomain(DB, declared[:128]).declarations), 128)
        self.invalid(EnumValueDomain, DB, declared)

    def test_per_enum_value_count_boundary(self):
        values = tuple(EnumValueDefinition(UUID(int=1000+i), 'V'+str(i)) for i in range(513))
        self.assertEqual(len(EnumValueDomain(DB, (EnumDefinition(UNITS, 'Unit', values[:512]),)).declarations[0][1]), 512)
        self.invalid(EnumValueDomain, DB, (EnumDefinition(UNITS, 'Unit', values),))

    def test_total_value_count_boundary(self):
        declared = tuple(EnumDefinition(UUID(int=100+i), 'E'+str(i), tuple(
            EnumValueDefinition(UUID(int=1000+i*512+j), 'V'+str(j)) for j in range(512))) for i in range(8))
        self.assertEqual(sum(len(v) for _, v in EnumValueDomain(DB, declared).declarations), 4096)
        self.invalid(EnumValueDomain, DB, declared +
                     (EnumDefinition(UUID(int=200), 'Overflow', (EnumValueDefinition(UUID(int=9999), 'V'),)),))

    def test_require_key_keeps_exact_owned_identity(self):
        self.assertIs(self.domain.require_key(self.key, UNITS), self.key)
        self.assertEqual(self.domain.require_key(self.domain.empty(UNITS), UNITS).value_id, ZERO)

    def test_require_key_rejects_foreign_database_target_or_value(self):
        for key, target in ((EnumKey(OTHER_DB, UNITS, PIECE), UNITS),
                            (self.key, STATES), (EnumKey(DB, UNITS, DRAFT), UNITS),
                            (EnumKey(DB, UNITS, UUID(int=999)), UNITS)):
            self.invalid(self.domain.require_key, key, target)

    def test_require_key_rejects_catalog_key_and_subclass(self):
        class Derived(EnumKey): pass
        for key in (CatalogKey(DB, UNITS, PIECE), Derived(DB, UNITS, PIECE)):
            self.invalid(self.domain.require_key, key, UNITS)

    def test_require_key_does_not_coerce_bsl_enum_or_strings(self):
        reference = BSLEnumReference(BSLEnumType(UNITS, 'Unit', object()), PIECE, object())
        for key in (reference, str(PIECE), (DB, UNITS, PIECE), None):
            self.invalid(self.domain.require_key, key, UNITS)

    def test_require_key_rejects_hostile_key_target_and_forged_components(self):
        self.invalid(self.domain.require_key, Hostile(), UNITS)
        self.invalid(self.domain.require_key, self.key, Hostile())
        for name in ('database_id', 'enum_id', 'value_id'):
            key = EnumKey(DB, UNITS, PIECE)
            object.__setattr__(key, name, Hostile())
            self.invalid(self.domain.require_key, key, UNITS)
        self.assertEqual(Hostile.touched, [])

    def test_require_key_rejects_uninitialized_key(self):
        self.invalid(self.domain.require_key, object.__new__(EnumKey), UNITS)

    def test_encode_is_explicit_internal_tag_and_canonical_uuid(self):
        self.assertEqual(self.domain.encode(self.key, UNITS),
                         ['enum_ref_v1', str(UNITS), str(PIECE)])

    def test_nonempty_and_empty_roundtrip(self):
        for key in (self.key, self.domain.empty(UNITS)):
            self.assertEqual(self.domain.decode(self.domain.encode(key, UNITS), UNITS), key)

    def test_decode_uses_owner_database_not_transport_authority(self):
        other = EnumValueDomain(OTHER_DB, definitions())
        key = other.decode(self.domain.encode(self.key, UNITS), UNITS)
        self.assertEqual(key.database_id, OTHER_DB)
        self.assertNotEqual(key, self.key)
        self.invalid(self.domain.require_key, key, UNITS)

    def test_decode_rejects_wrong_tag_shape_and_component_types(self):
        for payload in (None, (), [], ['enum_ref_v1'], ['r', str(UNITS), str(PIECE)],
                        ['enum_ref_v1', str(UNITS), PIECE],
                        ['enum_ref_v1', str(UNITS), str(PIECE), 'extra']):
            self.invalid(self.domain.decode, payload, UNITS, code='integrity')

    def test_decode_rejects_noncanonical_uuid_spellings(self):
        special = UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
        domain = EnumValueDomain(DB, (EnumDefinition(UNITS, 'Unit', (EnumValueDefinition(special, 'V'),)),))
        for text in (str(special).upper(), special.hex, '{'+str(special)+'}', ' '+str(special), 'not-a-uuid'):
            self.invalid(domain.decode, ['enum_ref_v1', str(UNITS), text], UNITS, code='integrity')

    def test_decode_rejects_wrong_enum_unknown_value_and_zero_target(self):
        for target, value in ((STATES, DRAFT), (UNITS, DRAFT), (UNITS, UUID(int=999)), (ZERO, ZERO)):
            self.invalid(self.domain.decode, ['enum_ref_v1', str(target), str(value)], UNITS, code='integrity')

    def test_decode_rejects_hostile_payload_without_hooks(self):
        for payload in (Hostile(), ['enum_ref_v1', Hostile(), str(PIECE)],
                        ['enum_ref_v1', str(UNITS), Hostile()]):
            self.invalid(self.domain.decode, payload, UNITS, code='integrity')
        self.assertEqual(Hostile.touched, [])

    def test_decode_rejects_list_and_string_subclasses_without_hooks(self):
        class DerivedList(list):
            def __len__(self): raise AssertionError('length hook')
        class DerivedString(str):
            def __eq__(self, other): raise AssertionError('equality hook')
        for payload in (DerivedList(['enum_ref_v1', str(UNITS), str(PIECE)]),
                        [DerivedString('enum_ref_v1'), str(UNITS), str(PIECE)]):
            self.invalid(self.domain.decode, payload, UNITS, code='integrity')

    def test_decode_and_encode_do_not_mutate_inputs_or_domain(self):
        payload = self.domain.encode(self.key, UNITS); snapshot = tuple(payload)
        self.domain.decode(payload, UNITS)
        self.assertEqual(tuple(payload), snapshot)
        payload[2] = str(PACK)
        self.assertEqual(self.domain.encode(self.key, UNITS)[2], str(PIECE))
