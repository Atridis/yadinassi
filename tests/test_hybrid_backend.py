import unittest
from decimal import Decimal, localcontext
from yadinassi import Interpreter
def HybridInterpreter(**kwargs):
    return Interpreter(execution_backend="hybrid", **kwargs)

class Differential(unittest.TestCase):
    def pair(self, source, compiled=None, initial=None):
        records=[]
        for cls in (Interpreter, HybridInterpreter):
            out=[];vm=cls(output=out.append)
            if initial: vm.variables.update(initial)
            error=None
            try: vm.execute(source)
            except Exception as e: error=(type(e),str(e))
            records.append((dict(vm.variables),out,error))
        self.assertEqual(*records)
        if compiled is not None: self.assertEqual(vm.execution_backend_stats['compiled'],compiled)
        return vm
    def test_numeric(self):
        cases=[
            'r=0; Для i=1 По 100 Цикл r=r+i*3-7; КонецЦикла;',
            'Для i=1 По 0 Цикл r=7; КонецЦикла;',
            'Для i=0.5 По 3.7 Цикл r=i; КонецЦикла;',
            'Для i=-3 По -1 Цикл r=-i; КонецЦикла;',
            'r=0; Для i=1 По 10 Цикл i=i+1;r=r+i;КонецЦикла;',
            'n=3; r=0;Для i=1 По n Цикл n=0;r=r+1;КонецЦикла;',
            'i=5;Для i=i-4 По i+1 Цикл r=i;КонецЦикла;',
            'Для i=1 По 2 Цикл r=1.23456789012345678901234567890123456789*9;КонецЦикла;',
            'Для i=1 По 2 Цикл r=+(1.23456789012345678901234567890123456789);КонецЦикла;',
            'Для i=1 По 2 Цикл r=-(1.23456789012345678901234567890123456789);КонецЦикла;',
            'Для i=1 По 2 Цикл r=1;s=r+2;КонецЦикла;',
            'Для i=1 По 2 Цикл Для j=1 По 2 Цикл r=j;КонецЦикла;КонецЦикла;',
        ]
        for index,src in enumerate(cases):
            with self.subTest(src=src):self.pair(src,2 if index==11 else 1)
    def test_unsupported_no_replay(self):
        cases=[
            'r=0;Для i=1 По 3 Цикл r=r+1;Сообщить(r);КонецЦикла;',
            'Для i=1 По 3 Цикл r=1/0;КонецЦикла;',
            'Для i=1 По 3 Цикл r="a"+i;КонецЦикла;',
            'r=0;Для i=1 По 3 Цикл r=r+1;Прервать;КонецЦикла;',
            'r=0;Для i=1 По 3 Цикл Продолжить;r=r+1;КонецЦикла;',
            'Для i=1 По 3 Цикл r=undefinedName+1;КонецЦикла;',
            'Функция f(x) Для i=1 По 2 Цикл x=x+1;КонецЦикла; Возврат x;КонецФункции r=0;s=f(r);',
            'Функция f() Сообщить(7);Возврат 2;КонецФункции Для i=1 По f() Цикл r=i;КонецЦикла;',
        ]
        for src in cases:
            with self.subTest(src=src):self.pair(src,0)
    def test_generated_decimal_cases(self):
        import random
        rng=random.Random(813)
        for _ in range(60):
            a,b,c=[rng.randrange(-100,100) for _ in range(3)]
            op=rng.choice(['+','-','*'])
            self.pair(f'r={a};Для i=-2 По 5 Цикл r=(r {op} {b})+i*{c};КонецЦикла;',1)
    def test_instance_instrumentation_fallback(self):
        vm=HybridInterpreter();writes=[];original=vm.set_variable
        def traced(name,value):
            writes.append((name,value));return original(name,value)
        vm.set_variable=traced
        vm.execute('Для i=1 По 2 Цикл r=i;КонецЦикла;')
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        self.assertEqual(len(writes),5)
    def test_reference_fallback(self):
        self.pair('Процедура f(x) Для x=1 По 3 Цикл x=x+1;КонецЦикла;КонецПроцедуры r=0;f(r);',0)
    def test_side_effect_bound_once(self):
        vm=self.pair('Функция f() Сообщить(7);Возврат 2;КонецФункции Для i=f() По f()+1 Цикл r=i;КонецЦикла;',0)
        self.assertEqual(vm.execution_backend_stats['fallback'],1)
    def test_overflow_error_location(self):
        self.pair('Для i=1 По 2 Цикл\nr=big*big;\nКонецЦикла;',1,{'big':Decimal('1e999999')})
    def test_compiled_error_never_replays(self):
        vm=self.pair('r=0;Для i=1 По 2 Цикл r=r+1;z=big*big;КонецЦикла;',1,{'big':Decimal('1e999999')})
        self.assertEqual(vm.variables['r'],Decimal(1))
    def test_counter_nonfinite_error(self):
        self.pair('Для i=1 По big Цикл r=i;КонецЦикла;',1,{'big':Decimal('NaN')})
    def test_decimal_scheduler_context(self):
        with localcontext() as ctx:
            ctx.prec=7
            vm=self.pair('Для i=1 По 1 Цикл r=12345678901234567890*12345678901234567890;КонецЦикла;',1)
            self.assertEqual(len(vm.variables['r'].as_tuple().digits),38)
            self.assertEqual(ctx.prec,7)
    def test_mutable_ast_recompiled(self):
        from yadinassi.syntax.parser import parse
        nodes=parse('Для i=1 По 2 Цикл r=1;КонецЦикла;')
        vm=HybridInterpreter();vm.execute_program(nodes)
        nodes[0].body[0].value.value=Decimal(4)
        vm.execute_program(nodes)
        self.assertEqual(vm.variables['r'],Decimal(4))



