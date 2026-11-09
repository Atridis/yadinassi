"""Documented callback contract and local composition, not native captures."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.callbacks import BSLCallbackDescription
from yadinassi.values import BSLType


SOURCE = '''
Var Count, Trace;
Function Sum(Result, Extra) Export
    Count=Count+1; Return Result+Extra;
EndFunction
Procedure Record(Result, Extra) Export
    Count=Count+1; Trace=Trace+String(Result)+String(Extra);
EndProcedure
Function Echo(Result, Extra) Export Return Result; EndFunction
Function Additional(Result, Extra) Export Return Extra; EndFunction
Function Hidden(Result, Extra) Return 999; EndFunction
Function Broken(Result, Extra) Export Count=Count+1; Raise "callback failure"; EndFunction
Function Describe(Name, Extra=Undefined) Export
    Return New CallbackDescription(Name, ThisObject, Extra);
EndFunction
Count=0; Trace="";
'''


class CallbackTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute(SOURCE, 'Handlers.bsl')

    def tearDown(self):
        self.vm.close()

    def test_bilingual_constructor_type_identity_and_case(self):
        for name in ('CallbackDescription', 'ОписаниеОповещения', 'cAlLbAcKdEsCrIpTiOn'):
            with self.subTest(name=name):
                self.vm.execute(f'c=New {name}("Sum", ThisObject, 3);')
                self.assertEqual(self.vm.execute('TypeOf(c)'), BSLType.CALLBACK_DESCRIPTION)
                self.assertEqual(self.vm.execute(f'Type("{name}")'), BSLType.CALLBACK_DESCRIPTION)
                self.assertEqual(self.vm.execute('String(c)'), 'ОписаниеОповещения')

    def test_bilingual_dispatch_returns_exported_function_result(self):
        self.vm.execute('c=New ОписаниеОповещения("sUM", ЭтотОбъект, 3);')
        for name in ('RunCallback', 'ВыполнитьОбработкуОповещения', 'rUnCaLlBaCk'):
            self.assertEqual(self.vm.execute(f'{name}(c, 7)'), Decimal(10))
        self.assertEqual(self.vm.variables['count'], Decimal(3))

    def test_procedure_returns_undefined_even_in_expression(self):
        self.vm.execute('c=New CallbackDescription("Record", ThisObject, "x"); '
                        'result=RunCallback(c, "y"); RunCallback(c, "z");')
        self.assertIsNone(self.vm.variables['result'])
        self.assertEqual(self.vm.variables['trace'], 'yxzx')

    def test_omitted_result_explicit_undefined_and_hole_are_two_parameters(self):
        self.vm.execute('c=New CallbackDescription("Echo", ThisObject);')
        for expression in ('RunCallback(c)', 'RunCallback(c, Undefined)', 'RunCallback(c,)'):
            self.assertIsNone(self.vm.execute(expression))
        self.assertIsNone(self.vm.execute('RunCallback(Describe("Additional"), 42)'))

    def test_optional_constructor_holes_and_empty_description(self):
        for expression in ('New CallbackDescription', 'New CallbackDescription(, , , ,)',
                           'New CallbackDescription(Undefined, Undefined)'):
            self.vm.execute(f'c={expression};')
            self.assertIsNone(self.vm.execute('c.ProcedureName'))
            self.assertIsNone(self.vm.execute('c.Module'))
            with self.assertRaisesRegex(BSLError, 'не заданы'):
                self.vm.execute('RunCallback(c)')
        self.vm.execute('c=New CallbackDescription("Echo", ThisObject, , ,);')
        self.assertEqual(self.vm.execute('RunCallback(c, 42)'), Decimal(42))

    def test_readonly_bilingual_properties_keep_receiver_and_object_identity(self):
        self.vm.execute('extra=New Structure("N",1); c=New CallbackDescription("Echo", ThisObject, extra);')
        for ru, en in (('ИмяПроцедуры','ProcedureName'), ('Модуль','Module'),
                       ('ДополнительныеПараметры','AdditionalParameters'),
                       ('ИмяПроцедурыОбработкиОшибки','ErrorHandlerProcedureName'),
                       ('МодульОбработкиОшибки','ErrorHandlerModule')):
            self.assertIs(self.vm.execute('c.'+ru), self.vm.execute('c.'+en))
            with self.assertRaisesRegex(BSLError, 'недоступно для записи'):
                self.vm.execute('c.'+en+'=Undefined;')
        self.assertTrue(self.vm.execute('c.Module=ThisObject'))
        self.assertIs(self.vm.execute('c.AdditionalParameters'), self.vm.variables['extra'])

    def test_properties_are_not_callable_and_python_attributes_are_closed(self):
        self.vm.execute('c=Describe("Echo");')
        for name in ('ProcedureName', 'module', 'additional_parameters', '__dict__', '__class__'):
            with self.assertRaises(BSLError):
                self.vm.execute('c.'+name+'()')
        for name in ('procedure_name', 'additional_parameters', '__dict__', '__class__', 'interpreter'):
            with self.assertRaises(BSLError):
                self.vm.execute('c.'+name)

    def test_dynamic_new_reuses_constructor_and_type_registry(self):
        self.vm.execute('args=New Array; args.Add("Sum"); args.Add(ThisObject); args.Add(4); '
                        'c=New(Type("ОписаниеОповещения"), args);')
        self.assertEqual(self.vm.execute('RunCallback(c,5)'), Decimal(9))
        self.assertEqual(self.vm.execute('TypeOf(New("CallbackDescription"))'), BSLType.CALLBACK_DESCRIPTION)

    def test_description_passes_through_parameters_return_arrays_and_structures(self):
        self.vm.execute('''
Function Forward(Val D) Return D; EndFunction
c=Describe("Sum",5); a=New Array; a.Add(Forward(c)); box=New Structure("Callback",a[0]);
result=RunCallback(box.Callback,7);
''')
        self.assertEqual(self.vm.variables['result'], Decimal(12))
        self.assertIs(self.vm.variables['c'], self.vm.execute('box.Callback'))

    def test_aliases_preserve_description_identity(self):
        self.vm.execute('a=Describe("Echo"); b=a; c=Describe("Echo");')
        self.assertTrue(self.vm.execute('a=b'))
        self.assertFalse(self.vm.execute('a=c'))

    def test_repeated_calls_retain_module_state_without_leaking_local_frames(self):
        self.vm.execute('''
Function Outer(Val Count)
    Return RunCallback(Describe("Sum",Count),2)+Count;
EndFunction
x=Outer(7); y=Outer(11);
''')
        self.assertEqual(self.vm.variables['x'], Decimal(16))
        self.assertEqual(self.vm.variables['y'], Decimal(24))
        self.assertEqual(self.vm.variables['count'], Decimal(2))
        self.assertIsNone(self.vm.locals)

    def test_nested_callback_chain_returns_all_results(self):
        self.vm.execute('''
Function Step(Result, Next) Export Return RunCallback(Next,Result+1)*2; EndFunction
''')
        self.vm.execute('tail=Describe("Sum",3); middle=Describe("Step",tail); '
                        'head=Describe("Step",middle); answer=RunCallback(head,4);')
        self.assertEqual(self.vm.variables['answer'], Decimal(36))
        self.assertEqual(self.vm.variables['count'], Decimal(1))

    def test_rebinding_formals_does_not_rebind_caller_values_or_description(self):
        self.vm.execute('''
Function Rebind(Result, Extra) Export Result=8; Extra=9; Return Result+Extra; EndFunction
''')
        self.vm.execute('x=1; extra=2; c=Describe("Rebind",extra); answer=RunCallback(c,x);')
        self.assertEqual(self.vm.variables['answer'], Decimal(17))
        self.assertEqual(self.vm.variables['x'], Decimal(1))
        self.assertEqual(self.vm.execute('c.AdditionalParameters'), Decimal(2))

    def test_mutable_argument_and_extra_objects_are_shared(self):
        self.vm.execute('''
Function Mutate(Result, Extra) Export Result.N=Result.N+1; Extra.Add(Result); Return Extra; EndFunction
''')
        self.vm.execute('x=New Structure("N",3); extra=New Array; c=Describe("Mutate",extra); '
                        'answer=RunCallback(c,x); RunCallback(c,x);')
        self.assertEqual(self.vm.execute('x.N'), Decimal(5))
        self.assertIs(self.vm.variables['answer'], self.vm.variables['extra'])
        self.assertIs(self.vm.execute('extra[1]'), self.vm.variables['x'])

    def test_callback_arguments_evaluate_once_left_to_right(self):
        self.vm.execute('''
Function D() Trace=Trace+"D"; Return Describe("Echo"); EndFunction
Function R() Trace=Trace+"R"; Return 7; EndFunction
answer=RunCallback(D(),R());
''')
        self.assertEqual(self.vm.variables['trace'], 'DR')
        self.assertEqual(self.vm.variables['answer'], Decimal(7))

    def test_constructor_arguments_evaluate_once_left_to_right(self):
        self.vm.execute('''
Function N() Trace=Trace+"N"; Return "Echo"; EndFunction
Function M() Trace=Trace+"M"; Return ThisObject; EndFunction
Function E() Trace=Trace+"E"; Return 2; EndFunction
c=New CallbackDescription(N(),M(),E());
''')
        self.assertEqual(self.vm.variables['trace'], 'NME')

    def test_missing_and_private_handler_fail_before_body(self):
        for name in ('Missing', 'Hidden'):
            self.vm.execute(f'c=Describe("{name}");')
            with self.assertRaisesRegex(BSLError, 'Метод объекта не обнаружен'):
                self.vm.execute('RunCallback(c,7)')
        self.assertEqual(self.vm.variables['count'], Decimal(0))

    def test_handler_arity_and_defaults_use_ordinary_dispatch(self):
        self.vm.execute('''
Function One(Result) Export Return Result; EndFunction
Function Three(Result, Extra, Tail=3) Export Return Result+Extra+Tail; EndFunction
''')
        with self.assertRaisesRegex(BSLError, 'ожидает 1 аргументов'):
            self.vm.execute('RunCallback(Describe("One"),1)')
        self.assertEqual(self.vm.execute('RunCallback(Describe("Three",2),1)'), Decimal(6))

    def test_handler_error_preserves_effects_diagnostics_and_recovers(self):
        self.vm.execute('''
c=Describe("Broken");
Try result=RunCallback(c,1); Except info=ErrorInfo(); caught=info.Description; EndTry;
after=RunCallback(Describe("Sum",2),3);
''')
        self.assertEqual(self.vm.variables['caught'], 'callback failure')
        self.assertEqual(self.vm.variables['count'], Decimal(2))
        self.assertEqual(self.vm.variables['after'], Decimal(5))
        self.assertEqual(self.vm.variables['info'].get_member('ModuleName'), 'Handlers.bsl')
        self.assertIsNone(self.vm.locals)
        self.assertEqual(self.vm.execution_context, 'client')

    def test_nested_error_uses_existing_try_except_stack(self):
        self.vm.execute('''
Function Wrapper(Result, Extra) Export Return RunCallback(Extra,Result); EndFunction
''')
        self.vm.execute('c=Describe("Wrapper",Describe("Broken")); '
                        'Try RunCallback(c); Except text=ErrorInfo().Description; EndTry;')
        self.assertEqual(self.vm.variables['text'], 'callback failure')
        self.assertEqual(self.vm._handled_errors, [])

    def test_invalid_description_and_call_arity_are_explicit_errors(self):
        for expression in ('RunCallback()', 'RunCallback(,)', 'RunCallback(1)',
                           'RunCallback(Undefined)', 'RunCallback(New Structure)',
                           'RunCallback(Describe("Echo"),1,2)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_wrong_module_and_name_types_and_unimported_strings(self):
        for expression in ('New CallbackDescription(1,ThisObject)',
                           'New CallbackDescription("Echo",1)',
                           'New CallbackDescription("Echo",New Structure)',
                           'New CallbackDescription("Echo","not.imported")',
                           'New CallbackDescription(,,,,,1)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_complex_error_handler_is_rejected_not_silently_ignored(self):
        for tail in ('"Broken"', '"Broken",ThisObject', 'Undefined,ThisObject'):
            with self.assertRaisesRegex(BSLError, 'Обработчик ошибки.*пока не поддерживается'):
                self.vm.execute('New CallbackDescription("Echo",ThisObject,Undefined,'+tail+')')

    def test_initialization_and_failed_initialization_do_not_publish_callbacks(self):
        other=Interpreter()
        try:
            other.execute('Function F(R,E) Export Return R; EndFunction '
                          'd=New CallbackDescription("F",ThisObject); '
                          'Try RunCallback(d,1); Except blocked=True; EndTry;')
            self.assertTrue(other.variables['blocked'])
            self.assertEqual(other.execute('RunCallback(d,2)'), Decimal(2))
        finally:
            other.close()
        other=Interpreter()
        try:
            with self.assertRaises(BSLError):
                other.execute('Function F(R,E) Export Return R; EndFunction '
                              'd=New CallbackDescription("F",ThisObject); Raise "init";')
            with self.assertRaisesRegex(BSLError, 'Метод объекта не обнаружен'):
                other.execute('RunCallback(d,2)')
        finally:
            other.close()

    def test_foreign_scheduler_receiver_and_description_are_rejected(self):
        other=Interpreter()
        try:
            other.execute(SOURCE)
            self.vm.variables['foreign']=other._self_module
            with self.assertRaisesRegex(BSLError, 'другого интерпретатора'):
                self.vm.execute('New CallbackDescription("Sum",foreign,1)')
            self.vm.variables['foreign']=other.execute('Describe("Sum",1)')
            with self.assertRaisesRegex(BSLError, 'другого интерпретатора'):
                self.vm.execute('RunCallback(foreign,2)')
            self.assertEqual(other.variables['count'], Decimal(0))
        finally:
            other.close()

    def test_server_handler_is_not_crossed_and_nocontext_cannot_restore_capability(self):
        self.vm.execute('''
&AtServer
Function Server(Val R,Val E) Export Return 8; EndFunction
&AtClientAtServerNoContext
Function NoContext(Val D) Return RunCallback(D,1); EndFunction
''')
        with self.assertRaisesRegex(BSLError, 'на клиенте'):
            self.vm.execute('RunCallback(Describe("Server"),1)')
        with self.assertRaisesRegex(BSLError, 'без контекста'):
            self.vm.execute('NoContext(Describe("Echo"))')

    def test_server_constructor_and_network_value_transport_remain_closed(self):
        self.vm.execute('''
&AtServer
Function Make() Return New CallbackDescription; EndFunction
&AtServer
Function Receive(Val D) Return 1; EndFunction
''')
        with self.assertRaisesRegex(BSLError, 'только на клиенте'):
            self.vm.execute('Make()')
        with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
            self.vm.execute('Receive(Describe("Echo"))')
        self.vm.execute('c=Describe("Echo");')
        for expression in ('ValueToStringInternal(c)', 'New ValueStorage(c)'):
            with self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_host_object_is_not_reflected_or_called(self):
        class Trap:
            def __getattr__(self,name):
                raise AssertionError('Python reflection must not happen')
        self.vm.variables['trap']=Trap()
        with self.assertRaises(BSLError):
            self.vm.execute('New CallbackDescription("anything",trap)')

    def test_eval_execute_and_bound_function_value_use_same_dispatch(self):
        self.vm.execute('c=Describe("Sum",4); dispatch=RunCallback; '
                        'a=dispatch(c,2); b=Eval("RunCallback(c,3)"); '
                        'Execute("a=RunCallback(c,5);");')
        self.assertEqual(self.vm.variables['a'], Decimal(9))
        self.assertEqual(self.vm.variables['b'], Decimal(7))

    def test_imported_modules_are_stable_distinct_and_string_names_are_explicit(self):
        module='''Var Count; Function Add(R,E) Export Count=Count+1; Return R+E+Count; EndFunction Count=0;'''
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('A','B'):
                (root/(name+'.bsl')).write_text(module,encoding='utf-8')
            self.vm.execute('// #Import A.bsl\n// #Import B.bsl\n'
                            'a=New CallbackDescription("Add",A,10); '
                            'b=New CallbackDescription("Add","b",20); '
                            'a1=RunCallback(a,1); b1=RunCallback(b,1); a2=RunCallback(a,1);',
                            str(root/'Main.bsl'))
        self.assertEqual([self.vm.variables[n] for n in ('a1','b1','a2')],
                         [Decimal(12),Decimal(22),Decimal(13)])
        self.assertIs(self.vm.execute('a.Module'), self.vm.imports['a'])

    def test_imported_descriptor_factory_and_cross_module_chain_use_owner_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'A.bsl').write_text('''
Var Count; Count=0;
Function Step(R,E) Export Count=Count+1; Return RunCallback(E,R+Count); EndFunction
Function Make(E) Export Return New CallbackDescription("Step",ThisObject,E); EndFunction
''',encoding='utf-8')
            self.vm.execute('// #Import A.bsl\n'
                            'c=A.Make(Describe("Sum",10)); x=RunCallback(c,1); y=RunCallback(c,1);',
                            str(root/'Main.bsl'))
        self.assertEqual(self.vm.variables['x'], Decimal(12))
        self.assertEqual(self.vm.variables['y'], Decimal(13))
        self.assertEqual(self.vm.variables['count'], Decimal(2))

    def test_directory_import_names_resolve_without_loading_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'Package').mkdir()
            (root/'Package'/'A.bsl').write_text(SOURCE,encoding='utf-8')
            self.vm.execute('// #Import Package.A.bsl\n'
                            'c=New CallbackDescription("Sum","pAcKaGe.a",4); answer=RunCallback(c,6);',
                            str(root/'Main.bsl'))
            self.assertEqual(self.vm.variables['answer'], Decimal(10))
            with self.assertRaises(BSLError):
                self.vm.execute('New CallbackDescription("Sum","../A.bsl")')

    def test_async_function_handler_returns_promise_and_existing_await_result(self):
        self.vm.execute('''
Async Function Work(R,E) Export t=Await 0; Return R+E; EndFunction
Async Function Main(D) Return Await RunCallback(D,7); EndFunction
''')
        self.vm.execute('c=Describe("Work",5); p=RunCallback(c,3); answer=Main(c);')
        self.assertEqual(self.vm.variables['p'].result, Decimal(8))
        self.assertEqual(self.vm.variables['answer'].result, Decimal(12))
        self.assertEqual(self.vm.execute('TypeOf(p)'), BSLType.PROMISE)

    def test_async_procedure_returns_undefined_and_completes_on_existing_queue(self):
        self.vm.execute('''
Async Procedure Work(R,E) Export t=Await 0; Count=Count+1; Trace=R+E; EndProcedure
''')
        self.vm.execute('c=Describe("Work","y"); returned=RunCallback(c,"x"); before=Count;')
        self.assertIsNone(self.vm.variables['returned'])
        self.assertEqual(self.vm.variables['before'], Decimal(0))
        self.assertEqual(self.vm.variables['count'], Decimal(1))
        self.assertEqual(self.vm.variables['trace'], 'xy')

    def test_pending_callback_does_not_pump_or_lose_its_arguments(self):
        signal=self.vm._scheduler.new_pending()
        self.vm.register_function('Signal',lambda:signal)
        self.vm.execute('''
Async Function Work(R,E) Export t=Await Signal(); Return R+E+t; EndFunction
''')
        self.vm.execute('c=Describe("Work",5); p=RunCallback(c,2); q=RunCallback(c,3);')
        self.assertEqual(self.vm.variables['p'].state,'pending')
        self.vm._scheduler.resolve(signal,Decimal(10))
        self.vm.run_until_idle()
        self.assertEqual(self.vm.variables['p'].result,Decimal(17))
        self.assertEqual(self.vm.variables['q'].result,Decimal(18))
        self.assertIsNone(self.vm.locals)

    def test_callback_after_await_and_awaited_actual_use_task_local_frame(self):
        self.vm.execute('''
Async Function Value() t=Await 0; Return 4; EndFunction
Async Function Main(Val Extra)
    t=Await 0; Return RunCallback(Describe("Sum",Extra),Await Value());
EndFunction
p=Main(3); q=Main(8);
''')
        self.assertEqual(self.vm.variables['p'].result,Decimal(7))
        self.assertEqual(self.vm.variables['q'].result,Decimal(12))
        self.assertEqual(self.vm.variables['count'],Decimal(2))

    def test_async_rejection_is_caught_by_await_and_repeated_await_keeps_error(self):
        self.vm.execute('''
Async Function Work(R,E) Export t=Await 0; Raise "async callback"; EndFunction
Async Function Main(D)
    P=RunCallback(D,1); Text="";
    For I=1 To 2 Do
        Try t=Await P; Except Text=Text+ErrorInfo().Description; EndTry;
    EndDo;
    Return Text;
EndFunction
''')
        self.vm.execute('answer=Main(Describe("Work"));')
        self.assertEqual(self.vm.variables['answer'].result,'async callbackasync callback')
        self.assertIsNone(self.vm.locals)

    def test_async_sibling_error_handlers_do_not_share_diagnostics(self):
        self.vm.execute('''
Async Function Work(R,E) Export t=Await 0; Return ErrorInfo().Description; EndFunction
Async Function Main(Label,D)
    Try Raise Label; Except t=Await 0; Return Await RunCallback(D,1); EndTry;
EndFunction
''')
        self.vm.execute('d=Describe("Work"); p=Main("first",d); q=Main("second",d);')
        self.assertEqual(self.vm.variables['p'].result,'')
        self.assertEqual(self.vm.variables['q'].result,'')

    def test_async_procedure_failure_keeps_existing_host_boundary_policy(self):
        self.vm.execute('''
Async Procedure Work(R,E) Export t=Await 0; Raise "procedure callback"; EndProcedure
''')
        with self.assertRaisesRegex(BSLError,'procedure callback'):
            self.vm.execute('RunCallback(Describe("Work"),1);')
        self.assertEqual(self.vm._scheduler.procedure_errors,[])
        self.assertIsNone(self.vm.locals)

    def test_callback_type_and_nested_values_have_explicit_serialization_boundary(self):
        self.vm.execute('c=Describe("Echo"); a=New Array; a.Add(c); '
                        'types=New Array; types.Add(Type("CallbackDescription"));')
        for value in ('c', 'a', 'Type("CallbackDescription")', 'types'):
            with self.subTest(value=value), self.assertRaisesRegex(BSLError, 'ОписаниеОповещения.*не поддерживается'):
                self.vm.execute('ValueToStringInternal('+value+')')
        with self.assertRaises(BSLError):
            self.vm.execute('ValueToStringInternal(New TypeDescription("CallbackDescription"))')
