"""Only installed immutable scalar literal Val defaults enter command calls."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.errors import BSLError
from yadinassi.syntax import ast
from configuration_runtime_fixture import module_files

SOURCE='''Function F(Val A=7, Val B=9) Export Return A;EndFunction
Function Sum(Val A, Val B=9) Export Return A+B;EndFunction
Function Inner(Val X=11) Return X;EndFunction
Function Nested(Val X=3) Export Return Inner()+X;EndFunction
Function Effect() Export Message("effect");Return 2;EndFunction'''

class ConfigurationDefaultTests(unittest.TestCase):
    def app(self,source=SOURCE,output=None):
        app=ConfigurationApplication.from_files(module_files([('Tools',source,{})]),output=output or (lambda x:None))
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_omitted_trailing_and_explicit_undefined_match_oracle(self):
        app=self.app();oracle=Interpreter(execution_backend='compiled-strict');self.addCleanup(oracle.close)
        oracle.execute(SOURCE)
        for call in ('F()','F(,2)','F(,)','F(Undefined)','F(3)','F(3,)','Sum(2)','Nested()','Nested(5)'):
            with self.subTest(call=call):
                oracle.execute('Result='+call+';');app.execute('Result=Tools.'+call+';')
                self.assertEqual(app.interpreter.variables['result'],oracle.variables['result'])

    def test_all_literal_scalar_types_and_aliases(self):
        for literal,expected in (('Undefined',None),('True',True),('False',False),('"text"','text'),('12.5',Decimal('12.5'))):
            app=self.app('Function F(Val X='+literal+') Export Return X;EndFunction')
            self.assertEqual(app.execute('tOoLs.f()'),expected)
            self.assertIsNone(app.execute('Tools.F(Undefined)'))

    def test_required_hole_binds_undefined_without_suppressing_other_actuals(self):
        seen=[];app=self.app(output=seen.append)
        with self.assertRaises(BSLError):app.execute('Tools.Sum(,Tools.Effect());')
        self.assertEqual(seen,['effect'])
        with self.assertRaises(BSLError):app.execute('Tools.Sum();')
        self.assertEqual(app.execute('Tools.Sum(2)'),Decimal(11))

    def test_explicit_argument_order_and_mutation_guard(self):
        seen=[];app=self.app(output=seen.append)
        self.assertEqual(app.execute('Tools.F(Tools.Effect(),Tools.Effect())'),Decimal(2))
        self.assertEqual(seen,['effect','effect'])
        routine=app._modules['tools','client'].interpreter.routines['f']
        literal=routine.parameters[0].default;original=literal.value
        def mutate(value):literal.value=Decimal(123)
        app.interpreter.output=mutate
        app._modules['tools','client'].interpreter.output=mutate
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F(,Tools.Effect());')
        finally:literal.value=original
        self.assertEqual(app.execute('Tools.F()'),Decimal(7))

    def test_default_ast_and_parameter_replacements_not_new_authority(self):
        app=self.app();routine=app._modules['tools','client'].interpreter.routines['f']
        parameter=routine.parameters[0];original=parameter.default
        parameter.default=ast.Literal(original.token,Decimal(100))
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F()')
        finally:parameter.default=original
        original_value=original.value
        class Host:
            def __eq__(self,other):raise AssertionError('host equality')
        original.value=Host()
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F()')
        finally:original.value=original_value
        self.assertEqual(app.execute('Tools.F()'),Decimal(7))

    def test_byref_and_nonliteral_defaults_remain_closed(self):
        for source in ('Function F(X=1) Export Return X;EndFunction',
                       'Function F(Val X=-1) Export Return X;EndFunction'):
            app=self.app(source)
            with self.assertRaises((PythonDirectUnsupported,BoundaryViolation)):app.execute('Tools.F()')

    def test_readers_and_message_do_not_gain_omission_protocol(self):
        app=self.app()
        for text in ('Message(,);','Metadata.CommonModules.Find(,).Name;'):
            with self.assertRaises((PythonDirectUnsupported,BSLError)):app.execute(text)

    def test_plan_snapshot_replacement_fails_after_binding(self):
        app=self.app();owner=app._modules['tools','client'].interpreter;plan=owner._direct_configuration_plan
        saved=plan._configuration_parameters
        def mutate(value):plan._configuration_parameters=()
        app.interpreter.output=mutate
        app._modules['tools','client'].interpreter.output=mutate
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F(,Tools.Effect());')
        finally:plan._configuration_parameters=saved
        self.assertEqual(app.execute('Tools.F()'),Decimal(7))

    def test_definition_time_snapshot_cannot_be_replaced_before_scope(self):
        app=self.app();owner=app._modules['tools','client'].interpreter;plan=owner._direct_configuration_plan
        original=plan._configuration_parameters
        plan._configuration_parameters=tuple(list(original))
        try:
            with self.assertRaises(BoundaryViolation):app.execute('Tools.F()')
        finally:plan._configuration_parameters=original
        self.assertEqual(app.execute('Tools.F()'),Decimal(7))

    def test_captured_optional_callable_checks_lifetime_and_default_identity(self):
        from yadinassi.python_direct_configuration_commands import _Scope
        from yadinassi.python_direct_configuration import ConfigurationBoundary
        app=self.app();scope=_Scope(app);scope.enter()
        try:
            context=ConfigurationBoundary(app,app.interpreter);context.enter()
            module=context.external_get('Tools');call=context.resolve_member(module,'F')
            self.assertEqual(call(),Decimal(7));self.assertIsNone(call(None))
            node=app._modules['tools','client'].interpreter.routines['f'].parameters[0].default
            saved=node.value;node.value=Decimal(123)
            try:
                with self.assertRaises(BoundaryViolation):call()
            finally:node.value=saved
        finally:scope.leave()
        with self.assertRaises(BoundaryViolation):call()

    def test_policy_callback_default_mutation_fails_before_body(self):
        app=self.app();routine=app._modules['tools','client'].interpreter.routines['f']
        node=routine.parameters[0].default;saved=node.value;original=app.check_call
        def check(routine,caller):
            original(routine,caller);node.value=Decimal(456)
        with patch.object(app,'check_call',check):
            try:
                with self.assertRaises(BoundaryViolation):app.execute('Tools.F()')
            finally:node.value=saved
        self.assertEqual(app.execute('Tools.F()'),Decimal(7))

    def test_noncommand_boundary_does_not_gain_default_or_hole_binding(self):
        from yadinassi.python_direct_configuration import ConfigurationBoundary
        app=self.app();context=ConfigurationBoundary(app,app.interpreter);context.enter()
        try:
            module=context.external_get('Tools');call=context.resolve_member(module,'F')
            with self.assertRaises(TypeError):call()
            self.assertIsNone(call(None,None))
        finally:context.leave()

    def test_hostile_by_value_flag_never_runs_boolean_hook(self):
        for after_argument in (False,True):
            app=self.app();parameter=app._modules['tools','client'].interpreter.routines['f'].parameters[0]
            original=parameter.by_value;seen=[]
            class Host:
                def __bool__(self):seen.append('bool');raise AssertionError('host truth')
            if after_argument:
                app._modules['tools','client'].interpreter.output=lambda value:setattr(parameter,'by_value',Host())
            else:parameter.by_value=Host()
            try:
                with self.assertRaises((BoundaryViolation,PythonDirectUnsupported)):
                    app.execute('Tools.F(,Tools.Effect())' if after_argument else 'Tools.F()')
            finally:parameter.by_value=original
            self.assertEqual(seen,[])

    def test_arity_errors_match_oracle_without_argument_effects(self):
        source=SOURCE+' Function Need(Val A,Val B) Export Return A;EndFunction'
        for call in ('Need(Effect())','F(Effect(),Effect(),Effect())'):
            seen=[];app=self.app(source,seen.append);expected=[]
            oracle=Interpreter(execution_backend='compiled-strict',output=expected.append);self.addCleanup(oracle.close)
            oracle.execute(source)
            oracle.execute('Try '+call+';Except Message("caught");EndTry;')
            qualified=call.replace('Effect()', 'Tools.Effect()')
            app.execute('Try Tools.'+qualified+';Except Message("caught");EndTry;')
            self.assertEqual(seen,expected);self.assertEqual(seen,['caught'])

    def test_nested_qualified_calls_and_collection_like_names_use_same_contract(self):
        source='Function Add(Val X=4,Val Y=5) Export Return X+Y;EndFunction Function Nested() Export Return Tools.Add(,3);EndFunction'
        app=self.app(source)
        self.assertEqual(app.execute('Tools.Add()'),Decimal(9))
        self.assertEqual(app.execute('Tools.Nested()'),Decimal(7))

    def test_required_hole_matches_undefined_oracle(self):
        source=SOURCE+' Function Need(Val A,Val B) Export Return A;EndFunction'
        for call in ('Need(,Effect())','Sum(,Effect())'):
            seen=[];app=self.app(source,seen.append);expected=[]
            oracle=Interpreter(execution_backend='compiled-strict',output=expected.append);self.addCleanup(oracle.close)
            oracle.execute(source);oracle.execute('Result="unset";Try Result='+call+';Except Message("caught");EndTry;')
            qualified=call.replace('Effect()', 'Tools.Effect()')
            app.execute('Result="unset";Try Result=Tools.'+qualified+';Except Message("caught");EndTry;')
            self.assertEqual(seen,expected)
            self.assertEqual(app.interpreter.variables['result'],oracle.variables['result'])

    def test_procedure_as_value_rejects_before_actual_effects(self):
        seen=[];app=self.app(SOURCE+' Procedure P(Val X=1) Export EndProcedure',seen.append)
        with self.assertRaises(BSLError):app.execute('Result=Tools.P(Tools.Effect());')
        self.assertEqual(seen,[])
        app.execute('Tools.P();')

    def test_configuration_count_hook_is_inert_outside_command_scope(self):
        from yadinassi.python_direct_configuration import ConfigurationBoundary
        app=self.app();context=ConfigurationBoundary(app,app.interpreter);context.enter()
        try:
            module=context.external_get('Tools')
            call=context.resolve_configuration_member_call(module,'F',argument_count=0)
            with self.assertRaises(TypeError):call()
        finally:context.leave()
