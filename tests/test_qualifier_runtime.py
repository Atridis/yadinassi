"""Interpreter integration for owner-observed standalone qualifiers."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError


class QualifierRuntimeTests(unittest.TestCase):
    def test_bilingual_constructors_and_properties(self):
        vm = Interpreter()
        for en, ru, prop, rusprop, expected in (
            ('NumberQualifiers(5,2)', 'КвалификаторыЧисла(5,2)', 'Digits', 'Разрядность', Decimal(5)),
            ('StringQualifiers(3)', 'КвалификаторыСтроки(3)', 'Length', 'Длина', Decimal(3)),
            ('BinaryDataQualifiers(3)', 'КвалификаторыДвоичныхДанных(3)', 'Length', 'Длина', Decimal(3)),
        ):
            with self.subTest(en=en):
                vm.execute('a = New ' + en + '; b = Новый ' + ru + ';')
                self.assertEqual(vm.execute('a.' + prop), expected)
                self.assertEqual(vm.execute('b.' + rusprop), expected)
                self.assertTrue(vm.execute('(TypeOf(a) = TypeOf(b))'))
        vm.execute('d = New DateQualifiers(DateFractions.Date);')
        self.assertTrue(vm.execute('(d.DateFractions = ЧастиДаты.Дата)'))

    def test_namespaces_are_bilingual_read_only_and_not_numeric(self):
        vm = Interpreter()
        for en, ru in (('AllowedSign.Any', 'ДопустимыйЗнак.Любой'),
                       ('AllowedLength.Variable', 'ДопустимаяДлина.Переменная'),
                       ('DateFractions.DateTime', 'ЧастиДаты.ДатаВремя')):
            self.assertTrue(vm.execute('(' + en + ' = ' + ru + ')'))
            with self.assertRaises(BSLRuntimeError):
                vm.execute(en + ' = 0;')
            with self.assertRaises(BSLRuntimeError):
                vm.execute('Number(' + en + ')')

    def test_instance_properties_are_read_only(self):
        vm = Interpreter()
        for ctor, prop in (('NumberQualifiers(5)', 'Digits'),
                           ('StringQualifiers(3)', 'Length'),
                           ('BinaryDataQualifiers(3)', 'Length'),
                           ('DateQualifiers()', 'DateFractions')):
            vm.execute('q = New ' + ctor + ';')
            previous = vm.execute('q.' + prop)
            with self.assertRaises(BSLRuntimeError):
                vm.execute('q.' + prop + ' = 0;')
            self.assertEqual(vm.execute('q.' + prop), previous)


if __name__ == '__main__':
    unittest.main()
