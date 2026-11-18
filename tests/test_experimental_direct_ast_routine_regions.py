"""Activation-local guarded regions; no production compiler selection."""
from direct_ast_text_oracle import compile_module as text_compile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, python_direct
from yadinassi import experimental_direct_ast as direct
from yadinassi import python_direct_collection_regions as regions
from yadinassi.value_lists import BSLValueList
import test_python_direct_collection_regions as canonical

class RoutineRegionsTests(unittest.TestCase):
    def paired(self, source, install=None):
        outcomes=[];decisions=[]
        for compiler in (text_compile,direct.compile_module,direct.compile_module_whole_source):
            vm=Interpreter()
            cleanup=install(vm) if install else None
            seen=[];real=regions.admitted
            def gate(*args,**kwargs):
                result=real(*args,**kwargs);seen.append(result);return result
            try:
                with patch.object(python_direct,'_compile',compiler),patch.object(regions,'admitted',gate):
                    try:vm.execute_prepared(vm.prepare(source,'routine-region.bsl'));error=None
                    except BaseException as exc:error=(type(exc).__name__,str(exc),getattr(exc,'line',None),getattr(exc,'column',None))
                outcomes.append((canonical.snapshot(vm),error));decisions.append(seen)
            finally:
                if cleanup:cleanup()
                vm.close()
        self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[0],outcomes[2])
        return decisions

    def test_straight_line_loops_local_and_module_graphs(self):
        for global_ in ('','Var T;'):
            for body in (
                'T=New ValueList;For I=0 To N Do T.Add(I);EndDo;R=0;For I=0 To N Do R=R+T.Get(I).Value;EndDo;Return R;',
                'T=New ValueTable;T.Columns.Add("N");For I=0 To N Do Row=T.Add();Row.N=I;EndDo;Return T.Count();',
            ):
                for n in (-1,0,3):
                    with self.subTest(global_=global_,body=body,n=n):
                        seen=self.paired(global_+'Function F(Val N) '+body+'EndFunction;R=F('+str(n)+');')
                        expected=[True,True] if 'R=0;' in body else [True]
                        self.assertEqual(seen[1:],[expected,expected])

    def test_partial_errors_and_repeated_activation(self):
        for source in (
            'Var T;Function F(Val N) T=New ValueTable;T.Columns.Add("N");For I=0 To N Do Row=T.Add();Row.N=1%(2-I);EndDo;Return 0;EndFunction;R=F(3);',
            'Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return T.Count();EndFunction;A=F(2);B=F(-1);C=F(0);',
            'Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;If N>0 Then Return F(N-1)+T.Count();EndIf;Return 1;EndFunction;R=F(3);',
        ):self.paired(source)

    def test_non_scalar_parameter_and_public_method_override_decline(self):
        self.paired('Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return T.Count();EndFunction;R=F("bad");')
        def install(vm):
            original=BSLValueList.add
            def closing(owner,*args,**kwargs):
                result=original(owner,*args,**kwargs);vm.close();return result
            BSLValueList.add=closing
            return lambda:setattr(BSLValueList,'add',original)
        seen=self.paired('Var T;Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return 1;EndFunction;R=F(2);',install)
        self.assertEqual(seen[1:],[[False],[False]])

    def test_boxed_and_nested_loops_remain_ordinary(self):
        for source in (
            'Function F(N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return T.Count();EndFunction;N=2;R=F(N);',
            'Function F(Val N) T=New ValueList;For I=0 To N Do For J=0 To N Do T.Add(I+J);EndDo;EndDo;Return T.Count();EndFunction;R=F(2);',
        ):
            self.assertEqual(self.paired(source)[1:],[[],[]])

    def test_hostile_global_key_declines_before_snapshot_lookups(self):
        from yadinassi.value_tables import BSLValueTableColumnCollection as Columns
        source='Var T,Row;Function F(Val N) T=New ValueTable;T.Columns.Add("N");For I=0 To N Do Row=T.Add();Row.N=I;EndDo;Return 1;EndFunction;R=F(1);'
        outcomes=[]
        for compiler in (text_compile,direct.compile_module,direct.compile_module_whole_source):
            vm=Interpreter();seen=[];original=Columns.add
            class Key:
                def __hash__(self):return hash('row')
                def __eq__(self,other):
                    if type(other) is str and other=='row':seen.append(len(vm.variables['t'].rows))
                    return False
            key=Key()
            def schema(owner,*args,**kwargs):
                result=original(owner,*args,**kwargs)
                Columns.add=original
                del vm.variables['row'];vm.variables[key]=None
                return result
            try:
                Columns.add=schema
                with patch.object(python_direct,'_compile',compiler):vm.execute(source)
                outcomes.append((list(seen),vm.variables['r'],len(vm.variables['t'].rows)))
            finally:Columns.add=original;vm.close()
        self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[0],outcomes[2])
        self.assertTrue(outcomes[0][0]);self.assertNotIn(0,outcomes[0][0])

    def test_possibly_bound_overwrites_decline_later_loop(self):
        for n in (-1,2):
            source='Function F(Val N) T=New ValueList;For I=0 To N Do Item=T.Add(I);EndDo;For J=0 To 2 Do Item=T.Add(J);EndDo;Return T.Count();EndFunction;R=F('+str(n)+');'
            self.assertEqual(self.paired(source)[1:],[[True],[True]])

    def test_definite_rebind_after_zero_trip_allows_later_loop(self):
        for n in (-1,2):
            source='Function F(Val N) T=New ValueList;For I=0 To N Do Item=T.Add(I);EndDo;Item=T.Add(9);For J=0 To 2 Do Item=T.Add(J);EndDo;Return T.Count();EndFunction;R=F('+str(n)+');'
            self.assertEqual(self.paired(source)[1:],[[True,True],[True,True]])
