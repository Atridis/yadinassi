"""Invented independently named identities/DBNames; no native compatibility claim."""
import dataclasses
import inspect
from pathlib import Path
import sys
import types
import unittest

STORAGE = Path(__file__).resolve().parents[1] / 'yadinassi/storage'
PACKAGE = '_catalog_binding_tests_storage'
package = types.ModuleType(PACKAGE)
package.__path__ = [str(STORAGE)]
sys.modules[PACKAGE] = package
binding = __import__(PACKAGE + '.config_catalog_binding', fromlist=['*'])
name = __import__(PACKAGE + '.config_catalog_name', fromlist=['*'])
attrs = __import__(PACKAGE + '.config_catalog_attributes', fromlist=['*'])
dbnames = __import__(PACKAGE + '.filedb_dbnames', fromlist=['*'])
catalog = __import__(PACKAGE + '.filedb_catalog', fromlist=['*'])
C = '11111111-1111-1111-1111-111111111111'
S = '22222222-2222-2222-2222-222222222222'
N = '33333333-3333-3333-3333-333333333333'
X = '44444444-4444-4444-4444-444444444444'


def identities(code=2, string=32, precision=9, scale=2):
    return (name.CatalogIdentityPrefix(C, 'InventedCatalog', code, 1, 0),
            attrs.CatalogAttributes((attrs.CatalogAttribute(S, 'TextRenamed', 'S', (string, 1)),
                                     attrs.CatalogAttribute(N, 'ValueRenamed', 'N', (precision, scale, 0)))))


def index(rows=None):
    if rows is None:
        rows = ((N, 'Fld', 741), (C, 'Reference', 19), (S, 'Fld', 62))
    text = '\ufeff{0,{' + str(len(rows)) + ''.join(',{%s,"%s",%d}' % row for row in rows) + '}}'
    return dbnames.parse_dbnames(text.encode(), profile=dbnames.DBNamesParseProfile(dbnames.DBNAMES_PROFILE_IDENTIFIER),
                                limits=dbnames.DBNamesParseLimits())


