"""Async standalone lifecycle, not a native API-family implementation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import io
from contextlib import redirect_stdout, redirect_stderr

from yadinassi import Interpreter
from yadinassi import cli

ROOT=Path(__file__).resolve().parents[1]
PROGRAM='Async Function F() Return Await 17; EndFunction\nAsync Procedure Main() Message(Await F()); EndProcedure\nMain();'

class AsyncCLITests(unittest.TestCase):
    def cli(self,*args,stdin=None):
        return subprocess.run([sys.executable,'-m','yadinassi',*args],input=stdin,
                              cwd=ROOT,text=True,encoding="utf-8",capture_output=True,timeout=20)

    def test_transport_is_utf8_under_non_utf8_host_locale(self):
        # Windows subprocess text decoding otherwise uses cp1252 even when the
        # child CLI explicitly writes UTF-8. Exercise both stdin and stdout.
        with patch('subprocess._text_encoding', return_value='cp1252'):
            result = self.cli('-', stdin='Message("проверка");')
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, 'проверка\n', ''))

    def test_command_file_stdin_console_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'async.bsl';source.write_text(PROGRAM,encoding='utf-8-sig')
            cases=[(('-c',PROGRAM),None),((str(source),),None),(('-',),PROGRAM),
                   ((),PROGRAM+'\n/exit\n')]
            for args,stdin in cases:
                with self.subTest(args=args):
                    r=self.cli(*args,stdin=stdin)
                    self.assertEqual((r.returncode,r.stdout,r.stderr),(0,'17\n',''))

    def test_procedure_failure_clean_exit(self):
        r=self.cli('-c','Async Procedure P() x=Await 1; Raise "async failure"; EndProcedure P();')
        self.assertEqual(r.returncode,1)
        self.assertIn('async failure',r.stderr)
        self.assertNotIn('Traceback',r.stderr)

    def test_blocked_cycle_is_not_success(self):
        program='''Var a,b;
        Async Function A1() x=Await 0; Return Await b; EndFunction
        Async Function B1() x=Await 0; Return Await a; EndFunction
        a=A1();b=B1();'''
        r=self.cli('-c',program)
        self.assertEqual(r.returncode,1)
        self.assertIn('незавершенные',r.stderr)
        self.assertNotIn('Traceback',r.stderr)

    def test_unawaited_function_failure_not_reported_as_procedure(self):
        r=self.cli('-c','Async Function F() Raise "ignored"; EndFunction p=F();Message("done");')
        self.assertEqual((r.returncode,r.stdout,r.stderr),(0,'done\n',''))

    def test_promise_type_codec_error_catchable(self):
        r=self.cli('-c','Try x=ValueToStringInternal(Type("Promise")); Except Message("caught"); EndTry;')
        self.assertEqual((r.returncode,r.stdout,r.stderr),(0,'caught\n',''))

    def test_noninteractive_interrupt_keeps_130(self):
        vm=Interpreter(lambda _:None)
        def interrupt(): raise KeyboardInterrupt
        vm.register_function('Interrupt',interrupt)
        program='Async Procedure P() x=Await 1; Interrupt(); EndProcedure P();'
        with patch.object(cli,'Interpreter',return_value=vm), patch('sys.stdin.isatty',return_value=False), \
             patch('builtins.input',side_effect=[program]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main([]),130)
        self.assertEqual(vm.pending_promises,())

    def test_interactive_interrupt_cancels_siblings_before_next_command(self):
        output=[];vm=Interpreter(output.append)
        def interrupt(): raise KeyboardInterrupt
        vm.register_function('Interrupt',interrupt)
        program=('Async Procedure P() x=Await 1; Interrupt(); EndProcedure '
                 'Async Procedure Q() x=Await 1; Message("leaked"); EndProcedure P();Q();')
        session=Mock();session.prompt.side_effect=[program,'Message("next");','/exit']
        with patch('prompt_toolkit.PromptSession',return_value=session), patch('sys.stdin.isatty',return_value=True), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.repl(vm),0)
        self.assertEqual(output,['next'])
        self.assertEqual(vm.pending_promises,())
