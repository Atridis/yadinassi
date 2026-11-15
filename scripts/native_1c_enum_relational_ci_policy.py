"""Exact owner-reviewed push admission for the enum relational observation packet.

This is a separate allowlist, not a translation into the general native route.
It grants no PR, main, dispatch or reusable-workflow fallback. Source and owner
binding is checked before acquisition credentials are supplied.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys

_spec = importlib.util.spec_from_file_location(
    '_enum_relational_shared_policy', Path(__file__).with_name('native_1c_ci_policy.py'))
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)

BRANCH = 'codex/db-enum-relational-reports'
REF = 'refs/heads/' + BRANCH
WORKFLOW = '.github/workflows/native-1c-enum-relational.yml'
require = policy.require


def validate_admission(event, context):
    require(type(event) is dict and type(context) is dict, 'event_invalid')
    expected = {
        'GITHUB_REPOSITORY': policy.REPOSITORY,
        'GITHUB_REPOSITORY_ID': str(policy.REPOSITORY_ID),
        'GITHUB_REPOSITORY_OWNER': policy.OWNER,
        'GITHUB_REPOSITORY_OWNER_ID': str(policy.OWNER_ID),
        'GITHUB_ACTOR': policy.OWNER,
        'GITHUB_ACTOR_ID': str(policy.OWNER_ID),
        'NATIVE_TRIGGERING_ACTOR': policy.OWNER,
        'GITHUB_EVENT_NAME': 'push',
        'GITHUB_REF': REF,
        'GITHUB_REF_TYPE': 'branch',
        'GITHUB_BASE_REF': '',
        'GITHUB_HEAD_REF': '',
    }
    require(all(context.get(key) == value for key, value in expected.items()),
            'push_context_not_approved')
    require(policy.trusted_repository(event.get('repository')), 'repository_not_approved')
    require(policy.owner_identity(event.get('sender')), 'sender_not_approved')
    require(event.get('ref') == REF and event.get('deleted') is False
            and event.get('forced') is False, 'push_ref_or_mode_not_approved')
    sha = context.get('GITHUB_SHA')
    require(policy.is_sha(sha) and event.get('after') == sha
            and policy.object_value(event.get('head_commit')).get('id') == sha,
            'push_revision_mismatch')
    require(context.get('GITHUB_WORKFLOW_REF') == f'{policy.REPOSITORY}/{WORKFLOW}@{REF}'
            and context.get('GITHUB_WORKFLOW_SHA') == sha, 'workflow_revision_mismatch')


def validate_binding(event, context, commit, worktree_status):
    validate_admission(event, context)
    require(policy.is_sha(commit) and commit == context['GITHUB_SHA'],
            'checkout_revision_mismatch')
    require(worktree_status == '', 'checkout_not_clean')


def git(*arguments):
    try:
        result = subprocess.run(['git', '--no-replace-objects', *arguments],
                                check=False, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30)
        require(result.returncode == 0 and not result.stderr and len(result.stdout) <= 65536,
                'checkout_evidence_unavailable')
        return result.stdout.decode('ascii').strip()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise policy.PolicyError('checkout_evidence_unavailable') from None


def main(arguments=None, context=None):
    if arguments is None:
        arguments = sys.argv[1:]
    if arguments != ['bind']:
        print('Native enum relational blocked: command_not_approved', file=sys.stderr)
        return 1
    if context is None:
        import os
        context = dict(os.environ)
    try:
        event = policy.read_event(context)
        # Do not run git or any acquisition step for a rejected event.
        validate_admission(event, context)
        validate_binding(event, context, git('rev-parse', 'HEAD^{commit}'),
                         git('status', '--porcelain', '--untracked-files=all'))
    except policy.PolicyError as error:
        print(f'Native enum relational blocked: {error}', file=sys.stderr)
        return 1
    print('Native enum relational exact push binding verified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