class CatalogBindingTests(unittest.TestCase):
    def compile(self, identity=None, attributes=None, names=None, budget=None, **kwargs):
        default_identity, default_attributes = identities()
        budget = budget if budget is not None else catalog._Budget(catalog.CatalogLimits())
        result = binding.compile_catalog_binding(
            default_identity if identity is None else identity,
            default_attributes if attributes is None else attributes,
            index() if names is None else names,
            profile=binding.CatalogBindingProfile(binding.PROFILE_IDENTIFIER), budget=budget, **kwargs)
        return result, budget

    def error(self, code, **kwargs):
        with self.assertRaises(binding.CatalogBindingError) as caught:
            self.compile(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_complete_independent_mapping_and_placements(self):
        result, _ = self.compile()
        self.assertEqual(result.table_name, '_Reference19')
        self.assertEqual(result.declarations, (
            ('_IDRREF', 'B', 0, 16, 0, 'CS'), ('_VERSION', 'RV', 0, 0, 0, 'CS'),
            ('_MARKED', 'L', 0, 0, 0, 'CS'), ('_PREDEFINEDID', 'B', 0, 16, 0, 'CS'),
            ('_CODE', 'NVC', 0, 2, 0, 'CI'), ('_FLD62', 'NVC', 0, 32, 0, 'CI'),
            ('_FLD741', 'N', 0, 9, 2, 'CS')))
        self.assertEqual(tuple(p.offset for p in result.placements), (17, 1, 33, 34, 50, 56, 122))
        self.assertEqual(result.record_size, 127)
        self.assertEqual([(x.name, x.physical_name) for x in result.attributes],
                         [('TextRenamed', '_FLD62'), ('ValueRenamed', '_FLD741')])
        self.assertEqual((result.recordlock, result.format_item), ('0', 0))

    def test_configuration_values_drive_widths_not_fixture_constants(self):
        i, a = identities(code=4, string=7, precision=8, scale=3)
        result, _ = self.compile(i, a)
        self.assertEqual(result.declarations[4][3], 4)
        self.assertEqual(result.declarations[5][3], 7)
        self.assertEqual(result.declarations[6][3:5], (8, 3))
        self.assertEqual(tuple(p.width for p in result.placements), (16, 16, 1, 16, 10, 16, 5))
        self.assertEqual(tuple(p.offset for p in result.placements), (17, 1, 33, 34, 50, 60, 76))
        self.assertEqual(result.record_size, 81)

    def test_tiny_and_even_precision_scale_zero(self):
        for p, expected in ((1, 1), (2, 2), (37, 19), (38, 20)):
            i, a = identities(code=1, string=1, precision=p, scale=0)
            result, _ = self.compile(i, a)
            self.assertEqual(result.placements[-1].width, expected)

    def test_immutable_output(self):
        result, _ = self.compile()
        for item, field, value in ((result, 'name', 'x'), (result.attributes[0], 'name', 'x'),
                                   (result.placements[0], 'offset', 0)):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(item, field, value)

    def test_input_signature_has_no_oracle_or_descriptor(self):
        self.assertEqual(tuple(inspect.signature(binding.compile_catalog_binding).parameters),
                         ('identity', 'attributes', 'dbnames', 'profile', 'budget', 'limits'))

    def test_missing_uuid(self):
        self.error('dbnames_missing', names=index(((C, 'Reference', 19), (S, 'Fld', 62))))

    def test_wrong_kind_not_suffix_or_first_match(self):
        self.error('dbnames_kind', names=index(((C, 'Reference', 19), (S, 'Fld', 62), (N, 'Other', 741))))

    def test_duplicate_target(self):
        rows = ((C, 'Reference', 19), (S, 'Fld', 62), (N, 'Fld', 741), (S, 'Fld', 63))
        self.error('dbnames_ambiguous', names=index(rows))

    def test_zero_target_id(self):
        self.error('dbnames_id', names=index(((C, 'Reference', 0), (S, 'Fld', 62), (N, 'Fld', 741))))

    def test_colliding_target_ids(self):
        self.error('dbnames_collision', names=index(((C, 'Reference', 19), (S, 'Fld', 62), (N, 'Fld', 62))))
        self.error('dbnames_collision', names=index(((C, 'Reference', 62), (S, 'Fld', 62), (N, 'Fld', 741))))

    def test_unrelated_entry_cannot_alias_selected_physical_name(self):
        self.error('dbnames_collision', names=index(((C, 'Reference', 19), (S, 'Fld', 62), (N, 'Fld', 741), (X, 'Fld', 62))))

    def test_unknown_unrelated_entry_preserved_not_target(self):
        value, _ = self.compile(names=index(((C, 'Reference', 19), (S, 'Fld', 62), (N, 'Fld', 741), (X, 'Other', 0))))
        self.assertEqual(value.table_name, '_Reference19')

    def test_bad_identity_and_names_are_finite(self):
        i, a = identities()
        for uuid in ('0' * 36, '00000000-0000-0000-0000-000000000000', C.upper().replace('1', 'A')):
            self.error('identity', identity=dataclasses.replace(i, metadata_uuid=uuid))
        for text in ('', 'x' * 257, 'secret\x00', '\ud800'):
            self.error('name', identity=dataclasses.replace(i, name=text))

    def test_standard_profile_restrictions(self):
        i, _ = identities()
        for changes in ({'code_type': 0}, {'description_length': 16}, {'code_length': 0},
                        {'code_length': True}, {'description_length': False}):
            self.error('standard_profile', identity=dataclasses.replace(i, **changes))

    def test_attribute_shape_and_identity(self):
        _, a = identities()
        self.error('attribute_shape', attributes=attrs.CatalogAttributes(()))
        self.error('attribute_shape', attributes=attrs.CatalogAttributes(a.attributes + (a.attributes[0],)))
        for changes in ({'metadata_uuid': S}, {'metadata_uuid': C}, {'name': 'TextRenamed'}):
            bad = dataclasses.replace(a.attributes[1], **changes)
            self.error('attribute_identity', attributes=attrs.CatalogAttributes((a.attributes[0], bad)))

    def test_types_and_qualifiers_fail_closed(self):
        _, a = identities()
        self.error('attribute_type', attributes=attrs.CatalogAttributes(tuple(reversed(a.attributes))))
        for q in ((32, 0), (0, 1), (2048, 1), (True, 1), (1,) * 100):
            self.error('qualifiers', attributes=attrs.CatalogAttributes((dataclasses.replace(a.attributes[0], qualifiers=q), a.attributes[1])))
        for q in ((9, 2, 1), (0, 0, 0), (39, 0, 0), (8, 9, 0), (8, -1, 0), (8, 0, False)):
            self.error('qualifiers', attributes=attrs.CatalogAttributes((a.attributes[0], dataclasses.replace(a.attributes[1], qualifiers=q))))

    def test_limits_lower_only(self):
        for changes in ({'max_dbnames_entries': 4097}, {'max_record_bytes': 4097},
                        {'max_numeric_precision': 39}, {'max_string_length': 2048},
                        {'max_record_bytes': True}, {'max_dbnames_entries': 0}):
            with self.assertRaises(binding.CatalogBindingError): binding.CatalogBindingLimits(**changes)
        self.error('dbnames_shape', limits=binding.CatalogBindingLimits(max_dbnames_entries=2))
        self.error('record_bytes', limits=binding.CatalogBindingLimits(max_record_bytes=126))
        result, _ = self.compile(limits=binding.CatalogBindingLimits(max_record_bytes=127))
        self.assertEqual(result.record_size, 127)

    def test_large_combined_layout_cannot_exceed_record_cap(self):
        i, a = identities(code=2047, string=2047)
        self.error('record_bytes', identity=i, attributes=a)

    def test_forged_dbnames_shape_and_entry(self):
        names = index()
        self.error('dbnames_shape', names=dataclasses.replace(names, declared_count=2))
        self.error('dbnames_shape', names=dataclasses.replace(names, entries=list(names.entries)))
        for changes in ({'ordinal': 99}, {'id': True}, {'kind': 'x' * 33}, {'uuid': 'x' * 1000}):
            altered = (dataclasses.replace(names.entries[0], **changes),) + names.entries[1:]
            self.error('dbnames_entry', names=dataclasses.replace(names, entries=altered))

    def test_budget_is_cumulative_and_failure_does_not_refund(self):
        budget = catalog._Budget(catalog.CatalogLimits())
        self.compile(budget=budget)
        first = dict(budget.counts)
        self.compile(budget=budget)
        for key in ('output_bytes', 'bytes_processed', 'tokens'):
            self.assertEqual(budget.counts[key], 2 * first[key])
        self.error('dbnames_missing', budget=budget, names=index(()))
        self.assertEqual(budget.counts['output_bytes'], 3 * first['output_bytes'])

    def test_reservations_precede_validation_and_retained_results(self):
        budget = catalog._Budget(catalog.CatalogLimits(max_output_bytes=8191))
        with self.assertRaises(catalog.ResourceLimit): self.compile(budget=budget)
        self.assertEqual(budget.counts['output_bytes'], 0)
        budget = catalog._Budget(catalog.CatalogLimits(max_bytes_processed=7167))
        with self.assertRaises(catalog.ResourceLimit): self.compile(budget=budget)
        self.assertEqual(budget.counts['output_bytes'], 8192)
        self.assertEqual(budget.counts['bytes_processed'], 0)

    def test_explicit_profile_and_exact_types(self):
        with self.assertRaises(binding.CatalogBindingError): binding.CatalogBindingProfile('other')
        i, a = identities()
        with self.assertRaises(binding.CatalogBindingError) as error:
            binding.compile_catalog_binding(i, a, index(), profile=None, budget=catalog._Budget(catalog.CatalogLimits()))
        self.assertEqual(error.exception.code, 'profile')
        self.error('input_type', identity=object())


if __name__ == '__main__':
    unittest.main()
