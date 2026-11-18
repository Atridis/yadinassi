"""Research-only architecture tests, never a default compiler switch."""
from direct_ast_text_oracle import compile_module as text_compile
import subprocess
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi import experimental_direct_ast as direct
from yadinassi.error_info import BSLErrorInfo
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse


class DirectASTResearchTests(unittest.TestCase):
    def outcome(self,source,enabled,setup=None,prepared=False):
        vm=Interpreter()
        if setup:setup(vm)
        with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
            try:
                if prepared:result=vm.execute_prepared(vm.prepare(source,'probe.bsl'))
                else:result=vm.execute(source,'probe.bsl')
                error=None
            except BaseException as caught:
                result=None;error=(type(caught).__name__,str(caught),getattr(caught,'line',None),getattr(caught,'column',None))
        def value(item):
            if type(item) is BSLErrorInfo:return ('ErrorInfo',item.description,item.module_name,item.line_number,item.initial_string)
            return (type(item).__name__,item)
        return error,value(result),{k:value(v) for k,v in vm.variables.items()}
    def compare(self,source,setup=None,prepared=False):
        expected=self.outcome(source,False,setup,prepared)
        actual=self.outcome(source,True,setup,prepared)
        self.assertEqual(expected,actual,source)

    def test_host_collection_write_binding_and_argument_close(self):
        from yadinassi.values import BSLArray
        for method in ('set','insert'):
            for mode in ('rebind','close','normal'):
                outcomes=[]
                for compiler in (text_compile,direct.compile_module,direct.compile_module_whole_source):
                    vm=Interpreter();array=BSLArray(Decimal(1));vm.variables['a']=array
                    original=getattr(BSLArray,method);seen=[]
                    def index():
                        seen.append('index')
                        if mode=='rebind':setattr(BSLArray,method,lambda *args:seen.append('new'))
                        if mode=='close':vm.close()
                        return Decimal(0)
                    def value():seen.append('value');return Decimal(7)
                    vm.register_function('Index',index);vm.register_function('Value',value)
                    try:
                        with patch.object(python_direct,'_compile',compiler):
                            try:vm.execute('A.'+method+'(Index(),Value());');error=None
                            except BaseException as exc:error=(type(exc).__name__,str(exc),getattr(exc,'line',None),getattr(exc,'column',None))
                        outcomes.append((error,list(seen),list(array.items)))
                    finally:setattr(BSLArray,method,original);vm.close()
                self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[0],outcomes[2])

    def test_collection_set_insert(self):
        for source in (
            'A=New Array(2);A.Set(1,7);R=A.Get(1);A=0;',
            'A=New Array;A.Insert(2,7);R=A.Count();S=A.Get(2);A=0;',
            'A=New Array(2);A.Set(8,Touch());',
            'A=New Array;A.Insert(-1,Touch());',
            'D=New Map;D.Insert("A",7);R=D.Get("A");D=0;',
            'D=New Map;D.Set("A",Touch());',
            'D=New Structure;D.Insert("A",7);R=D.A;D=0;',
            'D=New Structure;D.Insert("invalid name",Touch());',
            'Function F(Val N) A=New Array(N);A.Set(0,7);A.Insert(1,8);Return A.Get(0)+A.Get(1);EndFunction;R=F(1);',
        ):
            def setup(vm):
                def touch():vm.variables['seen']=Decimal(1);return Decimal(5)
                vm.register_function('Touch',touch)
            with self.subTest(source=source):self.compare(source,setup)

    def test_native_collection_constructors(self):
        for source in (
            'A=New Array;A.Add(2);A.Add(3);R=A.Get(1);A=0;',
            'A=New Array(2,3);A[1][2]=7;R=A[1][2];A=0;',
            'A=New Array(0);R=A.Count();A=0;',
            'A=New Array(-1);',
            'A=New Array(1.5);',
            'A=New Array("bad");',
            'D=New Map;D[1]=7;R=D[1];D=0;',
            'D=New Structure("A,B",2,3);R=D.A+D.B;D=0;',
            'D=New Structure(("A,A"),2,3);R=D.A;D=0;',
            'K="A,B";D=New Structure(K,2);R=D.A;S=D.B;D=0;',
            'D=New Structure("invalid name",Touch());',
            'D=New Structure(7,Touch());',
            'Function F(Val N) A=New Array(N);A[0]=2;D=New Structure("A",A);Return D.A[0];EndFunction;R=F(1);',
        ):
            def setup(vm):
                def touch():vm.variables['seen']=Decimal(1);return Decimal(5)
                vm.register_function('Touch',touch)
            with self.subTest(source=source):self.compare(source,setup)

    def test_scalars_control_flow_and_constant_folding(self):
        for source in (
            'X=0;For I=0 To 10 Do X=X+I;EndDo;R=X;',
            'X=0;While X<3 Do X=X+1;EndDo;',
            'If 1 Then X="a"+1;Else X="b";EndIf;',
            'X=0;For I=0 To 9 Do If I=2 Then Continue;EndIf;If I=5 Then Break;EndIf;X=X+I;EndDo;',
            'Var X;X=1;R=(X+2)*3-4;R;',
            'R="a"+True;S="b"+5;X=-(2)+3/2;',
            'X=True AND False OR True;Y=NOT 0;',
            'X=?(True,2,1/0);',
        ):
            with self.subTest(source=source):self.compare(source)

    def test_errors_exact_positions_and_partial_effects(self):
        for source in (
            'X=1;\nY=1/0;', 'X=1;\nY=Missing;',
            'X="a";Y=X-1;', 'X=1;\nIf "bad" Then Y=2;EndIf;',
            'X=1;While "bad" Do X=2;EndDo;',
            'X=1;Y=NOT "bad";', 'X=1;Y=True AND "bad";',
            'I=7;For I=0 To Missing Do EndDo;', 'X=1;Raise "failure";',
            'Тест=1;\nРезультат=Тест/0;',
        ):
            with self.subTest(source=source):self.compare(source)

    def test_caught_nested_reraised_diagnostics_and_prepared(self):
        sources=[
            'Try X=1/0;Except R=ErrorDescription();E=ErrorInfo();EndTry;',
            'Try Try X=1/0;Except Raise;EndTry;Except R=ErrorDescription();E=ErrorInfo();EndTry;',
            'Try X=1/0;Except R=ErrorDescription();Try Y=Missing;Except S=ErrorDescription();EndTry;EndTry;',
        ]
        for source in sources:
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):self.compare(source,prepared=prepared)

    def test_owner_close_and_service_policy_not_bypassed(self):
        self.compare('X=1;Stop();Y=2;',lambda vm:vm.register_function('Stop',vm.close))
        def setup(vm):
            vm.register_function('Stop',lambda:setattr(vm,'_configuration_runtime',object()))
        self.compare('X=1;Stop();Y=2;',setup)

    def test_initial_shadow_and_live_values(self):
        self.compare('R=Read();',lambda vm:vm.register_function('Read',lambda:7))
        def setup(vm):
            vm.register_function('Read',lambda:7);vm.variables['read']=Decimal(1)
        self.compare('R=Read();',setup)

    def test_prepared_owns_source_snapshot_but_reads_live_bindings(self):
        import gc,weakref
        from dataclasses import replace
        nodes=parse('X=1;\nY=1/0;','owned.bsl');ref=weakref.ref(nodes[0])
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter();plan=vm.prepare_program(nodes)
        nodes[0].value.value=Decimal(99)
        nodes[0].token=replace(nodes[0].token,source='changed.bsl',line=70)
        nodes.clear();gc.collect();self.assertIsNone(ref())
        with self.assertRaises(Exception) as caught:vm.execute_prepared(plan)
        self.assertEqual(vm.variables['x'],1)
        self.assertEqual((caught.exception.source,caught.exception.line),('owned.bsl',2))
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter();vm.variables['x']=Decimal(1);vm.register_function('Read',lambda:2)
            plan=vm.prepare('X=X+Read();X;')
        self.assertEqual(vm.execute_prepared(plan),3)
        vm.register_function('Read',lambda:3)
        self.assertEqual(vm.execute_prepared(plan),6)

    def test_procedure_shadow_and_malformed_loop_control(self):
        def setup(vm):vm.register_function('P',lambda:None,returns_value=False)
        self.compare('P();',setup);self.compare('X=P();',setup)
        from yadinassi.syntax import ast as bsl
        for kind in (bsl.Break,bsl.Continue):
            nodes=parse('X=1;');nodes.append(kind(nodes[0].token));vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module):
                with self.assertRaisesRegex(PythonDirectUnsupported,'outside a loop'):vm.execute_program(nodes)
            self.assertEqual(vm.variables,{})

    def test_constant_fold_visitation_preserves_source_order(self):
        from yadinassi import experimental_naked_scalar_semantics as scalar
        original=scalar.concatenate
        for source in ('If True Then X="a"+1;Else X="b"+2;EndIf;',
                       'While ("a"+1) Do X="b"+2;EndDo;',
                       'Try X="a"+1;Except X="b"+2;EndTry;'):
            recorded=[]
            for enabled in (False,True):
                seen=[]
                def observe(left,right):seen.append(left);return original(left,right)
                with patch.object(scalar,'concatenate',observe),patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                    Interpreter().prepare(source)
                recorded.append(seen)
            self.assertEqual(recorded,[['a','b'],['a','b']])

    def test_native_exception_trace_location_matches(self):
        positions=[]
        for enabled in (False,True):
            events=[]
            def trace(frame,event,arg):
                if event=='exception' and frame.f_code.co_filename=='trace.bsl':
                    pos=tuple(frame.f_code.co_positions())[frame.f_lasti//2] if hasattr(frame.f_code,'co_positions') else None
                    events.append((frame.f_lineno,pos,arg[0].__name__))
                return trace
            with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                old=sys.gettrace();sys.settrace(trace)
                try:
                    with self.assertRaises(Exception):Interpreter().execute('X=1;\nY=1/0;','trace.bsl')
                finally:sys.settrace(old)
            positions.append(events)
        self.assertEqual(*positions)

    def test_operator_temporaries_preserve_finalizer_order_and_owner_close(self):
        for source in ('X=Make()+1;Y=2;','A=1;X=A+Make();Y=2;'):
            for close in (False,True):
                outcomes=[]
                for enabled in (False,True):
                    vm=Interpreter();seen=[]
                    class Value:
                        def __add__(self,other):return 7
                        def __radd__(self,other):return 7
                        def __del__(self):
                            seen.append(tuple(sorted(vm.variables)))
                            if close:vm.close()
                    vm.register_function('Make',Value)
                    with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                        try:vm.execute(source);error=None
                        except BaseException as caught:error=(type(caught).__name__,str(caught))
                    outcomes.append((error,dict(vm.variables),list(seen)))
                self.assertEqual(*outcomes,(source,close))

    def test_argument_calls_references_and_evaluation_order(self):
        from yadinassi.runtime import HostFunction
        def setup(vm):
            vm.register_function('Sum',lambda a,b:a+b)
            vm.register_function('One',lambda:Decimal(1))
            vm.functions['setref']=HostFunction('SetRef',lambda ref,value:ref.set(value),reference_parameters=(0,))
        for source in ('X=Sum(One(),2);','X=1;SetRef(X,3);Y=X;',
                       'X=1;SetRef((X),Sum(X,2));Y=X;',
                       'X=Sum(Missing,One());','X=1;SetRef(1,3);Y=2;'):
            with self.subTest(source=source):self.compare(source,setup)

    def test_index_reads_native_and_nested(self):
        def setup(vm):
            vm.variables['a']=[Decimal(3),[Decimal(7)]]
            vm.variables['d']={'k':Decimal(9)}
        for source in ('X=A[0];','X=A[1][0];','X=D["k"];',
                       'X=A[-1];','X=A[1.5];','X=D["missing"];'):
            with self.subTest(source=source):self.compare(source,setup)

    def test_index_operand_finalizer_and_callback_order(self):
        for close in (False,True):
            outcomes=[]
            for enabled in (False,True):
                vm=Interpreter();seen=[];vm.variables['d']={'k':Decimal(9)}
                class Key(str):
                    def __del__(self):
                        seen.append(tuple(sorted(vm.variables)))
                        if close:vm.close()
                vm.register_function('Make',lambda:Key('k'))
                with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                    try:vm.execute('X=D[Make()];Y=2;');error=None
                    except BaseException as caught:error=(type(caught).__name__,str(caught))
                outcomes.append((error,dict(vm.variables),seen))
            self.assertEqual(*outcomes)

    def test_index_writes_and_canonical_constructors(self):
        def setup(vm):
            vm.variables['a']=[Decimal(3),[Decimal(7)]]
            vm.variables['d']={'k':Decimal(9)}
        for source in ('A[0]=8;X=A[0];','A[1][0]=8;',
                       'D["new"]=4;X=D["new"];','D.new=4;X=D.new;' , 'X=D.missing;','A[-1]=4;',
                       'A[99]=Missing;','A[Missing]=1;',
                       'T=New ValueTable;X=String(TypeOf(T));T=0;',
                       'T=New ValueList;X=String(TypeOf(T));T=0;',
                       'X=1;T=New ValueTable(1);'):
            with self.subTest(source=source):self.compare(source,setup)

    def test_direct_methods_and_collection_build_scan(self):
        def setup(vm):vm.variables['a']=[];vm.variables['d']={}
        sources=(
            'A.Add(3);A.Добавить();X=A.Count();R=A.Get(0);A.Clear();Y=A.Количество();',
            'A.Get(99);','D.Get(Missing);',
            'D.Add(Missing);',
            'T=New ValueTable;T.Columns.Add("N");For I=0 To 3 Do Row=T.Add();Row.N=I;EndDo;R=T.Get(3).N;N=T.Count();T.Clear();M=T.Count();Row=0;T=0;',
            'T=New ValueList;For I=0 To 3 Do Item=T.Add(I);EndDo;R=T.Get(3).Value;N=T.Count();T.Clear();M=T.Count();Item=0;T=0;',
        )
        for source in sources:
            with self.subTest(source=source):self.compare(source,setup)

    def test_foreach_native_host_and_loop_control(self):
        def setup(vm):
            vm.variables['a']=[Decimal(1),Decimal(2),Decimal(3)]
            vm.variables['d']={'x':Decimal(2),'y':Decimal(4)}
        sources=(
            'R=0;For Each V In A Do If V=2 Then Continue;EndIf;R=R+V;EndDo;',
            'R=0;For Each E In D Do R=R+E.Value;EndDo;E=0;',
            'For Each V In A Do Break;EndDo;X=V;',
            'For Each E In D Do D["z"]=5;EndDo;E=0;',
            'T=New ValueList;T.Add(1);T.Add(2);R=0;For Each E In T Do R=R+E.Value;EndDo;E=0;T=0;',
            'X=1;For Each E In Missing Do X=2;EndDo;',
        )
        for source in sources:
            with self.subTest(source=source):self.compare(source,setup)

    def test_property_output_names_and_partial_errors(self):
        from yadinassi.experimental_naked_structure import new_structure
        from yadinassi.structures import BSLStructure
        for host in (False,True):
            shared=BSLStructure('N',Decimal(7)) if host else new_structure('N',Decimal(7))
            def setup(vm):vm.variables['s']=shared
            for source in ('X=0;R=S.Property("N",X);Y=X;',
                           'X=0;R=S.Свойство("missing",(X));Y=X;',
                           'R=S.Property("N");','R=S.Property(1);',
                           'R=S.Property("N",Missing);',
                           'X=0;R=S.Property(Missing,X);'):
                with self.subTest(host=host,source=source):self.compare(source,setup)

    def test_property_index_and_member_outputs(self):
        from yadinassi.experimental_naked_structure import new_structure
        from yadinassi.structures import BSLStructure
        for host in (False,True):
            shared=BSLStructure('N',Decimal(7)) if host else new_structure('N',Decimal(7))
            def setup(vm):
                vm.variables['s']=shared;vm.variables['a']=[Decimal(0)];vm.variables['d']={'x':Decimal(0)}
            for source in ('R=S.Property("N",A[0]);X=A[0];',
                           'R=S.Property("N",D.x);X=D.x;',
                           'R=S.Property("N",A[99]);',
                           'R=S.Property("N",D.missing);',
                           'R=S.Property("N",A[Missing]);'):
                with self.subTest(host=host,source=source):self.compare(source,setup)

    def test_dynamic_index_member_references(self):
        from yadinassi.values import HostFunction
        for reference in (False,True):
            def setup(vm):
                vm.variables['a']=[Decimal(1)];vm.variables['d']={'x':Decimal(2)}
                def call(value):
                    if reference:value.set(Decimal(8));return value.get()
                    return value
                vm.functions['f']=HostFunction('F',call,reference_parameters=(0,) if reference else ())
            for source in ('R=F(A[0]);','R=F(D.x);','R=F(A[99]);','R=F(D.missing);'):
                with self.subTest(reference=reference,source=source):self.compare(source,setup)

    def test_zero_argument_source_routines_and_persistence(self):
        for source in (
            'Function F() Return 7;EndFunction;R=F();',
            'Function F() Return 7;EndFunction;R=F;',
            'Function F() Return 7;EndFunction;F=9;R=F;',
            'R=F();Function F() X=2;Y=X+3;Return Y;EndFunction;',
            'Var X;Procedure P() X=4;EndProcedure;P();R=X;',
            'Function F() Var X;X=8;Return X;EndFunction;R=F();',
            'Procedure P() Return;EndProcedure;R=P();',
            'Function F() Return G();EndFunction;Function G() Return 9;EndFunction;R=F();',
            'Function F() Return 1/0;EndFunction;R=F();',
        ):
            with self.subTest(source=source):self.compare(source)
        outcomes=[]
        for enabled in (False,True):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                vm.execute('Var X;Function F() Return X+1;EndFunction;X=2;')
                vm.execute('X=8;R=F();')
                vm.execute_prepared(vm.prepare('X=12;S=F();'))
            outcomes.append(dict(vm.variables))
        self.assertEqual(*outcomes)

    def test_source_routine_branches_and_definite_initialization(self):
        sources=(
            'Function F(Val A) If A=0 Then X=3;ElsIf A=1 Then X=5;Else X=7;EndIf;Return X;EndFunction;R=F(0)+F(1)+F(2);',
            'Function F(Val A) X=1;If A Then X=2;EndIf;Return X;EndFunction;R=F(True)+F(False);',
            'Function F(Val A,Val B) If A Then If B Then X=1;Else X=2;EndIf;Else X=3;EndIf;Return X;EndFunction;R=F(True,False)+F(False,True);',
            'Function F(Val N) If N=0 Then Return 1;Else Return N*F(N-1);EndIf;EndFunction;R=F(5);',
            'Procedure P(A,Val B) If B Then A=A+1;Else A=A-1;EndIf;EndProcedure;X=4;P(X,True);P(X,False);',
            'Function F(Val A) If A Then Var X;Else X=4;EndIf;Return X;EndFunction;R=F(True);S=F(False);',
            'Var X;Function F(Val A) If A Then X=4;Else X=7;EndIf;Return X;EndFunction;R=F(True);S=F(False);',
            'Function F(Val A) If A Then Return 1/0;Else Return 7;EndIf;EndFunction;R=F(True);',
            'Function F(Val A) If A Then Return 1;ElsIf 1/0 Then Return 2;EndIf;EndFunction;R=F(False);',
        )
        for source in sources:
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,prepared=prepared)
                    if '1/0' not in source:self.assertIsNone(self.outcome(source,True,prepared=prepared)[0])
        with patch.object(python_direct,'_compile',direct.compile_module):
            for source in (
                'Function F(Val A) If A Then X=1;EndIf;Return X;EndFunction;R=F(False);',
                'Function F(Val A) If A Then X=1;Else Return X;EndIf;EndFunction;R=F(False);',
                'Function F(Val A) If A Then X=1;ElsIf X Then Return 2;EndIf;EndFunction;R=F(False);',
            ):
                vm=Interpreter()
                with self.assertRaisesRegex(PythonDirectUnsupported,'definite initialization'):vm.execute(source)
                self.assertEqual(vm.variables,{})

    def test_conditional_local_declaration_shadow_rejected_before_effects(self):
        for flag in ('False','True'):
            source='Var X;Function F(Val C) If C Then Var X;X=2;Else X=3;EndIf;Return X;EndFunction;X=9;R=F('+flag+');'
            for enabled in (False,True):
                vm=Interpreter()
                with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                    with self.assertRaisesRegex(PythonDirectUnsupported,'conditional local Var shadowing module storage'):vm.execute(source)
                self.assertEqual(vm.variables,{})

    def test_source_routine_for_while_and_zero_trip_facts(self):
        sources=(
            'Function F(Val N) R=0;For I=0 To N Do If I=2 Then Continue;EndIf;If I=5 Then Break;EndIf;R=R+I;EndDo;Return R;EndFunction;R=F(9);',
            'Function F(Val N) R=0;I=0;While I<N Do I=I+1;If I=2 Then Continue;EndIf;R=R+I;EndDo;Return R;EndFunction;R=F(4);',
            'Function F() For I=3 To 0 Do X=1;EndDo;Return I;EndFunction;R=F();',
            'Function F() X=4;For I=3 To 0 Do X=1;EndDo;While False Do X=2;EndDo;Return X;EndFunction;R=F();',
            'Function F() R=0;For I=0 To 3 Do For J=0 To 2 Do If J=1 Then Break;EndIf;R=R+1;EndDo;EndDo;Return R;EndFunction;R=F();',
            'Procedure P(A) For I=0 To 2 Do A=A+1;EndDo;EndProcedure;X=7;P(X);',
            'Function F(Val N) For I=0 To N Do X=I+1;If X=2 Then Return X;EndIf;EndDo;Return 0;EndFunction;R=F(4);',
            'Function F() For I=0 To 2 Do X=1/(1-I);EndDo;Return 0;EndFunction;R=F();',
        )
        for source in sources:
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,prepared=prepared)
                    if '1/(1-I)' not in source:self.assertIsNone(self.outcome(source,True,prepared=prepared)[0])
        for source in (
            'Function F() For I=3 To 0 Do X=1;EndDo;Return X;EndFunction;R=F();',
            'Function F() While False Do X=1;EndDo;Return X;EndFunction;R=F();',
            'Function F() For I=0 To 2 Do Var X;X=1;EndDo;Return 0;EndFunction;R=F();',
        ):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module):
                with self.assertRaises(PythonDirectUnsupported):vm.execute(source)
            self.assertEqual(vm.variables,{})

    def test_source_routine_foreach_native_and_host(self):
        def setup(vm):vm.variables.update(a=[Decimal(1),Decimal(2),Decimal(3)],d={'x':Decimal(2),'y':Decimal(4)},empty=[])
        sources=(
            'Function F(Val A) R=0;For Each E In A Do If E=2 Then Continue;EndIf;R=R+E;EndDo;Return R;EndFunction;R=F(A);',
            'Function F(Val A) E=9;For Each E In A Do Break;EndDo;Return E;EndFunction;R=F(Empty);S=F(A);',
            'Function F(Val A) R=0;For Each E In A Do R=R+E.Value;EndDo;Return R;EndFunction;R=F(D);',
            'Function F(Val A) R=0;For Each E In A Do For Each E In A Do R=R+E;Break;EndDo;EndDo;Return R;EndFunction;R=F(A);',
            'Procedure P(E,Val A) For Each E In A Do If E=2 Then Return;EndIf;EndDo;EndProcedure;X=7;P(X,A);',
            'T=New ValueList;T.Add(2);T.Add(4);Function F(Val A) R=0;For Each E In A Do R=R+E.Value;EndDo;Return R;EndFunction;R=F(T);T=0;',
            'Function F(Val A) R=0;For Each E In A Do R=R+1/(2-E);EndDo;Return R;EndFunction;R=F(A);',
        )
        for source in sources:
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,setup,prepared)
                    if '1/(2-E)' not in source:self.assertIsNone(self.outcome(source,True,setup,prepared)[0])
        for source in (
            'Function F(Val A) For Each E In A Do EndDo;Return E;EndFunction;R=F(Empty);',
            'Function F(Val A) For Each E In A Do X=1;EndDo;Return X;EndFunction;R=F(Empty);',
        ):
            vm=Interpreter();setup(vm);before=dict(vm.variables)
            with patch.object(python_direct,'_compile',direct.compile_module):
                with self.assertRaisesRegex(PythonDirectUnsupported,'definite initialization'):vm.execute(source)
            self.assertEqual(vm.variables,before)

    def test_source_routine_try_raise_and_partial_state(self):
        sources=(
            'Function F(Val A) Try X=1/A;Except X=7;EndTry;Return X;EndFunction;R=F(0);S=F(2);',
            'Function F(Val A) X=4;Try X=1/A;Except EndTry;Return X;EndFunction;R=F(0);',
            'Function F() Try Return 1/0;Except Return 9;EndTry;EndFunction;R=F();',
            'Function F() Try Raise "inner";Except Raise;EndTry;EndFunction;Try R=F();Except E=ErrorInfo();EndTry;',
            'Function F() Try Try X=1/0;Except Raise "replacement";EndTry;Except Return 6;EndTry;EndFunction;R=F();',
            'Procedure P(A) Try A=8;X=1/0;Except A=A+1;EndTry;EndProcedure;X=2;P(X);',
            'Function F() R=0;For I=0 To 3 Do Try If I=1 Then Continue;EndIf;If I=2 Then Break;EndIf;R=R+1;Except R=99;EndTry;EndDo;Return R;EndFunction;R=F();',
            'Function G() Raise "child";EndFunction;Function F() Try Return G();Except Raise;EndTry;EndFunction;Try R=F();Except E=ErrorInfo();EndTry;',
        )
        for source in sources:
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,prepared=prepared)
                    self.assertIsNone(self.outcome(source,True,prepared=prepared)[0])
        for source in (
            'Function F() Try X=1/0;Except EndTry;Return X;EndFunction;R=F();',
            'Function F() Try X=1;Y=1/0;Except Return X;EndTry;EndFunction;R=F();',
            'Var X;Function F() Try Var X;Except EndTry;Return 1;EndFunction;R=F();',
        ):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module):
                with self.assertRaises(PythonDirectUnsupported):vm.execute(source)
            self.assertEqual(vm.variables,{})

    def test_persistent_routine_try_uses_current_activation_and_source(self):
        outcomes=[]
        for enabled in (False,True):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                vm.execute('Function F(Val N) Try Return 1/N;Except Raise "persisted";EndTry;EndFunction;','definition.bsl')
                vm.execute('Try R=F(0);Except E=ErrorInfo();EndTry;','caller.bsl')
                info=vm.variables['e']
                outcomes.append((info.description,info.module_name,info.line_number,info.initial_string))
                vm.execute_prepared(vm.prepare('R=F(2);','prepared-caller.bsl'))
                self.assertEqual(vm.variables['r'],Decimal('0.5'))
            vm.close()
        self.assertEqual(*outcomes)

    def test_source_routine_collection_members_methods_and_writes(self):
        from yadinassi.experimental_naked_structure import new_structure
        from yadinassi.value_lists import BSLValueList
        def setup(vm):
            host=BSLValueList();host.add(Decimal(3))
            vm.variables.update(a=[Decimal(1)],s=new_structure('N',Decimal(7)),host=host)
        sources=(
            'Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;R=0;For I=0 To N Do R=R+T.Get(I).Value;EndDo;Return R;EndFunction;R=F(3);Host=0;',
            'Function F(Val N) T=New ValueTable;T.Columns.Add("N");For I=0 To N Do Row=T.Add();Row.N=I;EndDo;R=0;For I=0 To N Do R=R+T.Get(I).N;EndDo;Return R;EndFunction;R=F(3);Host=0;',
            'Function F(Val A) A[0]=A[0]+1;A.Add();Return A.Count();EndFunction;R=F(A);Host=0;',
            'Procedure P(Val S,R) S.Property("N",R);EndProcedure;X=0;P(S,X);Host=0;',
            'Function F(Val A) A.Get(0).Value=8;Return A.Get(0).Value;EndFunction;R=F(Host);Host=0;',
            'Function F(Val A) Try A[99]=8;Except Return 7;EndTry;Return 0;EndFunction;R=F(A);Host=0;',
            'Function F(Val S) S.N=9;Return S.N;EndFunction;R=F(S);Host=0;',
        )
        for source in sources:
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,setup,prepared)
                    self.assertIsNone(self.outcome(source,True,setup,prepared)[0])
        source='Function F(Val S) R=0;S.Property("N",R);Return R;EndFunction;R=F(S);Host=0;'
        self.compare(source,setup)
        self.assertEqual(self.outcome(source,True,setup)[2]['r'][1],Decimal(7))

    def test_source_routine_zero_argument_services_and_error_info(self):
        def setup(vm):vm.register_function('Read',lambda:Decimal(7))
        for source in (
            'Function F() Return Read();EndFunction;R=F();',
            'Function F(Val Read) Return Read();EndFunction;R=F(3);',
            'Function F() If False Then Read=3;EndIf;Return Read();EndFunction;R=F();',
            'Var Read;Function F() Return Read();EndFunction;Read=3;R=F();',
            'Function F() Try Raise "inside";Except Return ErrorInfo();EndTry;EndFunction;E=F();',
            'Function F() Return ErrorDescription();EndFunction;Try Raise "outside";Except R=F();EndTry;',
            'Function F() Try Raise "inside";Except Return ErrorDescription();EndTry;EndFunction;R=F();',
        ):
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,setup,prepared)
                    if not source.startswith(('Function F(Val Read)','Var Read')):self.assertIsNone(self.outcome(source,True,setup,prepared)[0])
        def closing(vm):vm.register_function('Stop',lambda:vm.close())
        self.compare('Var X;Procedure F() X=1;Stop();X=2;EndProcedure;F();Y=3;',closing)
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter();setup(vm)
            with self.assertRaises(PythonDirectUnsupported):vm.execute('Function F() Return Read(,1);EndFunction;R=F();')
            self.assertEqual(vm.variables,{})

    def test_routine_service_conditional_binding_and_locals_lifetime(self):
        for flag in ('True','False'):
            source='Function F(Val C) If C Then Q=7;EndIf;Return Q();EndFunction;R=F('+flag+');'
            for registered in (False,True):
                def setup(vm):
                    if registered:vm.register_function('Q',lambda:Decimal(9))
                with self.subTest(flag=flag,registered=registered):self.compare(source,setup)
        def setup(vm):
            vm.variables['events']=[]
            class Item:
                def __del__(self):vm.variables['events'].append(vm.variables.get('y'))
            vm.register_function('Make',Item);vm.register_function('Read',lambda:Decimal(1))
        source='Var Y;Function F() X=Make();Read();X=0;Y=9;Return 1;EndFunction;R=F();'
        self.compare(source,setup)
        self.assertEqual(self.outcome(source,True,setup)[2]['events'][1],[Decimal(9)])

    def test_routine_dynamic_host_arguments_and_lexical_references(self):
        from yadinassi.values import HostFunction
        def setup(vm):
            vm.functions['echo']=HostFunction('Echo',lambda value:value+1)
            vm.functions['put']=HostFunction('Put',lambda ref:ref.set(Decimal(9)),reference_parameters=(0,),returns_value=False)
            vm.variables['a']=[Decimal(2)]
        for source in (
            'Function F() X=2;Return Echo(X);EndFunction;R=F();',
            'Function F() X=2;Put(X);Return X;EndFunction;R=F();',
            'Function F(Val X) Put(X);Return X;EndFunction;A0=2;R=F(A0);',
            'Function F(X) Put(X);Return X;EndFunction;A0=2;R=F(A0);',
            'Function F(Val A) Put(A[0]);Return A[0];EndFunction;R=F(A);',
            'Function F() Return Echo(Echo(2));EndFunction;R=F();',
            'Var X;Function F() Put(X);Return X;EndFunction;X=2;R=F();',
        ):
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,setup,prepared)
                    self.assertIsNone(self.outcome(source,True,setup,prepared)[0])
        def changing(vm):
            def mode():vm.functions['mutate'].reference_parameters=(1,);return Decimal(0)
            vm.register_function('Mode',mode)
            vm.functions['mutate']=HostFunction('Mutate',lambda flag,value:value.set(Decimal(8)),returns_value=False)
        self.compare('Function F() X=2;Mutate(Mode(),X);Return X;EndFunction;R=F();',changing)
        def escaping(vm):
            saved={}
            vm.functions['save']=HostFunction('Save',lambda value:saved.update(ref=value),reference_parameters=(0,),returns_value=False)
            def read():saved['ref'].set(Decimal(9));return saved['ref'].get()
            vm.register_function('ReadSaved',read)
        self.compare('Function F() X=2;Save(X);Return X;EndFunction;R=F();S=ReadSaved();',escaping)
        vm=Interpreter();setup(vm)
        with patch.object(python_direct,'_compile',direct.compile_module):
            with self.assertRaisesRegex(PythonDirectUnsupported,'unbound host argument local'):
                vm.execute('Function F() Put(Missing);Return 0;EndFunction;R=F();')
        self.assertNotIn('r',vm.variables)

    def test_routine_host_reference_getter_error_and_close(self):
        from yadinassi.values import HostFunction,Reference
        source='Procedure F(A)\n Host(A);\nEndProcedure;\nTry F(A);Except E=ErrorInfo();EndTry;Y=2;'
        for mode in ('raise','close','normal'):
            outcomes=[]
            for enabled in (False,True):
                vm=Interpreter();events=[]
                def get():
                    events.append('get')
                    if mode=='raise':raise ValueError('getter failed')
                    if mode=='close':vm.close()
                    return Decimal(2)
                vm.variables['a']=Reference(get,lambda value:events.append(('set',value)))
                vm.functions['host']=HostFunction('Host',lambda ref:events.append(('called',ref.get())),reference_parameters=(0,),returns_value=False)
                with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                    try:vm.execute(source,'getter.bsl');error=None
                    except BaseException as exc:error=(type(exc).__name__,str(exc),getattr(exc,'line',None),getattr(exc,'column',None))
                info=vm.variables.get('e')
                detail=None if info is None else (info.description,info.module_name,info.line_number,info.initial_string)
                outcomes.append((error,list(events),detail,vm.variables.get('y')))
            self.assertEqual(*outcomes,mode)

    def test_source_routine_local_cells_and_val_forwarding(self):
        for source in (
            'Procedure P(X) X=X+1;EndProcedure;Function F() X=2;P(X);Return X;EndFunction;R=F();',
            'Procedure P(X) X=X+1;EndProcedure;Function F(Val X) P(X);Return X;EndFunction;A=2;R=F(A);',
            'Procedure P(X,Y) X=4;Y=Y+1;EndProcedure;Function F() X=2;P(X,X);Return X;EndFunction;R=F();',
            'Procedure P(X) X=4;EndProcedure;Function F(Val X=2,Val Y=0) P(X);Return X;EndFunction;R=F();S=F(,);',
            'Procedure P(X) X=4;EndProcedure;Function F() Var X;P(X);Return X;EndFunction;R=F();',
            'Procedure P(X) X=4;EndProcedure;Function F() P(Missing);Return 0;EndFunction;Before=1;R=F();',
            'Procedure P(X) X=X+1;EndProcedure;Function F() X=2;For I=0 To 2 Do P(X);EndDo;Return X;EndFunction;R=F();',
        ):
            for prepared in (False,True):
                with self.subTest(source=source,prepared=prepared):
                    self.compare(source,prepared=prepared)
                    if 'Missing' not in source:self.assertIsNone(self.outcome(source,True,prepared=prepared)[0])
        from yadinassi.values import HostFunction
        def setup(vm):vm.functions['put']=HostFunction('Put',lambda ref:ref.set(Decimal(9)),reference_parameters=(0,),returns_value=False)
        self.compare('Procedure P(X) X=X+1;EndProcedure;Function F() X=2;Put(X);P(X);Return X;EndFunction;R=F();',setup)

    def test_by_value_source_parameters_and_persistent_calls(self):
        sources=(
            'Function F(Val A,Val B) Return A+B;EndFunction;R=F(2,3);',
            'Var X;X=7;Function F(Val X) X=X+1;Return X;EndFunction;R=F(X);S=X;',
            'Function F(Val A) Var A;Return A;EndFunction;R=F(8);',
            'Function F(Val A) Return G(A)+1;EndFunction;Function G(Val B) Return B*2;EndFunction;R=F(4);',
            'Function F(Val A) Return A;EndFunction;X=1;R=F(Missing,2);',
            'Procedure P(Val A) Return;EndProcedure;R=P(Missing);',
            'Function F(Val A) Return A/0;EndFunction;R=F(3);',
        )
        for source in sources:
            with self.subTest(source=source):self.compare(source)
        results=[]
        for enabled in (False,True):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                vm.execute('Function F(Val X) Return X+1;EndFunction;')
                vm.execute('A=3;R=F(A);')
                vm.execute_prepared(vm.prepare('S=F(8);'))
            results.append(dict(vm.variables))
        self.assertEqual(*results)

    def test_literal_defaults_and_local_omissions(self):
        for source in (
            'Function F(Val A=3,Val B=4) Return A+B;EndFunction;R=F();S=F(8);T=F(,9);',
            'Function F(Val A,Val B=4) Return B;EndFunction;R=F(,);',
            'Function F(Val A="x") Return A;EndFunction;R=F();S=F("z");',
            'Function F(Val A=True) Return A;EndFunction;R=F();',
            'Function F(Val A=Undefined) Return A;EndFunction;R=F();',
            'Function F(Val A,Val B=2) Return B;EndFunction;X=1;R=F();',
        ):
            with self.subTest(source=source):self.compare(source)
        results=[]
        for enabled in (False,True):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                vm.execute('Function F(Val X=5) Return X+1;EndFunction;')
                vm.execute('R=F();S=F(8);')
                vm.execute_prepared(vm.prepare('T=F();'))
            results.append(dict(vm.variables))
        self.assertEqual(*results)

    def test_source_byref_parameters_aliases_defaults_and_persistence(self):
        for source in (
            'Procedure P(A) A=A+1;EndProcedure;X=3;P(X);R=X;',
            'Function F(A,B) A=4;B=B+1;Return A;EndFunction;X=2;R=F(X,X);S=X;',
            'Procedure P(A) Q(A);EndProcedure;Procedure Q(B) B=9;EndProcedure;X=1;P(X);',
            'Function F(A=5) A=A+1;Return A;EndFunction;R=F();S=F(,);',
            'Function F(A) A=4;Return A;EndFunction;R=F(1+2);',
            'Procedure P(A) A=4;EndProcedure;X=1;P(Missing);',
            'Procedure P(A) Var A;A=4;EndProcedure;X=1;P(X);',
        ):
            with self.subTest(source=source):self.compare(source)
        def setup(vm):vm.variables['a']=[Decimal(1)];vm.variables['d']={'x':Decimal(2)}
        for source in ('Procedure P(X) X=8;EndProcedure;P(A[0]);',
                       'Procedure P(X) X=8;EndProcedure;P(D.x);',
                       'Procedure P(X) X=8;EndProcedure;P(A[99]);'):
            self.compare(source,setup)
        results=[]
        for enabled in (False,True):
            vm=Interpreter()
            with patch.object(python_direct,'_compile',direct.compile_module if enabled else text_compile):
                vm.execute('Function F(X) X=X+1;Return X;EndFunction;')
                vm.execute('A=3;R=F(A);')
                vm.execute_prepared(vm.prepare('S=F(A);'))
            results.append(dict(vm.variables))
        self.assertEqual(*results)

    def test_one_real_compile_per_call_and_actual_audit_denial(self):
        self.child(r'''
import ast,sys
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi.experimental_direct_ast import compile_module
python_direct._compile=compile_module
vm=Interpreter();vm.execute('X=1;','audit.bsl');events=[]
def observe(event,args):
    if event=='compile':events.append(args)
sys.addaudithook(observe)
for _ in range(2):
    events.clear();vm.execute('X=1;','audit.bsl')
    if len(events)!=1 or not isinstance(events[0][0],ast.Module):raise AssertionError('not one actual AST compile')
vm.variables.clear()
def deny(event,args):
    if event=='compile' and isinstance(args[0],ast.Module):raise RuntimeError('executable AST denied')
sys.addaudithook(deny)
try:vm.execute('X=1;','audit.bsl')
except RuntimeError as error:
    if str(error)!='executable AST denied' or vm.variables:raise AssertionError('denial after effects')
else:raise AssertionError('compiler policy bypassed')
''')

    def test_filename_only_audit_policy_is_an_explicit_migration_blocker(self):
        # Pure AST alone lacks the filename gate retained by the default source lane.
        self.child(r"""
import sys
from yadinassi import Interpreter,python_direct
from yadinassi.experimental_direct_ast import compile_module
vm=Interpreter();vm.execute('X=1;','warm.bsl');vm.variables.clear()
def deny_filename(event,args):
    if event=='compile' and args[1]=='blocked.bsl':raise RuntimeError('filename denied')
sys.addaudithook(deny_filename)
try:vm.execute('X=1;','blocked.bsl')
except RuntimeError:
    if vm.variables:raise AssertionError('baseline effects before denial')
else:raise AssertionError('baseline filename gate absent')
python_direct._compile=compile_module
vm.execute('X=1;','blocked.bsl')
if vm.variables.get('x')!=1:raise AssertionError('expected migration incompatibility not demonstrated')
""")

    def test_lowering_counts_linear_for_wide_and_nested_inputs(self):
        counters={}
        with patch.object(python_direct,'_compile',direct.compile_module):
            for shape in ('nested','wide'):
                for size in (8,16,32):
                    source='R='+'-'.join(['1']*size)+';' if shape=='nested' else ';'.join('X%d=%d'%(i,i) for i in range(size))+';'
                    plan=Interpreter().prepare(source)
                    counters[shape,size]=plan._plan._research_lowering_counts
                a=counters[shape,16];b=counters[shape,32]
                self.assertLessEqual(b[1],2*a[1]+2)
                self.assertLessEqual(b[2],2*a[2]+2)
        self.counters=counters

    def test_no_research_caps_and_unsupported_fail_before_effects(self):
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter();vm.execute('R='+'-'.join(['1']*100)+';')
            self.assertEqual(vm.variables['r'],-98)
            vm=Interpreter();vm.execute('\n'*50000+'X=1;')
            self.assertEqual(vm.variables['x'],1)
            self.assertGreater(direct._bounds(parse('X=1;'*3500)),10000)
            vm=Interpreter()
            with self.assertRaises(PythonDirectUnsupported):vm.execute('X=1;A=New UnsupportedResearchConstructor;')
            self.assertEqual(vm.variables,{})

    def child(self,code):
        result=subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
