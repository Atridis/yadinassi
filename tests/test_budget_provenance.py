"""The exhaustive budget optimization owns no shared mutable provenance."""
import unittest
from types import SimpleNamespace
from unittest import mock

from budget_provenance import copy_provenance, freeze_provenance, one_provenance_build


class BudgetProvenanceTests(unittest.TestCase):
    def test_snapshot_is_immutable_and_every_report_is_recursively_independent(self):
        original = {'source_file_count': 118, 'nested': {'files': ['original']}}
        template = freeze_provenance(original)
        self.assertIsInstance(template, bytes)
        original['nested']['files'].append('changed after capture')
        first, second = copy_provenance(template), copy_provenance(template)
        first['source_file_count'] = 512
        first['nested']['files'].append('tampered report')
        self.assertEqual(second, {'source_file_count': 118, 'nested': {'files': ['original']}})
        self.assertEqual(copy_provenance(template), second)

    def test_separate_tests_can_observe_changed_sources(self):
        first = freeze_provenance({'hash': 'before'})
        second = freeze_provenance({'hash': 'after'})
        self.assertNotEqual(first, second)
        self.assertEqual(copy_provenance(first), {'hash': 'before'})
        self.assertEqual(copy_provenance(second), {'hash': 'after'})

    def test_call_guard_runs_real_builder_and_rejects_repeated_hashing(self):
        observed = []
        full = SimpleNamespace(interpreter_provenance=lambda: observed.append('hashed'))

        @one_provenance_build(full)
        def once(case):
            full.interpreter_provenance()

        once(self)
        self.assertEqual(observed, ['hashed'])

        @one_provenance_build(full)
        def twice(case):
            full.interpreter_provenance()
            full.interpreter_provenance()

        with self.assertRaisesRegex(AssertionError, 'one real provenance build'):
            twice(self)
        self.assertEqual(observed, ['hashed', 'hashed', 'hashed'])
        self.assertNotIsInstance(full.interpreter_provenance, mock.Mock)
