"""Pure canonical binder contracts; no runtime/transaction activation."""
from dataclasses import replace
import unittest
from uuid import UUID
from yadinassi.catalog_backend import BackendError
from yadinassi.enum_storage_binding import EnumStorageBinding
from yadinassi.enum_storage_values import EnumKey, EnumValueDomain
from yadinassi.enumerations import BSLEnumerations
from yadinassi.enum_types import BSLEnumReference
from test_enum_storage_values import DB, OTHER_DB, UNITS, STATES, PIECE, definitions, Hostile

class Lifetime:
    def __init__(self): self.calls = 0; self.open = True
    def require(self):
        self.calls += 1
        if not self.open: raise BackendError('closed')

class EnumStorageBindingTests(unittest.TestCase):
    def setUp(self):
        self.definitions = definitions()
        self.domain = EnumValueDomain(DB, self.definitions)
        self.namespace = BSLEnumerations(self.definitions)
        self.lifetime = Lifetime()
        self.binding = EnumStorageBinding(self.domain, self.definitions, self.namespace, require_live=self.lifetime.require)
        self.manager = self.namespace._managers['unit']
        self.ref = self.manager._values[0]

    def denied(self, fn, *args, **kwargs):
        with self.assertRaises(BackendError): fn(*args, **kwargs)

    def test_named_key_identity(self):
        self.assertEqual(self.binding.key(self.ref, UNITS), EnumKey(DB, UNITS, PIECE))

    def test_decode_returns_existing_reference(self):
        self.assertIs(self.binding.value(EnumKey(DB, UNITS, PIECE), UNITS), self.ref)

    def test_empty_roundtrip(self):
        key = self.binding.key(self.manager._empty, UNITS)
        self.assertEqual(key, self.domain.empty(UNITS))
        self.assertIs(self.binding.value(key, UNITS), self.manager._empty)

    def test_value_type_is_existing_type(self):
        self.assertIs(self.binding.value_type(UNITS), self.manager._value_type)

    def test_equal_fabricated_reference_denied(self):
        self.denied(self.binding.key, replace(self.ref), UNITS)

    def test_altered_metadata_and_presentation_denied(self):
        for ref in (replace(self.ref, metadata=Hostile()), replace(self.ref, presentation='fake')):
            self.denied(self.binding.key, ref, UNITS)

    def test_cloned_equal_type_denied(self):
        self.denied(self.binding.key, replace(self.ref, value_type=replace(self.ref.value_type)), UNITS)

    def test_foreign_namespace_denied(self):
        other = BSLEnumerations(self.definitions)
        self.denied(self.binding.key, other._managers['unit']._values[0], UNITS)

    def test_measured_assignment_adjusts_but_storage_key_stays_strict(self):
        from decimal import Decimal
        empty=self.manager._empty
        wrong=self.namespace._managers['state']._values[0]
        for value in (wrong,'Piece',Decimal(1),None):
            self.assertIs(self.binding.assigned(value,UNITS),empty)
            self.denied(self.binding.key,value,UNITS)
        self.assertIs(self.binding.assigned(self.ref,UNITS),self.ref)
        self.assertIs(self.binding.assigned(empty,UNITS),empty)

    def test_assignment_never_coerces_foreign_or_fabricated_enums(self):
        other=BSLEnumerations(self.definitions)
        for value in (other._managers['unit']._values[0],other._managers['state']._values[0],
                      replace(self.ref),replace(self.ref,metadata=Hostile())):
            self.denied(self.binding.assigned,value,UNITS)

    def test_unmeasured_assignment_kinds_remain_closed(self):
        from decimal import Decimal
        from yadinassi.dates import BSLDate
        for value in (True,BSLDate(0),[],{},Hostile(),Decimal('NaN'),'x'*4097):
            self.denied(self.binding.assigned,value,UNITS)

    def test_assignment_checks_lifetime_before_adjustment(self):
        self.lifetime.open=False
        for value in (None,'Piece',self.ref):
            with self.assertRaises(BackendError) as caught:self.binding.assigned(value,UNITS)
            self.assertEqual(caught.exception.code,'closed')

    def test_wrong_enum_denied(self):
        self.denied(self.binding.key, self.ref, STATES)
        self.denied(self.binding.value, EnumKey(DB, UNITS, PIECE), STATES)

    def test_wrong_database_denied(self):
        self.denied(self.binding.value, EnumKey(OTHER_DB, UNITS, PIECE), UNITS)

    def test_unknown_value_denied(self):
        self.denied(self.binding.value, EnumKey(DB, UNITS, UUID(int=999)), UNITS)

    def test_hostile_args_no_hooks(self):
        Hostile.touched.clear()
        self.denied(self.binding.key, Hostile(), UNITS)
        self.denied(self.binding.key, self.ref, Hostile())
        self.denied(self.binding.value, Hostile(), UNITS)
        self.denied(self.binding.value_type, Hostile())
        self.assertEqual(Hostile.touched, [])

    def test_guard_on_each_operation_even_invalid(self):
        before = self.lifetime.calls
        for fn, args in ((self.binding.key, (Hostile(), UNITS)), (self.binding.value, (Hostile(), UNITS)), (self.binding.value_type, (Hostile(),))):
            self.denied(fn, *args)
        self.assertEqual(self.lifetime.calls, before + 3)

    def test_expired_lifetime_precedes_invalid_args(self):
        self.lifetime.open = False
        for fn, args in ((self.binding.key, (Hostile(), Hostile())), (self.binding.value, (Hostile(), Hostile())), (self.binding.value_type, (Hostile(),))):
            with self.assertRaises(BackendError) as c: fn(*args)
            self.assertEqual(c.exception.code, 'closed')

    def test_constructor_requires_bound_method(self):
        self.denied(EnumStorageBinding, self.domain, self.definitions, self.namespace, require_live=lambda: None)

    def test_constructor_guard_precedes_invalid_args(self):
        self.lifetime.open = False
        with self.assertRaises(BackendError) as c:
            EnumStorageBinding(Hostile(), Hostile(), Hostile(), require_live=self.lifetime.require)
        self.assertEqual(c.exception.code, 'closed')

    def test_constructor_full_definitions(self):
        changed = (replace(self.definitions[0], comment='changed'), self.definitions[1])
        self.denied(EnumStorageBinding, self.domain, changed, self.namespace, require_live=self.lifetime.require)

    def test_constructor_domain_membership(self):
        self.denied(EnumStorageBinding, EnumValueDomain(DB, ()), self.definitions, self.namespace, require_live=self.lifetime.require)

    def test_namespace_subclass_denied(self):
        class Derived(BSLEnumerations): pass
        self.denied(EnumStorageBinding, self.domain, self.definitions, Derived(self.definitions), require_live=self.lifetime.require)

    def test_replaced_snapshot_invalidates(self):
        self.namespace.metadata = BSLEnumerations(self.definitions).metadata
        self.denied(self.binding.value_type, UNITS)

    def test_replaced_manager_invalidates(self):
        self.namespace._managers['unit'] = BSLEnumerations(self.definitions)._managers['unit']
        self.denied(self.binding.value_type, UNITS)

    def test_replaced_values_invalidates(self):
        self.manager._values = (replace(self.ref), *self.manager._values[1:])
        self.denied(self.binding.key, self.ref, UNITS)

    def test_replaced_empty_invalidates(self):
        self.manager._empty = replace(self.manager._empty)
        self.denied(self.binding.value, self.domain.empty(UNITS), UNITS)

    def test_changed_reference_metadata_invalidates(self):
        object.__setattr__(self.ref, 'metadata', Hostile())
        self.denied(self.binding.key, self.ref, UNITS)

    def test_changed_reference_presentation_invalidates(self):
        object.__setattr__(self.ref, 'presentation', Hostile())
        self.denied(self.binding.key, self.ref, UNITS)

    def test_changed_type_snapshot_invalidates(self):
        object.__setattr__(self.manager._value_type, 'snapshot', Hostile())
        self.denied(self.binding.value_type, UNITS)

    def test_named_lookup_drift_invalidates(self):
        self.manager._named['piece'] = replace(self.ref)
        self.denied(self.binding.key, self.ref, UNITS)

    def test_constructor_modified_presentation_denied(self):
        object.__setattr__(self.ref, 'presentation', 'fake')
        self.denied(EnumStorageBinding, self.domain, self.definitions, self.namespace, require_live=self.lifetime.require)

    def test_reference_subclass_denied(self):
        class Derived(BSLEnumReference): pass
        self.denied(self.binding.key, Derived(self.ref.value_type, self.ref.reference_uuid, self.ref.metadata), UNITS)

    def test_callable_hook_does_not_execute_equality(self):
        Hostile.touched.clear()
        self.denied(EnumStorageBinding, self.domain, self.definitions, self.namespace, require_live=Hostile())
        self.assertEqual(Hostile.touched, [])
