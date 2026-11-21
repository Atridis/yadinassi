"""Finite direct HTTP/file protocol; external-access checks remain canonical."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import gc
import unittest
import weakref
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.http.http_client import BSLHTTPConnection,BSLHTTPRequest,_headers
from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap
from yadinassi.execution.direct.python_direct_plain_map import PlainMap

class DirectHTTPTests(unittest.TestCase):
    def test_file_body_follows_bsl_alias_not_method_receiver_temps(self):
        from yadinassi.http import http_client

        with TemporaryDirectory() as root:
            path=Path(root,'request.bin')
            path.write_bytes(b'abc')
            for kind, statements, expected in (
                ('success','Q.GetBodyFileName(); Q=Undefined; Message("check");',[True]),
                ('caught','Q.GetBodyFileName(); Try Raise "stop"; Except Q=Undefined; Message("check"); EndTry;',[True]),
                ('alias','A=Q; Q.GetBodyFileName(); Q=Undefined; Message("check"); '
                         'A=Undefined; Message("check");',[False,True]),
            ):
                with self.subTest(kind=kind):
                    opened=[]
                    observed=[]
                    open_regular=http_client._open_regular
                    def track(name):
                        handle=open_regular(name)
                        opened.append(handle)
                        return handle
                    vm=Interpreter(lambda _:observed.append(opened[0].closed))
                    vm.variables['path']=str(path)
                    with patch.object(http_client,'_open_regular',track):
                        vm.execute('Procedure Run(Val Path) Q=New HTTPRequest("/"); '
                                   'Q.SetBodyFileName(Path); '+statements+' EndProcedure Run(Path);')
                    self.assertEqual(len(opened),1)
                    self.assertEqual(observed,expected)

    def test_constructor_holes_source_ast_prepared(self):
        from yadinassi.syntax.parser import parse
        source='C=New HTTPConnection("127.0.0.1",8080,,,,10);R=C.Timeout;Q=New HTTPRequest("/",);'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('legacy')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['r'],10)

    def test_required_and_unknown_constructor_holes_refuse_before_effects(self):
        for source in ('C=New HTTPConnection(,Effect());','Q=New HTTPRequest(,Effect());','F=New File(Effect(),);'):
            vm=Interpreter(allow_extensions=True);events=[];vm.register_function('Effect',lambda:events.append(1))
            with self.assertRaises(BSLRuntimeError):vm.execute(source)
            self.assertEqual(events,[])

    def test_constructor_override_refuses_before_argument_effects(self):
        vm=Interpreter(allow_extensions=True);events=[];vm.register_type('HTTPConnection',lambda *a:events.append('factory'))
        vm.register_function('Effect',lambda:events.append('arg'))
        with self.assertRaises(BoundaryViolation):vm.execute('C=New HTTPConnection(Effect());')
        self.assertEqual(events,[])

    def test_headers_alias_and_revalidation_before_socket(self):
        vm=Interpreter();vm.execute('H=New Map;H.Insert("X-Test","one");Q=New HTTPRequest("/",H);H.Insert("X-Test","two");R=Q.Headers.Get("X-Test");C=New HTTPConnection("127.0.0.1",8080);')
        self.assertEqual(vm.variables['r'],'two')
        self.assertIs(vm.variables['q'].get_member('Headers'),vm.variables['h'])
        vm.execute('H.Insert("X-Test","bad"+Chars.LF);')
        with patch('socket.create_connection',side_effect=AssertionError('network')) as connect:
            with self.assertRaises(BSLRuntimeError):vm.execute('C.Get(Q);')
            connect.assert_not_called()

    def test_exact_maps_header_syntax_and_duplicates(self):
        for map_type in (_TypedMap,PlainMap):
            class Child(map_type):pass
            for value in ({},Child()):
                with self.assertRaises(TypeError):_headers(value)
            for pairs in ([('x','a'),('X','b')],[(Decimal(1),'x')],[('x','bad\r\n')]):
                value=map_type()
                for key,item in pairs:value[key]=item
                with self.assertRaises((TypeError,ValueError)):_headers(value)

    def test_no_private_header_count_or_size_cap(self):
        value=PlainMap()
        for index in range(110):
            value['X-'+str(index)]='x'*700
        self.assertEqual(len(_headers(value)),110)
        self.assertEqual(len(_headers(PlainMap({'X-Large':'x'*70000}))[0][1]),70000)

    def test_closed_runtime_and_external_access_guard(self):
        vm=Interpreter(allow_extensions=True);vm.execute('C=New HTTPConnection("127.0.0.1",8080);Q=New HTTPRequest("/");')
        with patch('yadinassi.http.http_client.require_external_access',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):vm.execute('C.Get(Q);')
        def close():vm.close();return BSLHTTPRequest('/')
        vm.register_function('Close',close)
        with patch('socket.create_connection',side_effect=AssertionError('network')) as connect:
            with self.assertRaises(BoundaryViolation):vm.execute('C.Get(Close());')
            connect.assert_not_called()

    def test_constructor_capability_does_not_require_cyclic_gc(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        original=BoundaryContext.resolve_callable;references=[]
        def capture(context,*args,**kwargs):
            bound=original(context,*args,**kwargs);references.append(weakref.ref(bound));return bound
        enabled=gc.isenabled();gc.disable()
        try:
            with patch.object(BoundaryContext,'resolve_callable',capture):
                vm=Interpreter();vm.execute('C=New HTTPConnection("127.0.0.1",8080,,,,10);')
            self.assertTrue(references)
            self.assertTrue(all(ref() is None for ref in references))
        finally:
            if enabled:gc.enable()

    def test_original_owned_loopback_native40_without_vm(self):
        from native_1c_http_route import replay,SOURCE
        from native_1c_http_fixture import owned_fixture
        root=Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp,owned_fixture() as fixture:
            with patch.object(Interpreter,'block',side_effect=AssertionError('legacy')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy')):
                actual=replay((root/SOURCE).read_bytes(),Path(tmp).resolve(),fixture.server_port)
        self.assertEqual(actual,(root/'tests/fixtures/http_family/native-initial/output.txt').read_bytes())

    def test_constructor_implementation_mutation_cannot_use_bound_capability(self):
        for source in ('C=New HTTPConnection(Effect(),8080,,,,10);',
                       'Q=New HTTPRequest(Effect());', 'F=New File(Effect());'):
            vm=Interpreter(allow_extensions=True);events=[]
            key='httpconnection' if source.startswith('C=') else 'httprequest' if source.startswith('Q=') else 'file'
            def effect():
                vm.types[key].function=lambda *args:events.append(args)
                return '127.0.0.1'
            vm.register_function('Effect',effect)
            with self.assertRaises(BoundaryViolation):vm.execute(source)
            self.assertEqual(events,[])
