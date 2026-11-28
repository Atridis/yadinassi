"""Existing enum identity and persistence contracts with legacy execution poisoned."""
import unittest
import test_source_enumeration_runtime as runtime
import test_source_enum_constants as constants


class NoVM:
    def setUp(self):
        super().setUp()


class SourceEnumsNoVM(NoVM,runtime.SourceEnumerationRuntimeTests):
    def test_metadata_iteration_and_saved_method(self):
        _,out=self.run_source('M=Enums.Status; F=M.Count; Message(F()); '
            'For Each V In M Do Message(V.Metadata().Name); EndDo; '
            'Message(M.Metadata().Name);')
        self.assertEqual(out,['2','Status','Status','Status'])


class SourceEnumConstantsNoVM(NoVM,constants.EnumConstantsTests):
    pass


if __name__=='__main__':unittest.main()
