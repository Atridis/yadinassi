"""BSL surface tests. Storage is independently covered with actual CONFIG bytes."""
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.database_context import FileDBContext


class CatalogMetadataRuntimeTests(unittest.TestCase):
    def runtime(self, names=('DifferentCatalog',)):
        context = Mock(spec=FileDBContext)
        context.catalog_metadata.return_value = tuple(
            SimpleNamespace(name=name, metadata_uuid=str(i)) for i, name in enumerate(names))
        runtime = Interpreter(database_context=context)
        self.addCleanup(runtime.close)
        return runtime, context

    def test_lookup_is_lazy_even_without_database(self):
        runtime = Interpreter()
        self.addCleanup(runtime.close)
        for text in ('Metadata', 'Метаданные.Справочники',
                     'Если Ложь Тогда Metadata.Catalogs.Count(); КонецЕсли;'):
            runtime.execute(text)
        for text in ('Metadata.Catalogs.Count()', 'Metadata.Catalogs.Find("X")',
                     'Metadata.Catalogs.X', 'Metadata.Catalogs[0]'):
            with self.subTest(text=text), self.assertRaisesRegex(BSLRuntimeError, 'db required'):
                runtime.execute(text)
        self.assertEqual(runtime.execute('20 + 22'), Decimal(42))
        runtime.execute('Попытка Metadata.Catalogs.Count(); Исключение X = 42; КонецПопытки;')
        self.assertEqual(runtime.execute('X'), Decimal(42))

    def test_aliases_dynamic_names_identity_and_one_snapshot(self):
        runtime, context = self.runtime(('ИнойСправочник',))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(1))
        self.assertEqual(runtime.execute('Метаданные.Справочники.ИнойСправочник.Имя'), 'ИнойСправочник')
        self.assertEqual(runtime.execute('Metadata.Catalogs[0].FullName()'), 'Справочник.ИнойСправочник')
        self.assertTrue(runtime.execute('(Metadata.Catalogs.Find("инойсправочник") = Метаданные.Справочники.ИнойСправочник)'))
        self.assertTrue(runtime.execute('(Metadata.Catalogs["ИНОЙСПРАВОЧНИК"] = Metadata.Catalogs[0])'))
        context.catalog_metadata.assert_called_once_with()

    def test_multi_names_count_not_invented_numeric_order(self):
        runtime, _ = self.runtime(('Second', 'First'))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(2))
        self.assertEqual(runtime.execute('Metadata.Catalogs.First.Name'), 'First')
        with self.assertRaisesRegex(BSLRuntimeError, 'ordering is unsupported'):
            runtime.execute('Metadata.Catalogs[0]')

    def test_find_general_scalar_rule_and_missing_name(self):
        runtime, _ = self.runtime()
        for text in ('"Absent"', '1', '42', '-7', '1.5'):
            with self.subTest(text=text):
                self.assertIsNone(runtime.execute(f'Metadata.Catalogs.Find({text})'))
        for text in ('Истина', 'Undefined', 'Новый Массив'):
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError):
                runtime.execute(f'Metadata.Catalogs.Find({text})')

    def test_readonly_arity_bounds_and_excluded_surfaces(self):
        runtime, _ = self.runtime()
        failures = ('Metadata.Catalogs.Find()', 'Metadata.Catalogs.Find("DifferentCatalog", 1)',
                    'Metadata.Catalogs.Count(1)', 'Metadata.Catalogs.Absent',
                    'Metadata.Catalogs[-1]', 'Metadata.Catalogs[1]', 'Metadata.Catalogs[0.5]',
                    'Metadata.Catalogs[Истина]', 'Metadata.Catalogs["Absent"]',
                    'Metadata.Catalogs.DifferentCatalog.Name = "Changed";',
                    'Metadata.Catalogs[0] = Undefined;', 'Metadata.Catalogs = Undefined;',
                    'Metadata.Catalogs.DifferentCatalog.Attributes',
                    'Metadata.Catalogs.DifferentCatalog.FullName(1)',
                    'String(Metadata)', 'String(Metadata.Catalogs)',
                    'String(Metadata.Catalogs[0])',
                    'Для Каждого X Из Metadata.Catalogs Цикл КонецЦикла;')
        for text in failures:
            with self.subTest(text=text), self.assertRaises(BSLRuntimeError): runtime.execute(text)
        self.assertEqual(runtime.execute('Metadata.Catalogs[0].Name'), 'DifferentCatalog')

    def test_context_availability_and_missing_database_are_lazy(self):
        for directive in ('', '&AtServer\n', '&AtServerNoContext\n',
                          '&AtClientAtServerNoContext\n'):
            with self.subTest(directive=directive):
                runtime, _ = self.runtime()
                runtime.execute(directive + 'Function ReadName() '
                                'Return Metadata.Catalogs[0].Name; EndFunction')
                self.assertEqual(runtime.execute('ReadName()'), 'DifferentCatalog')
                missing = Interpreter()
                self.addCleanup(missing.close)
                missing.execute(directive + 'Function Lazy() '
                                'Return Metadata.Catalogs = Метаданные.Справочники; EndFunction\n'
                                + directive + 'Function ReadName() '
                                'Return Metadata.Catalogs[0].Name; EndFunction')
                self.assertTrue(missing.execute('Lazy()'))
                with self.assertRaisesRegex(BSLRuntimeError, 'db required'):
                    missing.execute('ReadName()')

    def test_method_name_catalogs_remain_accessible_without_guessing_precedence(self):
        runtime, _ = self.runtime(('Count', 'Find'))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Count()'), Decimal(2))
        self.assertEqual(runtime.execute('Metadata.Catalogs.Find("Count").Name'), 'Count')
        self.assertEqual(runtime.execute('Metadata.Catalogs["Find"].Name'), 'Find')
        with self.assertRaisesRegex(BSLRuntimeError, 'method-name property'):
            runtime.execute('Metadata.Catalogs.Count')

    def test_failed_load_is_not_cached(self):
        runtime, context = self.runtime()
        context.catalog_metadata.side_effect = [ValueError('unsupported image'),
            (SimpleNamespace(name='Recovered'),)]
        with self.assertRaises(BSLRuntimeError): runtime.execute('Metadata.Catalogs.Count()')
        self.assertEqual(runtime.execute('Metadata.Catalogs[0].Name'), 'Recovered')

    def test_ambiguous_casefold_rejected(self):
        runtime, _ = self.runtime(('Same', 'same'))
        with self.assertRaisesRegex(BSLRuntimeError, 'ambiguous'):
            runtime.execute('Metadata.Catalogs.Count()')

    def test_index_argument_can_be_read_without_mutation(self):
        runtime, _ = self.runtime()
        runtime.execute('Функция Read(Value) Возврат Value.Name; КонецФункции')
        self.assertEqual(runtime.execute('Read(Metadata.Catalogs[0])'), 'DifferentCatalog')
        runtime.execute('Процедура Write(Value) Value = Undefined; КонецПроцедуры')
        with self.assertRaisesRegex(BSLRuntimeError, 'read-only'):
            runtime.execute('Write(Metadata.Catalogs[0]);')

if __name__ == '__main__': unittest.main()
