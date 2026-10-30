"""Actual reviewed probe parsing with exec intercepted, never native execution."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_native_catalog_zero_code_host as host_tests
import test_native_catalog_zero_code_policy as facts
import test_native_catalog_description_rows_workflow as shell
import inputs

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/'scripts/native_1c_db_oracle/probe.sh'
# Intercept only the Bash exec builtin at its last boundary. No script text is
# rewritten; the production nonce/flag parser and argv construction run intact.
STUB='''exec() {
  if [ "$#" -eq 0 ]; then builtin exec; return; fi
  [ "$1" = python3 ] || exit 97
  shift
  printf '%s\\n' "$@"
  exit 0
}
source "$@"
'''

def dispatch(args):
    env={k:v for k,v in os.environ.items() if k not in ('BASH_ENV','ENV')}
    return subprocess.run([shell.bash_executable(),'--noprofile','--norc','-c',STUB,
        'probe-test',PROBE.as_posix(),*args],env=env,stdin=subprocess.DEVNULL,
        capture_output=True,text=True,timeout=10)

class NumericCodeProbeTests(unittest.TestCase):
    def test_host_emitted_args_reach_exact_run_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            try:
                for case in ('zero0','zero8'):
                    prov=facts.provenance();prov['actual_version']=None
                    prov['sources']=inputs.source_hashes(ROOT,zero_case=case)
                    stage=root/case
                    inputs.stage_inputs(ROOT,stage,facts.NONCE,prov,zero_case=case)
                    command=host_tests.host.container_command(stage,'onec-db-oracle-'+'a'*32,
                        facts.NONCE,zero_case=case)
                    result=dispatch(command[-3:])
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout.splitlines(),['-B','/oracle/run.py',*command[-3:]])
            finally:host_tests.old.old.old.writable(root)
    def test_old_modes_and_malformed_or_unknown_args(self):
        for flag in (None,'--catalog-description-rows-8','--catalog-description-rows-17','--catalog-description-8'):
            args=['--invocation-nonce',facts.NONCE]+([] if flag is None else [flag])
            result=dispatch(args);self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout.splitlines(),['-B','/oracle/run.py',*args])
        for args in ([],['--invocation-nonce'],['--wrong',facts.NONCE],
            ['--invocation-nonce','a'*31,'--catalog-zero-code-0'],
            ['--invocation-nonce','A'*32,'--catalog-zero-code-0'],
            ['--invocation-nonce',facts.NONCE,'--catalog-zero-code-9'],
            ['--invocation-nonce',facts.NONCE,'--catalog-zero-code-0','extra']):
            result=dispatch(args)
            self.assertEqual(result.returncode,2,(args,result.stdout,result.stderr))
            self.assertEqual(result.stdout,'')
