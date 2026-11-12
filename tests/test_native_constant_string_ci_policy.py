"""Offline exact reviewed-push admission; no credentials or native execution."""
from copy import deepcopy
import contextlib
import io
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import native_1c_constant_string_ci_policy as route
from test_native_1c_ci_policy import fixtures, MERGE

ROOT = Path(__file__).resolve().parents[1]


def accepted():
    event, context = fixtures('push')
    event.update(ref=route.REF, forced=False)
    context.update(GITHUB_REF=route.REF, GITHUB_REF_TYPE='branch', GITHUB_HEAD_REF='',
                   GITHUB_WORKFLOW_REF=f'{route.policy.REPOSITORY}/{route.WORKFLOW}@{route.REF}',
                   GITHUB_WORKFLOW_SHA=MERGE)
    return event, context


class ConstantStringPushPolicyTests(unittest.TestCase):
    def test_exact_reviewed_push_and_binding(self):
        event, context = accepted()
        route.validate_admission(event, context)
        route.validate_binding(event, context, MERGE, '')

    def test_every_context_identity_is_required(self):
        event, context = accepted()
        for key in ('GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_REPOSITORY_OWNER',
                    'GITHUB_REPOSITORY_OWNER_ID','GITHUB_ACTOR','GITHUB_ACTOR_ID',
                    'NATIVE_TRIGGERING_ACTOR'):
            for bad in ('other', None):
                with self.subTest(key=key,bad=bad), self.assertRaises(route.policy.PolicyError):
                    route.validate_admission(event,dict(context,**{key:bad}))

    def test_no_event_or_ref_fallback(self):
        event, context = accepted()
        for name in ('pull_request','pull_request_target','workflow_dispatch','workflow_call','schedule'):
            with self.subTest(event=name), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(event,dict(context,GITHUB_EVENT_NAME=name))
        for ref in ('refs/heads/main',route.policy.ASYNC_REVIEWED_REF,
                    route.REF+'-other','refs/tags/'+route.BRANCH):
            with self.subTest(ref=ref), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(dict(event,ref=ref),dict(context,GITHUB_REF=ref))

    def test_push_fields_are_exact_and_not_truthy(self):
        event, context = accepted()
        for key in ('deleted','forced'):
            for value in (True,0,'false',None):
                with self.subTest(key=key,value=value), self.assertRaises(route.policy.PolicyError):
                    route.validate_admission(dict(event,**{key:value}),context)
        for key,value in (('GITHUB_REF_TYPE','tag'),('GITHUB_BASE_REF','main'),('GITHUB_HEAD_REF',route.BRANCH)):
            with self.subTest(key=key), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(event,dict(context,**{key:value}))
        with self.assertRaises(route.policy.PolicyError):
            route.validate_admission(dict(event,ref=route.REF+'x'),context)

    def test_repository_sender_and_owner_objects_are_exact(self):
        event, context = accepted()
        paths=[('repository','full_name'),('repository','id'),('repository','fork'),
               ('repository','owner','login'),('repository','owner','id'),
               ('repository','owner','type'),('sender','login'),('sender','id'),('sender','type')]
        for path in paths:
            changed=deepcopy(event);node=changed
            for part in path[:-1]:node=node[part]
            node[path[-1]]=True if path[-1] in ('id','fork') else 'other'
            with self.subTest(path=path), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(changed,context)

    def test_exact_revision_and_workflow_witnesses(self):
        event, context = accepted()
        for bad in ('0'*40,'x'*40,'a'*39,None):
            changed=deepcopy(event);changed['after']=bad;changed['head_commit']['id']=bad
            with self.subTest(bad=bad), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(changed,dict(context,GITHUB_SHA=bad,GITHUB_WORKFLOW_SHA=bad))
        for target in ('after','head_commit'):
            changed=deepcopy(event)
            if target=='after':changed['after']='4'*40
            else:changed['head_commit']['id']='4'*40
            with self.subTest(target=target), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(changed,context)
        for key in ('GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW_SHA'):
            with self.subTest(key=key), self.assertRaises(route.policy.PolicyError):
                route.validate_admission(event,dict(context,**{key:'other'}))

    def test_checkout_revision_and_tracked_or_untracked_drift_refused(self):
        event, context = accepted()
        for commit,status in (('4'*40,''),(MERGE,' M scripts/probe.py'),(MERGE,'?? extra')):
            with self.subTest(commit=commit,status=status), self.assertRaises(route.policy.PolicyError):
                route.validate_binding(event,context,commit,status)

    def test_invalid_event_does_not_run_git_or_print_payload(self):
        event,context=accepted();event['forced']=True
        with mock.patch.object(route.policy,'read_event',return_value=event), \
             mock.patch.object(route,'git') as git, contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(route.main(['bind'],context),1)
        git.assert_not_called();self.assertEqual(output.getvalue(),'Native constant string blocked: push_ref_or_mode_not_approved\n')

    def test_only_bind_command_is_supported(self):
        for arguments in ([],['admit'],['dispatch'],['bind','extra']):
            with mock.patch.object(route.policy,'read_event') as read, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(route.main(arguments,{}),1)
            read.assert_not_called()

    def test_main_requires_immutable_commit_and_clean_all_files(self):
        event,context=accepted()
        with mock.patch.object(route.policy,'read_event',return_value=event), \
             mock.patch.object(route,'git',side_effect=[MERGE,'']) as git, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(route.main(['bind'],context),0)
        self.assertEqual(git.call_args_list,[mock.call('rev-parse','HEAD^{commit}'),mock.call('status','--porcelain','--untracked-files=all')])

    def test_git_evidence_is_bounded_and_uses_no_replace_objects(self):
        result=subprocess.CompletedProcess([],0,b'a'*40+b'\n',b'')
        with mock.patch.object(route.subprocess,'run',return_value=result) as run:
            self.assertEqual(route.git('rev-parse','HEAD^{commit}'),'a'*40)
        self.assertEqual(run.call_args.args[0],['git','--no-replace-objects','rev-parse','HEAD^{commit}'])
        self.assertEqual(run.call_args.kwargs['timeout'],30)
        for outcome in (subprocess.CompletedProcess([],1,b'',b''),subprocess.CompletedProcess([],0,b'',b'warning'),
                        subprocess.CompletedProcess([],0,b'a'*65537,b''),subprocess.CompletedProcess([],0,b'\xff',b'')):
            with mock.patch.object(route.subprocess,'run',return_value=outcome),self.assertRaises(route.policy.PolicyError):
                route.git('status')
        for error in (OSError('private path'),subprocess.TimeoutExpired('git',30)):
            with mock.patch.object(route.subprocess,'run',side_effect=error),self.assertRaises(route.policy.PolicyError):
                route.git('status')

    def test_workflow_exact_push_only_and_before_credentials(self):
        source=(ROOT/route.WORKFLOW).read_text(encoding='utf-8')
        trigger=source.split('on:\n',1)[1].split('permissions:',1)[0]
        self.assertEqual(trigger,'  push:\n    branches: [codex/native-constant-string-reviewed]\n')
        for forbidden in ('pull_request_target:','workflow_dispatch:','workflow_call:','schedule:', 'secrets: inherit'):
            self.assertNotIn(forbidden,source)
        self.assertIn('permissions: {}',source)
        self.assertIn('      contents: read\n      packages: read',source)
        self.assertIn('ref: ${{ github.sha }}',source)
        self.assertIn('persist-credentials: false',source)
        self.assertIn('submodules: false',source);self.assertIn('lfs: false',source)
        bind=source.index('python3 -I -B scripts/native_1c_constant_string_ci_policy.py bind')
        self.assertLess(bind,source.index('uses: actions/setup-python@'))
        self.assertLess(bind,source.index('GHCR_TOKEN'))
        for use in ('actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
                    'actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97',
                    'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'):
            self.assertIn(use,source)
        self.assertIn("steps.constant_string.outputs.constant_string_outputs_ready == 'true'",source)


if __name__=='__main__':unittest.main()
