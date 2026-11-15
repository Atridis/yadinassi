"""Explicit pre-slice query conditions: authored host contract, not native capture."""
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import query_parser as syntax
from yadinassi.dates import literal_date
from yadinassi.values import BSLArray, BSLFixedArray
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.register_query_conditions import bind_condition
import test_periodic_information_registers as legacy


def array(items):
    result=BSLArray();result.items.extend(items);return result


class PeriodicQueryConditions(unittest.TestCase):
    setUp = legacy.PeriodicRegisterTests.setUp
    seed = legacy.PeriodicRegisterTests.seed
    execute = legacy.PeriodicRegisterTests.execute
    query = legacy.PeriodicRegisterTests.query

    def filtered(self, condition, *, first=False, fields='Item,Price', **parameters):
        q = self.query('SELECT '+fields+' FROM InformationRegister.Prices.'+
            ('SliceFirst' if first else 'SliceLast')+'(&At,'+condition+') ORDER BY Item', literal_date('20240102'))
        for key, value in parameters.items(): q.set_parameter(key, value)
        return q

    def test_dimension_equality_and_casefold(self):
        self.seed()
        self.assertEqual(self.filtered('Item=&Item', Item='a').execute()._rows, (('A',Decimal(20)),))

    def test_resource_condition_before_last_selects_older_row(self):
        self.seed()
        self.assertEqual(self.filtered('Price=&Price', Price=Decimal(10)).execute()._rows, (('A',Decimal(10)),))

    def test_attribute_condition_is_not_residual_where(self):
        self.seed()
        self.assertEqual(self.filtered('Enabled=&Flag', Flag=True).execute()._rows,
            (('A',Decimal(10)),('B',Decimal(7))))
        self.assertEqual(self.query('SELECT Item,Price FROM InformationRegister.Prices.SliceLast(&At) WHERE Enabled=TRUE',literal_date('20240102')).execute()._rows, (('B',Decimal(7)),))

    def test_first_filters_before_selecting_edge(self):
        self.seed()
        self.assertEqual(self.filtered('Enabled=&Flag',first=True, Flag=True).execute()._rows,
            (('A',Decimal(30)),('B',Decimal(7))))

    def test_array_and_fixed_array_membership(self):
        self.seed()
        for values in (array(['A','B']), BSLFixedArray(array(['A','B']))):
            self.assertEqual(len(self.filtered('Item IN (&Items)',Items=values).execute()._rows),2)

    def test_array_is_resnapshotted_between_executions(self):
        self.seed();values=array(['A']);q=self.filtered('Item IN (&Items)',Items=values)
        self.assertEqual(q.execute()._rows,(('A',Decimal(20)),))
        values.items[:]=['B'];self.assertEqual(q.execute()._rows,(('B',Decimal(7)),))

    def test_empty_array_has_no_rows(self):
        self.seed();self.assertEqual(self.filtered('Item IN (&Items)',Items=array([])).execute()._rows,())

    def test_and_parentheses_and_repeated_dimension(self):
        self.seed();q=self.filtered('(Item=&Item AND Region=&Region) AND Item IN (&Items)',
            Item='A',Region='North',Items=array(['A']))
        self.assertEqual(q.execute()._rows,(('A',Decimal(20)),))

    def test_period_condition_is_exact_not_assignment_normalization(self):
        self.seed();q=self.filtered('Period=&Day',Day=literal_date('20240102'))
        self.assertEqual(len(q.execute()._rows),2)
        self.assertEqual(len(self.filtered('Период=&Day',Day=literal_date('20240102')).execute()._rows),2)
        q.set_parameter('Day',literal_date('20240102120000'));self.assertEqual(q.execute()._rows,())

    def test_explicit_empty_condition_preserves_legacy_slice(self):
        self.seed();self.assertEqual(len(self.filtered('').execute()._rows),2)

    def test_russian_source_and_operators(self):
        self.seed();q=self.query('ВЫБРАТЬ Item ИЗ РегистрСведений.Prices.СрезПоследних(&At, Item В (&Items) И Enabled=&Flag)',literal_date('20240102'))
        q.set_parameter('Items',array(['A']));q.set_parameter('Flag',True)
        self.assertEqual(q.execute()._rows,(('A',),))

    def test_join_has_independent_conditions_and_one_view(self):
        self.seed();q=self.query('SELECT A.Item,A.Price,B.Price AS Other FROM InformationRegister.Prices.SliceLast(&At,Enabled=&Flag) AS A JOIN InformationRegister.Prices.SliceLast(&At) AS B ON A.Item=B.Item ORDER BY A.Item',literal_date('20240102'))
        q.set_parameter('Flag',True)
        self.assertEqual(q.execute()._rows,(('A',Decimal(10),Decimal(20)),('B',Decimal(7),Decimal(7))))

    def test_union_preserves_each_source_condition(self):
        self.seed();q=self.query('SELECT Price FROM InformationRegister.Prices.SliceLast(&At,Enabled=&Flag) UNION ALL SELECT Price FROM InformationRegister.Prices.SliceFirst(&At,Enabled=&Flag)',literal_date('20240102'))
        q.set_parameter('Flag',True);self.assertEqual(len(q.execute()._rows),4)

    def test_package_and_detached_temporary_table(self):
        self.seed();q=self.query('SELECT Item,Price INTO T FROM InformationRegister.Prices.SliceLast(&At,Enabled=&Flag); SELECT SUM(Price) AS Total FROM T',literal_date('20240102'))
        q.set_parameter('Flag',True);self.assertEqual(q.execute()._rows,((Decimal(17),),))

    def test_derived_source_filter_before_grouping(self):
        self.seed();q=self.query('SELECT SUM(T.Price) AS Total FROM (SELECT Price FROM InformationRegister.Prices.SliceLast(&At,Enabled=&Flag)) AS T',literal_date('20240102'))
        q.set_parameter('Flag',True);self.assertEqual(q.execute()._rows,((Decimal(17),),))

    def test_missing_and_wrong_type_rejected_on_empty_source(self):
        for kwargs in ({},{'Item':Decimal(1)},{'Item':array(['A'])}):
            with self.subTest(kwargs=kwargs),self.assertRaises((TypeError,ValueError)):
                self.filtered('Item=&Item',**kwargs).execute()

    def test_in_requires_array_even_on_empty_source(self):
        with self.assertRaises(TypeError):self.filtered('Item IN (&Items)',Items='A').execute()

    def test_unknown_field_rejected_on_empty_source(self):
        with self.assertRaises(ValueError):self.filtered('Missing=&Item',Item='A').execute()

    def test_mixed_array_rejected_before_scan(self):
        with self.assertRaises(TypeError):self.filtered('Item IN (&Items)',Items=array(['A',Decimal(1)])).execute()

    def test_member_limit_before_deduplication(self):
        self.filtered('Item IN (&Items)',Items=array(['A']*256)).execute()
        with self.assertRaises(ValueError):self.filtered('Item IN (&Items)',Items=array(['A']*257)).execute()

    def test_term_limit(self):
        self.filtered(' AND '.join(['Item=&Item']*16),Item='A').execute()
        with self.assertRaises(ValueError):self.filtered(' AND '.join(['Item=&Item']*17),Item='A').execute()

    def test_per_binding_parameter_budget(self):
        source=syntax.parse_query('SELECT Item FROM InformationRegister.Prices.SliceLast(&At,Item=&Item)')
        from yadinassi.queries import _MAX_CELLS
        with self.assertRaises(ValueError):bind_condition(self.manager,source.virtual_condition,{'item':'A'},[_MAX_CELLS,0])

    def test_condition_budget_shared_across_union_and_derived_arms(self):
        arm='SELECT Item FROM InformationRegister.Prices.SliceLast(&At,Item IN (&Items))'
        for text in (arm+' UNION ALL '+arm,
                     'SELECT T.Item FROM ('+arm+' UNION ALL '+arm+') AS T'):
            q=self.query(text,literal_date('20240102'));q.set_parameter('Items',array(['A','B']))
            with self.subTest(text=text),patch('yadinassi.queries._MAX_CELLS',3),self.assertRaises(ValueError):q.execute()

    def test_condition_budget_shared_across_package_and_preserves_manager(self):
        manager=BSLTempTablesManager()
        q=self.query('SELECT Item INTO T FROM InformationRegister.Prices.SliceLast(&At,Item IN (&Items)); SELECT Item FROM InformationRegister.Prices.SliceFirst(&At,Item IN (&Items))',literal_date('20240102'))
        q.set_member('TempTablesManager',manager);q.set_parameter('Items',array(['A','B']))
        with patch('yadinassi.queries._MAX_CELLS',3),self.assertRaises(ValueError):q.execute()
        self.assertEqual(manager._tables,{})

    def test_unsupported_syntax_remains_closed(self):
        for condition in ('Item="A"','Item<> &Item','Item=&Item OR Region=&Item','Item IN &Items','Item IN (SELECT Item FROM X)','P.Item=&Item'):
            with self.subTest(condition=condition),self.assertRaises((ValueError,TypeError)):
                self.filtered(condition,Item='A',Items=array(['A'])).execute()

    def test_filtered_rows_still_charge_input_budget(self):
        self.seed()
        with patch('yadinassi.queries._MAX_CELLS',5),self.assertRaises(ValueError):
            self.filtered('Item=&Item',Item='absent').execute()

    def test_filtered_rows_still_charge_historical_count(self):
        self.seed()
        with patch('yadinassi.query_parser.MAX_ROWS',2),self.assertRaises(ValueError):
            self.filtered('Item=&Item',Item='absent').execute()


