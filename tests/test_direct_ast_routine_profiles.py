"""Side-specific Python definitions never invoke the retired text emitter."""
import unittest
from yadinassi import Interpreter

class DirectASTRoutineProfiles(unittest.TestCase):
    def test_server_dual_and_initializer_without_old_compiler(self):
        source='''
&AtServer
Var Counter;
#If AtServer Then
Counter=10;
#EndIf
&AtClientAtServerNoContext
Function Both(Val N=2) Return N+1; EndFunction
&AtServer
Function Server() Counter=Counter+Both(); Return Counter; EndFunction
R=Server(); C=Both();
'''
        vm=Interpreter(compilation_profile='managed-thick-file');self.addCleanup(vm.close)
        vm.execute_prepared(vm.prepare(source))
        self.assertEqual((vm.variables['r'],vm.variables['c']),(13,3))
        self.assertNotIn('counter',vm.variables)

    def test_uninitialized_lexical_read_is_runtime_not_compile_error(self):
        vm=Interpreter();self.addCleanup(vm.close)
        prepared=vm.prepare('Function F() X=X+1; Return X; EndFunction; R=F();')
        from yadinassi.types.errors import BSLRuntimeError
        with self.assertRaisesRegex(BSLRuntimeError, 'local variable'):vm.execute_prepared(prepared)

    def test_source_startup_and_safe_mode_without_retired_compiler(self):
        from test_configuration_source_runtime import source
        from yadinassi.configuration.configuration_source_runtime import SourceApplication
        code=b'Procedure Inner() SetSafeMode(True); Raise "error"; EndProcedure\nProcedure Outer() SetSafeMode(True);Try Inner();Except EndTry;Message(SafeMode());EndProcedure\nProcedure OnStart() Outer();Message(SafeMode());EndProcedure'
        output=[]
        app=SourceApplication(source(code),output=output.append);self.addCleanup(app.close)
        app.start()
        self.assertEqual(output,['Да','Нет'])

    def test_source_direct_frames_cover_defaults_and_nested_calls(self):
        from test_python_direct_source_scopes import ScopeContext
        from yadinassi.execution.codegen.direct_emitter import compile_owned
        from yadinassi.syntax.parser import parse
        text='Function Inner() Return Depth(); EndFunction Function Outer(Val X=1) Return X+Inner(); EndFunction A=Outer(); B=Depth();'
        program=parse(text)
        program[1].parameters[0].default=parse('Depth();')[0].expression
        plan=compile_owned(program,source_text=text,source_name='<scope>',source_scopes=True)
        context=ScopeContext();state={};plan.run(state,context=context)
        self.assertEqual(state,{'a':3,'b':0})
        self.assertEqual(context.frames,[])
        self.assertEqual(context.events,[('enter',1),('enter',2),('leave',2),('leave',1)])

    def test_source_callable_byref_accepts_canonical_forwarded_storage(self):
        from test_python_direct_source_scopes import ScopeContext
        from yadinassi.execution.codegen.direct_emitter import compile_owned
        from yadinassi.execution.codegen.direct_collections import _Cell
        from yadinassi.syntax.parser import parse
        from yadinassi.types.values import HostFunction
        callback=HostFunction('C',lambda:42)
        for actual in ('C','A[0]'):
            text='Function Invoke(F) Return F(); EndFunction R=Invoke('+actual+');'
            plan=compile_owned(parse(text),source_text=text,source_name='<call>',source_scopes=True,source_dispatch=True)
            state={'c':callback,'a':[callback]};context=ScopeContext();plan.run(state,context=context)
            self.assertEqual(state['r'],42);self.assertEqual(context.frames,[])
        text='Function Invoke(F) Return F(); EndFunction'
        plan=compile_owned(parse(text),source_text=text,source_name='<call>',source_scopes=True,source_dispatch=True,exports=True)
        context=ScopeContext();context.enter()
        try:self.assertEqual(plan.function({},plan.constants,context)['invoke'](_Cell(callback)),42)
        finally:context.leave()

    def test_source_constructor_arity_is_checked_before_argument_effects(self):
        from test_configuration_source_runtime import source
        from yadinassi.configuration.configuration_source_runtime import SourceApplication
        from yadinassi.types.errors import BSLError
        for arguments in ('Effect(), Effect()', 'Effect(),, Effect()'):
            output=[]
            code=('Function Effect() Message("wrong-effect");Return 1;EndFunction Procedure OnStart() X=New Query('+arguments+'); EndProcedure').encode()
            app=SourceApplication(source(code),output=output.append);self.addCleanup(app.close)
            with self.assertRaises((BSLError,ValueError,TypeError)):
                app.start()
            self.assertEqual(output,[])

    def test_owned_handler_declarations_and_casefolded_external_names(self):
        from yadinassi.execution.direct.python_direct_handlers import prepare_handlers
        from yadinassi.execution.codegen.direct_boundaries import BoundaryContext
        from yadinassi.syntax.parser import parse
        state={};external={'field':4}
        class Context(BoundaryContext):
            def external_get(self,name):return external[name]
            def external_set(self,name,value):external[name]=value
        text='Var Total; Procedure Event(x) Field=Field+1;x=Total;EndProcedure'
        plan=prepare_handlers(parse(text),source_text=text,external_names=('FiElD',))
        self.assertEqual(plan.invoke('Event','client',[0],state=state,context_factory=Context),[None])
        state['total']=9
        self.assertEqual(plan.invoke('Event','client',[0],state=state,context_factory=Context),[9])
        self.assertEqual(state,{'total':9});self.assertEqual(external,{'field':6})

    def test_unknown_handler_argument_does_not_gain_module_authority(self):
        from yadinassi.execution.direct.python_direct_handlers import prepare_handlers
        from yadinassi.execution.codegen.direct_boundaries import BoundaryContext
        from yadinassi.syntax.parser import parse
        from yadinassi.types.errors import BSLRuntimeError
        text='Procedure Event() Capture(Field);EndProcedure'
        plan=prepare_handlers(parse(text),source_text=text)
        seen=[];state={'field':42}
        def context():
            return BoundaryContext(services={'capture':seen.append})
        # A same-named undeclared state value is not an implicit lexical grant.
        with self.assertRaises(BSLRuntimeError) as denied:
            plan.invoke('Event','client',[],state=state,context_factory=context)
        error=denied.exception
        self.assertIs(type(error),BSLRuntimeError)
        self.assertEqual((error.source,error.line,error.source_line),('<direct-form>',1,text))
        code=self.test_unknown_handler_argument_does_not_gain_module_authority.__code__
        positions=getattr(code,'co_positions',None)
        has_columns=positions is not None and any(pos[2] is not None for pos in positions())
        self.assertEqual(error.column,27 if has_columns else 1)
        self.assertIn('Field',error.message)
        self.assertEqual(seen,[]);self.assertEqual(state,{'field':42})
        # The same body and service see the value when the source declares it.
        declared='Var Field;\n'+text
        plan=prepare_handlers(parse(declared),source_text=declared)
        plan.invoke('Event','client',[],state=state,context_factory=context)
        self.assertEqual(seen,[42]);self.assertEqual(state,{'field':42})

    def test_unknown_source_host_argument_never_leaks_unset_sentinel(self):
        from test_python_direct_source_scopes import ScopeContext
        from yadinassi.execution.codegen.direct_emitter import compile_owned
        from yadinassi.syntax.parser import parse
        text='Procedure Event() Capture(Missing);EndProcedure Event();'
        plan=compile_owned(parse(text),source_text=text,source_name='<unknown>',source_scopes=True)
        calls=[];context=ScopeContext();context._services['capture']=calls.append
        with self.assertRaises(__import__("yadinassi.types.errors",fromlist=["BSLRuntimeError"]).BSLRuntimeError):plan.run({},context=context)
        self.assertEqual(calls,[]);self.assertEqual(context.frames,[])
