"""Static profile tests only. No native or automatic-event execution evidence."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import UUID

from yadinassi.catalog_backend import CatalogSchema, FieldSchema, TabularSectionSchema
from yadinassi.configuration_xml import import_configuration
from yadinassi import object_module_analysis as om
from yadinassi.syntax import ast
from yadinassi.syntax.lexer import Token
from sqlite_catalog_fixture import configuration_files


DATABASE = UUID(int=1)
CONFIGURATION = UUID(int=2)
CATALOG = CatalogSchema(UUID(int=3), 'Products', 8, 64, (
    FieldSchema(UUID(int=4), 'Amount', 'number', (12, 2, 'Any')),
    FieldSchema(UUID(int=5), 'Active', 'boolean'),
    FieldSchema(UUID(int=6), 'Stamp', 'datetime', ('DateTime',)),
))
EMPTY = b'Procedure BeforeWrite(Cancel)\nEndProcedure'


def binding(source=EMPTY, **changes):
    return replace(om.ObjectModuleBinding(DATABASE, CONFIGURATION, 1, CATALOG,
                                         sha256(source).hexdigest()), **changes)


def source(body='', helpers=''):
    return ('Procedure BeforeWrite(Cancel)\n' + body + '\nEndProcedure\n' + helpers).encode()


class ObjectModuleAnalysisTests(unittest.TestCase):
    def analyze(self, raw=EMPTY, **changes):
        if type(raw) is str:
            raw = raw.encode()
        return om.analyze_object_module(raw, binding(raw, **changes))

    def reject(self, raw, **changes):
        with self.assertRaises(om.ObjectModuleAnalysisError):
            self.analyze(raw, **changes)

    def test_nonempty_or_malformed_tabular_metadata_is_rejected(self):
        section = TabularSectionSchema(UUID(int=7), 'Rows', ())
        for sections in ((section,), None, []):
            with self.subTest(sections=sections):
                self.reject(EMPTY, catalog=replace(CATALOG, tabular_sections=sections))

    def test_empty_beforewrite_is_static_ir(self):
        value = self.analyze()
        self.assertEqual(value.event, 'beforewrite')
        self.assertEqual(value.procedures[0].body, ())
        self.assertEqual(value.profile, 'catalog-before-write-static-v1')
        self.assertIs(value.native_parity, False)

    def test_russian_event_and_fields(self):
        value = self.analyze('Процедура ПередЗаписью(Отказ)\nЭтотОбъект.Наименование = "Товар"; Отказ = Ложь;\nКонецПроцедуры')
        self.assertEqual(value.event, 'передзаписью')
        self.assertEqual(value.procedures[0].body[0].arguments[0], om.IRNode('field', ('description',)))

    def test_case_insensitive_direct_names(self):
        value = self.analyze(source('cOdE = "A"; ThIsObJeCt.AcTiVe = TRUE; cAnCeL = False;'))
        self.assertEqual(value.procedures[0].body[1].arguments[0], om.IRNode('field', ('active',)))

    def test_scalar_expressions_lower_without_evaluation(self):
        value = self.analyze(source('Amount = -(1.25 + 2) * 3 / 0 % 2; Active = NOT (Amount < 0) AND True OR False; Stamp = Stamp;'))
        self.assertEqual(len(value.procedures[0].body), 3)

    def test_if_elsif_else_and_conditional(self):
        value = self.analyze(source('If Amount = 0 Then Cancel = True; ElsIf Amount > 3 Then Code = "A"; Else Description = ?(Active, "Y", "N"); EndIf;'))
        self.assertEqual(value.procedures[0].body[0].operation, 'if')

    def test_local_declarations_and_definite_assignment(self):
        value = self.analyze(source('Var X, Y; If Active Then X = 1; Else X = 2; EndIf; Y = X; Amount = Y;'))
        self.assertEqual(value.procedures[0].locals, ('x', 'y'))

    def test_helpers_forward_references_and_take_values(self):
        value = self.analyze(source('_om_Check(Cancel, Description);',
            'Procedure _om_Check(Stop, Val Text)\nIf Text = "" Then Stop = True; EndIf;\nEndProcedure'))
        self.assertEqual(value.procedures[0].body[0].operation, 'call')
        self.assertEqual(value.procedures[1].parameters, (('stop', False), ('text', True)))

    def test_forward_helper_declaration_and_return(self):
        value = self.analyze(source('_om_A(); Return; Cancel = True;',
            'Procedure _om_A()\n_om_B();\nEndProcedure\nProcedure _om_B()\nReturn;\nEndProcedure'))
        self.assertEqual(len(value.procedures), 3)
        self.assertEqual(value.expanded_nodes, value.ast_nodes)

    def test_comments_strings_and_escaped_quotes(self):
        value = self.analyze(source('// New HTTPConnection is only a comment\nDescription = "Eval(""x"")";'))
        self.assertEqual(value.procedures[0].body[0].arguments[1].arguments, ('Eval("x")',))

    def test_utf8_bom_crlf_and_exact_bytes_retained(self):
        raw = b'\xef\xbb\xbf' + EMPTY.replace(b'\n', b'\r\n')
        value = self.analyze(raw)
        self.assertIs(value.source, raw)
        self.assertEqual(value.binding.source_sha256, sha256(raw).hexdigest())

    def test_max_source_boundary(self):
        raw = EMPTY + b'\n//' + b'x' * (om.MAX_SOURCE_BYTES - len(EMPTY) - 3)
        self.assertEqual(len(self.analyze(raw).source), om.MAX_SOURCE_BYTES)

    def test_result_binding_and_ir_are_immutable(self):
        value = self.analyze(source('Cancel = True;'))
        for target, name, replacement in ((value, 'source', b'x'), (value.binding, 'configuration_generation', 2),
                (value.procedures[0], 'body', ()), (value.procedures[0].body[0], 'arguments', ())):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(target, name, replacement)

    def test_distinct_identity_commitments_remain_distinct(self):
        first = self.analyze()
        second = self.analyze(database_id=UUID(int=100), configuration_generation=2)
        self.assertNotEqual(first.binding, second.binding)
        self.assertEqual(first.source, second.source)
        self.assertEqual(first.module_path, 'Catalogs/Products/Ext/ObjectModule.bsl')

    def test_empty_field_catalog_is_admitted(self):
        value = self.analyze(source('Description = "ok";'), catalog=replace(CATALOG, fields=()))
        self.assertEqual(value.binding.catalog.fields, ())

    def test_analysis_never_calls_interpreter(self):
        with patch('yadinassi.runtime.Interpreter.execute', side_effect=AssertionError('executed')), \
             patch('yadinassi.runtime.Interpreter.execute_program', side_effect=AssertionError('executed')):
            self.analyze(source('Amount = 1 / 0;'))

    def test_existing_configuration_activation_blocker_remains(self):
        files = configuration_files()
        raw = source('Cancel = True;')
        files['Catalogs/Products/Ext/ObjectModule.bsl'] = raw
        before = import_configuration(files)
        # This analyzer's deliberately narrower schema excludes string/ref attrs.
        scalar = replace(before.catalogs[1], fields=before.catalogs[1].fields[1:4])
        committed = binding(raw, configuration_id=before.config_uuid, catalog=scalar)
        om.analyze_object_module(raw, committed)
        after = import_configuration(files)
        self.assertEqual(before, after)
        self.assertIn('module execution unsupported:Catalogs/Products/Ext/ObjectModule.bsl', after.activation_issues)

    def test_wrong_source_hash_rejected_before_parser(self):
        with patch.object(om, 'Parser', side_effect=AssertionError('parsed')):
            self.reject(EMPTY, source_sha256='0' * 64)

    def test_hash_changes_with_bom_or_whitespace(self):
        for raw in (b'\xef\xbb\xbf' + EMPTY, EMPTY + b'\n'):
            with self.subTest(raw=raw), self.assertRaises(om.ObjectModuleAnalysisError):
                om.analyze_object_module(raw, binding(EMPTY))

    def test_source_requires_exact_bounded_bytes(self):
        for raw in ('text', bytearray(EMPTY), b'', b'x' * (om.MAX_SOURCE_BYTES + 1)):
            with self.subTest(kind=type(raw)), self.assertRaises(om.ObjectModuleAnalysisError):
                om.analyze_object_module(raw, binding())

    def test_invalid_utf8_and_syntax_are_closed_errors(self):
        for raw in (b'\xff', b'Procedure BeforeWrite(', b'\x00', b'Procedure BeforeWrite(Cancel) @ EndProcedure'):
            with self.subTest(raw=raw): self.reject(raw)

    def test_invalid_binding_type(self):
        with self.assertRaises(om.ObjectModuleAnalysisError):
            om.analyze_object_module(EMPTY, {})

    def test_uuid_types_and_nil_ids(self):
        for name in ('database_id', 'configuration_id'):
            for value in (str(DATABASE), UUID(int=0), None):
                with self.subTest(name=name, value=value): self.reject(EMPTY, **{name: value})
        self.reject(EMPTY, catalog=replace(CATALOG, identity=UUID(int=0)))

    def test_generation_and_hash_shape(self):
        for generation in (0, -1, True, 2**63, '1'):
            with self.subTest(generation=generation): self.reject(EMPTY, configuration_generation=generation)
        for digest in ('A' * 64, 'x' * 64, 'a' * 63, None):
            with self.subTest(digest=digest): self.reject(EMPTY, source_sha256=digest)

    def test_catalog_shape_and_path_name(self):
        for catalog in (None, replace(CATALOG, name='../Products'), replace(CATALOG, name='A/B'),
                        replace(CATALOG, name='New'), replace(CATALOG, code_length=True),
                        replace(CATALOG, description_length=1025), replace(CATALOG, fields=[])):
            with self.subTest(catalog=catalog): self.reject(EMPTY, catalog=catalog)

    def test_metadata_uuid_collisions(self):
        self.reject(EMPTY, configuration_id=CATALOG.identity)
        for identity in (CATALOG.identity, CONFIGURATION, CATALOG.fields[1].identity):
            fields = (replace(CATALOG.fields[0], identity=identity), *CATALOG.fields[1:])
            with self.subTest(identity=identity): self.reject(EMPTY, catalog=replace(CATALOG, fields=fields))

    def test_field_names_cannot_shadow_profile_symbols(self):
        for name in ('Code', 'Код', 'Cancel', 'ThisObject', 'BeforeWrite', '_om_Check', 'active'):
            fields = (*CATALOG.fields, FieldSchema(UUID(int=50), name, 'boolean'))
            with self.subTest(name=name): self.reject(EMPTY, catalog=replace(CATALOG, fields=fields))

    def test_field_types_and_qualifiers_are_exact(self):
        for field in (FieldSchema(UUID(int=20), 'X', 'string', (10,)),
                      FieldSchema(UUID(int=20), 'X', 'catalog_ref', (), CATALOG.identity),
                      FieldSchema(UUID(int=20), 'X', 'number', (12, 2, 'Nonnegative')),
                      FieldSchema(UUID(int=20), 'X', 'number', (12, True, 'Any')),
                      FieldSchema(UUID(int=20), 'X', 'datetime', ('Date',)),
                      FieldSchema(UUID(int=20), 'X', 'boolean', ('extra',))):
            with self.subTest(field=field): self.reject(EMPTY, catalog=replace(CATALOG, fields=(field,)))

    def test_field_count_budget(self):
        fields = tuple(FieldSchema(UUID(int=i + 100), 'F' + str(i), 'boolean') for i in range(65))
        self.reject(EMPTY, catalog=replace(CATALOG, fields=fields))

    def test_preprocessor_hidden_branches_rejected_before_lexer(self):
        raw = b'#If Server Then\nNew HTTPConnection("x");\n#EndIf\n' + EMPTY
        with patch.object(om, 'Lexer', side_effect=AssertionError('lexed')):
            self.reject(raw)

    def test_all_directive_characters_even_in_comments_or_strings(self):
        for raw in (b'&AtServer\n' + EMPTY, b'// #Import Secret\n' + EMPTY,
                    b'#Region X\n' + EMPTY + b'\n#EndRegion', source('Description = "#If";'),
                    source('// &AtServer'), source('Description = "A&B";')):
            with self.subTest(raw=raw): self.reject(raw)

    def test_module_variables_and_initialization_rejected(self):
        for prefix in (b'Var X;\n', b'X = 1;\n', b'BeforeWrite(False);\n'):
            with self.subTest(prefix=prefix): self.reject(prefix + EMPTY)

    def test_exports_async_and_functions_rejected(self):
        for raw in (EMPTY.replace(b'(Cancel)', b'(Cancel) Export'), b'Async ' + EMPTY,
                    EMPTY.replace(b'Procedure', b'Function')):
            with self.subTest(raw=raw): self.reject(raw)

    def test_exactly_one_event_and_no_other_lifecycle(self):
        for raw in (b'// empty', b'Procedure _om_Check()\nEndProcedure',
                    EMPTY + b'\nProcedure BeforeDelete(Cancel)\nEndProcedure',
                    EMPTY + b'\nProcedure OnWrite(Cancel)\nEndProcedure',
                    EMPTY + '\nПроцедура ПередЗаписью(Отказ)\nКонецПроцедуры'.encode()):
            with self.subTest(raw=raw): self.reject(raw)

    def test_event_signature_is_closed(self):
        for signature in (b'()', b'(Val Cancel)', b'(Cancel, Other)', b'(Cancel=False)', b'(Stop)'):
            with self.subTest(signature=signature): self.reject(EMPTY.replace(b'(Cancel)', signature))

    def test_unknown_helper_names_and_unused_helpers_rejected(self):
        for name in ('Validate', '_om_Unused'):
            self.reject(source('', f'Procedure {name}()\nEndProcedure'))

    def test_default_parameters_and_parameter_shadowing_rejected(self):
        for parameters in ('X=False', 'Val Description', 'ThisObject', '_om_Other', 'Write'):
            self.reject(source('_om_A();', f'Procedure _om_A({parameters})\nEndProcedure'))

    def test_procedure_and_parameter_duplicates_rejected(self):
        self.reject(EMPTY + b'\n' + EMPTY.lower())
        self.reject(source('_om_A(Cancel, Cancel);', 'Procedure _om_A(X, x)\nEndProcedure'))

    def test_local_shadowing_and_implicit_locals_rejected(self):
        for body in ('Var Cancel;', 'Var Code;', 'Var _om_X;', 'Var X, x;', 'X = 1;'):
            with self.subTest(body=body): self.reject(source(body))

    def test_local_declarations_only_at_routine_start(self):
        for body in ('Cancel = False; Var X;', 'If Active Then Var X; EndIf;'):
            with self.subTest(body=body): self.reject(source(body))

    def test_uninitialized_local_and_branch_assignment_rejected(self):
        for body in ('Var X; Amount = X;', 'Var X; If Active Then X = 1; EndIf; Amount = X;',
                     'Var X; _om_A(X);'):
            helpers = 'Procedure _om_A(X)\nEndProcedure' if '_om_A' in body else ''
            with self.subTest(body=body): self.reject(source(body, helpers))

    def test_unknown_globals_and_method_names_rejected(self):
        for expression in ('Catalogs', 'Metadata', 'Documents', 'Registers', 'Eval', 'ThisObject', 'Ref', 'DataExchange.Load'):
            with self.subTest(expression=expression): self.reject(source('Cancel = ' + expression + ';'))

    def test_host_calls_rejected_including_dead_code(self):
        for call in ('Eval("1")', 'Message("x")', 'CurrentDate()', 'InfoBaseConnectionString()',
                     'ThisObject.Write()', 'Catalogs.Products.CreateItem()', 'ReadFile("x")'):
            with self.subTest(call=call): self.reject(source('If False Then ' + call + '; EndIf;'))

    def test_unreachable_code_after_return_is_checked(self):
        self.reject(source('Return; Eval("x");'))
        self.reject(source('_om_A();', 'Procedure _om_A()\nReturn; ThisObject.Write();\nEndProcedure'))

    def test_constructors_execute_imports_and_await_rejected(self):
        for body in ('Cancel = New HTTPConnection("x");', 'Cancel = New("Array");',
                     'Execute("Cancel=True;");', 'Cancel = Await _om_A();'):
            with self.subTest(body=body): self.reject(source(body))

    def test_member_and_index_escapes_rejected(self):
        for body in ('ThisObject["Code"] = "A";', 'Cancel = ThisObject.Code.Length;',
                     '(ThisObject).Write();', 'Cancel = ThisObject.Unknown;',
                     'Var X; X = "a"; X.Trim();', 'Thi\u017fObject.Active = True;'):
            with self.subTest(body=body): self.reject(source(body))

    def test_helper_cannot_be_value_or_expression_call(self):
        for body in ('Cancel = _om_A;', 'Cancel = _om_A();', '(_om_A)();', 'Var F; F = _om_A; F();'):
            with self.subTest(body=body): self.reject(source(body, 'Procedure _om_A()\nEndProcedure'))

    def test_helper_wrong_arity_and_omitted_argument_rejected(self):
        for call in ('_om_A();', '_om_A(Cancel, Cancel);', '_om_A(,);'):
            with self.subTest(call=call): self.reject(source(call, 'Procedure _om_A(X)\nEndProcedure'))

    def test_reference_arguments_cannot_be_fields_literals_or_groups(self):
        for argument in ('Description', 'ThisObject.Description', 'False', '(Cancel)', '1 + 2'):
            with self.subTest(argument=argument):
                self.reject(source(f'_om_A({argument});', 'Procedure _om_A(X)\nEndProcedure'))

    def test_event_calls_and_recursion_rejected(self):
        self.reject(source('BeforeWrite(Cancel);'))
        self.reject(source('_om_A();', 'Procedure _om_A()\n_om_A();\nEndProcedure'))
        self.reject(source('_om_A();', 'Procedure _om_A()\n_om_B();\nEndProcedure\nProcedure _om_B()\n_om_A();\nEndProcedure'))

    def test_loops_try_raise_and_goto_rejected(self):
        for body in ('While False Do Cancel = True; EndDo;', 'For X = 1 To 2 Do Cancel = True; EndDo;',
                     'Try Cancel = True; Except Cancel = False; EndTry;', 'Raise "no";', '~L: Goto ~L;'):
            with self.subTest(body=body): self.reject(source(body))

    def test_date_null_and_oversized_literals_rejected(self):
        for literal in ("'20260101'", 'Null', '9' * 39, '0.' + '1' * 19, '"' + 'x' * 1025 + '"'):
            with self.subTest(literal=literal[:30]): self.reject(source('Cancel = ' + literal + ';'))

    def test_routine_parameter_and_local_count_bounds(self):
        raw = source('', '\n'.join('Procedure _om_P' + str(i) + '()\nEndProcedure' for i in range(16)))
        self.reject(raw)
        self.reject(source('_om_A();', 'Procedure _om_A(' + ','.join('P' + str(i) for i in range(9)) + ')\nEndProcedure'))
        self.reject(source('Var ' + ','.join('X' + str(i) for i in range(33)) + ';'))

    def test_token_budget(self):
        self.reject(source('Cancel = False;\n' * 600))

    def test_nesting_and_unary_budget_before_parser(self):
        for body in ('Cancel = ' + '(' * 20 + 'True' + ')' * 20 + ';',
                     'If True Then ' * 20 + 'Cancel = True; ' + 'EndIf; ' * 20,
                     'Cancel = ' + 'NOT ' * 20 + 'True;'):
            with self.subTest(body=body[:50]), patch.object(om, 'Parser', side_effect=AssertionError('parsed')):
                self.reject(source(body))

    def test_ast_depth_and_node_budgets(self):
        self.reject(source('Amount = ' + '+'.join('1' for _ in range(100)) + ';'))
        with patch.object(om, 'MAX_AST_NODES', 2):
            self.reject(source('Cancel = True;'))

    def test_call_graph_expansion_budget(self):
        helpers = '\n'.join('Procedure _om_P' + str(i) + '()\n' +
            (('_om_P' + str(i + 1) + '();\n') * 2 if i < 14 else '') + 'EndProcedure' for i in range(15))
        self.reject(source('_om_P0();', helpers))

    def test_unknown_ast_node_is_fail_closed(self):
        token = Token('IDENT', 'x', 1, 1, '<static-test>')
        with patch.object(om.Parser, 'parse', return_value=[ast.Execute(token, ast.Literal(token, 'x'))]):
            self.reject(EMPTY)

    def test_parser_recursion_is_closed_error(self):
        with patch.object(om.Parser, 'parse', side_effect=RecursionError):
            self.reject(EMPTY)

    def test_diagnostics_do_not_echo_source(self):
        raw = source('SecretPrivateName = "sensitive-value";')
        with self.assertRaises(om.ObjectModuleAnalysisError) as caught:
            self.analyze(raw)
        self.assertNotIn('SecretPrivateName', str(caught.exception))
        self.assertNotIn('sensitive-value', str(caught.exception))

    def test_zero_calls_into_database_or_configuration_activation(self):
        with patch('yadinassi.database_context.SQLiteDBContext', side_effect=AssertionError('database')), \
             patch('yadinassi.sqlite_catalog.SQLiteCatalogBackend', side_effect=AssertionError('database')):
            self.analyze()


if __name__ == '__main__':
    unittest.main()
