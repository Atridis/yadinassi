"""Source qualifiers admit declarations without guessing conversion semantics."""
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from test_source_defined_type_constants import package as defined_package
from test_source_session_parameters import declaration
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_constants import source_constant_definitions
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.dates import BSLDate,TICKS_PER_SECOND


def string(length,allowed='Variable'):
    return '<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>'+str(length)+'</v8:Length><v8:AllowedLength>'+allowed+'</v8:AllowedLength></v8:StringQualifiers>'


def date(fraction):
    return '<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>'+fraction+'</v8:DateFractions></v8:DateQualifiers>'


def package(kind,body=''):
    files={f.path:f.content for f in configuration().files}
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Constant>Choice</Constant></ChildObjects>')
    files['Constants/Choice.xml']=declaration('Choice',kind).replace(b'SessionParameter',b'Constant')
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    return import_source(files)


class ConstantQualifierTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.path=Path(d.name)/'scratch.sqlite'

    def store(self,kind):
        store=SourceConstantStore.create(self.path,package(kind));self.addCleanup(store.close);return store

    def test_unlimited_string_roundtrip(self):
        store=self.store(string(0));text='hello '*1000;store.set('Choice',text);self.assertEqual(store.get('Choice'),text)

    def test_unlimited_string_byte_bound_not_disabled(self):
        store=self.store(string(0));store.set('Choice','old')
        with self.assertRaises(ValueError):store.set('Choice','я'*40000)
        self.assertEqual(store.get('Choice'),'old')

    def test_unlimited_rejects_nonstring(self):
        with self.assertRaises(TypeError):self.store(string(0)).set('Choice',True)

    def test_unlimited_has_no_default(self):
        with self.assertRaisesRegex(ValueError,'uninitialized'):self.store(string(0)).get('Choice')

    def test_fixed_exact_utf16_length(self):
        store=self.store(string(3,'Fixed'));store.set('Choice','😀x');self.assertEqual(store.get('Choice'),'😀x')

    def test_fixed_no_padding_or_truncation(self):
        store=self.store(string(3,'Fixed'));store.set('Choice','abc')
        for value in ('ab','abcd'):
            with self.assertRaises(ValueError):store.set('Choice',value)
        self.assertEqual(store.get('Choice'),'abc')

    def test_fixed_zero_rejected(self):
        _,errors,_=source_constant_definitions(package(string(0,'Fixed')));self.assertIn('choice',errors)

    def test_fixed_surrogate_rejected(self):
        with self.assertRaises(ValueError):self.store(string(1,'Fixed')).set('Choice','\ud800')

    def test_date_only(self):
        store=self.store(date('Date'));value=BSLDate(86400*TICKS_PER_SECOND);store.set('Choice',value);self.assertEqual(store.get('Choice'),value)

    def test_date_only_rejects_time(self):
        with self.assertRaises(ValueError):self.store(date('Date')).set('Choice',BSLDate(TICKS_PER_SECOND))

    def test_time_only(self):
        store=self.store(date('Time'));value=BSLDate(3600*TICKS_PER_SECOND);store.set('Choice',value);self.assertEqual(store.get('Choice'),value)

    def test_time_only_rejects_date_component(self):
        with self.assertRaises(ValueError):self.store(date('Time')).set('Choice',BSLDate(86400*TICKS_PER_SECOND))

    def test_time_only_rejects_fractional_seconds(self):
        with self.assertRaises(ValueError):self.store(date('Time')).set('Choice',BSLDate(1))

    def test_unknown_fraction_rejected(self):
        _,errors,_=source_constant_definitions(package(date('Future')));self.assertIn('choice',errors)

    def test_duplicate_qualifier_rejected(self):
        for kind in (string(0)+'<v8:StringQualifiers/>',date('Time')+'<v8:DateQualifiers/>'):
            _,errors,_=source_constant_definitions(package(kind));self.assertIn('choice',errors)

    def test_qualifier_attributes_still_rejected(self):
        _,errors,_=source_constant_definitions(package(string(3,'Fixed').replace('<v8:AllowedLength>','<v8:AllowedLength extra="x">')));self.assertIn('choice',errors)

    def test_composite_unlimited_date(self):
        store=self.store(string(0)+date('Time'))
        for value in ('long'*1000,BSLDate(TICKS_PER_SECOND),None):store.set('Choice',value);self.assertEqual(store.get('Choice'),value)

    def test_defined_type_preserves_qualifiers(self):
        source=defined_package({'Setting':string(2,'Fixed')});store=SourceConstantStore.create(self.path,source);self.addCleanup(store.close);store.set('Choice','ab')
        with self.assertRaises(ValueError):store.set('Choice','a')

    def test_manager_and_package_query(self):
        source=package(string(3,'Fixed'),'M=Constants.Choice.CreateValueManager(); M.Value="abc"; M.Write(); Q=New Query("SELECT Choice AS X INTO Temp FROM Constants; SELECT X FROM Temp"); S=Q.Execute().Select(); S.Next(); Message(S.X);')
        out=[];app=SourceApplication(source,scratch_database=self.path,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['abc'])

    def test_unlimited_query_unload(self):
        source=package(string(0),'Constants.Choice.Set("long text"); Q=New Query("SELECT Choice AS X FROM Constants"); T=Q.Execute().Unload(); Message(T[0].X);')
        out=[];app=SourceApplication(source,scratch_database=self.path,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['long text'])

    def test_reopen_fixed(self):
        store=self.store(string(3,'Fixed'));store.set('Choice','abc');store.close();store=SourceConstantStore.reopen(self.path,package(string(3,'Fixed')));self.addCleanup(store.close);self.assertEqual(store.get('Choice'),'abc')

    def test_update_qualifier_change_refused_unchanged(self):
        store=self.store(string(3,'Fixed'));store.set('Choice','abc');store.close();before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,package(string(0)))
        self.assertEqual(self.path.read_bytes(),before)

    def test_tampered_fixed_storage_rejected(self):
        store=self.store(string(3,'Fixed'));store.set('Choice','abc');store.close()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE constant_value SET value_json='[\"string\",\"ab\"]' WHERE identity=(SELECT identity FROM constant_schema WHERE name='Choice')")
        with self.assertRaises(ValueError):SourceConstantStore.reopen(self.path,package(string(3,'Fixed')))

    def test_transaction_failed_value_keeps_previous(self):
        store=self.store(date('Date'));old=BSLDate(0);store.set('Choice',old);store.begin_transaction()
        with self.assertRaises(ValueError):store.set('Choice',BSLDate(TICKS_PER_SECOND))
        self.assertFalse(store.transaction_active);self.assertEqual(store.get('Choice'),old)