class PeriodicReferenceConditions(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from test_information_register_queries import register_files
        from yadinassi.configuration_xml import import_configuration
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi import Interpreter
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        files=register_files()
        files['InformationRegisters/Rates.xml']=files['InformationRegisters/Rates.xml'].replace(b'Nonperiodical',b'Day')
        self.context=SQLiteDBContext.create(Path(self.temp.name)/'refs.sqlite',import_configuration(files));self.addCleanup(self.context.close)
        self.vm=Interpreter(database_context=self.context,output=lambda v:None)
        self.ref=self.vm.execute('Catalogs.Categories.EmptyRef()')

    def query(self,value):
        from yadinassi.queries import BSLQuery
        q=BSLQuery(self.vm._catalogs,'SELECT Amount FROM InformationRegister.Rates.SliceLast(&At,Category IN (&Refs))',self.vm._documents,self.vm._information_registers)
        q.set_parameter('At',literal_date('20240102'));q.set_parameter('Refs',array([value]));return q

    def test_owned_empty_reference_allowed(self):
        self.assertEqual(self.query(self.ref).execute()._rows,())

    def test_owned_missing_reference_allowed_without_lookup(self):
        from uuid import uuid4
        ref=self.vm._catalogs.get_index('Categories')._ref(uuid4())
        self.assertEqual(self.query(ref).execute()._rows,())

    def test_foreign_interpreter_reference_rejected_even_on_empty_scan(self):
        from yadinassi import Interpreter
        other=Interpreter(database_context=self.context,output=lambda v:None)
        with self.assertRaises(TypeError):self.query(other.execute('Catalogs.Categories.EmptyRef()')).execute()

    def test_wrong_catalog_rejected(self):
        with self.assertRaises(TypeError):self.query(self.vm.execute('Catalogs.Products.EmptyRef()')).execute()

    def test_fabricated_callbacks_rejected(self):
        for ref in (replace(self.ref,read_member=None),replace(self.ref,get_object=lambda v:None),replace(self.ref,metadata=None)):
            with self.subTest(ref=repr(ref)),self.assertRaises(TypeError):self.query(ref).execute()

    def test_current_issuer_checked_after_binding(self):
        from yadinassi.register_query_conditions import bind_condition
        from yadinassi.relational_queries import snapshot_parameters
        source=syntax.parse_query('SELECT Amount FROM InformationRegister.Rates.SliceLast(&At,Category IN (&Refs))')
        manager=self.vm._information_registers.get_index('Rates')
        condition=bind_condition(manager,source.virtual_condition,snapshot_parameters({'refs':array([self.ref])}),[0,0])
        issuer=self.vm._catalogs.get_index('Categories')
        with patch.object(issuer,'_value_type',replace(issuer._value_type)),self.assertRaises(TypeError):
            condition.require_current(manager)