class AdmissionTests(unittest.TestCase):
    def test_default_is_unchanged_and_stats_are_copy(self):
        vm=Interpreter();vm.execute('Для i=1 По 2 Цикл r=i;КонецЦикла;')
        self.assertEqual(vm.execution_backend,'interpreter')
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        copy=vm.execution_backend_stats;copy['compiled']=99
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        with self.assertRaises(ValueError):Interpreter(execution_backend='python')

    def test_class_hook_instrumentation_falls_back(self):
        from unittest.mock import patch
        original=Interpreter.set_variable
        writes=[]
        def trace(vm,name,value):
            writes.append(name);return original(vm,name,value)
        with patch.object(Interpreter,'set_variable',trace):
            vm=HybridInterpreter();vm.execute('Для i=1 По 2 Цикл r=i;КонецЦикла;')
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        self.assertEqual(len(writes),5)

    def test_numeric_helper_instrumentation_falls_back(self):
        from unittest.mock import patch
        from yadinassi import runtime
        original=runtime.require_number;seen=[]
        def traced(value):
            seen.append(value);return original(value)
        with patch.object(runtime,'require_number',traced):
            vm=HybridInterpreter();vm.execute('Для i=1 По 2 Цикл r=i;КонецЦикла;')
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        self.assertTrue(seen)

    def test_profile_and_trace_fall_back(self):
        import sys
        for setter,getter in ((sys.settrace,sys.gettrace),(sys.setprofile,sys.getprofile)):
            previous=getter()
            try:
                setter(lambda *args: None)
                vm=HybridInterpreter();vm.execute('Для i=1 По 2 Цикл r=i;КонецЦикла;')
                self.assertEqual(vm.execution_backend_stats['compiled'],0)
            finally: setter(previous)

    def test_subclass_falls_back(self):
        class Traced(Interpreter):pass
        vm=Traced(execution_backend='hybrid')
        vm.execute('Для i=1 По 2 Цикл r=i;КонецЦикла;')
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        self.assertEqual(vm.execution_backend_stats['fallback'],1)

    def test_restricted_contexts_not_admitted(self):
        from yadinassi.hybrid_backend import eligible
        for field,value in (('_configuration_runtime',object()),('_database_context',object()),
                            ('_family_owner',object()),('imports',{'x':object()})):
            vm=HybridInterpreter();setattr(vm,field,value)
            self.assertFalse(eligible(vm))
        vm=HybridInterpreter();vm.locals={};self.assertFalse(eligible(vm))
        vm=HybridInterpreter();vm._eval_depth[0]=1;self.assertFalse(eligible(vm))
        vm=HybridInterpreter(compilation_profile='managed-thick-file');self.assertFalse(eligible(vm))

    def test_compile_body_budget_falls_back_before_effects(self):
        vm=HybridInterpreter();vm.execute('r=0;Для i=1 По 1 Цикл '+'r=r+1;'*257+'КонецЦикла;')
        self.assertEqual(vm.variables['r'],Decimal(257))
        self.assertEqual(vm.execution_backend_stats['compiled'],0)
        self.assertEqual(vm.execution_backend_stats['fallback'],1)

    def test_compile_depth_budget_is_bounded(self):
        from yadinassi.hybrid_backend import Compiler, Unsupported
        from yadinassi.syntax.parser import parse
        from yadinassi.syntax import ast
        node=parse('Для i=1 По 1 Цикл r=1;КонецЦикла;')[0]
        for _ in range(80):node.body[0].value=ast.Group(node.token,node.body[0].value)
        with self.assertRaises(Unsupported):Compiler(HybridInterpreter()).build(node)

    def test_no_code_cache_after_state_type_changes(self):
        vm=HybridInterpreter();vm.execute('r=0;Для i=1 По 1 Цикл r=r+1;КонецЦикла;')
        vm.variables['r']='s'
        vm.execute('Для i=1 По 1 Цикл r=r+1;КонецЦикла;')
        self.assertEqual(vm.variables['r'],'s1')
        self.assertEqual(vm.execution_backend_stats['compiled'],1)
        self.assertEqual(vm.execution_backend_stats['fallback'],1)

class HybridCLITests(unittest.TestCase):
    def run_cli(self,*args):
        import subprocess,sys
        return subprocess.run([sys.executable,'-m','yadinassi',*args],capture_output=True,
                              encoding='utf-8',timeout=15)
    def test_explicit_cli_mode(self):
        for mode in ('interpreter','hybrid'):
            r=self.run_cli('--execution-backend',mode,'-c',
                           'r=0;Для i=1 По 10 Цикл r=r+i*3-7;КонецЦикла;Сообщить(r);')
            self.assertEqual((r.returncode,r.stdout.strip(),r.stderr),(0,'95',''))
    def test_source_and_database_modes_are_rejected(self):
        for args in (('--f','missing.sqlite'),('--preprocessor-profile','managed-thick-file'),
                     ('--configuration-source','missing')):
            r=self.run_cli('--execution-backend','hybrid',*args)
            self.assertEqual(r.returncode,2)
            self.assertIn('standalone BSL only',r.stderr)

if __name__=='__main__':unittest.main()
