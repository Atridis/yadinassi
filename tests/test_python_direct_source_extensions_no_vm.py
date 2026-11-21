"""Existing scratch-extension checks stay real with legacy execution poisoned."""
import unittest
from unittest.mock import patch
import test_source_extensions as existing
from yadinassi.runtime import Interpreter


class DirectSourceExtensionsNoVM(existing.SourceExtensionTests):
    def setUp(self):
        super().setUp()
        for name in ('_execute_program','call_routine'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start();self.addCleanup(poison.stop)

    def test_saved_method_keeps_optional_omissions(self):
        app=self.app('F=ConfigurationExtensions.Get; Message(F(, ConfigurationExtensionsSource.Database).Count());')
        self.assertTrue(app.start())


if __name__=='__main__':unittest.main()
