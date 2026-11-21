"""Fresh catalog fixtures prove exact physical storage and query arithmetic."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal, localcontext
from operator import eq, ge, gt, le, lt, ne
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlite_catalog_fixture import configuration_files
from yadinassi import Interpreter
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.catalog.catalog_backend import CatalogComparison, CatalogOrder, CatalogScanRequest
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.query import query_pushdown
from yadinassi.db.query.queries import BSLQuery
from yadinassi.db.query.relational_queries import _Plan
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier


class CatalogNumbersTests(unittest.TestCase):
    high = Decimal('999999999999999999999999999.99999999999')
    low = Decimal('-999999999999999999999999999.99999999998')

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        files = configuration_files()
        path = 'Catalogs/Products.xml'
        additions = ''.join(f'''<Attribute uuid="{uuid4()}"><Properties><Name>{name}</Name><Type>
            <v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>{digits}</v8:Digits>
            <v8:FractionDigits>{scale}</v8:FractionDigits><v8:AllowedSign>{sign}</v8:AllowedSign>
            </v8:NumberQualifiers></Type></Properties></Attribute>'''
            for name, digits, scale, sign in (('Wide',38,11,'Any'),('Narrow',18,0,'Nonnegative')))
        files[path] = files[path].replace(b'</ChildObjects>', additions.encode()+b'</ChildObjects>')
        self.path = Path(temp.name) / 'fresh.sqlite'
        db = SQLiteDBContext.create(self.path, import_configuration(files))
        self.addCleanup(db.close)
        self.backend = db.backend
        self.vm = Interpreter(database_context=db)
        self.addCleanup(self.vm.close)
        self.schema = self.vm._catalogs.get_index('Products')._schema
        self.fields = {field.name: field for field in self.schema.fields}
        self.table = quote_identifier(self.backend._layout.table_name(self.schema.identity))

    def column(self, name):
        return quote_identifier(self.backend._layout.field_name(self.schema.identity,self.fields[name].identity))

    def seed(self, wide):
        for i, value in enumerate(wide):
            self.vm.variables.update(code=str(i), w=value, n=Decimal('999999999999999999'))
            self.vm.execute('P=Catalogs.Products.CreateItem();P.Code=Code;P.Wide=W;P.Narrow=N;P.Write();')

    def query(self, text):
        return BSLQuery(self.vm._catalogs,text).execute()._rows

    def test_declared_physical_types_range_and_crud(self):
        self.seed((self.low,self.high,Decimal(0)))
        narrow, wide = self.column('Narrow'), self.column('Wide')
        with closing(sqlite3.connect(self.path)) as sql, sql:
            row = sql.execute(f'SELECT typeof({narrow}),{narrow},typeof({wide}),length({wide}) FROM {self.table} LIMIT 1').fetchone()
            self.assertEqual(row,('integer',999999999999999999,'blob',16))
            for column, value in ((narrow,-1),(narrow,10**18),(narrow,1.25),
                                  (wide,'1.2'),(wide,b'\xff'*16),(wide,b'123')):
                with self.subTest(column=column,value=value),self.assertRaises(sqlite3.IntegrityError):
                    sql.execute(f'UPDATE {self.table} SET {column}=? WHERE code=?',(value,'0'))
        self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("0").Wide'),self.low)
        self.vm.execute('P=Catalogs.Products.FindByCode("0").GetObject();P.Wide=0.00000000001;P.Write();')
        self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("0").Wide'),Decimal('0.00000000001'))

    def test_wide_comparisons_and_paging_match_exact_decimal(self):
        values = (self.low, self.high, Decimal('-0.00000000001'), Decimal(0), Decimal('0.00000000001'))
        self.seed(values)
        field = self.fields['Wide'].identity
        with closing(self.backend.begin_read()) as view:
            for op, expected_cmp in (('eq',eq),('ne',ne),('lt',lt),('le',le),('gt',gt),('ge',ge)):
                for operand in (Decimal('-1E+50'),self.low, Decimal('-0.000000000005'),
                                Decimal(0),Decimal('0.000000000005'),self.high, Decimal('1E+50')):
                    with self.subTest(op=op,operand=operand):
                        request = CatalogScanRequest(CatalogComparison(field,op,operand),(CatalogOrder(field),),page_size=2)
                        result = []
                        while True:
                            page = view.scan_catalog_values(self.schema.identity,request,(field,))
                            result.extend(row.values[0] for row in page.rows)
                            if page.continuation is None: break
                            request = replace(request,continuation=page.continuation)
                        self.assertEqual(result,sorted(value for value in values if expected_cmp(value,operand)))
        with patch.object(_Plan,'load',side_effect=AssertionError('not the SQLite ordered query')):
            self.assertEqual(self.query('SELECT TOP 2 Wide FROM Catalog.Products ORDER BY Wide DESC'),
                             ((self.high,),(Decimal('0.00000000001'),)))
            self.assertEqual(self.query('SELECT TOP 2 Wide FROM Catalog.Products '
                                        'WHERE Wide < 0.000000000005 ORDER BY Wide DESC'),
                             ((Decimal(0),),(Decimal('-0.00000000001'),)))

    def test_exact_sum_beyond_sqlite_integer_and_cancellation_without_real(self):
        text = 'SELECT SUM(Narrow) AS SN, AVG(Narrow) AS AN, SUM(Wide) AS SW, AVG(Wide) AS AW, COUNT(*) AS N FROM Catalog.Products'
        self.seed((self.low,self.high,*(Decimal(0),)*9))
        with localcontext() as context:
            context.prec = 2
            with patch.object(query_pushdown,'try_numeric',return_value=None): expected = self.query(text)
            with patch.object(_Plan,'load',side_effect=AssertionError('not the SQLite aggregate')): actual = self.query(text)
        self.assertEqual(actual,expected)
        self.assertEqual(actual,((Decimal('10999999999999999989'),Decimal('999999999999999999'),
                                  Decimal('0.00000000001'),Decimal('0.0000000000'),Decimal(11)),))

    def test_average_half_even_and_out_of_range_sum(self):
        self.seed((Decimal('0.00000000015'),Decimal(0),Decimal(0)))
        avg = 'SELECT AVG(Wide) FROM Catalog.Products'
        self.assertEqual(self.query(avg),((Decimal('0.0000000000'),),))
        self.vm.execute('P=Catalogs.Products.FindByCode("0").GetObject();P.Wide=0.00000000045;P.Write();')
        self.assertEqual(self.query(avg),((Decimal('0.0000000002'),),))
        self.vm.variables['w'] = self.high
        for code in ('0','1'):
            self.vm.variables['code'] = code
            self.vm.execute('P=Catalogs.Products.FindByCode(Code).GetObject();P.Wide=W;P.Write();')
        with self.assertRaisesRegex(ValueError,'Query aggregate Number range exceeded'):
            self.query('SELECT SUM(Wide) FROM Catalog.Products')


if __name__ == '__main__':
    unittest.main()
