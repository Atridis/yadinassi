"""Authored host16 helper contracts, no activation or native parity claim."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
import unittest
from uuid import UUID

from yadinassi import sqlite_catalog as codec
from yadinassi.accumulation_movements import (
    AccumulationRegisterSchema, AccumulationMovementRow, AccumulationDirection,
    AccumulationReplacement, validate_schema, validate_replacement)
from yadinassi.catalog_backend import BackendError, FieldSchema, CatalogSchema
from yadinassi.document_backend import DocumentKey
from yadinassi.enum_storage_values import EnumKey, EnumValueDomain
from yadinassi.sqlite_accumulation_movements import schema_data
from test_enum_storage_values import DB, OTHER_DB, UNITS, STATES, PIECE, definitions, Hostile


class EnumStorageCodecTests(unittest.TestCase):
    def setUp(self):
        self.domain = EnumValueDomain(DB, definitions())
        self.field = FieldSchema(UUID(int=100), 'Unit', 'enum_ref', (), None, UNITS)
        self.number = FieldSchema(UUID(int=101), 'Quantity', 'number', (12, 2, 'Any'))
        self.key = EnumKey(DB, UNITS, PIECE)
        self.catalog = CatalogSchema(UUID(int=102), 'Products', 9, 100, (self.field,))
        self.schema = AccumulationRegisterSchema(UUID(int=103), 'Stock', (UUID(int=104),),
            (self.field,), (self.number,), value_profile='catalog_enum_reference_v1')
        self.row = AccumulationMovementRow(1, datetime(2025, 1, 1), True,
            AccumulationDirection.RECEIPT, (self.key,), (Decimal('2.00'),))
        self.request = AccumulationReplacement(self.schema.identity,
            DocumentKey(DB, UUID(int=104), UUID(int=105)), (self.row,), '0' * 64)

    def denied(self, function, *args, **kwargs):
        with self.assertRaises(BackendError): function(*args, **kwargs)

    def test_enum_codec_named_roundtrip(self):
        raw = codec._encode(self.key, self.field, DB, enum_domain=self.domain)
        self.assertEqual(codec._decode(raw, self.field, DB, enum_domain=self.domain), self.key)

    def test_enum_codec_empty_roundtrip(self):
        key = self.domain.empty(UNITS)
        self.assertEqual(codec._decode(codec._encode(key, self.field, DB, enum_domain=self.domain),
            self.field, DB, enum_domain=self.domain), key)

    def test_default_closed_enum_encode_and_decode(self):
        self.denied(codec._encode, self.key, self.field, DB)
        self.denied(codec._decode, self.domain.encode(self.key, UNITS), self.field, DB)

    def test_exact_domain_not_subclass_or_hooks(self):
        class Derived(EnumValueDomain): pass
        for domain in (Hostile(), Derived(DB, definitions())):
            self.denied(codec._encode, self.key, self.field, DB, enum_domain=domain)

    def test_foreign_database_domain(self):
        self.denied(codec._encode, self.key, self.field, OTHER_DB, enum_domain=self.domain)

    def test_foreign_database_key(self):
        self.denied(codec._encode, replace(self.key, database_id=OTHER_DB), self.field, DB, enum_domain=self.domain)

    def test_wrong_enum_key(self):
        self.denied(codec._encode, self.domain.empty(STATES), self.field, DB, enum_domain=self.domain)

    def test_unknown_value_key(self):
        self.denied(codec._encode, replace(self.key, value_id=UUID(int=999)), self.field, DB, enum_domain=self.domain)

    def test_unknown_enum_target(self):
        self.denied(codec._fields_data, (replace(self.field, target_enum_id=UUID(int=999)),), enum_domain=self.domain)

    def test_qualifier_and_catalog_target_denied(self):
        for field in (replace(self.field, qualifiers=(1,)), replace(self.field, target_catalog_id=UNITS)):
            self.denied(codec._encode, self.key, field, DB, enum_domain=self.domain)

    def test_malformed_payload_integrity(self):
        for raw in (['s', 'Piece'], ['enum_ref_v1', str(UNITS), str(UUID(int=999))], ['enum_ref_v1', Hostile(), str(PIECE)]):
            with self.assertRaises(BackendError) as caught:
                codec._decode(raw, self.field, DB, enum_domain=self.domain)
            self.assertEqual(caught.exception.code, 'integrity')

    def test_scalar_with_enum_target_rejected_every_codec(self):
        field = replace(self.number, target_enum_id=UNITS)
        for domain in (None, self.domain):
            self.denied(codec._fields_data, (field,), enum_domain=domain)
            self.denied(codec._encode, Decimal('1'), field, DB, enum_domain=domain)
            self.denied(codec._decode, ['n', '1.00'], field, DB, enum_domain=domain)

    def test_legacy_scalar_bytes_unchanged(self):
        self.assertEqual(codec._fields_data((self.number,)), [[str(self.number.identity), 'Quantity', 'number', [12, 2, 'Any'], None]])
        self.assertEqual(codec._encode(Decimal('1'), self.number, DB), ['n', '1.00'])

    def test_catalog_schema_roundtrip_explicit_domain(self):
        data = codec._schema_data(self.catalog, enum_domain=self.domain)
        self.assertEqual(len(data[4][0]), 6)
        self.assertEqual(codec._schema(json.dumps(data), enum_domain=self.domain), self.catalog)

    def test_catalog_schema_default_closed(self):
        self.denied(codec._schema_data, self.catalog)
        self.denied(codec._schema, json.dumps(codec._schema_data(self.catalog, enum_domain=self.domain)))

    def test_old_five_slot_schema_not_enum_schema(self):
        scalar = replace(self.catalog, fields=(self.number,))
        self.denied(codec._schema, json.dumps(codec._schema_data(scalar)), enum_domain=self.domain)

    def test_forged_domain_rejected_without_hooks(self):
        domain = EnumValueDomain(DB, ())
        object.__setattr__(domain, 'declarations', ((Hostile(), ()),))
        Hostile.touched.clear()
        self.denied(codec._encode, self.key, self.field, DB, enum_domain=domain)
        self.assertEqual(Hostile.touched, [])

    def test_uninitialized_domain_rejected(self):
        self.denied(codec._fields_data, (self.field,), enum_domain=object.__new__(EnumValueDomain))

    def test_accumulation_explicit_schema(self):
        self.assertIs(validate_schema(self.schema, enum_domain=self.domain), self.schema)
        self.assertEqual(schema_data(self.schema, enum_domain=self.domain)[0], 'accumulation_enum_reference_v1')

    def test_accumulation_default_closed(self):
        self.denied(validate_schema, self.schema)
        self.denied(schema_data, self.schema)

    def test_old_accumulation_profile_cannot_use_domain(self):
        for profile in ('scalar_v1', 'catalog_reference_v1'):
            self.denied(validate_schema, replace(self.schema, value_profile=profile), enum_domain=self.domain)

    def test_legacy_accumulation_scalar_target_denied(self):
        for profile in ('scalar_v1', 'catalog_reference_v1'):
            schema = replace(self.schema, dimensions=(), resources=(replace(self.number, target_enum_id=UNITS),), value_profile=profile)
            self.denied(validate_schema, schema)

    def test_enum_resources_always_denied(self):
        self.denied(validate_schema, replace(self.schema, dimensions=(), resources=(self.field,)), enum_domain=self.domain)

    def test_accumulation_replacement_roundtrip_validation(self):
        self.assertIs(validate_replacement(self.schema, self.request, DB, enum_domain=self.domain), self.request)

    def test_accumulation_replacement_owner_domain(self):
        self.denied(validate_replacement, self.schema, self.request, DB, enum_domain=EnumValueDomain(OTHER_DB, definitions()))

    def test_accumulation_replacement_no_string_coercion(self):
        request = replace(self.request, rows=(replace(self.row, dimensions=('Piece',)),))
        self.denied(validate_replacement, self.schema, request, DB, enum_domain=self.domain)

    def test_accumulation_attribute_enum(self):
        schema = replace(self.schema, dimensions=(), attributes=(self.field,))
        request = replace(self.request, rows=(replace(self.row, dimensions=(), attributes=(self.key,)),))
        self.assertIs(validate_replacement(schema, request, DB, enum_domain=self.domain), request)

    def test_accumulation_reserved_catalog_name_not_reused(self):
        field = replace(self.field, name='Code')
        schema = replace(self.schema, dimensions=(field,))
        self.assertEqual(schema_data(schema, enum_domain=self.domain)[5][0][1], 'Code')
        self.assertEqual(codec._encode(self.key, field, DB, enum_domain=self.domain), self.domain.encode(self.key, UNITS))
