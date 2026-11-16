"""Source-owned enum queries, not legacy inventory profile or native parity."""
import unittest
from dataclasses import replace
import test_source_record_enums as fixtures
from yadinassi.errors import BSLError

CAT='C=Catalogs.Items.CreateItem();C.Code="A";C.Choice=Enums.State.Active;C.Write();'
DOC='D=Documents.Invoice.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);'

class SourceEnumQueryTests(unittest.TestCase):
    setUp=fixtures.SourceRecordEnumTests.setUp
    app=fixtures.SourceRecordEnumTests.app
    run_body=fixtures.SourceRecordEnumTests.run_body
    def query(self,text,tail='S=Q.Execute().Select();S.Next();Message(S.E=Enums.State.Active);',prefix=CAT,where='catalog'):
        return self.run_body(prefix+'Q=New Query("'+text.replace('"','""')+'");'+tail,where)
    def test_catalog_enum_projection(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items');self.assertEqual(out,['Да'])
    def test_count_does_not_reject_enum_bearing_schema(self):
        _,out=self.query('SELECT COUNT(*) AS E FROM Catalog.Items','S=Q.Execute().Select();S.Next();Message(S.E);');self.assertEqual(out,['1'])
    def test_scalar_projection_from_enum_bearing_schema(self):
        _,out=self.query('SELECT Code AS E FROM Catalog.Items','S=Q.Execute().Select();S.Next();Message(S.E);');self.assertEqual(out,['A'])
    def test_filter_parameter(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items WHERE Choice=&Wanted','Q.SetParameter("Wanted",Enums.State.Active);S=Q.Execute().Select();Message(S.Next());Message(S.E=Enums.State.Active);');self.assertEqual(out,['Да','Да'])
    def test_enum_join(self):
        _,out=self.query('SELECT A.Choice AS E FROM Catalog.Items AS A INNER JOIN Catalog.Items AS B ON A.Choice=B.Choice');self.assertEqual(out,['Да'])
    def test_union_and_derived(self):
        _,out=self.query('SELECT E FROM (SELECT Choice AS E FROM Catalog.Items UNION ALL SELECT Choice AS E FROM Catalog.Items) AS T');self.assertEqual(out,['Да'])
    def test_unload_retains_domain(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items','T=Q.Execute().Unload();Message(T.Get(0).E=Enums.State.Active);');self.assertEqual(out,['Да'])
    def test_report_requery(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items','T=Q.Execute().Unload();Q=New Query("SELECT E FROM &Input");Q.SetParameter("Input",T);S=Q.Execute().Select();S.Next();Message(S.E=Enums.State.Active);');self.assertEqual(out,['Да'])
    def test_temp_table_and_batch(self):
        _,out=self.query('SELECT Choice AS E INTO T FROM Catalog.Items; SELECT E FROM T','R=Q.ExecuteBatch();S=R.Get(1).Select();S.Next();Message(S.E=Enums.State.Active);');self.assertEqual(out,['Да'])
    def test_membership(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items WHERE Choice IN (&A)','A=New Array;A.Add(Enums.State.Active);A.Add(Enums.State.Inactive);Q.SetParameter("A",A);S=Q.Execute().Select();Message(S.Next());');self.assertEqual(out,['Да'])
    def test_scalar_membership_still_works(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items WHERE Code IN ("A","B")');self.assertEqual(out,['Да'])
    def test_document_enum(self):
        _,out=self.query('SELECT Choice AS E FROM Document.Invoice',prefix=DOC+'D.Choice=Enums.State.Active;D.Write();',where='document');self.assertEqual(out,['Да'])
    def test_section_enum(self):
        _,out=self.query('SELECT Choice AS E FROM Document.Invoice.Lines',prefix=DOC+'R=D.Lines.Add();R.Choice=Enums.State.Active;D.Write();',where='section');self.assertEqual(out,['Да'])
    def test_other_owned_enum_comparison_is_nonmatch(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items WHERE Choice=&Wanted','Q.SetParameter("Wanted",Enums.Mode.Auto);Message(Q.Execute().Select().Next());');self.assertEqual(out,['Нет'])
    def test_enum_ordering_remains_closed(self):
        with self.assertRaises(BSLError):self.query('SELECT Choice AS E FROM Catalog.Items ORDER BY Choice')

    def test_binding_lifecycle_and_forgery(self):
        from yadinassi.source_query_enums import SourceEnumScope
        from yadinassi.configuration_source_runtime import SourceApplication
        app,_=self.app(fixtures.package());app.start()
        scope=SourceEnumScope(app,app.interpreter._catalogs)
        manager=app.enumerations.get_member('State')
        value=manager._values[0];descriptor=scope.value_descriptor(value)
        binding=scope.domain(descriptor)
        self.assertIs(binding.value(value),value)
        with self.assertRaises(TypeError):scope.require_descriptor(replace(descriptor))
        with self.assertRaises(TypeError):binding.value(replace(value))
        foreign=SourceApplication(fixtures.package());self.addCleanup(foreign.close)
        with self.assertRaises(TypeError):binding.value(foreign.enumerations.get_member('State')._values[0])
        with self.assertRaises(TypeError):binding.require_context(foreign.interpreter._catalogs,None)
        with self.assertRaises(TypeError):replace(binding,kind=object()).require_owner()
        scope._retired=True
        with self.assertRaises(ValueError):scope.require_descriptor(descriptor)
        self.assertIs(binding.value(value),value)
        app.close()
        with self.assertRaises((ValueError,RuntimeError)):binding.value(value)

    def test_empty_reference_query(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items','S=Q.Execute().Select();S.Next();Message(S.E.IsEmpty());',prefix=CAT.replace('Enums.State.Active','Enums.State.EmptyRef()'))
        self.assertEqual(out,['Да'])

    def test_membership_subquery(self):
        _,out=self.query('SELECT Choice AS E FROM Catalog.Items WHERE Choice IN (SELECT Choice FROM Catalog.Items)')
        self.assertEqual(out,['Да'])

    def test_source_does_not_acquire_native_snapshot(self):
        from unittest.mock import patch
        with patch('yadinassi.inventory_enum_runtime.read_snapshot',side_effect=AssertionError('native snapshot')):
            _,out=self.query('SELECT Choice AS E FROM Catalog.Items')
        self.assertEqual(out,['Да'])

    def test_enum_constant_profile_query(self):
        from test_source_enum_constants import package
        from yadinassi.configuration_source_runtime import SourceApplication
        body='Constants.Choice.Set(Enums.State.Active);Q=New Query("SELECT Choice AS E FROM Constants");S=Q.Execute().Select();S.Next();Message(S.E=Enums.State.Active);'
        out=[];app=SourceApplication(package(body),scratch_database=self.path,output=out.append);self.addCleanup(app.close)
        app.start();self.assertEqual(out,['Да'])

    def test_grouping_and_distinct(self):
        _,out=self.query('SELECT Choice AS E,COUNT(*) AS N FROM Catalog.Items GROUP BY Choice','S=Q.Execute().Select();S.Next();Message(S.E=Enums.State.Active);Message(S.N);')
        self.assertEqual(out,['Да','1'])

    def test_nullable_left_join(self):
        _,out=self.query('SELECT B.Choice AS E FROM Catalog.Items AS A LEFT JOIN Catalog.Items AS B ON A.Code<>B.Code','S=Q.Execute().Select();S.Next();Message(S.E=NULL);')
        self.assertEqual(out,['Да'])
