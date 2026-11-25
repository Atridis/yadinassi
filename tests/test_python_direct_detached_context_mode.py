"""Detached mode omits context audits, not local owner authorization."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import make_boundary
from yadinassi.execution.direct.python_direct_table_iteration import resolve
from yadinassi.execution.direct.python_direct_table_references import bind


class DetachedContextModeTests(unittest.TestCase):
    def boundary(self, verify):
        vm = Interpreter()
        self.addCleanup(vm.close)
        boundary = make_boundary(vm)
        boundary._verify_context = verify
        boundary.enter()
        self.addCleanup(boundary.leave)
        return boundary

    def table(self):
        table = BSLValueTable()
        table.columns.add('Amount')
        row = table.add()
        row.set_member('Amount', Decimal(2))
        return table, row

    def test_table_detached_bind_and_iteration_omit_only_context_verification(self):
        boundary = self.boundary(False)
        table, row = self.table()
        with patch.object(boundary, '_check', side_effect=AssertionError('context audit')):
            self.assertEqual(boundary.get_member(row, 'Amount'), Decimal(2))
            reference = bind(boundary, row, 'Amount')
            reference.set(Decimal(3))
            self.assertEqual(reference.get(), Decimal(3))
            self.assertEqual(list(resolve(boundary, table)()), [row])
            row.table = BSLValueTable()
            with self.assertRaises(BoundaryViolation):
                reference.get()

    def test_strict_table_operations_retain_context_verification(self):
        boundary = self.boundary(True)
        table, row = self.table()
        with patch.object(boundary, '_check', side_effect=BoundaryViolation('revoked')):
            for operation in (lambda: boundary.get_member(row, 'Amount'),
                              lambda: bind(boundary, row, 'Amount'),
                              lambda: resolve(boundary, table)):
                with self.assertRaisesRegex(BoundaryViolation, 'revoked'):
                    operation()

    def test_tree_relaxed_mode_keeps_local_activation_checks(self):
        boundary = self.boundary(False)
        boundary.vm.execute('T=New ValueTree;T.Columns.Add("X");R=T.Rows.Add();R.X=2;')
        row = boundary.vm.variables['r']
        with patch.object(boundary, '_check', side_effect=AssertionError('context audit')):
            self.assertEqual(boundary.get_member(row, 'X'), Decimal(2))
            boundary.leave()
            with self.assertRaisesRegex(BoundaryViolation, 'activation expired'):
                boundary.get_member(row, 'X')

    def test_detached_metadata_keeps_its_own_liveness(self):
        from test_source_metadata import files
        from yadinassi.configuration.configuration_source import import_source
        from yadinassi.configuration.configuration_source_metadata import SourceMetadataRoot
        root = SourceMetadataRoot(import_source(files()))
        boundary = self.boundary(False)
        with patch.object(boundary, '_check', side_effect=AssertionError('context audit')):
            self.assertEqual(boundary.get_member(root, 'Name'), 'Demo')
            subjects = boundary.get_member(root, 'Subsystems')
            count = boundary.resolve_member(subjects, 'Count')
            self.assertEqual(count(), Decimal(2))
            boundary.leave()
            with self.assertRaisesRegex(BoundaryViolation, 'boundary expired'):
                count()

    def test_fixed_array_uses_canonical_detached_member_route(self):
        from yadinassi.types.values import BSLArray, BSLFixedArray
        boundary = self.boundary(False)
        mutable = BSLArray()
        mutable.add(Decimal(4))
        array = BSLFixedArray(mutable)
        with patch.object(boundary, '_check', side_effect=AssertionError('context audit')):
            self.assertEqual(boundary.resolve_member(array, 'Get')(Decimal(0)), Decimal(4))

    def test_database_receivers_do_not_use_relaxed_collection_authority(self):
        boundary = self.boundary(False)
        with patch.object(boundary, '_check_effect', side_effect=BoundaryViolation('DB audit')):
            with self.assertRaisesRegex(BoundaryViolation, 'DB audit'):
                boundary.get_member(boundary.vm._catalogs, 'Products')
