"""One source snapshot for composed Constants queries, no extra DB sources."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_source_constant_queries import package
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.errors import BSLError


class ConstantQueryCompositionTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.path=Path(d.name)/'scratch.sqlite'

    def run_query(self,text,tail='S=Q.Execute().Select(); While S.Next() Do Message(S.Result); EndDo;',prefix=''):
        out=[];body='Constants.Text.Set("hello"); Constants.Amount.Set(2); Constants.Flag.Set(True); '+prefix+'Q=New Query("'+text.replace('"','""')+'"); '+tail
        app=SourceApplication(package(body),scratch_database=self.path,output=out.append);self.addCleanup(app.close);app.start();return app,out

    def test_union_all(self):
        _,out=self.run_query('SELECT Text AS Result FROM Constants UNION ALL SELECT Text AS Result FROM Constants')
        self.assertEqual(out,['hello','hello'])

    def test_union_deduplicates(self):
        _,out=self.run_query('SELECT Text AS Result FROM Constants UNION SELECT Text AS Result FROM Constants')
        self.assertEqual(out,['hello'])

    def test_union_order_and_expression(self):
        _,out=self.run_query('SELECT Amount AS Result FROM Constants UNION ALL SELECT Amount + 1 AS Result FROM Constants ORDER BY Result DESC')
        self.assertEqual(out,['3','2'])

    def test_inner_self_join(self):
        _,out=self.run_query('SELECT A.Text AS Result FROM Constants AS A INNER JOIN Constants AS B ON A.Amount = B.Amount')
        self.assertEqual(out,['hello'])

    def test_left_join_matching(self):
        _,out=self.run_query('SELECT A.Text AS Result FROM Constants AS A LEFT JOIN Constants AS B ON A.Amount = B.Amount')
        self.assertEqual(out,['hello'])

    def test_join_qualified_both_columns(self):
        _,out=self.run_query('SELECT A.Amount + B.Amount AS Result FROM Constants AS A INNER JOIN Constants AS B ON A.Text = B.Text')
        self.assertEqual(out,['4'])

    def test_derived_select(self):
        _,out=self.run_query('SELECT D.Label AS Result FROM (SELECT Text AS Label FROM Constants) AS D')
        self.assertEqual(out,['hello'])

    def test_derived_join(self):
        _,out=self.run_query('SELECT D.Label AS Result FROM Constants AS C INNER JOIN (SELECT Text AS Label FROM Constants) AS D ON C.Text = D.Label')
        self.assertEqual(out,['hello'])

    def test_membership_select(self):
        _,out=self.run_query('SELECT Text AS Result FROM Constants WHERE Amount IN (SELECT Amount FROM Constants)')
        self.assertEqual(out,['hello'])

    def test_membership_parameter_list(self):
        _,out=self.run_query('SELECT Text AS Result FROM Constants WHERE Amount IN (1,2,3)')
        self.assertEqual(out,['hello'])

    def test_membership_negated(self):
        _,out=self.run_query('SELECT Text AS Result FROM Constants WHERE Amount NOT IN (SELECT Amount FROM Constants)',tail='Message(Q.Execute().IsEmpty());')
        self.assertEqual(out,['Да'])

    def test_group_having(self):
        _,out=self.run_query('SELECT SUM(Amount) AS Result FROM Constants GROUP BY Text HAVING SUM(Amount) > 1')
        self.assertEqual(out,['2'])

    def test_alias_typo_refused(self):
        with self.assertRaises(BSLError):self.run_query('SELECT Missing.Text AS Result FROM Constants AS C')

    def test_ambiguous_join_field_refused(self):
        with self.assertRaises(BSLError):self.run_query('SELECT Text AS Result FROM Constants AS A INNER JOIN Constants AS B ON A.Amount = B.Amount')

    def test_mixed_catalog_union_refused(self):
        with self.assertRaises(BSLError):self.run_query('SELECT Text AS Result FROM Constants UNION ALL SELECT Description AS Result FROM Catalog.Items')

    def test_external_join_refused(self):
        with self.assertRaises(BSLError):self.run_query('SELECT C.Text AS Result FROM Constants AS C INNER JOIN &External AS E ON C.Text = E.Name')

    def test_select_into_refused(self):
        with self.assertRaises(BSLError):self.run_query('SELECT Text AS Result INTO Temporary FROM Constants')

    def test_uninitialized_nested_field_refused(self):
        with self.assertRaisesRegex(BSLError,'uninitialized'):self.run_query('SELECT Text AS Result FROM Constants WHERE Date IN (SELECT Date FROM Constants)')

    def test_one_snapshot_for_all_union_arms(self):
        calls=[];original=SourceConstantStore.get_many
        def read(store,names):calls.append(names);return original(store,names)
        with patch.object(SourceConstantStore,'get_many',read):
            _,out=self.run_query('SELECT Text AS Result FROM Constants UNION ALL SELECT Text AS Result FROM Константы')
        self.assertEqual(out,['hello','hello']);self.assertEqual(calls,[('Text',)])

    def test_explicit_transaction_preserved(self):
        app,out=self.run_query('SELECT Text AS Result FROM Constants UNION ALL SELECT Text AS Result FROM Constants',prefix='BeginTransaction(); Constants.Text.Set("pending");',tail='S=Q.Execute().Select(); While S.Next() Do Message(S.Result); EndDo; RollbackTransaction(); Message(Constants.Text.Get());')
        self.assertEqual(out,['pending','pending','hello']);self.assertFalse(app.constant_store.transaction_active)

    def test_join_result_uses_frozen_snapshot_after_later_write(self):
        original=SourceConstantStore.get_many
        def read(store,names):
            result=original(store,names)
            store.set('Text','later')
            return result
        with patch.object(SourceConstantStore,'get_many',read):
            app,out=self.run_query('SELECT A.Text AS Result FROM Constants AS A INNER JOIN Constants AS B ON A.Text = B.Text')
        self.assertEqual(out,['hello']);self.assertEqual(app.constant_store.get('Text'),'later')

    def test_unqualified_derived_field_in_mixed_join(self):
        _,out=self.run_query('SELECT Label AS Result FROM Constants AS C INNER JOIN (SELECT Text AS Label FROM Constants) AS D ON C.Text = D.Label')
        self.assertEqual(out,['hello'])
