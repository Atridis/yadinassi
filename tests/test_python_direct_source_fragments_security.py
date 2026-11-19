"""Source fragments keep live slots, authority and finite activation lifetimes."""
import unittest
from unittest.mock import patch
from decimal import Decimal
from test_configuration_source_runtime import source
from test_source_application_exports import configuration
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_source import SourceBoundary
from yadinassi.execution.direct.source.python_direct_source_fragments import execution, _ACTIVE


class SourceFragmentsSecurity(unittest.TestCase):
    def setUp(self):
        old=patch('yadinassi.execution.codegen.experimental_naked_collections.prepare',create=True,side_effect=AssertionError('old compiler'))
        old.start();self.addCleanup(old.stop)
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            guard=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            guard.start();self.addCleanup(guard.stop)

    def app(self,code='',helper=None):
        output=[]
        package=source(code.encode()) if helper is None else configuration(code,helper)
        app=SourceApplication(package,output=output.append)
        self.addCleanup(app.close)
        return app,output

    def test_local_export_shadow_and_live_export_slot(self):
        app,out=self.app('''Var Shared Export;
Procedure OnStart() Shared=1;Message(Helpers.Run(4));Message(Shared);Helpers.WriteShared();Message(Shared);EndProcedure''',
            '''Function Run(Val Shared) Export
Execute("Shared=Shared+2;");Return Eval("Shared");EndFunction
Procedure WriteShared() Export Execute("Shared=9;");EndProcedure''')
        app.start();self.assertEqual(out,['6','1','9'])

    def test_depth_spans_new_source_routine_boundaries_and_restores(self):
        for expression in ('Eval("Helpers.Run()")','Helpers.Run()'):
            helper=('Function Run() Export Return '+expression+';EndFunction' if expression.startswith('Eval') else
                    'Function Run() Export Execute("Helpers.Run();");Return 1;EndFunction')
            app,_=self.app('',helper);app.start()
            with self.assertRaisesRegex(Exception,'предел вложенности'):
                app.interpreter.execute('Helpers.Run();')
            self.assertEqual(_ACTIVE.get(),())
            self.assertEqual(app.interpreter.execute('Eval("3");'),Decimal(3))

    def test_warm_constructor_binding_rechecked(self):
        app,_=self.app();app.start();vm=app.interpreter;effects=[]
        def replace():vm.types['array']=HostFunction('Array',lambda:effects.append('factory'))
        vm.register_function('Replace',replace)
        with self.assertRaises((Exception,BoundaryViolation)):
            vm.execute('For I=1 To 2 Do Execute("A=New Array;");Replace();EndDo;')
        self.assertEqual(effects,[])

    def test_qualified_procedure_value_rejected_before_arguments(self):
        app,_=self.app('', 'Procedure P(Val X) Export EndProcedure');app.start()
        effects=[];app.interpreter.register_function('Touch',lambda:effects.append('arg') or Decimal(1))
        with self.assertRaises((Exception,BoundaryViolation)):
            app.interpreter.execute('Eval("Helpers.P(Touch())");')
        self.assertEqual(effects,[])

    def test_retained_fragment_reference_revoked(self):
        app,_=self.app();app.start();saved=[]
        app.interpreter.functions['hold']=HostFunction('Hold',lambda ref:saved.append(ref),reference_parameters=frozenset({0}))
        app.interpreter.execute('X=1;Execute("Hold(X);X=3;");')
        self.assertEqual(len(saved),1)
        with self.assertRaises(BoundaryViolation):saved[0].get()
        with self.assertRaises(BoundaryViolation):saved[0].set(Decimal(8))
        self.assertEqual(app.interpreter.variables['x'],Decimal(3))

    def test_source_boundary_subclasses_refused(self):
        app,_=self.app();app.start()
        class Derived(SourceBoundary):pass
        context=object.__new__(Derived);context.app=app;context.vm=app.interpreter
        for kind in ('execute','eval'):
            with self.assertRaises(BoundaryViolation):
                with execution(context,kind,{}, {},None):self.fail('subclass admitted')

    def test_depth_tamper_rejected_before_arithmetic_callback(self):
        app,_=self.app();app.start();effects=[]
        class Counter:
            def __sub__(self,other):effects.append('subtract');return 0
        def mutate():_ACTIVE.get()[-1][1][0]=Counter()
        app.interpreter.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('Execute("Mutate();");')
        self.assertEqual(effects,[])
        self.assertEqual(_ACTIVE.get(),())

    def test_injected_cache_refused_without_callbacks_and_released(self):
        from yadinassi.execution.direct.source.python_direct_source_fragments import _UNITS
        for kind,expression in (('execute','Execute("X=1;");'),('eval','Eval("1");')):
            app,_=self.app();app.start();effects=[];owners=[]
            class Cache(dict):
                def get(self,*args):effects.append('get');return None
                def __iter__(self):effects.append('iter');return iter(())
            def poison():
                owner=next(owner for owner in _UNITS if owner.app is app)
                owners.append(owner);setattr(owner,'_'+kind+'_units',Cache())
            app.interpreter.register_function('Poison',poison)
            with self.assertRaises(BoundaryViolation):
                app.interpreter.execute(expression+'Poison();'+expression)
            self.assertEqual(effects,[])
            self.assertEqual(len(owners),1)
            self.assertNotIn(owners[0],_UNITS)

    def test_unsupported_fragment_is_fatal_and_depth_recovers(self):
        from yadinassi.execution.codegen.experimental_naked_collections import UnsupportedNakedSyntax
        app,_=self.app();app.start();vm=app.interpreter;effects=[]
        vm.register_function('Effect',lambda:effects.append(1))
        for expression in ('Execute("Effect();New UnsupportedConstructor;")',
                           'Eval("New UnsupportedConstructor(Effect())")'):
            for _ in range(2):
                with self.assertRaises(UnsupportedNakedSyntax):
                    vm.execute('Try '+expression+';Except Caught=True;EndTry;')
                self.assertEqual(effects,[]);self.assertNotIn('caught',vm.variables)
                self.assertEqual(_ACTIVE.get(),())
        self.assertEqual(vm.execute('Eval("2+3");'),5)

    def test_loop_authority_is_checked_after_callback_before_next_effect(self):
        app,_=self.app();app.start();effects=[];vm=app.interpreter
        def close():
            effects.append('close');app.close()
        vm.register_function('CloseOwner',close)
        vm.register_function('Touch',lambda:effects.append('touch'))
        with self.assertRaises(BoundaryViolation):
            vm.execute('Execute("For I=1 To 2 Do CloseOwner();Touch();EndDo;");')
        self.assertEqual(effects,['close'])
        self.assertEqual(_ACTIVE.get(),())
