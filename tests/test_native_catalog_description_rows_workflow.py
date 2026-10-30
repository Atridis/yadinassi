"""Closed typed Description workflow dispatch; synthetic shell, no native run."""
import itertools
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import shutil
import textwrap
import unittest
from unittest import mock
import test_native_1c_db_oracle_ci_policy as old

ROUTE='catalog-description-rows-v1'
ROUTES=('catalog-reference-identity-v1','catalog-reference-codec-v1','catalog-reference-rows-v1','catalog-description-measurement-v1',ROUTE)

def marker(job,name):
    source=old.workflow_job(job)
    return textwrap.dedent(source.split('# BEGIN NATIVE DB ORACLE '+name+'\n',1)[1].split('# END NATIVE DB ORACLE '+name,1)[0])

def steps(job):
    return re.split(r'\n      - ',old.workflow_job(job))

def command(job,flag):
    step=next(s for s in steps(job) if flag in s)
    return textwrap.dedent(step.split('        run: |\n',1)[1]).strip()

def rendered(script,route):
    script=script.replace('${{ needs.eligibility.outputs.route }}',route)
    expr="${{ needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec' }}"
    script=script.replace(expr,'rows' if route=='catalog-reference-rows-v1' else 'codec')
    if '${{' in script:raise ValueError('unhandled workflow expression')
    return script

def bash_executable(*, platform=None, which=None, is_file=None):
    """Use an actual Bash, never the Windows System32 WSL launcher."""
    platform=os.name if platform is None else platform
    which=shutil.which if which is None else which
    is_file=(lambda value:Path(value).is_file()) if is_file is None else is_file
    if platform not in ('nt','posix'):raise AssertionError('Unsupported shell fixture platform')
    if platform=='nt':
        git=which('git.exe') or which('git')
        executable=PureWindowsPath(git) if git else None
        if (executable is not None and executable.is_absolute()
                and executable.name.lower()=='git.exe'
                and executable.parent.name.lower() in ('cmd','bin')):
            # Git-for-Windows normally exposes cmd/git.exe (or bin/git.exe).
            root=executable.parent.parent
            for relative in ('bin/bash.exe','usr/bin/bash.exe'):
                candidate=str(root/relative)
                if is_file(candidate):return candidate
        raise AssertionError('Git-for-Windows Bash is required for actual workflow dispatch')
    bash=which('bash')
    if not bash:raise AssertionError('Bash is required for actual workflow dispatch')
    return bash


def dispatch(script):
    # Shell function avoids a CRLF-sensitive shebang, chmod and host PATH
    # translation. Bash itself still executes the unchanged workflow branches.
    stub="python3() { printf '%s\\n' \"$*\"; }\n"
    env={key:value for key,value in os.environ.items() if key not in ('BASH_ENV','ENV')}
    return subprocess.run([bash_executable(),'--noprofile','--norc','-e','-c',stub+script],
        env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10)

