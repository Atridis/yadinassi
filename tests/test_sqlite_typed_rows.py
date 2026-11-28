from decimal import Decimal, localcontext
import sqlite3
import unittest
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError, FieldSchema
from yadinassi.db.sqlite.sqlite_typed_rows import attribute_definitions, encode_number, decode_number


class ScaledNumberTests(unittest.TestCase):
    def field(self, precision, scale, sign='Any'):
        return FieldSchema(UUID(int=1),'Amount','number',(precision,scale,sign))

    def test_integer_exact_scale_and_validation(self):
        field = self.field(18,2)
        with localcontext() as context:
            context.prec = 2
            value = Decimal('9999999999999999.99')
            raw = encode_number(value,field)
            self.assertIs(type(raw),int)
            self.assertEqual(raw,999999999999999999)
            self.assertEqual(decode_number(raw,field).as_tuple(),value.as_tuple())
            self.assertEqual(encode_number(Decimal('1.2300'),field),123)
            self.assertEqual(encode_number(Decimal('-0.00'),field),0)
        for value in ('0.001','10000000000000000.00','Infinity','NaN','1E+10000'):
            with self.subTest(value=value), self.assertRaisesRegex(BackendError,'invalid_input'):
                encode_number(Decimal(value),field)
        for raw in (True, '1', 10**18, 1.0, None):
            with self.subTest(raw=raw), self.assertRaisesRegex(BackendError,'integrity'):
                decode_number(raw,field)

    def test_wide_is_exact_and_sorts_with_sqlites_native_blob_order(self):
        narrow,wide = self.field(18,0),self.field(38,17)
        values = tuple(map(Decimal,(
            '-999999999999999999999.12345678901234567', '-2', '-0.00000000000000001',
            '0', '0.00000000000000001', '2', '999999999999999999999.12345678901234567')))
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        names = attribute_definitions((wide,),None)
        conn.execute('CREATE TABLE wide('+names[0]+')')
        conn.executemany('INSERT INTO wide VALUES(?)',((encode_number(value,wide),) for value in reversed(values)))
        ordered = conn.execute('SELECT typeof('+names[0].split()[0]+'),* FROM wide ORDER BY '+names[0].split()[0]).fetchall()
        self.assertEqual(tuple(kind for kind,_ in ordered),('blob',)*len(values))
        self.assertEqual(tuple(decode_number(value,wide) for _,value in ordered),values)
        self.assertTrue(all(len(value)==16 for _,value in ordered))
        conn.execute('CREATE TABLE narrow('+attribute_definitions((narrow,),None)[0]+')')
        conn.execute('INSERT INTO narrow VALUES(?)',(encode_number(Decimal(2),narrow),))
        self.assertEqual(conn.execute('SELECT typeof('+names[0].split()[0]+'),* FROM narrow').fetchone(),('integer',2))
