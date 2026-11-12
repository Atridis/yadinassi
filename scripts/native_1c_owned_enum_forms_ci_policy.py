"""Finite same-repository PR route for configuration-owned enum form acquisition.

The shared owner and exact merge-parent policy remains unchanged. This separate
route adds one head branch and no push/dispatch or alternate-ref fallback.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys

_spec=importlib.util.spec_from_file_location('_owned_enum_forms_shared_policy',Path(__file__).with_name('native_1c_ci_policy.py'))
policy=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)
BRANCH='codex/native-inventory-enum-forms-acquisition'
WORKFLOW='.github/workflows/native-1c-owned-enum-forms.yml'
require=policy.require


def validate_admission(event,context):
    route=policy.validate_admission(event,context)
    require(route=='pull_request','owned_forms_event_not_approved')
    require(event['pull_request']['head'].get('ref')==BRANCH
            and context.get('GITHUB_HEAD_REF')==BRANCH,'owned_forms_branch_not_approved')
    return route


def validate_binding(event,context,commit,parents,status):
    validate_admission(event,context)
    policy.validate_binding(event,context,commit,parents,status)


def git(*arguments):
    try:
        result=subprocess.run(['git','--no-replace-objects',*arguments],check=False,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        require(result.returncode==0 and not result.stderr and len(result.stdout)<=65536,'checkout_evidence_unavailable')
        return result.stdout.decode('ascii').strip()
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise policy.PolicyError('checkout_evidence_unavailable') from None


def main(arguments=None,context=None):
    if arguments is None:arguments=sys.argv[1:]
    if arguments!=['bind']:
        print('Native owned enum forms blocked: command_not_approved',file=sys.stderr);return 1
    if context is None:
        import os
        context=dict(os.environ)
    try:
        event=policy.read_event(context)
        validate_admission(event,context)
        validate_binding(event,context,git('rev-parse','HEAD^{commit}'),
                         git('show','-s','--format=%P','HEAD').split(),
                         git('status','--porcelain','--untracked-files=all'))
    except policy.PolicyError as error:
        print(f'Native owned enum forms blocked: {error}',file=sys.stderr);return 1
    print('Native owned enum forms exact PR merge binding verified.');return 0


if __name__=='__main__':raise SystemExit(main())
