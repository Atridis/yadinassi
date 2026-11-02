"""SQLite MVP explicitly refuses unported document/register data surfaces."""
import unittest
from uuid import UUID
from dataclasses import FrozenInstanceError
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.document_types import BSLDocumentType, BSLDocumentReference
from yadinassi.serialization import value_to_string_internal

class DocumentScenarioTests(unittest.TestCase):
    def test_unported_namespaces_fail_without_physical_access(self):
        vm=Interpreter()
        for code in ('Documents.Orders','InformationRegisters.Prices','Type("DocumentRef.Orders")',
                     'Type("InformationRegisterManager.Prices")','Metadata.Documents.Count()',
                     'Metadata.InformationRegisters.Count()'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError):vm.execute(code)
        self.assertIsNotNone(vm.execute('Type("String")'))
    def test_neutral_document_reference_identity_remains_immutable_and_codec_closed(self):
        snapshot=object();kind=BSLDocumentType(UUID(int=1),'Orders',snapshot)
        ref=BSLDocumentReference(kind,UUID(int=2))
        self.assertEqual(ref,BSLDocumentReference(kind,UUID(int=2)))
        self.assertNotEqual(ref,BSLDocumentReference(BSLDocumentType(UUID(int=1),'Orders',object()),UUID(int=2)))
        with self.assertRaises(FrozenInstanceError):ref.reference_uuid=UUID(int=3)
        with self.assertRaises((ValueError,TypeError)):value_to_string_internal(ref)
