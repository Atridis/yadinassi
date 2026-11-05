"""Local host contract only. No native form or imported handler execution."""
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import UUID

from yadinassi.catalog_backend import FieldSchema
from yadinassi.form_data import ScalarFormData, ScalarFormField, ScalarFormBinding


def field(name, kind='string', qualifiers=(16,), aliases=(), writable=True, identity=1):
    return ScalarFormField(FieldSchema(UUID(int=identity), name, kind, qualifiers), aliases, writable)


def make():
    return ScalarFormData((field('Code', aliases=('Код',)),
        field('Description', aliases=('Наименование',), identity=2),
        field('DeletionMark', 'boolean', (), aliases=('ПометкаУдаления',), identity=3)),
        (('Code', '01'), ('Description', ' old '), ('DeletionMark', False)), root='Объект', bindings=(
            ScalarFormBinding('CodeControl', 'Объект.Code', False),
            ScalarFormBinding('DescriptionControl', 'Объект.Description')))


class ScalarFormDataTests(unittest.TestCase):
    def test_closed_bilingual_members(self):
        data = make()
        data.set_member('нАиМеНоВаНиЕ', 'new')
        self.assertEqual(data.get_member('DESCRIPTION'), 'new')
        self.assertEqual(data.get_member('Код'), '01')

    def test_no_methods_or_host_members(self):
        data = make()
        for name in ('Write', 'Записать', '_values', 'snapshot', 'Ref', 'GetObject'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError): data.get_member(name)
                with self.assertRaises(ValueError): data.get_method(name)

    def test_snapshot_immutable_and_detached(self):
        data = make(); before = data.snapshot()
        with self.assertRaises(FrozenInstanceError): before.revision = 9
        with self.assertRaises(TypeError): before.values[0] = ('Code', 'forged')
        with self.assertRaises(TypeError): before.values[0][1] = 'forged'
        data.set_member('Description', 'new')
        self.assertEqual(dict(before.values)['Description'], ' old ')

    def test_atomic_patch_failure(self):
        data = make(); before = data.snapshot()
        with self.assertRaises(TypeError):
            data.patch((('Code', '02'), ('Description', [])), revision=0)
        self.assertEqual(data.snapshot(), before)

    def test_duplicate_alias_patch_rejected(self):
        data = make(); before = data.snapshot()
        with self.assertRaises(ValueError):
            data.patch((('Code', '02'), ('Код', '03')), revision=0)
        self.assertEqual(data.snapshot(), before)

    def test_stale_and_boolean_revision(self):
        data = make(); data.set_member('Description', 'new')
        for revision in (0, True, Decimal(1)):
            with self.assertRaises(ValueError): data.patch((), revision=revision)

    def test_host_owned_path_and_read_only_control(self):
        data = make()
        self.assertEqual(data.data_path('DescriptionControl'), 'Объект.Description')
        expanded = 'ß' * 65
        unicode_data = ScalarFormData((field(expanded),), ((expanded, ''),),
            bindings=(ScalarFormBinding('Control', 'Object.' + expanded),))
        unicode_data.change_control('Control', 'value', revision=0)
        self.assertEqual(unicode_data.get_member(expanded), 'value')
        for control in ('CodeControl', 'Объект.Description', 'Description'):
            with self.assertRaises(ValueError): data.change_control(control, 'x', revision=0)
        data.change_control('DescriptionControl', 'new', revision=0)
        self.assertEqual(data.get_member('Description'), 'new')

    def test_detached_save_refusal_or_failure_never_copies_back(self):
        data = make(); baseline = data.snapshot(); candidate = data.detached_save_image()
        candidate.set_member('Description', 'trimmed')
        candidate.set_member('ПометкаУдаления', True)
        self.assertFalse(data.get_member('DeletionMark'))
        self.assertTrue(candidate.get_member('DeletionMark'))
        with self.assertRaises(ValueError): candidate.set_member('Write', 'no')
        self.assertEqual(data.snapshot(), baseline)
        data.set_member('Code', '02')
        self.assertEqual(candidate.get_member('Code'), '01')

    def test_failed_setter_does_not_rollback_prior_setter(self):
        data = make(); data.set_member('Description', 'changed')
        with self.assertRaises(TypeError): data.set_member('Code', object())
        self.assertEqual(data.get_member('Description'), 'changed')
        self.assertEqual(data.snapshot().revision, 1)

    def test_existing_scalar_qualifiers(self):
        data = ScalarFormData((field('Text', qualifiers=(2,)),
            field('Flag', 'boolean', (), identity=3)),
            (('Text', 'abc'), ('Flag', True)))
        self.assertEqual(dict(data.snapshot().values), {'Text': 'ab', 'Flag': True})

    def test_unsupported_mutable_or_capability_values(self):
        data = make()
        class HostileString(str):
            def encode(self, *args, **kwargs):
                raise AssertionError('host hook executed')
        with self.assertRaises(TypeError): data.set_member('Description', HostileString('x'))
        for value in ([], {}, object(), None, 1, True):
            with self.assertRaises(TypeError): data.set_member('Description', value)

    def test_malformed_unicode_rejected_before_truncation(self):
        data = make(); before = data.snapshot()
        for value in ('a\x00b', 'a' * 17 + '\ud800', 'x' * 65537):
            with self.assertRaises(ValueError): data.set_member('Description', value)
        self.assertEqual(data.snapshot(), before)

    def test_schema_and_registration_validation(self):
        cases = ((field('Code'), field('Other', aliases=('code',), identity=2)),
                 (field('Code'), field('Description')),
                 (field('Nested', 'reference', ()),),
                 (field('Amount', 'number', (3, 1, 'Any')),),
                 (field('Flag', 'boolean', (1,)),))
        for fields in cases:
            with self.assertRaises(ValueError): ScalarFormData(fields, ())
        with self.assertRaises(ValueError):
            ScalarFormData((field('Code'),), (('Code', ''),), bindings=(
                ScalarFormBinding('Control', 'Object.Code'),
                ScalarFormBinding('CONTROL', 'Object.Code')))
        for path in ('Other.Code', 'Object.Code.Write', 'Object.Unknown', 'Object.Код'):
            with self.assertRaises(ValueError):
                ScalarFormData((field('Code', aliases=('Код',)),), (('Code', ''),),
                               bindings=(ScalarFormBinding('Control', path),))

    def test_complete_image_and_member_readonly(self):
        with self.assertRaises(ValueError): ScalarFormData((field('Code'),), ())
        data = ScalarFormData((field('Code', writable=False),), (('Code', '01'),))
        with self.assertRaises(ValueError): data.set_member('Code', '02')
        self.assertEqual(data.get_member('Code'), '01')

    def test_total_bound_and_atomic_rebalancing(self):
        fields = tuple(field('F' + str(i), qualifiers=(65536,), identity=i + 1) for i in range(5))
        data = ScalarFormData(fields, tuple((f.schema.name, 'x' * 65536 if i < 4 else '') for i, f in enumerate(fields)))
        before = data.snapshot()
        with self.assertRaises(ValueError): data.patch((('F4', 'x'),), revision=0)
        self.assertEqual(data.snapshot(), before)
        data.patch((('F4', 'x' * 65536), ('F0', '')), revision=0)
        self.assertEqual(data.get_member('F0'), '')


if __name__ == '__main__':
    unittest.main()
