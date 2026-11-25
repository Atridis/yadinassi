"""Client command enum provenance and selected-only lookup."""
import re
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_configuration_enumerations import enum_files
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.source import python_direct_source_enums
from yadinassi.types.values import HostFunction


class DirectConfigurationEnumerationTests(unittest.TestCase):
    def application(self, files=None):
        app = ConfigurationApplication.from_files(enum_files() if files is None else files)
        self.addCleanup(lambda: app.close(force=True))
        app.start()
        return app

    def test_touches_only_selected_enum_without_source_preflight(self):
        files = enum_files()
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'</ChildObjects>', b'<Enum>Unused</Enum></ChildObjects>')
        files['Enums/Unused.xml'] = re.sub(rb'uuid="[^"]+"',
            lambda _: b'uuid="' + str(uuid4()).encode() + b'"',
            files['Enums/Status.xml'].replace(b'<Name>Status</Name>', b'<Name>Unused</Name>'))
        app = self.application(files)
        root = app.interpreter._metadata._enumerations
        root._managers['unused'] = object()  # Unrelated manager isn't opened.
        with patch.object(python_direct_source_enums, '_managers', side_effect=AssertionError('full enum scan')):
            self.assertTrue(app.execute('(Tools.Pick()=Перечисления.Status.Active)'))
            self.assertTrue(app.execute('(TypeOf(Enums.Status.Active)=Type("EnumRef.Status"))'))
            self.assertEqual(app.execute('Metadata.Enums.Status.EnumValues.Get(0).Name'), 'Active')
            with self.assertRaises(BoundaryViolation):
                app.execute('Enums.Unused.Active')

    def test_replaced_namespace_and_foreign_transfers_denied(self):
        files = enum_files()
        app, other = self.application(files), self.application(files)
        other_root = other.interpreter._metadata._enumerations
        app.interpreter.variables['selected'] = other.execute('Enums.Status.Active')
        with self.assertRaises(BoundaryViolation):
            app.execute('Selected')
        del app.interpreter.variables['selected']
        with patch.object(app.interpreter._metadata, '_enumerations', other_root):
            with self.assertRaises(BoundaryViolation):
                app.execute('Enums.Status.Active')
        self.assertTrue(app.execute('(Enums.Status.Active=Enums.Status.Active)'))

    def test_client_enum_service_checks_selected_registry_binding(self):
        app = self.application()
        interpreter = app.interpreter
        seen = []
        replacement = HostFunction('String', seen.append)
        with patch.dict(interpreter.functions, string=replacement), self.assertRaises(BoundaryViolation):
            app.execute('String(Enums.Status.Active)')
        self.assertEqual(seen, [])
