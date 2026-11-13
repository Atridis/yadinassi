"""Offline declaration guard, not browser execution or native evidence."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeletionMarksBrowserContractTests(unittest.TestCase):
    def test_single_opt_in_original_source_scenario_keeps_acquisition_bounds(self):
        source = (ROOT / 'tests/browser_ui/reference_rows_browser_qa.mjs').read_text(encoding='utf-8')
        fixture = (ROOT / 'tests/browser_ui/reference_rows_fixture.py').read_text(encoding='utf-8')
        for required in (
            "'--demo-deletion-marks'", "'demo_products_deletion_marks_v1'",
            "'original_deletion_marks_refs_refusal_bypass_recovery_restart'",
            "'mark_kind_and_refuse_product'", "'unmark_kind_and_mark_warehouse'",
            "'mark_product_bypasses_original_validation'", "'restart_marked_product'",
            "'unmark_product_refused_and_discarded'", "'recover_warehouse_then_product'",
            "'checkbox_persisted_before_save'", "'refused_save_changed_durable_record_or_row'",
            "'refusal_lost_unmark_draft'", "'discard_changed_marked_identity_or_revision'",
            "'deletion_mark_changed_identity'", "'reference_save_changed_other_revision'",
            "'viewport_overflow'", "'narrow_checkbox_missing'",
            "'examples/demo'", "'source_bytes_changed'",
            "chromiumSandbox:true", "if(rpc>=200)", 'expectedScenarios:1',
            "assert.equal(results.length,1)", "allowedRequest(target,origin)",
        ):
            self.assertIn(required, source)
        self.assertEqual(source.count('chromium.launch('), 1)
        self.assertEqual(source.count('await scenario('), 1)
        for forbidden in ('route.fulfill', 'addInitScript', 'ignoreDefaultArgs', 'args:', 'tracing.start', 'recordHar'):
            self.assertNotIn(forbidden, source)
        self.assertIn('create_main_demo', fixture)
        self.assertIn('import_main_demo_configuration(files, profile=PROFILE)', fixture)
        self.assertNotIn('create_demo_products', fixture)
        self.assertIn("'audit-deletion-marks': lambda root: audit_products(root, allow_marks=True)", fixture)
        self.assertIn("SQLiteCatalogBackend(root / 'owned.sqlite', read_only=True)", fixture)
        self.assertIn("'rowIdentity': str(row.identity)", fixture)
        self.assertIn("product.values != (kind.key,)", fixture)
        self.assertIn("row.values != (warehouse.key,)", fixture)


if __name__ == '__main__':
    unittest.main()
