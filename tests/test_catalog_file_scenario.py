"""BSL through real physical parsing of invented offline bytes, not native proof."""
from pathlib import Path
import tempfile
import unittest

import test_catalog_binding_integration as fixture
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.database_context import FileDBContext


class CatalogFileScenarioTests(unittest.TestCase):
    def runtime(self, value):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / '1Cv8.1CD'
        with path.open('wb') as stream:
            for number in range(value.page_count):
                stream.write(value.pages.get(number, bytes(fixture.P)))
        original = path.read_bytes()
        self.addCleanup(lambda: self.assertEqual(path.read_bytes(), original))
        context = FileDBContext(path.parent)
        identities = context.catalog_metadata()
        selected = next(entry for entry in identities
                        if entry.metadata_uuid == fixture.config_fixture.KEYS[0])
        output = []
        runtime = Interpreter(output.append, database_context=context)
        self.addCleanup(runtime.close)
        runtime.variables['catalogname'] = selected.name
        return runtime, output

    def test_file_manager_selection_fields_reference_type_lookup(self):
        runtime, output = self.runtime(fixture.source())
        runtime.execute('''
M = Catalogs[CatalogName];
S = M.Select();
While S.Next() Do
 Message(S.Code); Message(S.Payload); Message(S.Amount);
 Message(S.Description); Message(S.DeletionMark);
 R = S.Ref;
 Message(TypeOf(R) = Type("CatalogRef." + CatalogName));
 Message(TypeOf(TypeOf(R)) = Type("Type"));
 Message(R.Metadata() = Metadata.Catalogs[CatalogName]);
 Message(R = M.FindByCode(S.Code));
 Message(R = M.GetRef(R.UUID()));
 Message(R.Payload); Message(R.Amount);
 Message(ValueIsFilled(R));
EndDo;
Message(M.FindByCode("missing").IsEmpty());
Message(S.Next());
S.Reset(); Message(S.Next()); Message(S.Code);
''')
        self.assertEqual(output, ['K1', 'alpha', '1,25', '', 'Нет',
                                  'Да', 'Да', 'Да', 'Да', 'Да', 'alpha', '1,25',
                                  'Да', 'Да', 'Нет', 'Да', 'K1'])

    def test_both_physical_empty_shapes(self):
        for length in (0, 127):
            with self.subTest(length=length):
                value = fixture.source()
                value.page(40)[16:24] = length.to_bytes(8, 'little')
                runtime, output = self.runtime(value)
                runtime.execute('''
M = Справочники[CatalogName];
S = M.Выбрать();
Сообщить(S.Следующий()); Сообщить(S.Следующий());
S.Сбросить(); Сообщить(S.Следующий());
Сообщить(M.НайтиПоКоду("K1").Пустая());
Сообщить(ЗначениеЗаполнено(M.ПустаяСсылка()));
''')
                self.assertEqual(output, ['Нет', 'Нет', 'Нет', 'Да', 'Нет'])

    def test_marked_for_deletion_remains_an_active_row(self):
        value = fixture.source()
        value.page(43)[127 + 33] = 1
        runtime, output = self.runtime(value)
        runtime.execute('''
M = Catalogs[CatalogName]; S = M.Select();
Message(S.Next()); Message(S.DeletionMark);
Message(M.FindByCode("K1") = S.Ref); Message(S.Next());
''')
        self.assertEqual(output, ['Да', 'Да', 'Да', 'Нет'])

    def test_unmeasured_multiple_records_and_free_slots_stay_rejected(self):
        for shape, error in (('multiple', 'active_records'),
                             ('freed', 'nonreserved_free_slot')):
            with self.subTest(shape=shape):
                value = fixture.source()
                if shape == 'multiple':
                    value.page(43)[254:381] = value.page(43)[127:254]
                    value.page(40)[16:24] = (381).to_bytes(8, 'little')
                else:
                    value.page(43)[127] = 1
                runtime, output = self.runtime(value)
                with self.assertRaisesRegex(BSLRuntimeError, error):
                    runtime.execute('S = Catalogs[CatalogName].Select();')
                self.assertEqual(output, [])


if __name__ == '__main__':
    unittest.main()
