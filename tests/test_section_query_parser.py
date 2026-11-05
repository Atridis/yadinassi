"""Authored section Query grammar contract; not native 1C evidence."""
import unittest
from yadinassi.query_parser import Parameter, parse_query


class SectionQueryParserTests(unittest.TestCase):
    def test_section_source_keeps_owner_catalog_and_section_separate(self):
        query = parse_query('SELECT L.Text AS Text, L.Amount FROM Catalog.Products.Lines AS L '
                            'WHERE L.Ref=&Owner AND L.Amount>=&Min ORDER BY L.Amount')
        self.assertEqual((query.catalog, query.section, query.source_alias),
                         ('Products', 'Lines', 'L'))
        self.assertEqual(query.projections[0].field.parts, ('L', 'Text'))
        self.assertEqual(query.predicate.terms[0].value, Parameter('Owner'))
        self.assertEqual(query.predicate.terms[1].value, Parameter('Min'))
        self.assertEqual(query.order[0].field.parts, ('L', 'Amount'))

    def test_russian_source_and_implicit_alias(self):
        query = parse_query('ВЫБРАТЬ Ссылка, Amount ИЗ Справочник.Products.Lines '
                            'ГДЕ Amount>0 УПОРЯДОЧИТЬ ПО Amount УБЫВ')
        self.assertEqual(query.section, 'Lines')
        self.assertTrue(query.order[0].descending)
        self.assertIsNone(parse_query('SELECT Code FROM Catalog.Products').section)

    def test_source_is_one_optional_section_not_arbitrary_traversal(self):
        for text in (
            'SELECT Text FROM Catalog.Products.Lines.More',
            'SELECT L.Ref.Code FROM Catalog.Products.Lines AS L',
            'SELECT L.Category.Description FROM Catalog.Products.Lines AS L',
            'SELECT Text FROM Catalog.Products.Lines JOIN Catalog.Categories AS C ON Ref=C.Ref',
            'SELECT Text FROM Catalog.Products.Lines, Catalog.Products.Notes',
            'SELECT * FROM Catalog.Products.Lines',
            'SELECT COUNT(Text) FROM Catalog.Products.Lines',
            'SELECT Text FROM Catalog.Products.Lines; DELETE FROM Catalog.Products',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_query(text)