class DescriptionRowsWorkflowTests(unittest.TestCase):
    def test_no_jobs_permissions_or_external_trust_expansion(self):
        workflow=old.WORKFLOW_PATH.read_text()
        self.assertEqual(set(re.findall(r'^  ([a-z_]+):$',workflow,re.M)),{'push','eligibility','native_reference_a','native_oracle','native_codec_a','native_codec_b','verdict'})
        self.assertIn('NATIVE_DB_ROUTE: catalog-params-slot-measurement-v1',old.workflow_job('eligibility'))
        for job in ('native_codec_a','native_codec_b'):
            block=old.workflow_job(job)
            self.assertIn("needs.eligibility.outputs.route == '"+ROUTE+"'",block)
            self.assertIn('    permissions:\n      contents: read\n      packages: read',block)
            self.assertEqual(block.count('GHCR_TOKEN:'),1)
            for expected in ('persist-credentials: false','ref: ${{ github.sha }}','github.workflow_sha == github.sha',"github.event.deleted == false && github.event.forced == false","github.actor_id == '30860798'","github.repository_id == '359770628'","github.ref == 'refs/heads/codex/native-file-db-oracle-reviewed'"):
                self.assertIn(expected,block)
            self.assertLess(block.index('scripts/native_1c_db_oracle_ci_policy.py bind'),block.index('GHCR_TOKEN:'))
        self.assertNotIn('packages: write',workflow);self.assertNotIn('contents: write',workflow)

    def test_closed_route_admission_and_exhaustive_new_verdict(self):
        class PolicyError(ValueError):pass
        env={'PolicyError':PolicyError};exec(marker('eligibility','ROUTE ADMISSION'),env)
        for route in ROUTES:self.assertEqual(env['admitted_route'](route),route)
        for invalid in (None,True,'','catalog-description-rows-v2','foreign'):
            with self.assertRaises(PolicyError):env['admitted_route'](invalid)
        env={};exec(marker('verdict','ROUTE VERDICT'),env)
        for statuses in itertools.product(('success','failure','cancelled','skipped'),repeat=4):
            expected='success' if statuses==('skipped','skipped','success','success') else 'failure'
            self.assertEqual(env['selected_native_result'](ROUTE,*statuses),expected)
        for route in ROUTES[1:]:self.assertEqual(env['selected_native_result'](route,'skipped','skipped','success','success'),'success')
        self.assertEqual(env['selected_native_result']('foreign','skipped','skipped','success','success'),'failure')

    def test_exact_artifact_members_handoff_order_and_output_flags(self):
        a=old.workflow_job('native_codec_a');b=old.workflow_job('native_codec_b')
        self.assertIn('description_rows_sha256: ${{ steps.native.outputs.description_rows_sha256 }}',a)
        self.assertLess(b.index('--validate-description-rows8'),b.index('GHCR_TOKEN:'))
        self.assertIn('needs: [eligibility, native_codec_a]',b)
        for key in ('DESCRIPTION_ROWS8_SHA256','DESCRIPTION_ROWS8_RUN_ID','DESCRIPTION_ROWS8_RUN_ATTEMPT'):self.assertEqual(b.count(key+':'),2)
        self.assertIn('DESCRIPTION_ROWS8_SHA256: ${{ needs.native_codec_a.outputs.description_rows_sha256 }}',b)
        self.assertIn('artifact-ids: ${{ needs.native_codec_a.outputs.artifact_id }}',b);self.assertIn('digest-mismatch: error',b)
        for block,number in ((a,'8'),(b,'17')):
            self.assertIn("&& 'description_rows"+number+".json'",block)
            self.assertIn("&& 'description-rows' ||",block)
            self.assertIn("if: always() && steps.native.outputs.report_ready == 'true'",block)
        self.assertIn("if: always() && steps.native.outputs.aggregate_ready == 'true'",b)
        self.assertIn("}}-aggregate.json",b)
        handoff=next(s for s in steps('native_codec_b') if '--validate-description-rows8' in s)
        self.assertNotIn('GHCR_TOKEN',handoff);self.assertNotIn('GHCR_USER',handoff)

    def test_actual_bash_dispatch_preserves_new_and_old_case_paths(self):
        for route in ROUTES[1:]:
            for job,number,letter in (('native_codec_a','8','a'),('native_codec_b','17','b')):
                script=rendered(command(job,'--execute-approved-image'),route)
                run=dispatch(script)
                self.assertEqual(run.returncode,0,run.stderr)
                if route==ROUTE:expected='--catalog-description-rows description'+number+' --output native-db-oracle/description_rows'+number+'.json'
                elif route=='catalog-description-measurement-v1':expected='--catalog-description description'+number+' --output native-db-oracle/description'+number+'.json'
                else:
                    kind='rows' if route=='catalog-reference-rows-v1' else 'codec'
                    expected='--catalog-reference-'+kind+' distinct_'+letter+' --output native-db-oracle/'+kind+'_distinct_'+letter+'.json'
                self.assertEqual(run.stdout.strip(),'scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle '+expected)
            script=rendered(command('native_codec_b','--validate-description-rows8'),route)
            run=dispatch(script)
            expected='description-rows8' if route==ROUTE else 'description8' if route=='catalog-description-measurement-v1' else ('rows-a' if route=='catalog-reference-rows-v1' else 'codec-a')
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stdout.strip(),'scripts/native_1c_db_oracle.py --validate-'+expected)

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
        with mock.patch(__name__+'.bash_executable',return_value='/verified/bash'), \
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

if __name__=='__main__':unittest.main()
