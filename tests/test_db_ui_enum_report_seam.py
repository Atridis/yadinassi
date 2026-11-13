"""Integration probe: full forms grant plus durable enum query pipeline."""
import unittest
from unittest.mock import patch
import test_configuration_inventory_enum_app as enum_fixture
from yadinassi.catalog_backend import BackendError
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.inventory_enum_runtime import query_owner


class EnumFormsReportSeamTests(unittest.TestCase):
    setUp = enum_fixture.EnumApplicationTests.setUp
    rpc = enum_fixture.EnumApplicationTests.rpc
    open = enum_fixture.EnumApplicationTests.open
    event = enum_fixture.EnumApplicationTests.event
    choose = enum_fixture.EnumApplicationTests.choose

    def test_discovery_does_not_reexport_fixture_test_cases(self):
        import sys
        suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
        def leaves(node):
            if isinstance(node, unittest.TestSuite):
                for child in node:
                    yield from leaves(child)
            else:
                yield node
        ids = [test.id() for test in leaves(suite)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(name.startswith(__name__ + ".") for name in ids))

    def interpreter(self, saved=False):
        sid = self.open('Catalog.Products.Form.Card')
        if saved:
            self.event(sid, 'change', control='CodeInput', value='P1')
            self.event(sid, 'change', control='DescriptionInput', value='Product')
            self.choose(sid, 'UnitInput')
            self.event(sid, control='SaveButton')
        return sid, self.broker.objects[sid]._interpreter

    def query(self, vm, text, table=None, manager=None):
        query = vm.execute('New Query')
        query.set_member('Text', text)
        if table is not None:
            query.set_parameter('Input', table)
        if manager is not None:
            query.set_member('TempTablesManager', manager)
        return query

    def test_empty_enum_domain_survives_unload_and_external_query(self):
        _, vm = self.interpreter()
        table = self.query(vm, 'SELECT Unit FROM Catalog.Products').execute().unload()
        result = self.query(vm, 'SELECT Unit FROM &Input', table).execute().unload()
        self.assertEqual(len(result.rows), 0)
        self.assertIs(result.columns.items[0].value_type.types[0], table.columns.items[0].value_type.types[0])

    def test_saved_enum_roundtrips_package_and_manager(self):
        _, vm = self.interpreter(saved=True)
        manager = BSLTempTablesManager()
        self.addCleanup(manager.close)
        result = self.query(vm, 'SELECT Ref,Unit INTO Prepared FROM Catalog.Products; '
                            'SELECT Unit FROM Prepared', manager=manager).execute()
        table = result.unload()
        self.assertEqual(len(table.rows), 1)
        expected = table.rows[0].get_member('Unit')
        self.assertFalse(expected.is_empty())
        reused = self.query(vm, 'SELECT Unit FROM Prepared', manager=manager).execute().unload()
        self.assertIs(reused.rows[0].get_member('Unit'), expected)
        external = self.query(vm, 'SELECT Unit FROM &Input', table).execute().unload()
        self.assertIs(external.rows[0].get_member('Unit'), expected)

    def test_retired_form_owner_cannot_reuse_detached_enum_table(self):
        sid, vm = self.interpreter(saved=True)
        table = self.query(vm, 'SELECT Unit FROM Catalog.Products').execute().unload()
        descriptor = table.columns.items[0].value_type
        self.broker.exchange({'operation': 'retire', 'session': sid, 'payload': {}})
        from yadinassi.query_reference_tables import description_binding
        with self.assertRaises(BackendError):
            description_binding(descriptor)

    def test_unknown_configuration_type_is_rejected_without_hooks_or_reader(self):
        _, vm = self.interpreter()
        scope = vm._metadata._enum_storage_scope
        original = scope.configuration
        class Foreign:
            @property
            def profile(self):
                raise AssertionError('foreign profile hook')
        scope.configuration = Foreign()
        try:
            with patch.object(scope.backend, 'begin_read', side_effect=AssertionError('reader')):
                with self.assertRaises(BackendError):
                    query_owner(vm._catalogs)
        finally:
            scope.configuration = original
