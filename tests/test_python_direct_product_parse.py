"""Parsed product source reuse retains current admission and fresh event state."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch
from yadinassi.syntax import parser
from yadinassi.form_event_simulation import simulate_product_form_event
from yadinassi.execution_policy import execution_backend_policy
from yadinassi.catalog_backend import BackendError
import test_product_form_events as fixture

class ProductParseTests(TestCase):
    def setUp(self):
        self.f=fixture.ProductFormEventTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def test_repeated_events_parse_once_and_state_is_fresh(self):
        with patch.object(parser,'parse',wraps=parser.parse) as parse:
            self.f.card.set_member('Description',' x ')
            first=self.f.run_event('DescriptionOnChange')
            self.assertTrue(first.messages)
            self.f.card.set_member('Description','  New description  ')
            second=self.f.run_event('DescriptionOnChange')
            self.assertFalse(second.messages)
            self.assertEqual(self.f.card.get_member('Description'),'New description')
        self.assertEqual(parse.call_count,1)
        self.assertTrue(self.f.card.is_new())
    def test_source_drift_is_rejected_even_with_warm_slot(self):
        self.f.run_event('DescriptionOnChange');cached=self.f.card._manager._direct_product_program
        for form,obj in ((fixture.FORM+b'\n',fixture.OBJECT),(fixture.FORM,fixture.OBJECT+b'\n')):
            with self.subTest(form_changed=form!=fixture.FORM),patch.object(parser,'parse',side_effect=AssertionError('parse after denial')):
                with self.assertRaisesRegex(ValueError,'original source'):
                    simulate_product_form_event(form,obj,self.f.card,event='DescriptionOnChange')
        self.assertIs(self.f.card._manager._direct_product_program,cached)
    def test_schema_reference_target_and_current_row_stay_live(self):
        self.f.run_event('DescriptionOnChange');m=self.f.card._manager;old=m._schema
        try:
            m._schema=replace(old,name='Other')
            with self.assertRaisesRegex(ValueError,'schema'):self.f.run_event('DescriptionOnChange')
        finally:m._schema=old
        target=m._catalogs._manager_by_metadata_uuid(old.fields[0].target_catalog_id);schema=target._schema
        try:
            target._schema=replace(schema,name='Other')
            with self.assertRaisesRegex(ValueError,'reference target'):self.f.run_event('DescriptionOnChange')
        finally:target._schema=schema
        rows=self.f.card.get_member('Склады');row=rows.add();rows.delete(row)
        with self.assertRaisesRegex(ValueError,'stale current row'):
            self.f.run_event('WarehouseOnChange',current_row_id=row._identity)
    def test_cached_parse_does_not_retain_cancellation_or_receiver(self):
        self.assertFalse(self.f.run_event('BeforeWriteAtServer').cancel)
        m=self.f.card._manager;other=m.create_item()
        other.set_member('Description','Valid description')
        result=simulate_product_form_event(fixture.FORM,fixture.OBJECT,other,event='BeforeWriteAtServer')
        self.assertTrue(result.cancel);self.assertTrue(result.messages)
        self.assertFalse(self.f.run_event('BeforeWriteAtServer').cancel)
    def test_pending_write_still_rejects_before_cached_execution(self):
        self.f.run_event('DescriptionOnChange')
        with patch.object(self.f.card,'_pending_write',object()):
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):
                self.f.run_event('DescriptionOnChange')
    def test_legacy_does_not_consult_or_fill_direct_slot(self):
        m=self.f.card._manager
        for backend in ('interpreter', 'compiled-strict'):
            with self.subTest(backend=backend),execution_backend_policy(backend),patch.object(parser,'parse',wraps=parser.parse) as parse:
                self.f.run_event('DescriptionOnChange');self.f.run_event('DescriptionOnChange')
            self.assertEqual(parse.call_count,2)
            self.assertFalse(hasattr(m,'_direct_product_program'))
