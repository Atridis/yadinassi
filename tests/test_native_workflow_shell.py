"""Shared native workflow shell fixtures keep Windows Git Bash and startup guards."""
import os
import subprocess
import unittest
from unittest import mock
from native_workflow_shell import bash_executable, dispatch


class NativeWorkflowShellTests(unittest.TestCase):
    def test_windows_selects_git_bash_never_wsl_launcher(self):
        calls=[]
        def which(name):
            calls.append(name)
            return r'C:\Program Files\Git\cmd\git.exe' if name=='git.exe' else r'C:\Windows\System32\bash.exe'
        expected=r'C:\Program Files\Git\bin\bash.exe'
        self.assertEqual(bash_executable(platform='nt',which=which,is_file=lambda path:path==expected),expected)
        self.assertEqual(calls,['git.exe'])
        fallback=r'C:\Program Files\Git\usr\bin\bash.exe'
        self.assertEqual(bash_executable(platform='nt',which=which,is_file=lambda path:path==fallback),fallback)
        with self.assertRaisesRegex(AssertionError,'Git-for-Windows'):
            bash_executable(platform='nt',which=which,is_file=lambda path:False)
        self.assertNotIn('bash',calls)
        with self.assertRaisesRegex(AssertionError,'Git-for-Windows'):
            bash_executable(platform='nt',which=lambda name:None,is_file=lambda path:True)
        for unknown in (r'C:\tools\git.exe',r'cmd\git.exe',r'C:\Git\cmd\other.exe'):
            with self.subTest(path=unknown),self.assertRaisesRegex(AssertionError,'Git-for-Windows'):
                bash_executable(platform='nt',which=lambda name:unknown,is_file=lambda path:True)
        self.assertEqual(bash_executable(platform='nt',
            which=lambda name:None if name=='git.exe' else r'C:\Git\bin\git.exe',
            is_file=lambda path:path==r'C:\Git\bin\bash.exe'),r'C:\Git\bin\bash.exe')
        with self.assertRaisesRegex(AssertionError,'Bash is required'):
            bash_executable(platform='posix',which=lambda name:None)
        self.assertEqual(bash_executable(platform='posix',which=lambda name:'/bin/bash'),'/bin/bash')

    def test_dispatch_uses_only_inprocess_stub_and_no_shell_startup_hook(self):
        with mock.patch('native_workflow_shell.bash_executable',return_value='/verified/bash'), \
             mock.patch.object(subprocess,'run') as run, \
             mock.patch.dict(os.environ,{'BASH_ENV':'untrusted','ENV':'untrusted'},clear=False):
            dispatch('python3 fixed --argument')
        args=run.call_args.args[0];options=run.call_args.kwargs
        self.assertEqual(args[:5],['/verified/bash','--noprofile','--norc','-e','-c'])
        self.assertTrue(args[5].startswith("python3() { printf '%s\\n' \"$*\"; }\n"))
        self.assertTrue(args[5].endswith('python3 fixed --argument'))
        self.assertNotIn('BASH_ENV',options['env']);self.assertNotIn('ENV',options['env'])
        self.assertIs(options['stdin'],subprocess.DEVNULL)
        with self.assertRaisesRegex(AssertionError,'Unsupported'):
            bash_executable(platform='unknown',which=lambda name:'/bin/bash')
