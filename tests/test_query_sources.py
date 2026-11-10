"""UNION / external ValueTable host contract, not measured native 1C parity."""
from decimal import Decimal, Inexact, Rounded, localcontext
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, query_parser as syntax
from yadinassi.dates import BSLDate, TICKS_PER_SECOND
from yadinassi.queries import BSLQuery
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.query_sources import _snapshot
from yadinassi.sqlite_catalog import _View
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
    BSLDateQualifiers, BSLAllowedLength, BSLAllowedSign, BSLDateFractions)
from yadinassi.value_tables import BSLValueTable
from yadinassi.values import NULL, BSLType
import test_catalog_queries as fixtures


def number(digits=12, scale=2, sign=BSLAllowedSign.ANY):
    return BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(digits), Decimal(scale), sign))


def string(length=20, fixed=False):
    return BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(length),
        BSLAllowedLength.FIXED if fixed else BSLAllowedLength.VARIABLE))


def table(columns, rows=()):
    result = BSLValueTable()
    for name, description in columns: result.columns.add(name, description)
    for values in rows:
        row = result.add()
        for column, value in zip(result.columns.items, values): row.set_member(column.name, value)
    return result


class QuerySourceGrammarTests(unittest.TestCase):
    def test_union_chain_owns_final_order_and_into(self):
        q = syntax.parse_query('SELECT TOP 1 A AS Result INTO Temp FROM &First AS T '
            'UNION ALL SELECT TOP 2 B FROM Other UNION SELECT C FROM Catalog.Products ORDER BY Result DESC')
        self.assertIs(type(q), syntax.Union)
        self.assertEqual(q.all, (True, False))
        self.assertEqual(q.into, 'Temp')
        self.assertTrue(q.arms[0].external)
        self.assertEqual([arm.limit for arm in q.arms[:2]], [1, 2])
        self.assertTrue(all(not arm.order and arm.into is None for arm in q.arms))
        self.assertTrue(q.order[0].descending)

    def test_russian_external_union_package(self):
        q = syntax.parse_package('ВЫБРАТЬ Т.Сумма ПОМЕСТИТЬ Итог ИЗ &Данные КАК Т '
            'ОБЪЕДИНИТЬ ВСЕ ВЫБРАТЬ Amount ИЗ Справочник.Products; УНИЧТОЖИТЬ Итог;')
        self.assertEqual(q[0].all, (True,))
        self.assertEqual(q[0].arms[0].source_alias, 'Т')
        self.assertIs(type(q[1]), syntax.Destroy)

    def test_ambiguous_or_unsupported_union_shapes_fail_closed(self):
        for text in (
            'SELECT A FROM &T ORDER BY A UNION SELECT A FROM &T',
            'SELECT A FROM &T UNION SELECT A INTO Temp FROM &T',
            'SELECT A FROM &T UNION DISTINCT SELECT A FROM &T',
            'SELECT A FROM &T UNION ALL',
            '(SELECT A FROM &T) UNION SELECT A FROM &T',
            'SELECT A FROM (&T)',
            'SELECT A FROM &T.Field',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError): syntax.parse_query(text)

    def test_union_arm_limit(self):
        with patch.object(syntax, 'MAX_UNION_ARMS', 2):
            with self.assertRaisesRegex(ValueError, 'arm limit'):
                syntax.parse_query(' UNION '.join(['SELECT A FROM &T'] * 3))


class QuerySourceTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def query(self, text, parameters=(), manager=None):
        q = BSLQuery(self.vm._catalogs, text)
        for name, value in parameters: q.set_parameter(name, value)
        if manager is not None: q.set_member('TempTablesManager', manager)
        return q

    def rows(self, text, parameters=(), manager=None):
        return self.query(text, parameters, manager).execute()._rows

    def test_end_to_end_bsl_report_external_union_temp_join_and_group(self):
        self.vm.execute('''T=New ValueTable;
T.Columns.Add("Item",New TypeDescription("String",,New StringQualifiers(8)));
T.Columns.Add("Amount",New TypeDescription("Number",New NumberQualifiers(12,2)));
R=T.Add();R.Item="1";R.Amount=5;
M=New TempTablesManager;Q=New Query;Q.TempTablesManager=M;Q.SetParameter("Input",T);
Q.Text="SELECT T.Item,T.Amount INTO Combined FROM &Input AS T UNION ALL SELECT Code AS Item,Amount FROM Catalog.Products; SELECT P.Active,SUM(C.Amount) AS Total FROM Combined AS C JOIN Catalog.Products AS P ON C.Item=P.Code GROUP BY P.Active ORDER BY P.Active; DESTROY Combined";
A=Q.ExecuteBatch();Message(A.Count());Message(A[0].Unload()[0].Count);
Report=A[1].Unload();Message(Report[0].Total);Message(Report[1].Total);
Message(A[2].IsEmpty());M.Close();''')
        self.assertEqual(self.output, ['3', '4', '20', '45', 'Да'])

    def test_union_all_keeps_duplicates_and_first_names(self):
        result = self.query('SELECT Code AS Item FROM Catalog.Products '
            'UNION ALL SELECT Code AS Ignored FROM Catalog.Products ORDER BY Item DESC').execute()
        self.assertEqual(result._rows, (('3',), ('3',), ('2',), ('2',), ('1',), ('1',)))
        self.assertEqual(result._columns[0].name, 'Item')
        self.assertEqual(result.unload().columns.items[0].name, 'Item')

    def test_union_distinct_uses_casefold_numbers_null_and_boolean(self):
        text = ('SELECT "Same" AS Label,1.0 AS N,NULL AS Empty,TRUE AS Flag FROM Catalog.Products '
                'UNION SELECT "sAME" AS Other,1 AS Num,CASE WHEN FALSE=TRUE THEN Amount END AS Nothing,TRUE AS B '
                'FROM Catalog.Products')
        self.assertEqual(self.rows(text), (('Same', Decimal(1), NULL, True),))

    def test_mixed_union_chains_are_left_associative(self):
        arm = 'SELECT Amount FROM Catalog.Products'
        self.assertEqual(len(self.rows(arm + ' UNION ALL ' + arm + ' UNION ' + arm)), 3)
        self.assertEqual(len(self.rows(arm + ' UNION ' + arm + ' UNION ALL ' + arm)), 6)

    def test_final_order_is_global_and_top_is_per_arm(self):
        rows = self.rows('SELECT TOP 1 Amount AS N FROM Catalog.Products WHERE Amount=10 '
            'UNION ALL SELECT TOP 1 Amount FROM Catalog.Products WHERE Amount=30 ORDER BY N DESC')
        self.assertEqual(rows, ((Decimal(30),), (Decimal(10),)))

    def test_union_order_requires_first_arm_unqualified_output(self):
        for order in ('P.Amount', 'Other', 'Amount+1', '1'):
            with self.subTest(order=order), patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('no scan')):
                with self.assertRaises(ValueError):
                    self.rows('SELECT Amount AS FirstValue FROM Catalog.Products AS P '
                        'UNION ALL SELECT Amount AS Other FROM Catalog.Products ORDER BY ' + order)

    def test_incompatible_union_columns_fail_before_scan_even_empty(self):
        for right in ('Active', 'Amount,Amount AS Other', 'NULL AS N'):
            left = 'NULL AS N' if right == 'NULL AS N' else 'Amount'
            with self.subTest(right=right), patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('no scan')):
                with self.assertRaises((ValueError, TypeError)):
                    self.rows('SELECT '+left+' FROM Catalog.Products WHERE Amount>100 '
                        'UNION SELECT '+right+' FROM Catalog.Products WHERE Amount>100')

    def test_null_only_first_arm_infers_typed_metadata_even_empty_peer(self):
        result = self.query('SELECT NULL AS N FROM Catalog.Products UNION '
            'SELECT Amount FROM Catalog.Products WHERE Amount>100 ORDER BY N').execute()
        self.assertEqual(result._rows, ((NULL,),))
        description = result.unload().columns.items[0].value_type
        self.assertTrue(description.contains_type(BSLType.NUMBER))
        self.assertEqual(description.number_qualifiers.fraction_digits, Decimal(2))

    def test_nullable_typed_union_orders_null_first(self):
        rows = self.rows('SELECT NULL AS N FROM Catalog.Products UNION SELECT Amount FROM Catalog.Products ORDER BY N')
        self.assertEqual(rows, ((NULL,), (Decimal(10),), (Decimal(20),), (Decimal(30),)))

    def test_union_numeric_qualifiers_widen_without_rounding(self):
        a = table([('N', number(4, 1, BSLAllowedSign.NONNEGATIVE))], [(Decimal('99.9'),)])
        b = table([('N', number(6, 3))], [(Decimal('-0.125'),)])
        result = self.query('SELECT N FROM &A UNION ALL SELECT N FROM &B', [('A',a),('B',b)]).execute()
        q = result.unload().columns.items[0].value_type.number_qualifiers
        self.assertEqual((q.digits, q.fraction_digits, q.allowed_sign), (Decimal(6), Decimal(3), BSLAllowedSign.ANY))
        self.assertEqual(result._rows, ((Decimal('99.9'),), (Decimal('-0.125'),)))

    def test_union_numeric_overflow_fails_instead_of_narrowing_values(self):
        a = table([('N', number(38, 0))], [(Decimal('1e37'),)])
        b = table([('N', number(38, 2))], [(Decimal('0.01'),)])
        with self.assertRaisesRegex(ValueError, 'qualifiers'):
            self.rows('SELECT N FROM &A UNION ALL SELECT N FROM &B', [('A',a),('B',b)])

    def test_union_reference_identity_survives_null_and_materialization(self):
        text = ('SELECT NULL AS Category INTO Refs FROM Catalog.Products '
            'UNION SELECT Category FROM Catalog.Products; '
            'SELECT C.Code AS Item FROM Refs AS R JOIN Catalog.Categories AS C ON R.Category=C.Ref')
        self.assertEqual(self.rows(text), (('01',),))
        result = self.query('SELECT Category FROM Catalog.Products UNION SELECT Ref FROM Catalog.Categories').execute()
        self.assertEqual(len(result._rows), 1)
        with self.assertRaises(ValueError): result.unload()

    def test_union_wrong_reference_family_or_snapshot_rejected_before_scan(self):
        other = Interpreter(database_context=self.context)
        foreign = other.execute('Catalogs.Categories.EmptyRef()')
        for right, parameters in (('Ref', ()), ('&R AS R', [('R', foreign)])):
            with self.subTest(right=right), patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('no scan')):
                with self.assertRaises(TypeError):
                    self.rows('SELECT Category FROM Catalog.Products WHERE Amount>100 UNION SELECT '+right+
                              ' FROM Catalog.Products WHERE Amount>100', parameters)

    def test_all_union_arms_and_statements_share_one_read_view(self):
        original, views = _View.scan_catalog_values, []
        def scan(view, *args): views.append(view); return original(view, *args)
        with patch.object(_View, 'scan_catalog_values', scan):
            result = self.rows('SELECT Amount INTO Prepared FROM Catalog.Products UNION ALL '
                'SELECT Amount FROM Catalog.Products; SELECT SUM(Amount) AS N FROM Prepared UNION '
                'SELECT SUM(Amount) AS N FROM Catalog.Products ORDER BY N')
        self.assertEqual(result, ((Decimal(60),), (Decimal(120),)))
        self.assertEqual(len({id(view) for view in views}), 1)
        self.context.backend.begin_read().close()

    def test_union_input_and_output_limits_are_not_hidden_by_top_or_distinct(self):
        with patch.object(syntax, 'MAX_ROWS', 4):
            with self.assertRaisesRegex(ValueError, 'UNION row limit'):
                self.rows('SELECT Amount FROM Catalog.Products UNION ALL SELECT Amount FROM Catalog.Products')
        with patch.object(syntax, 'MAX_ROWS', 2):
            with self.assertRaisesRegex(ValueError, 'input resource'):
                self.rows('SELECT TOP 1 Amount FROM Catalog.Products UNION SELECT TOP 1 Amount FROM Catalog.Products')
        # Scalar projections expand output text independently of narrow input.
        with patch('yadinassi.queries._MAX_RESULT_TEXT', 20):
            with self.assertRaisesRegex(ValueError, 'UNION result'):
                self.rows('SELECT "abcd" AS N FROM Catalog.Products UNION SELECT "abcd" AS N FROM Catalog.Products')

    def test_union_failure_rolls_back_destroy_create_and_releases_view(self):
        manager = BSLTempTablesManager()
        self.rows('SELECT Amount INTO Original FROM Catalog.Products', manager=manager)
        with self.assertRaises(ValueError):
            self.rows('DESTROY Original; SELECT Amount INTO Created FROM Catalog.Products UNION ALL '
                'SELECT Amount/(Amount-20) AS N FROM Catalog.Products', manager=manager)
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Original', manager=manager), ((Decimal(3),),))
        with self.assertRaises(ValueError): self.rows('SELECT Amount FROM Created', manager=manager)
        self.context.backend.begin_read().close()

    def test_external_direct_select_into_and_case_insensitive_lookup(self):
        source = table([('N', number())], [(Decimal(2),), (Decimal(5),)])
        parameters = [('Table', source)]
        self.assertEqual(self.rows('SELECT T.n INTO Temp FROM &tAbLe AS T; SELECT SUM(N) AS Total FROM Temp', parameters),
                         ((Decimal(7),),))

    def test_external_join_self_join_and_empty_aggregate(self):
        source = table([('Item', string(8)), ('N', number())], [('1',Decimal(7)), ('2',Decimal(8))])
        params = [('T', source)]
        rows = self.rows('SELECT P.Amount+T.N AS N FROM Catalog.Products AS P JOIN &T AS T ON P.Code=T.Item ORDER BY N', params)
        self.assertEqual(rows, ((Decimal(17),), (Decimal(28),)))
        self.assertEqual(self.rows('SELECT SUM(A.N+B.N) AS N FROM &T AS A JOIN &t AS B ON A.Item=B.Item', params), ((Decimal(30),),))
        empty = table([('N', number())])
        self.assertEqual(self.rows('SELECT COUNT(*) AS C,SUM(N) AS N FROM &T', [('T',empty)]), ((Decimal(0),NULL),))

    def test_external_only_queries_do_not_open_backend(self):
        source = table([('N', number())], [(Decimal(2),)])
        with patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('no read')):
            self.assertEqual(self.rows('SELECT N FROM &T UNION SELECT N FROM &T', [('T',source)]), ((Decimal(2),),))

    def test_external_snapshot_once_at_execute_and_refresh_next_execution(self):
        source = table([('N', number())], [(Decimal(2),)])
        query = self.query('SELECT N INTO Temp FROM &T; SELECT N FROM &t UNION ALL '
            'SELECT Amount FROM Catalog.Products UNION ALL SELECT N FROM Temp', [('T',source)])
        source.rows[0].set_member('N', Decimal(3))  # SetParameter is not the snapshot boundary.
        original = _View.scan_catalog_values
        def scan(view, *args):
            source.rows[0].set_member('N', Decimal(99))
            return original(view, *args)
        with patch('yadinassi.query_sources._snapshot', wraps=_snapshot) as snapshot, patch.object(_View, 'scan_catalog_values', scan):
            result = query.execute()
        self.assertEqual(snapshot.call_count, 1)
        self.assertEqual((result._rows[0], result._rows[-1]), ((Decimal(3),), (Decimal(3),)))
        self.assertEqual(sorted(result._rows[1:-1]), [(Decimal(10),), (Decimal(20),), (Decimal(30),)])
        self.assertEqual(query.execute()._rows[0], (Decimal(99),))
        source.rows.clear(); source.columns.clear()
        self.assertEqual(result._rows[-1], (Decimal(3),))

    def test_external_rows_and_metadata_detach_from_buffer_and_manager_close(self):
        source = table([('N', number())], [(Decimal(2),)])
        manager = BSLTempTablesManager()
        self.rows('SELECT N INTO Temp FROM &T', [('T',source)], manager)
        source.rows[0].set_member('N', Decimal(99)); source.columns.items[0].set_member('Name', 'Renamed')
        result = self.query('SELECT N FROM Temp', manager=manager).execute()
        manager.close()
        self.assertEqual(result.unload().rows[0].get_member('N'), Decimal(2))

    def test_external_preserves_fixed_string_date_boolean_and_decimal_qualifiers(self):
        date_type = BSLTypeDescription('Date', None, None, BSLDateQualifiers(BSLDateFractions.DATE))
        source = table([('Text',string(4,True)),('N',number(9,3,BSLAllowedSign.NONNEGATIVE)),
                        ('Stamp',date_type),('Flag',BSLTypeDescription('Boolean'))],
                       [('a',Decimal('1.125'),BSLDate(86400*TICKS_PER_SECOND),True)])
        output = self.query('SELECT Text,N,Stamp,Flag FROM &T', [('T',source)]).execute().unload()
        qs = [c.value_type for c in output.columns.items]
        self.assertEqual(output.rows[0].get_member('Text'), 'a   ')
        self.assertIs(qs[0].string_qualifiers.allowed_length, BSLAllowedLength.FIXED)
        self.assertEqual(qs[1].number_qualifiers.fraction_digits, Decimal(3))
        self.assertIs(qs[1].number_qualifiers.allowed_sign, BSLAllowedSign.NONNEGATIVE)
        self.assertIs(qs[2].date_qualifiers.date_fractions, BSLDateFractions.DATE)

    def test_unbounded_string_and_mixed_string_date_qualifiers_promote_truthfully(self):
        a = table([('S',string(3,True)),('D',BSLTypeDescription('Date',None,None,BSLDateQualifiers(BSLDateFractions.DATE)))], [('a',BSLDate(0))])
        b = table([('S',string(0)),('D',BSLTypeDescription('Date',None,None,BSLDateQualifiers(BSLDateFractions.TIME)))], [('longer',BSLDate(TICKS_PER_SECOND))])
        result = self.query('SELECT S,D FROM &A UNION ALL SELECT S,D FROM &B', [('A',a),('B',b)]).execute().unload()
        self.assertEqual(result.columns.items[0].value_type.string_qualifiers.length, Decimal(0))
        self.assertIs(result.columns.items[0].value_type.string_qualifiers.allowed_length, BSLAllowedLength.VARIABLE)
        self.assertIs(result.columns.items[1].value_type.date_qualifiers.date_fractions, BSLDateFractions.DATE_TIME)

    def test_unloaded_nullable_scalar_table_is_valid_source_without_codec_bypass(self):
        source = self.query('SELECT CASE WHEN Amount>20 THEN Amount END AS N FROM Catalog.Products').execute().unload()
        result = self.query('SELECT N FROM &T UNION SELECT N FROM &T ORDER BY N', [('T',source)]).execute()
        self.assertEqual(result._rows, ((NULL,), (Decimal(30),)))
        self.vm.variables['inputtable'] = source
        with self.assertRaises(Exception): self.vm.execute('ValueToStringInternal(InputTable)')
        with self.assertRaises(ValueError): source.add()

    def test_external_untyped_mixed_null_uuid_and_unbounded_number_rejected_even_empty(self):
        for description in (BSLTypeDescription(), BSLTypeDescription('String,Number'),
                            BSLTypeDescription('Null'), BSLTypeDescription('UUID'),
                            BSLTypeDescription('Number'), number(39,2)):
            with self.subTest(description=str(description)), patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('no scan')):
                source = table([('N', number())])
                source.columns.items[0].value_type = description
                with self.assertRaises((ValueError, TypeError)):
                    self.rows('SELECT N FROM &T UNION SELECT Amount FROM Catalog.Products', [('T',source)])

    def test_external_missing_wrong_source_and_scalar_misuse_are_explicit(self):
        source = table([('N', number())])
        for parameters in ((), [('T',Decimal(1))], [('T','wrong')]):
            with self.subTest(parameters=parameters), self.assertRaises((ValueError, TypeError)):
                self.rows('SELECT N FROM &T', parameters)
        with self.assertRaises(TypeError):
            self.rows('SELECT Amount+&T AS N FROM Catalog.Products', [('T',source)])
        with self.assertRaises(TypeError):
            self.rows('SELECT Code FROM Catalog.Products WHERE Amount=&T', [('T',source)])

    def test_external_validates_unprojected_cells_without_coercion_or_host_hooks(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('must not compare')
            def __hash__(self): raise AssertionError('must not hash')
            def __str__(self): raise AssertionError('must not stringify')
        for value in (None, NULL, True, '1', [], Hostile(), Decimal('NaN'), Decimal('1.001'), Decimal('1e1000')):
            source = table([('Keep',string()),('N',number())], [('safe',Decimal(1))])
            source.rows[0].cells[source.columns.items[1]] = value
            with self.subTest(kind=type(value).__name__), self.assertRaises((ValueError, TypeError)):
                self.rows('SELECT TOP 1 Keep FROM &T WHERE Keep="absent"', [('T',source)])

    def test_external_checks_utf16_fixed_and_date_fraction_limits(self):
        cases = [(string(1), '😀'), (string(4,True),'x'), (string(4),'\ud800'),
                 (BSLTypeDescription('Date',None,None,BSLDateQualifiers(BSLDateFractions.DATE)), BSLDate(1))]
        for description, value in cases:
            source = table([('V',description)])
            row = source.add(); row.cells[source.columns.items[0]] = value
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                self.rows('SELECT V FROM &T', [('T',source)])

    def test_external_resource_limits_count_entire_source_before_top(self):
        source = table([('N',number()),('S',string())], [(Decimal(1),'hello'),(Decimal(2),'world')])
        for module, limit, value in [('query_parser','MAX_ROWS',1), ('queries','_MAX_CELLS',3), ('queries','_MAX_RESULT_TEXT',9)]:
            with self.subTest(limit=limit), patch('yadinassi.'+module+'.'+limit,value):
                with self.assertRaises(ValueError): self.rows('SELECT TOP 1 N FROM &T', [('T',source)])

    def test_external_snapshot_budget_is_shared_across_distinct_parameters(self):
        a = table([('N',number())], [(Decimal(1),),(Decimal(2),)])
        b = table([('N',number())], [(Decimal(3),),(Decimal(4),)])
        with patch('yadinassi.queries._MAX_CELLS',3):
            with self.assertRaisesRegex(ValueError, 'source cell'):
                self.rows('SELECT TOP 1 N FROM &A UNION SELECT TOP 1 N FROM &B', [('A',a),('B',b)])

    def test_external_invalid_later_source_leaves_manager_unchanged(self):
        manager = BSLTempTablesManager()
        self.rows('SELECT Amount INTO Original FROM Catalog.Products', manager=manager)
        bad = table([('N',BSLTypeDescription())])
        with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must validate all external sources first')):
            with self.assertRaises(TypeError):
                self.rows('DESTROY Original; SELECT Amount INTO Created FROM Catalog.Products; SELECT N FROM &Bad', [('Bad',bad)], manager)
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Original', manager=manager), ((Decimal(3),),))
        with self.assertRaises(ValueError): self.rows('SELECT Amount FROM Created', manager=manager)

    def test_external_zero_columns_invalid_identifiers_and_restricted_slices_rejected(self):
        zero = BSLValueTable()
        unnamed = table([('',number())])
        restricted = table([('N',number())]); restricted._bounded_slice_read = True
        for source in (zero, unnamed, restricted):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.rows('SELECT COUNT(*) AS N FROM &T', [('T',source)])

    def test_number_validation_ignores_hostile_decimal_context(self):
        source = table([('N',number(12,3))], [(Decimal('12345.125'),)])
        with localcontext() as context:
            context.prec = 2; context.traps[Inexact] = True; context.traps[Rounded] = True
            self.assertEqual(self.rows('SELECT N FROM &T UNION SELECT N FROM &T', [('T',source)]), ((Decimal('12345.125'),),))

    def test_simple_catalog_select_retains_original_fast_path(self):
        with patch('yadinassi.query_packages.execute_package',side_effect=AssertionError('not a package')):
            with patch('yadinassi.relational_queries._Plan.execute',side_effect=AssertionError('not relational execution')):
                self.assertEqual(self.rows('SELECT TOP 1 Amount FROM Catalog.Products ORDER BY Amount'), ((Decimal(10),),))


if __name__ == '__main__': unittest.main()
