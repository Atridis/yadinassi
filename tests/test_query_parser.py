"""Pure grammar tests: no SQL execution, native process or shared fixture."""
from pathlib import Path
import sys
import unittest
from decimal import Decimal
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi.query_parser import parse_query, Parameter, Predicate, MAX_TEXT


class QueryParserTests(unittest.TestCase):
    def test_english_projection_alias_order_and_parameter(self):
        q = parse_query('SELECT TOP 15 P.Code AS ItemCode, P.Amount FROM Catalog.Products AS P '
                        'WHERE P.Amount >= &Minimum AND (P.Active = TRUE OR P.Text = "a""b") '
                        'ORDER BY P.Amount DESC, P.Code ASC')
        self.assertEqual((q.catalog, q.source_alias, q.limit), ('Products', 'P', 15))
        self.assertEqual(q.projections[0].alias, 'ItemCode')
        self.assertTrue(q.projections[0].explicit_alias)
        self.assertFalse(q.projections[1].explicit_alias)
        self.assertEqual(q.predicate.kind, 'and')
        self.assertEqual(q.predicate.terms[0].value, Parameter('Minimum'))
        self.assertEqual(q.predicate.terms[1].terms[1].value, 'a"b')
        self.assertEqual([x.descending for x in q.order], [True, False])

    def test_russian_and_precedence(self):
        q = parse_query('ВЫБРАТЬ Код КАК Артикул ИЗ Справочник.Товары '
                        'ГДЕ Код = "1" ИЛИ Число <> -1.25 И Флаг = ЛОЖЬ '
                        'УПОРЯДОЧИТЬ ПО Код УБЫВ')
        self.assertEqual(q.predicate.kind, 'or')
        self.assertIsInstance(q.predicate.terms[1], Predicate)
        self.assertEqual(q.predicate.terms[1].terms[0].value, Decimal('-1.25'))

    def test_unsupported_language_is_never_partially_accepted(self):
        variants = [
            'SELECT * FROM Catalog.Products',
            'SELECT Code FROM Document.Invoice',
            'SELECT Code FROM Catalog.Products, Catalog.Categories',
            'SELECT Code FROM Catalog.Products UNION SELECT Code FROM Catalog.Products',
            'SELECT Code FROM Catalog.Products; SELECT Code FROM Catalog.Products',
            'DELETE FROM Catalog.Products',
            'SELECT Code FROM Catalog.Products WHERE Code = (SELECT Code FROM Catalog.Categories)',
            'SELECT Code FROM Catalog.Products WHERE Code LIKE "A%"',
            'SELECT P.Category.Code FROM Catalog.Products AS P',
        ]
        for text in variants:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_query(text)

    def test_relational_extension_accepts_previously_unsupported_shapes(self):
        from yadinassi.query_parser import Aggregate, Field
        materialized = parse_query('SELECT Code INTO Temp FROM Catalog.Products')
        self.assertEqual(materialized.into, 'Temp')
        temporary = parse_query('SELECT Code FROM Temp')
        self.assertTrue(temporary.temporary)
        aggregate = parse_query('SELECT COUNT(Code) FROM Catalog.Products')
        self.assertIsInstance(aggregate.projections[0].field, Aggregate)
        joined = parse_query('SELECT P.Code FROM Catalog.Products AS P JOIN Catalog.Categories AS C ON P.Category=C.Ref')
        self.assertEqual(joined.joins[0].source.catalog, 'Categories')
        grouped = parse_query('SELECT Code FROM Catalog.Products GROUP BY Code')
        self.assertEqual(grouped.groups, (Field(('Code',)),))
        compared = parse_query('SELECT Code FROM Catalog.Products WHERE Code=Code')
        self.assertEqual(compared.predicate.value, Field(('Code',)))

    def test_duplicate_projection_and_invalid_top(self):
        for text in ('SELECT Code, Code FROM Catalog.Products',
                     'SELECT Code AS X, Description AS x FROM Catalog.Products',
                     *('SELECT TOP '+n+' Code FROM Catalog.Products' for n in ('0','10001','1.1','-1'))):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_query(text)

    def test_resource_bounds_and_host_types(self):
        with self.assertRaises(TypeError): parse_query(object())
        for text in (' ' * (MAX_TEXT+1),
                     'SELECT Code FROM Catalog.Products WHERE Amount = '+'1'*10000,
                     'SELECT Code FROM Catalog.Products WHERE '+'('*34+'Code="x"'+')'*34,
                     'SELECT Code FROM Catalog.Products WHERE Code="'+'x'*5000+'"'):
            with self.assertRaises(ValueError): parse_query(text)


if __name__ == '__main__': unittest.main()
