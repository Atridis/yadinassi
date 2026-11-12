"""Bounded enum relational/stock queries on one owned source snapshot."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_inventory_enums import import_inventory_enum_configuration,PROFILE
from yadinassi.database_context import SQLiteDBContext
from yadinassi.errors import BSLRuntimeError
from yadinassi.runtime import Interpreter
from yadinassi.values import NULL
from test_configuration_inventory_enums import source

ROOT=Path(__file__).resolve().parents[1]

class InventoryEnumQueryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'owned.sqlite'
        self.context=SQLiteDBContext.create_inventory_enum(self.path,import_inventory_enum_configuration(source(),inventory_runtime=PROFILE))
        self.addCleanup(self.context.close)
        self.vm=Interpreter(database_context=self.context);self.addCleanup(self.vm.close)
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="P";P.Unit=Enums.Units.Piece;P.Write(); E=Catalogs.Products.CreateItem();E.Code="E";E.Write(); K=Catalogs.Products.CreateItem();K.Code="K";K.Unit=Enums.Units.Pack;K.Write();')
        self.piece=self.vm.execute('Enums.Units.Piece');self.empty=self.vm.execute('Enums.Units.EmptyRef()')

    def query(self,text,**parameters):
        q=self.vm.execute('New Query')
        q.set_member('Text',text)
        for name,value in parameters.items():q.set_parameter(name,value)
        return q.execute()

    def seed_document(self):
        self.vm.execute('W=Catalogs.Warehouses.CreateItem();W.Code="W";W.Write(); D=Documents.Receipt.CreateDocument();D.Number="R";D.Date=Date(2024,2,10);D.Warehouse=W.Ref;D.State=Enums.States.Approved;L=D.Lines.Add();L.Product=P.Ref;L.Unit=Enums.Units.Piece;L.Quantity=5;L.Amount=10;L=D.Lines.Add();L.Product=P.Ref;L.Unit=Enums.Units.Pack;L.Quantity=4;L.Amount=8;D.Write(DocumentWriteMode.Posting);')

    def test_catalog_projection_uses_owned_canonical_objects(self):
        rows=self.query('SELECT Unit FROM Catalog.Products ORDER BY Code')._rows
        self.assertIs(rows[0][0],self.empty);self.assertIs(rows[2][0],self.piece)

    def test_exact_enum_eq_and_ne(self):
        self.assertEqual(len(self.query('SELECT Unit FROM Catalog.Products WHERE Unit=&U',U=self.piece)._rows),1)
        self.assertEqual(len(self.query('SELECT Unit FROM Catalog.Products WHERE Unit<>&U',U=self.piece)._rows),2)

    def test_wrong_owned_enum_parameter_is_not_empty_match(self):
        wrong=self.vm.execute('Enums.States.Draft')
        self.assertEqual(self.query('SELECT Unit FROM Catalog.Products WHERE Unit=&U',U=wrong)._rows,())
        self.assertEqual(len(self.query('SELECT Unit FROM Catalog.Products WHERE Unit<>&U',U=wrong)._rows),3)

    def test_foreign_parameter_is_rejected_before_query_lease(self):
        with closing(Interpreter(database_context=self.context)) as other:
            foreign=other.execute('Enums.Units.Piece')
            with mock.patch.object(self.context.backend,'begin_query_read') as opened:
                with self.assertRaises((BackendError,ValueError,TypeError)):
                    self.query('SELECT Unit FROM Catalog.Products WHERE Unit=&U',U=foreign)
                opened.assert_not_called()

    def test_fabricated_equal_parameter_is_not_authority(self):
        from yadinassi.catalog_backend import BackendError
        for value in (replace(self.piece),replace(self.piece,metadata=object())):
            with self.assertRaises(BackendError):self.query('SELECT Unit FROM Catalog.Products WHERE Unit=&U',U=value)

    def test_group_and_distinct_keep_empty_separate(self):
        rows=self.query('SELECT Unit,COUNT(*) AS N FROM Catalog.Products GROUP BY Unit')._rows
        self.assertEqual(len(rows),3);self.assertTrue(all(r[1]==Decimal(1) for r in rows))
        self.assertEqual(self.query('SELECT COUNT(DISTINCT Unit) AS N FROM Catalog.Products')._rows,((Decimal(3),),))
        self.assertEqual(len(self.query('SELECT DISTINCT Unit FROM Catalog.Products')._rows),3)

    def test_same_enum_join_and_left_null(self):
        joined=self.query('SELECT A.Unit FROM Catalog.Products AS A INNER JOIN Catalog.Products AS B ON A.Unit=B.Unit')._rows
        self.assertEqual(len(joined),3)
        rows=self.query('SELECT B.Unit FROM Catalog.Products AS A LEFT JOIN Catalog.Products AS B ON A.Unit=B.Unit AND B.Code="absent"')._rows
        self.assertTrue(all(row[0] is NULL for row in rows));self.assertEqual(len(rows),3)

    def test_enum_order_min_max_remain_refused(self):
        for text in ('SELECT Unit FROM Catalog.Products ORDER BY Unit','SELECT MIN(Unit) FROM Catalog.Products','SELECT MAX(Unit) FROM Catalog.Products','SELECT Unit FROM Catalog.Products WHERE Unit>&U'):
            with self.assertRaises((ValueError,TypeError)):self.query(text,U=self.piece)

    def test_mixed_scalar_predicate_not_assignment_coercion(self):
        for value in ('Piece',Decimal(1),True):
            with self.assertRaises(TypeError):self.query('SELECT Unit FROM Catalog.Products WHERE Unit=&U',U=value)

    def test_enum_unload_and_packages_stay_closed(self):
        with self.assertRaises((ValueError,TypeError)):self.query('SELECT Unit FROM Catalog.Products').unload()
        with self.assertRaises(ValueError):self.query('SELECT Unit FROM Catalog.Products;SELECT Unit FROM Catalog.Products')

    def test_document_header_and_lines_projection(self):
        self.seed_document()
        state=self.vm.execute('Enums.States.Approved')
        self.assertIs(self.query('SELECT State FROM Document.Receipt')._rows[0][0],state)
        self.assertIs(self.query('SELECT Unit FROM Document.Receipt.Lines ORDER BY LineNumber')._rows[0][0],self.piece)

    def test_raw_movements_keep_enum_dimension_and_attribute(self):
        self.seed_document()
        rows=self.query('SELECT Unit,State,Quantity FROM AccumulationRegister.Stock ORDER BY Quantity')._rows
        self.assertEqual([r[2] for r in rows],[Decimal(4),Decimal(5)])
        self.assertIs(rows[1][0],self.piece);self.assertIs(rows[1][1],self.vm.execute('Enums.States.Approved'))

    def test_balance_turnovers_and_month_statement(self):
        self.seed_document();start=self.vm.execute('Date(2024,1,1)');end=self.vm.execute('Date(2024,3,31,23,59,59)')
        for source_name,column in (('Balance(&EndAt)','QuantityBalance'),('Turnovers(&StartAt,&EndAt)','QuantityTurnover'),('BalanceAndTurnovers(&StartAt,&EndAt,Month)','QuantityClosingBalance')):
            rows=self.query('SELECT Unit,'+column+' FROM AccumulationRegister.Stock.'+source_name+' WHERE Unit=&U',U=self.piece,StartAt=start,EndAt=end)._rows
            self.assertTrue(rows);self.assertTrue(all(r[0] is self.piece and r[1]==Decimal(5) for r in rows))

    def test_query_views_do_not_survive_result_or_end_owner(self):
        self.seed_document()
        self.query('SELECT Unit FROM AccumulationRegister.Stock')
        self.assertIsNone(self.context.backend._active)
        self.vm.execute('BeginTransaction(); Found=Catalogs.Products.FindByCode("P"); Rejected=False;Try Catalogs.Products.FindByDescription("P",True);Except Rejected=True;EndTry;Q=New Query("SELECT Unit FROM Catalog.Products"); S=Q.Execute().Select();Inside=TransactionActive();RollbackTransaction();')
        self.assertTrue(self.vm.execute('(Found=P.Ref)'))
        self.assertTrue(self.vm.execute('Rejected'))
        self.assertTrue(self.vm.execute('Inside'))

    def test_measured_catalog_condition_has_explicit_enum_profile_grant(self):
        self.seed_document()
        self.assertEqual(self.context.backend.format_version,16)
        start=self.vm.execute('Date(2024,1,1)')
        end=self.vm.execute('Date(2024,3,31,23,59,59)')
        product=self.vm.execute('P.Ref')
        for suffix,column,count in (
                ('Balance(&EndAt,Product=&P)','QuantityBalance',1),
                ('Turnovers(&StartAt,&EndAt,,Product=&P)','QuantityTurnover',1),
                ('Turnovers(&StartAt,&EndAt,Month,Product=&P)','QuantityTurnover',1),
                ('BalanceAndTurnovers(&StartAt,&EndAt,,,Product=&P)','QuantityClosingBalance',1),
                ('BalanceAndTurnovers(&StartAt,&EndAt,Month,,Product=&P)','QuantityClosingBalance',2)):
            with self.subTest(source=suffix):
                self.assertEqual(self.query('SELECT '+column+' FROM AccumulationRegister.Stock.'+suffix,
                    P=product,StartAt=start,EndAt=end)._rows,((Decimal(9),),)*count)
            self.assertIsNone(self.context.backend._active)

    def test_enum_condition_and_new_direct_membership_have_separate_grants(self):
        self.seed_document();end=self.vm.execute('Date(2024,3,31,23,59,59)')
        self.assertEqual(self.query('SELECT QuantityBalance FROM '
            'AccumulationRegister.Stock.Balance(&EndAt,Unit=&U)',
            U=self.piece,EndAt=end)._rows,((Decimal(5),),))
        values=self.vm.execute('New Array');values.items.append(self.piece)
        self.assertEqual(self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN (&Units)',Units=values)._rows,
                         ((self.piece,),))
        with self.assertRaises(ValueError):
            self.query('SELECT Unit FROM Catalog.Products WHERE Unit IN &Units',Units=values)
        self.assertEqual(self.query('SELECT Unit,SUM(QuantityBalance) AS N '
            'FROM AccumulationRegister.Stock.Balance(&EndAt) WHERE Unit=&U GROUP BY Unit',
            U=self.piece,EndAt=end)._rows,((self.piece,Decimal(5)),))

    def test_blank_condition_slots_keep_unconditioned_enum_groups(self):
        self.seed_document()
        start=self.vm.execute('Date(2024,1,1)');end=self.vm.execute('Date(2024,3,31,23,59,59)')
        for plain,blank,column in (
                ('Balance(&EndAt)','Balance(&EndAt,)','QuantityBalance'),
                ('Turnovers(&StartAt,&EndAt)','Turnovers(&StartAt,&EndAt,,)','QuantityTurnover'),
                ('BalanceAndTurnovers(&StartAt,&EndAt)','BalanceAndTurnovers(&StartAt,&EndAt,,,)','QuantityClosingBalance'),
                ('BalanceAndTurnovers(&StartAt,&EndAt,Month)','BalanceAndTurnovers(&StartAt,&EndAt,Month,,)','QuantityClosingBalance')):
            with self.subTest(source=plain):
                def rows(source_name,fields):
                    return self.query('SELECT '+fields+' FROM AccumulationRegister.Stock.'+source_name,
                        StartAt=start,EndAt=end)._rows
                expected=rows(plain,'Unit,'+column)
                self.assertEqual(rows(blank,'Unit,'+column),expected)
                # Month B&T retains February flow and March closing carry.
                amounts=sorted([Decimal(4),Decimal(5)]*(2 if ',Month' in plain else 1))
                self.assertEqual(sorted(row[1] for row in expected),amounts)
                self.assertEqual(sorted(row[0] for row in rows(blank,column)),amounts)
                self.assertTrue(any(row[0] is self.piece for row in expected))

    def test_unprojected_enum_fields_still_decode_and_raw_condition_stays_closed(self):
        self.seed_document()
        from yadinassi.accumulation_queries import AccumulationQueryManager
        original=AccumulationQueryManager._logical
        decoded=[]
        def observe(manager,field,value):
            decoded.append((field.name,field.kind))
            return original(manager,field,value)
        with mock.patch.object(AccumulationQueryManager,'_logical',observe):
            self.query('SELECT QuantityBalance FROM AccumulationRegister.Stock.Balance(&EndAt)',
                EndAt=self.vm.execute('Date(2024,3,31,23,59,59)'))
        self.assertEqual(decoded.count(('Unit','enum_ref')),2)
        self.assertEqual(decoded.count(('State','enum_ref')),2)
        from yadinassi import query_parser
        with self.assertRaises(ValueError):
            query_parser.parse_package('SELECT Quantity FROM AccumulationRegister.Stock(&At,Product=&P)')
        self.assertEqual(len(self.query('SELECT Unit,State FROM AccumulationRegister.Stock')._rows),2)
