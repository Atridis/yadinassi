"""Same reviewed-source privilege boundary; finite artifact only, offline tests."""
import itertools
import os
from pathlib import Path
import re
import tempfile
import subprocess
import shutil
import unittest
from unittest import mock
import test_native_1c_db_oracle_ci_policy as existing
import test_native_params_slot_workflow as routes
import test_metadata_catalog_runner as fixtures
import native_1c_metadata_catalog_oracle as host
from snapshots import OracleError

ROUTE='metadata-catalog-applied-view-v1'


class MetadataWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'git is required for the real autocrlf checkout')
    def test_trusted_probe_retains_exact_bytes_in_real_autocrlf_checkout(self):
        root=Path(__file__).resolve().parents[1]
        relative=Path('scripts/native_1c_db_oracle/modules/MetadataCatalogProbe.bsl')
        expected=(root/relative).read_bytes()
        self.assertNotIn(b'\r',expected)
        env={key:value for key,value in os.environ.items()
             if key.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP')}
        env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        with tempfile.TemporaryDirectory(prefix='metadata-lf-') as work:
            source=Path(work)/'source';source.mkdir();checkout=Path(work)/'checkout'
            (source/relative).parent.mkdir(parents=True)
            (source/relative).write_bytes(expected)
            (source/'.gitattributes').write_bytes((root/'.gitattributes').read_bytes())
            def git(*args):
                result=subprocess.run(['git',*args],cwd=source,env=env,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
                return result.stdout
            git('init','--template=')
            git('-c','core.autocrlf=false','add','.')
            git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                '-c','commit.gpgsign=false','commit','-m','Synthetic autocrlf fixture')
            git('clone','--no-hardlinks','--config','core.autocrlf=true',str(source),str(checkout))
            self.assertEqual((checkout/relative).read_bytes(),expected)

    def test_only_selected_route_and_exhaustive_terminal_verdict(self):
        namespace={'PolicyError':ValueError}
        exec(routes.marker('eligibility','ROUTE ADMISSION'),namespace)
        exec(routes.marker('verdict','ROUTE VERDICT'),namespace)
        self.assertEqual(namespace['admitted_route'](ROUTE),ROUTE)
        for value in (None,True,'metadata','metadata-catalog-applied-view-v2',''):
            with self.assertRaises(ValueError):namespace['admitted_route'](value)
        for states in itertools.product(('success','failure','cancelled','skipped','timed_out',None),repeat=5):
            expected='success' if states==('skipped','skipped','skipped','skipped','success') else 'failure'
            self.assertEqual(namespace['selected_native_result'](ROUTE,*states),expected)
        for old_route in ('catalog-reference-identity-v1','catalog-zero-code-rows-v1'):
            states=('success','success','skipped','skipped') if 'identity' in old_route else ('skipped','skipped','success','success')
            for extra in ('success','failure',None):
                self.assertEqual(namespace['selected_native_result'](old_route,*states,extra),'failure')
    def test_exact_security_header_token_order_and_artifact(self):
        block=existing.workflow_job('native_metadata')
        reference=existing.workflow_job('native_reference_a')
        expected=reference.split('    outputs:\n')[0].replace('Native 1C reference identity case A','Native 1C Metadata Catalogs applied-view measurement').replace('catalog-reference-identity-v1',ROUTE)
        self.assertEqual(block.split('    steps:\n')[0],expected)
        self.assertEqual(re.findall(r'uses: ([^\n]+)',block),[
            'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7',
            'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7'])
        self.assertIn('ref: ${{ github.sha }}',block)
        for line in ('persist-credentials: false','fetch-depth: 1','submodules: false','lfs: false'):
            self.assertIn(line,block)
        self.assertEqual(block.count('GHCR_TOKEN:'),1)
        self.assertEqual(block.count('GHCR_USER:'),1)
        self.assertLess(block.index('scripts/native_1c_db_oracle_ci_policy.py bind'),block.index('GHCR_TOKEN:'))
        self.assertIn('run: python3 scripts/native_1c_metadata_catalog_oracle.py --run --ci-report',block)
        self.assertIn("if: always() && steps.native.outputs.report_ready == 'true'",block)
        self.assertEqual(re.findall(r'^          path: (.*)$',block,re.M),['native-db-oracle/metadata-catalogs.json'])
        for forbidden in ('workflow_dispatch','pull_request_target','secrets.','download-artifact','*.json','*.log',': write'):
            self.assertNotIn(forbidden,block)
    @unittest.skipUnless(os.name=='posix' and hasattr(os,'O_NOFOLLOW'),'POSIX descriptor export')
    def test_export_exact_exclusive_nofollow_and_readiness(self):
        for attack in ('none','existing','symlink-parent','symlink-file','foreign-file'):
            with self.subTest(attack=attack),tempfile.TemporaryDirectory() as work:
                root=Path(work)/'repo';root.mkdir();outside=Path(work)/'outside';outside.mkdir()
                target=root/host.OUTPUT;info=root.stat()
                if attack=='symlink-parent':target.parent.symlink_to(outside,target_is_directory=True)
                elif attack!='none':
                    target.parent.mkdir()
                    if attack=='existing':target.write_bytes(b'old')
                    elif attack=='symlink-file':target.symlink_to(outside/'report')
                    else:(target.parent/'foreign').write_bytes(b'x')
                with mock.patch.object(host,'ROOT',root):
                    if attack=='none':
                        host.export_report(b'{}',(info.st_dev,info.st_ino));self.assertEqual(target.read_bytes(),b'{}\n')
                    else:
                        with self.assertRaises((OracleError,OSError)):host.export_report(b'{}',(info.st_dev,info.st_ino))
                self.assertEqual(list(outside.iterdir()),[])
    def test_failed_export_never_announces_readiness(self):
        with tempfile.TemporaryDirectory() as work:
            output=Path(work)/'github-output'
            value=fixtures.report();value['lifecycle']['accepted']=True
            with mock.patch.object(host,'run_oracle',return_value=value),mock.patch.object(host,'export_report',side_effect=OracleError('stale_evidence')),mock.patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}):
                self.assertEqual(host.main(['--run','--ci-report']),1)
            self.assertFalse(output.exists())
    def test_validated_failure_export_is_ready_but_not_success(self):
        with tempfile.TemporaryDirectory() as work:
            output=Path(work)/'github-output';value=fixtures.report();value['lifecycle']['accepted']=False
            with mock.patch.object(host,'run_oracle',return_value=value),mock.patch.object(host,'export_report') as exported,mock.patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}):
                self.assertEqual(host.main(['--run','--ci-report']),1)
            exported.assert_called_once();self.assertEqual(output.read_text(),'report_ready=true\n')
