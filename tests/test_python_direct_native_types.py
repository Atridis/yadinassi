from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import BSLType, Reference
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct_services import ServicesBoundary
from yadinassi.types.type_values import type_of

class DirectNativeTypeTests(unittest.TestCase):
    def test_native_collections_source_ast_prepared_without_vm(self):
        from yadinassi.syntax.parser import parse
        source='A=New Array;S=New Structure;M=New Map;R=TypeOf(A)=Type("Array") And ТипЗнч(S)=Type("Structure") And TypeOf(M)=Type("Map");'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            if route=='source':vm.execute(source)
            elif route=='ast':vm.execute_program(parse(source))
            else:vm.execute_prepared(vm.prepare(source))
            self.assertTrue(vm.variables['r'])

    def test_canonical_alias_and_custom_overrides(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Alias',type_of)
        self.assertIs(vm.execute('Alias(New Structure)'),BSLType.STRUCTURE)
        vm.register_function('TypeOf',lambda value:'custom')
        self.assertEqual(vm.execute('TypeOf(New Structure)'),'custom')
        with patch('yadinassi.types.type_values.type_of',lambda value:'patched'):
            from yadinassi.types import type_values
            other=Interpreter(allow_extensions=True);other.register_function('Alias',type_values.type_of)
            self.assertEqual(other.execute('Alias(New Array)'),'patched')

    def test_plain_dict_subclasses_and_global_type_api_are_not_admitted(self):
        with self.assertRaises(TypeError):type_of([])
        for value in ({},type('ListChild',(list,),{})(),type('DictChild',(dict,),{})()):
            vm=Interpreter();vm.variables['v']=value
            with self.assertRaises(BSLRuntimeError):vm.execute('TypeOf(V);')
        vm=Interpreter();self.assertIs(vm.execute('TypeOf(StrSplit("a,b",","))'),BSLType.ARRAY)

    def test_current_service_policy_and_revocation_remain_enforced(self):
        class Context(ServicesBoundary,BoundaryContext):pass
        vm=Interpreter(allow_extensions=True);calls=[]
        context=Context(services=vm.functions,policy=lambda action,name:calls.append((action,name)) or False)
        context.vm=vm;context.enter()
        with self.assertRaises(BoundaryViolation):context.resolve_service('typeof')([])
        self.assertEqual(calls,[('call','typeof')])
        vm=Interpreter(allow_extensions=True)
        def change():vm.functions['typeof'].function=lambda value:'wrong';return []
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('R=TypeOf(Change());')
        self.assertNotIn('r',vm.variables)

    def test_named_val_is_late_expression_is_early_without_copyback(self):
        source='''Function Identity(Val X) Return X;EndFunction
Function Change(X) X=9;Return 2;EndFunction
&AtServer
Function F(Val Named,Val Expression,Val Token) R=Named*100+Expression*10+Token;Named=77;Return R;EndFunction
X=1;R=F((X),Identity(X),Change(X));'''
        vm=Interpreter();vm.execute(source)
        self.assertEqual((vm.variables['x'],vm.variables['r']),(9,912))

    def test_val_property_and_index_expressions_keep_early_values(self):
        vm=Interpreter();vm.execute('''Function Change(S,A) S.X=9;A[0]=8;Return 0;EndFunction
&AtServer
Function F(Val P,Val I,Val Token) Return P*10+I;EndFunction
S=New Structure("X",1);A=New Array;A.Add(2);R=F(S.X,A[0],Change(S,A));''')
        self.assertEqual(vm.variables['r'],12)

    def test_named_val_reference_revocation_stops_before_callee(self):
        vm=Interpreter(allow_extensions=True);events=[]
        def get():vm.close();return Decimal(1)
        vm.variables['x']=Reference(get,lambda value:events.append('write'))
        vm.register_function('Later',lambda:events.append('later') or Decimal(2))
        vm.register_function('Callee',lambda:events.append('callee'))
        vm.execute('&AtServer\nFunction F(Val X,Val Y) Callee();Return X;EndFunction')
        with self.assertRaises(BoundaryViolation):vm.execute('R=F(X,Later());')
        self.assertEqual(events,['later']);self.assertNotIn('r',vm.variables)

    def test_named_val_from_execute_and_server_nocontext(self):
        vm=Interpreter();vm.execute('''Function Change(X) X=9;Return 2;EndFunction
&AtServerNoContext
Function F(Val X,Val Token) Return X;EndFunction
X=1;R=0;Execute("R=F(X,Change(X));");''')
        self.assertEqual((vm.variables['x'],vm.variables['r']),(9,9))

    def test_pinned_sqlite_client_output_matches_exactly(self):
        # The full Linux ownership/census proof runs in its own mandatory Light
        # workflow step. This test covers the real client output on every OS.
        from scripts import native_1c_full_host as host
        root = Path(__file__).resolve().parents[1]
        source = root / host.CLIENT_SOURCE
        self.assertEqual(sha256(source.read_bytes()).hexdigest(), host.PREPROCESSOR_SOURCE_SHA256)
        fixture = host._load_infobase_fixture()
        expected = json.dumps(host.CLIENT_SQLITE_RUNTIME_VALUES + [host.PREPROCESSOR_RUNTIME_TOKEN],
                              ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.assertEqual(sha256(expected).hexdigest(),
                         '71c3061d8f776e5831b1ec38559319876a555edf799e152b4911a820d4ab4a2b')
        env = host.child_environment()
        if sys.platform == 'win32':
            # Windows requires this native loader setting for a child with
            # an explicitly supplied environment.
            env['SystemRoot'] = os.environ['SystemRoot']
        with TemporaryDirectory(prefix='pinned-sqlite-client-') as folder:
            directory = Path(folder).resolve(strict=True)
            database = directory / 'application.sqlite'
            self.assertEqual(sha256(fixture._FIXTURE_BYTES).hexdigest(), fixture._FIXTURE_SHA256)
            database.write_bytes(fixture._FIXTURE_BYTES)
            flags = ['-I', '-B', '-X', 'utf8']
            if sys.flags.optimize:
                flags.append('-' + 'O' * sys.flags.optimize)
            result = subprocess.run(
                [sys.executable, *flags, '-c', host.CLIENT_EXECUTE_SCRIPT,
                 str(root), host.PREPROCESSOR_COMPILATION_PROFILE, str(source), str(database)],
                cwd=root, env=env, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(result.stdout, expected)
            self.assertEqual(sha256(source.read_bytes()).hexdigest(), host.PREPROCESSOR_SOURCE_SHA256)
            self.assertEqual(database.read_bytes(), fixture._FIXTURE_BYTES)
            self.assertEqual(list(directory.iterdir()), [database])
