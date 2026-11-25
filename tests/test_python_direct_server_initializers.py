from decimal import Decimal
import json
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

DECL='&AtServer\nVar N;\n&AtServer\nFunction Read() Return N;EndFunction\n'
def initialize(body):return '#If AtServer Then\n'+body+'\n#EndIf\n'
def vm(*, allow_extensions=False):return Interpreter(allow_extensions=allow_extensions, compilation_profile='managed-thick-file')

class DirectServerInitializerTests(unittest.TestCase):
    def test_source_ast_prepared_initializer_once_per_crossing(self):
        from yadinassi.syntax.parser import parse
        source=DECL+'&AtServer\nFunction Nested() N=N+1;Return Read();EndFunction\n'+initialize('N=100;Tick();')+'R=Nested();'
        for route in ('source','ast','prepared'):
            owner=vm(allow_extensions=True);ticks=[];owner.register_function('Tick',lambda:ticks.append(owner.execution_context))
            if route=='source':owner.execute(source)
            elif route=='ast':owner.execute_program(parse(source,compilation_profile='managed-thick-file'))
            else:owner.execute_prepared(owner.prepare(source))
            self.assertEqual(owner.variables['r'],101)
            owner.execute('R=Read();');self.assertEqual(owner.variables['r'],100)
            self.assertEqual(ticks,['server','server']);self.assertNotIn('n',owner.variables)

    def test_initializer_calls_routines_without_recursing_initialization(self):
        owner=vm();owner.execute(DECL+'&AtServer\nProcedure Init() N=42;EndProcedure\n'+initialize('Init();')+'R=Read();')
        self.assertEqual(owner.variables['r'],42)

    def test_standalone_and_repeated_prepared_initializers_accumulate_in_order(self):
        owner=vm();owner.execute(DECL+initialize('N=1;'))
        plan=owner.prepare(initialize('N=N*10+2;'))
        owner.execute_prepared(plan);owner.execute_prepared(plan)
        owner.execute('R=Read();');self.assertEqual(owner.variables['r'],122)
        # Source routine replacement must not erase prior initializers.
        owner.execute('&AtServer\nFunction Read() Return N;EndFunction')
        owner.execute('R=Read();');self.assertEqual(owner.variables['r'],122)

    def test_declaration_load_does_not_run_server_initializer(self):
        owner=vm(allow_extensions=True);effects=[];owner.register_function('Tick',lambda:effects.append(1))
        owner.execute(DECL+initialize('Tick();N=1;'))
        self.assertEqual(effects,[])
        owner.execute('R=Read();');self.assertEqual(effects,[1])

    def test_initializer_failure_discards_output_and_recovers(self):
        owner=vm(allow_extensions=True);enabled=[True];owner.register_function('FailNow',lambda:enabled[0])
        owner.execute(DECL+'&AtServer\nProcedure SetX(X) X=9;EndProcedure\n'+initialize('N=1;If FailNow() Then Raise "init-failure";EndIf;'))
        owner.execute('X=3;')
        with self.assertRaisesRegex(BSLRuntimeError,'init-failure'):owner.execute('SetX(X);')
        self.assertEqual(owner.variables['x'],3);self.assertEqual(owner.execution_context,'client')
        enabled[0]=False;owner.execute('SetX(X);');self.assertEqual(owner.variables['x'],9)

    def test_current_constructor_and_initializer_dependencies_admit_before_effects(self):
        owner=vm(allow_extensions=True);owner.execute(DECL+initialize('N=New Array;'))
        owner.register_type('Array',lambda:[])
        with self.assertRaises(PythonDirectUnsupported):owner.execute('Effect=1;Read();')
        self.assertNotIn('effect',owner.variables)

    def test_initializer_layout_change_rejects_before_effects(self):
        owner=vm();owner.execute(DECL+initialize('N=1;'))
        owner.execute('&AtServer\nVar Later;\n&AtServer\nFunction Next() Return Later;EndFunction')
        with self.assertRaisesRegex(PythonDirectUnsupported,'initializer layout changed'):
            owner.execute('Effect=1;Next();')
        self.assertNotIn('effect',owner.variables)

    def test_prepared_initializer_owns_ast_and_requires_layout(self):
        from yadinassi.syntax.parser import parse
        owner=vm();owner.execute(DECL)
        source=parse(initialize('N=7;'),compilation_profile='managed-thick-file')
        plan=owner.prepare_program(source);source.clear();owner.execute_prepared(plan)
        owner.execute('R=Read();');self.assertEqual(owner.variables['r'],7)
        fresh=vm()
        with self.assertRaisesRegex(PythonDirectUnsupported,'prepared server module-name layout changed'):fresh.execute_prepared(plan)
        self.assertFalse(getattr(fresh,'_direct_server_initializers',()))

    def test_host_closure_during_initializer_fails_closed(self):
        owner=vm(allow_extensions=True);owner.register_function('Close',owner.close)
        owner.execute(DECL+initialize('Close();'))
        with self.assertRaises(BoundaryViolation):owner.execute('Read();')

    def test_initializer_cannot_invoke_client_routine(self):
        owner=vm(allow_extensions=True);effects=[];owner.register_function('Effect',lambda:effects.append(1))
        owner.execute('Function C(Val X) Return X;EndFunction\n'+DECL+initialize('N=C(Effect());'))
        with self.assertRaises(BSLRuntimeError):owner.execute('Read();')
        self.assertEqual(effects,[])

    def test_original_module_context_witness_matches_native_capture(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'scripts/native_1c_bootstrap/client_probe.bsl').read_text(encoding='utf-8')
        declarations=text.split('// BEGIN bounded module context declarations\n',1)[1].split('// END bounded module context declarations',1)[0]
        body=text.split('// BEGIN bounded module context measurement\n',1)[1].split('// BEGIN bounded no-context witness',1)[0]
        tail=text.split('// Initialization runs in its explicitly compiled side only.',1)[1]
        source=declarations+body+tail[tail.index('#If AtClient'):]
        capture=json.loads((root/'integrational_tests/directive_probes/module_context_native.json').read_text(encoding='utf-8'))
        expected=['module.context.v1',*(Decimal(v) if type(v) is int else v for v in capture['values'])]
        owner=vm();self.addCleanup(owner.close)
        owner.execute(source)
        result=list(owner.execute('RunModuleContextProbe()'))
        self.assertEqual(result,expected)
        self.assertEqual(list(map(type,result)),list(map(type,expected)))
