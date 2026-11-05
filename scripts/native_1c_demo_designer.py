"""Separate, archive-bound DESIGNER-only demo acquisition. No ENTERPRISE route."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_cf_fixture as fixture

SCHEMA = 'native-demo-designer-v1'
VERSION = '8.3.27.1508'
IMAGE = 'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728'
ONEC = '/opt/1cv8t/x86_64/' + VERSION + '/1cv8t'
CHECK_FLAGS = ('-ConfigLogIntegrity', '-IncorrectReferences', '-ThinClient', '-Server',
               '-ThickClientManagedApplication', '-HandlersExistence', '-ExtendedModulesCheck')
INPUTS = ('scripts/native_1c_demo_designer.py', 'scripts/native_1c_demo_designer.sh',
          'scripts/demo_cf_fixture.py', 'tests/fixtures/demo_cf/original.zip',
          'tests/fixtures/demo_cf/manifest.json')
PHASES = ('inputs', 'create', 'load', 'check', 'update', 'redump', 'witness', 'complete')
FAILURES = ('none', 'invalid_input', 'process_failed', 'timeout', 'invalid_result', 'witness_mismatch')

class DemoError(ValueError):
    pass


def require(condition, reason='invalid_input'):
    if not condition:
        raise DemoError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=1048576):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit)
    with path.open('rb') as source:
        data = source.read(limit + 1)
    require(len(data) <= limit)
    return data


def inventory(root):
    return {name: digest(read_regular(root / name)) for name in INPUTS}


def stage_inputs(root, target):
    require(not target.exists() and not target.is_symlink())
    hashes = inventory(root)
    target.mkdir(mode=0o755)
    for name in INPUTS:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(read_regular(root / name))
        path.chmod(0o644)
    for path in target.rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
    require(inventory(target) == hashes)
    return hashes


def dump_files(root):
    require(root.is_dir() and not root.is_symlink())
    result, pending, count, total = {}, [root], 0, 0
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                count += 1
                require(count <= 512)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    pending.append(Path(entry.path))
                else:
                    path = Path(entry.path)
                    raw = read_regular(path)
                    total += len(raw)
                    require(total <= 8 * 1048576 and len(result) < 256)
                    result[path.relative_to(root).as_posix()] = raw
    return result


def xml_signature(raw):
    # Conservative: preserve QName prefix bindings, significant leaf text and all
    # attributes. Prefix/default/schema rewrites need separate native evidence.
    try:
        text = raw.decode('utf-8-sig')
        require('\x00' not in text and '<!DOCTYPE' not in text.upper()
                and '<!ENTITY' not in text.upper(), 'witness_mismatch')
        body = re.sub(r'^<\?xml\s+[^?]*\?>', '', text, count=1)
        require('<?' not in body, 'witness_mismatch')
        namespaces = {}
        for _, (prefix, uri) in ET.iterparse(io.StringIO(text), events=('start-ns',)):
            require(prefix not in namespaces or namespaces[prefix] == uri, 'witness_mismatch')
            namespaces[prefix] = uri
        root = ET.fromstring(text)
        def visit(node, depth=0):
            require(depth < 128, 'witness_mismatch')
            value = node.text or ''
            if len(node) and not value.strip(' \t\r\n'):
                value = ''  # indentation between elements only
            return (node.tag, tuple(sorted(node.attrib.items())), value,
                    tuple((visit(child, depth + 1), '' if not (child.tail or '').strip(' \t\r\n')
                           else child.tail) for child in node))
        return tuple(sorted(namespaces.items())), visit(root)
    except (ET.ParseError, RecursionError, UnicodeError, ValueError):
        raise DemoError('witness_mismatch') from None


def redump_mismatches(expected, actual):
    failures = {}
    if set(actual) - {'ConfigDumpInfo.xml'} - set(expected):
        failures['$inventory'] = 'unexpected_file'
    for name, raw in expected.items():
        if name not in actual:
            failures[name] = 'missing_file'
            continue
        try:
            if name.endswith('.bsl'):
                normalize = lambda data: data.decode('utf-8-sig').replace('\r\n', '\n')
                if normalize(raw) != normalize(actual[name]):
                    failures[name] = 'module_changed'
            elif xml_signature(raw) != xml_signature(actual[name]):
                failures[name] = 'metadata_changed'
        except (DemoError, UnicodeError):
            failures[name] = 'invalid_encoding_or_xml'
    return failures


def verify_redump(expected, actual):
    require(not redump_mismatches(expected, actual), 'witness_mismatch')
    return {name: digest(actual[name]) for name in sorted(expected)}


def operations(root):
    db = root / 'db'
    common = ['/AppAutoCheckVersion-', '/DisableStartupDialogs', '/DisableStartupMessages', '/L', 'ru']
    result = [('create', [ONEC, 'CREATEINFOBASE', f'File="{db}";', '/Lru'])]
    for phase, flags in (
        ('load', ['/LoadConfigFromFiles', str(root / 'source')]),
        ('check', ['/CheckConfig', *CHECK_FLAGS]),
        ('update', ['/UpdateDBCfg']),
        ('redump', ['/DumpConfigToFiles', str(root / 'redump'), '-Format', 'Hierarchical'])):
        result.append((phase, [ONEC, 'DESIGNER', '/F', str(db), *common, *flags]))
    return [(phase, command + ['/Out', str(root / (phase + '.log')),
                               '/DumpResult', str(root / (phase + '.result'))])
            for phase, command in result]


def zero_result(path):
    raw = read_regular(path, 128)
    try:
        text = raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig').strip()
    except UnicodeError:
        raise DemoError('invalid_result') from None
    require(text == '0', 'invalid_result')


def native_quiet():
    # Container PID namespace only. Refuse overlap with surviving native children.
    for item in Path('/proc').iterdir():
        if item.name.isdigit():
            try:
                executable = os.readlink(item / 'exe')
            except FileNotFoundError:
                continue
            except PermissionError:
                raise DemoError('process_failed') from None
            require(not Path(executable).name.startswith('1cv8'), 'process_failed')


def native_run(nonce):
    report = dict(schema=SCHEMA, nonce=nonce, status='failed', phase='inputs', failure='invalid_input',
                  archive_sha256=fixture.ARCHIVE_SHA256, input_sha256={}, redump_sha256={}, mismatches={})
    try:
        require(re.fullmatch('[0-9a-f]{32}', nonce) is not None and os.getuid() == 1000)
        report['input_sha256'] = inventory(ROOT)
        root = Path('/tmp/demo-designer')
        root.mkdir(mode=0o700)
        fixture.stage(root / 'source')
        expected = fixture.fixture_files()
        (root / 'redump').mkdir()
        for phase, command in operations(root):
            report['phase'] = phase
            require(not (root / (phase + '.result')).exists())
            # Outer owned-container deadline/removal is the hard process-tree bound.
            code = subprocess.run(['timeout', '--signal=TERM', '--kill-after=5s', '120s', *command],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=135).returncode
            require(code == 0, 'timeout' if code in (124, 137) else 'process_failed')
            native_quiet()
            zero_result(root / (phase + '.result'))
            if phase == 'create':
                require((root / 'db/1Cv8.1CD').is_file(), 'invalid_result')
        report['phase'] = 'witness'
        actual = dump_files(root / 'redump')
        report['mismatches'] = redump_mismatches(expected, actual)
        report['redump_sha256'] = verify_redump(expected, actual)
        require(inventory(ROOT) == report['input_sha256'])
        report.update(status='ok', phase='complete', failure='none')
    except subprocess.TimeoutExpired:
        report['failure'] = 'timeout'
    except Exception as error:
        report['failure'] = str(error) if isinstance(error, DemoError) and str(error) in FAILURES else 'invalid_input'
    print(json.dumps(report, sort_keys=True, separators=(',', ':')))
    return 0 if report['status'] == 'ok' else 1


def container_command(staged, nonce):
    require(staged.is_absolute() and ',' not in str(staged) and re.fullmatch('[0-9a-f]{32}', nonce))
    return ['docker', 'create', '--name', 'onec-demo-designer-' + nonce,
            '--label', 'org.yadinassi.native.invocation=' + nonce, '--hostname', 'onec-smoke',
            '--pull', 'never', '--platform', 'linux/amd64', '--network', 'none',
            '--user', '1000:1000', '--read-only', '--no-healthcheck', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--pids-limit', '256',
            '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
            '--ulimit', 'nofile=1024:1024', '--ulimit', 'fsize=67108864:67108864',
            '--ipc', 'private', '--shm-size', '128m', '--log-driver', 'none',
            '--stop-timeout', '10', '--init',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777',
            '--mount', f'type=bind,src={staged},dst=/smoke,readonly',
            '--workdir', '/tmp', '--entrypoint', '/usr/bin/env', IMAGE, '-i',
            'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME=/tmp/home', 'XDG_RUNTIME_DIR=/tmp/runtime', 'DISPLAY=:99',
            'LANG=ru_RU.UTF-8', 'LC_ALL=ru_RU.UTF-8', 'TZ=Etc/UTC',
            '/bin/bash', '--noprofile', '--norc', '/smoke/scripts/native_1c_demo_designer.sh', nonce]


def validate_report(raw, nonce, hashes):
    require(type(raw) is bytes and len(raw) <= 16384, 'invalid_result')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'invalid_result')
            value[key] = item
        return value
    try:
        report = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise DemoError('invalid_result') from None
    require(type(report) is dict and set(report) == {'schema', 'nonce', 'status', 'phase', 'failure',
            'archive_sha256', 'input_sha256', 'redump_sha256', 'mismatches'}, 'invalid_result')
    require(report['schema'] == SCHEMA and report['nonce'] == nonce
            and report['archive_sha256'] == fixture.ARCHIVE_SHA256
            and report['input_sha256'] == hashes and report['phase'] in PHASES
            and report['failure'] in FAILURES and report['status'] in ('ok', 'failed'), 'invalid_result')
    failures = report['mismatches']
    require(type(failures) is dict and set(failures) <= set(fixture.fixture_files()) | {'$inventory'}
            and all(type(value) is str and value in ('unexpected_file', 'missing_file', 'module_changed',
                    'metadata_changed', 'invalid_encoding_or_xml') for value in failures.values()), 'invalid_result')
    witness = report['redump_sha256']
    require(type(witness) is dict, 'invalid_result')
    require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) for value in witness.values()), 'invalid_result')
    if report['status'] == 'ok':
        require(not failures and report['phase'] == 'complete' and report['failure'] == 'none'
                and set(witness) == set(fixture.fixture_files()), 'invalid_result')
    else:
        require(report['failure'] != 'none' and set(witness) <= set(fixture.fixture_files()), 'invalid_result')
    return report


def run_host():
    import native_1c_docker_lifecycle as lifecycle
    import native_1c_smoke as smoke
    require(IMAGE == smoke.IMAGE and VERSION == smoke.EXPECTED_VERSION)
    def revision():
        value = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                        stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        require(re.fullmatch('[0-9a-f]{40}', value) is not None)
        subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', 'HEAD'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True)
        return value
    source_sha = revision()
    require(os.environ.get('GITHUB_SHA') == source_sha)
    nonce = uuid.uuid4().hex
    token, actor = os.environ.pop('GHCR_TOKEN', ''), os.environ.pop('GHCR_USER', '')
    require(token and re.fullmatch('[A-Za-z0-9-]{1,39}', actor))
    with tempfile.TemporaryDirectory(prefix='onec-demo-designer-') as directory:
        work = Path(directory).resolve()
        staged = work / 'staged'
        hashes = stage_inputs(ROOT, staged)
        fixture.fixture_files()  # Verify archive before any native action.
        auth = work / 'auth'
        auth.mkdir(mode=0o700)
        try:
            env = smoke.docker_environment(auth)
            smoke.run_silent(['docker', 'login', 'ghcr.io', '--username', actor, '--password-stdin'], env, 60, token.encode())
            token = ''
            smoke.run_silent(['docker', 'pull', '--platform', 'linux/amd64', IMAGE], env, 600)
        finally:
            token = ''
            shutil.rmtree(auth)
        clean = work / 'no-auth'
        clean.mkdir(mode=0o700)
        code, raw = lifecycle.run_owned(container_command(staged, nonce), smoke.docker_environment(clean),
                                       name='onec-demo-designer-' + nonce, nonce=nonce, image=IMAGE,
                                       seconds=900, output_limit=16384)
        report = validate_report(raw, nonce, hashes)
        require(code == (0 if report['status'] == 'ok' else 1), 'invalid_result')
        require(inventory(ROOT) == hashes and inventory(staged) == hashes and revision() == source_sha)
    # Only after verified owned-container removal and private directory cleanup.
    return dict(schema=SCHEMA + '-host', source_sha=source_sha, image=IMAGE, expected_version=VERSION,
                native=report, container_cleanup_verified=True, docker_cli_reap_verified=True,
                enterprise_executed=False, security_settings_changed=False)


def failure_report(error):
    import native_1c_docker_lifecycle as lifecycle
    failure = dict(schema=SCHEMA + '-host', status='failed', failure='host_failed',
                   container_cleanup_verified=None, docker_cli_reap_verified=None)
    if isinstance(error, lifecycle.LifecycleError):
        failure.update(failure=str(error), container_cleanup_verified=error.container_cleanup_verified,
                       docker_cli_reap_verified=error.cli_reap_verified)
    return failure


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--inside-container':
        raise SystemExit(native_run(sys.argv[2]))
    if sys.argv[1:] != ['--execute-approved-image']:
        raise SystemExit('Use --execute-approved-image only after exact-source review and CI admission.')
    try:
        value = run_host()
        print(json.dumps(value, sort_keys=True))
        raise SystemExit(0 if value['native']['status'] == 'ok' else 1)
    except Exception as error:
        # Never serialize exception text, native logs, credentials or unvalidated bytes.
        print(json.dumps(failure_report(error)))
        raise SystemExit(1)
