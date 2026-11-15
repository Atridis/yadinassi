"""Compiler RHS temporaries must not extend resource lifetime past BSL refs.

Weakrefs and actual HTTP body handles make the Windows unlink failure observable
on every platform, without relying on GC timing or changing file permissions.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from yadinassi import Interpreter
from yadinassi.http_client import BSLHTTPRequest


class CompiledTemporaryLifetimeTests(unittest.TestCase):
    def observe(self, mode, body):
        references, handles, observations = [], [], []
        original_init = BSLHTTPRequest.__init__
        original_file = BSLHTTPRequest.set_body_file_name

        def init(request, *args, **kwargs):
            original_init(request, *args, **kwargs)
            references.append(weakref.ref(request))

        def set_file(request, path):
            result = original_file(request, path)
            handles.append(request._file_handle)
            return result

        def output(message):
            observations.append((str(message), tuple(ref() is not None for ref in references),
                                 tuple(handle.closed for handle in handles)))

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'body.bin'
            path.write_bytes(b'abc')
            source = body.replace('BODY_FILE', str(path).replace('"', '""'))
            with patch.object(BSLHTTPRequest, '__init__', init), \
                    patch.object(BSLHTTPRequest, 'set_body_file_name', set_file):
                vm = Interpreter(output, execution_backend=mode)
                vm.execute(source)
            if mode == 'compiled-strict':
                self.assertGreater(vm.compiled_backend_stats['block_executions'], 0)
                self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)
            self.assertTrue(all(handle.closed for handle in handles))
        return observations

    def pair(self, source, expected):
        baseline = self.observe('interpreter', source)
        self.assertEqual(baseline, expected)
        self.assertEqual(self.observe('compiled-strict', source), baseline)

    def test_reassignment_releases_file_before_next_statement(self):
        self.pair('''Procedure Run()
Q=New HTTPRequest("/echo");Q.SetBodyFileName("BODY_FILE");
Q=Undefined;Message("released");DeleteFiles("BODY_FILE");
EndProcedure Run();''', [('released', (False,), (True,))])

    def test_nested_rhs_and_alias_keep_only_live_bsl_reference(self):
        self.pair('''Procedure Run()
Q=((New HTTPRequest("/echo")));Q.SetBodyFileName("BODY_FILE");
Alias=Q;Q=Undefined;Message("alias-live");
Alias=Undefined;Message("released");DeleteFiles("BODY_FILE");
EndProcedure Run();''', [('alias-live', (True,), (False,)),
                       ('released', (False,), (True,))])

    def test_returned_resource_and_byref_clear_preserve_call_semantics(self):
        self.pair('''Function Make()
Return New HTTPRequest("/echo");EndFunction
Procedure Clear(Value) Value=Undefined;EndProcedure
Procedure Run()
Q=Make();Q.SetBodyFileName("BODY_FILE");Message("live");
Clear(Q);Message("released");DeleteFiles("BODY_FILE");
EndProcedure Run();''', [('live', (True,), (False,)),
                       ('released', (False,), (True,))])

    def test_replaced_resource_released_before_next_file_owner(self):
        self.pair('''Procedure Run()
Q=New HTTPRequest("/echo");Q.SetBodyFileName("BODY_FILE");
Q=New HTTPRequest("/other");Message("replaced");
Q=Undefined;Message("released");DeleteFiles("BODY_FILE");
EndProcedure Run();''', [('replaced', (False, True), (True,)),
                       ('released', (False, False), (True,))])

    def test_failed_rhs_does_not_clear_existing_variable_or_error(self):
        self.pair('''Procedure Run()
Q=New HTTPRequest("/echo");Q.SetBodyFileName("BODY_FILE");
Try Q=1/0;Except Message("still-live");EndTry;
Q=Undefined;Message("released");DeleteFiles("BODY_FILE");
EndProcedure Run();''', [('still-live', (True,), (False,)),
                       ('released', (False,), (True,))])
