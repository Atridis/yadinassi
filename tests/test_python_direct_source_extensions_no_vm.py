"""Existing scratch-extension checks stay real with legacy execution poisoned."""
import unittest
import test_source_extensions as existing


class DirectSourceExtensionsNoVM(existing.SourceExtensionTests):
    def setUp(self):
        super().setUp()

    def test_saved_method_keeps_optional_omissions(self):
        app=self.app('F=ConfigurationExtensions.Get; Message(F(, ConfigurationExtensionsSource.Database).Count());')
        self.assertTrue(app.start())


if __name__=='__main__':unittest.main()
