"""Offline finite PR routing; no credentials, native process or GitHub calls."""
from copy import deepcopy
import contextlib
import io
from pathlib import Path
import re
import unittest
from unittest import mock
import native_1c_owned_enum_forms_ci_policy as route
from test_native_1c_ci_policy import fixtures, BASE, HEAD, MERGE
ROOT=Path(__file__).resolve().parents[1]


def accepted():
    event,context=fixtures()
    event['pull_request']['head']['ref']=route.BRANCH
    context['GITHUB_HEAD_REF']=route.BRANCH
    return event,context


class OwnedEnumFormsPolicyTests(unittest.TestCase):
    def test_exact_owner_pr_and_merge_binding(self):
        event,context=accepted()
        self.assertEqual(route.validate_admission(event,context),'pull_request')
        route.validate_binding(event,context,MERGE,[BASE,HEAD],'')

    def test_other_branch_and_context_mismatch_refused(self):
        event,context=accepted()
        for ref in ('main',route.BRANCH+'-other','codex/configuration-form-results',None):
            changed=deepcopy(event);changed['pull_request']['head']['ref']=ref
            with self.assertRaises(route.policy.PolicyError):route.validate_admission(changed,context)
            with self.assertRaises(route.policy.PolicyError):route.validate_admission(event,dict(context,GITHUB_HEAD_REF=ref))

    def test_no_push_dispatch_or_target_route(self):
        for name in ('push','workflow_dispatch','pull_request_target','workflow_call','schedule'):
            event,context=fixtures(name)
            with self.subTest(name=name),self.assertRaises(route.policy.PolicyError):route.validate_admission(event,context)

    def test_owner_identity_context_required(self):
        event,context=accepted()
        for key in ('GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_REPOSITORY_OWNER','GITHUB_REPOSITORY_OWNER_ID','GITHUB_ACTOR','GITHUB_ACTOR_ID','NATIVE_TRIGGERING_ACTOR'):
            with self.subTest(key=key),self.assertRaises(route.policy.PolicyError):route.validate_admission(event,dict(context,**{key:'other'}))

    def test_fork_and_different_pr_author_refused(self):
        event,context=accepted()
        for side in ('head','base'):
            changed=deepcopy(event);changed['pull_request'][side]['repo']['fork']=True
            with self.assertRaises(route.policy.PolicyError):route.validate_admission(changed,context)
        changed=deepcopy(event);changed['pull_request']['user']['id']=1
        with self.assertRaises(route.policy.PolicyError):route.validate_admission(changed,context)

    def test_dirty_wrong_sha_and_wrong_parent_order_refused(self):
        event,context=accepted()
        for sha,parents,status in ((HEAD,[BASE,HEAD],''),(MERGE,[HEAD,BASE],''),(MERGE,[BASE],''),(MERGE,[BASE,HEAD],'?? untracked')):
            with self.subTest(sha=sha,parents=parents,status=status),self.assertRaises(route.policy.PolicyError):route.validate_binding(event,context,sha,parents,status)

    def test_closed_merged_and_wrong_action_refused(self):
        event,context=accepted()
        for key,value in (('state','closed'),('merged',True)):
            changed=deepcopy(event);changed['pull_request'][key]=value
            with self.assertRaises(route.policy.PolicyError):route.validate_admission(changed,context)
        with self.assertRaises(route.policy.PolicyError):route.validate_admission(dict(event,action='edited'),context)

    def test_rejected_event_does_not_read_checkout(self):
        event,context=accepted();event['pull_request']['head']['ref']='unapproved'
        with mock.patch.object(route.policy,'read_event',return_value=event),mock.patch.object(route,'git') as git,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(route.main(['bind'],context),1);git.assert_not_called()

    def test_successful_main_binds_exact_three_checkout_facts(self):
        event,context=accepted()
        with mock.patch.object(route.policy,'read_event',return_value=event),mock.patch.object(route,'git',side_effect=[MERGE,BASE+' '+HEAD,'']) as git,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(route.main(['bind'],context),0)
        self.assertEqual(git.call_count,3)

    def test_workflow_exact_branch_and_no_dispatch(self):
        source=(ROOT/route.WORKFLOW).read_text()
        self.assertIn("github.event.pull_request.head.ref == '"+route.BRANCH+"'",source)
        self.assertNotIn('workflow_dispatch:',source);self.assertNotIn('pull_request_target:',source)
        self.assertNotIn('\n  push:',source)
        self.assertIn('cancel-in-progress: false',source)
        self.assertIn('types: [opened, synchronize, reopened]',source)

    def test_workflow_pinned_permissions_and_credentials_after_binding(self):
        source=(ROOT/route.WORKFLOW).read_text()
        self.assertIn('permissions: {}',source);self.assertIn('contents: read',source);self.assertIn('packages: read',source)
        self.assertNotIn('contents: write',source);self.assertNotIn('packages: write',source)
        self.assertIn('persist-credentials: false',source);self.assertIn('fetch-depth: 2',source)
        self.assertIn('ref: ${{ github.sha }}',source)
        self.assertLess(source.index('native_1c_owned_enum_forms_ci_policy.py bind'),source.index('GHCR_TOKEN:'))
        refs=re.findall(r'uses: ([^\s]+)',source)
        self.assertEqual(len(refs),4)
        self.assertTrue(all(re.fullmatch(r'actions/[a-z-]+@[0-9a-f]{40}',ref) for ref in refs))

    def test_workflow_output_requires_verified_profile_signal(self):
        source=(ROOT/route.WORKFLOW).read_text()
        self.assertIn("steps.results.outputs.owned_enum_forms_outputs_ready == 'true'",source)
        self.assertIn('scripts/native_1c_owned_enum_forms_profile.py --execute-approved-image --export-native-outputs',source)
        self.assertIn('native-smoke/owned-enum-forms-outputs/owned-enum-forms.out',source)
        self.assertIn('native-smoke/owned-enum-forms-outputs/provenance.json',source)
        self.assertNotIn('*.log',source)
