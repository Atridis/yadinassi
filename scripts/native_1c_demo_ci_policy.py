"""Owner-dispatched exact-source admission for the separate demo profile."""
# BEGIN DEMO ADMISSION
import json
import os
import re
import sys


def admission(event, context):
    def need(ok):
        if not ok:
            raise ValueError('demo_admission_denied')
    def owner(value):
        return (type(value) is dict and value.get('login') == 'Atridis'
                and type(value.get('id')) is int and value['id'] == 30860798
                and value.get('type') == 'User')
    need(type(event) is dict and type(context) is dict)
    expected = dict(GITHUB_REPOSITORY='Atridis/yadinassi', GITHUB_REPOSITORY_ID='359770628',
                    GITHUB_REPOSITORY_OWNER='Atridis', GITHUB_REPOSITORY_OWNER_ID='30860798',
                    GITHUB_ACTOR='Atridis', GITHUB_ACTOR_ID='30860798',
                    NATIVE_TRIGGERING_ACTOR='Atridis', GITHUB_EVENT_NAME='workflow_dispatch',
                    GITHUB_REF_TYPE='branch', GITHUB_BASE_REF='', GITHUB_HEAD_REF='')
    need(all(context.get(key) == value for key, value in expected.items()))
    repo = event.get('repository')
    need(type(repo) is dict and repo.get('full_name') == 'Atridis/yadinassi'
         and type(repo.get('id')) is int and repo['id'] == 359770628
         and repo.get('fork') is False and owner(repo.get('owner')) and owner(event.get('sender')))
    sha, ref = context.get('GITHUB_SHA'), context.get('GITHUB_REF')
    need(type(sha) is str and re.fullmatch('[0-9a-f]{40}', sha) is not None and sha != '0' * 40)
    need(type(ref) is str and re.fullmatch(r'refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]{0,239}', ref) is not None
         and '..' not in ref and '//' not in ref and not ref.endswith(('/', '.'))
         and all(not part.startswith('.') and not part.endswith('.lock') for part in ref.split('/')))
    need(event.get('ref') in (ref, ref.removeprefix('refs/heads/')))
    need(context.get('GITHUB_WORKFLOW_SHA') == sha and context.get('GITHUB_WORKFLOW_REF') ==
         'Atridis/yadinassi/.github/workflows/native-1c-demo-designer.yml@' + ref)
    need(event.get('inputs') == {'reviewed_sha': sha})
    need(json.loads(context.get('NATIVE_DISPATCH_INPUTS', 'null'), object_pairs_hook=unique) == {'reviewed_sha': sha})
    return sha


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('demo_admission_denied')
        value[key] = item
    return value


def check_environment():
    with open(os.environ['GITHUB_EVENT_PATH'], 'rb') as source:
        raw = source.read(8 * 1048576 + 1)
    if len(raw) > 8 * 1048576:
        raise ValueError('demo_admission_denied')
    return admission(json.loads(raw, object_pairs_hook=unique), dict(os.environ))
# END DEMO ADMISSION


def main():
    import subprocess
    try:
        sha = check_environment()
        def git(*args):
            return subprocess.check_output(['git', *args], stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        if git('rev-parse', 'HEAD') != sha or git('status', '--porcelain', '--untracked-files=all'):
            raise ValueError('demo_binding_denied')
    except Exception:
        print('Demo source binding denied.', file=sys.stderr)
        return 1
    print('Demo source binding accepted.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
