"""Direct value-manager admission, revocation and typed Value references."""
import unittest
from unittest.mock import patch
import test_python_direct_source_storage_guards as fixtures
import test_python_direct_source_query as query_fixtures
from test_source_constant_store import configuration
from yadinassi.db.metadata.source_constants_runtime import SourceConstants
from yadinassi.db.metadata.source_constant_managers import SourceConstantValueManager,_ValueInterpreter,create_manager
from yadinassi.execution.direct.source.python_direct_source_constants import check_manager,bind_export
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class DirectConstantSecurity(unittest.TestCase):
    app=fixtures.DirectSourceStorageGuards.app
    boundary=query_fixtures.DirectSourceQueryTests.boundary

    def test_legacy_attached_manager_has_no_direct_seal(self):
        app,caller=self.app(configuration());owner=SourceConstants(app)
        manager=SourceConstantValueManager(owner,'Text');vm=_ValueInterpreter(manager,app)
        self.addCleanup(vm.close);manager.interpreter=vm
        with self.assertRaisesRegex(BoundaryViolation,'admission'):check_manager(manager,caller)

    def test_bound_export_rechecks_closed_manager_and_declaration(self):
        package=configuration({'Constants/Text/Ext/ValueManagerModule.bsl':b'Value="initial"; Function Answer() Export Return Value; EndFunction'})
        app,caller=self.app(package)
        with self.boundary(app,caller) as boundary:
            manager=create_manager(caller,SourceConstants(app),'Text')
            bound=bind_export(boundary,manager,'Answer',require_value=True,argument_count=0)
            self.assertEqual(bound(),'initial')
            node=manager.interpreter.server_routines['answer'];old=node.is_function
            node.is_function=False
            try:
                with self.assertRaises(BoundaryViolation):bound()
            finally:node.is_function=old
            manager._closed=True
            with self.assertRaises(BoundaryViolation):bound()

    def test_foreign_manager_refused_before_export_lookup(self):
        package=configuration({'Constants/Text/Ext/ValueManagerModule.bsl':b'Function Answer() Export Return "ok"; EndFunction'})
        app,caller=self.app(package);other,other_caller=self.app(package)
        with self.boundary(other,other_caller):manager=create_manager(other_caller,SourceConstants(other),'Text')
        with self.boundary(app,caller) as boundary,patch.object(manager,'exported_routine',side_effect=AssertionError('foreign lookup')):
            with self.assertRaises(BoundaryViolation):bind_export(boundary,manager,'Answer')


if __name__=='__main__':unittest.main()
