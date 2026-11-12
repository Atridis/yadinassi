"""Отдельная загрузка основной демо в DESIGNER: без запуска приложения и выгрузки."""
from __future__ import annotations
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_1c_main_demo_diagnostics as diagnostics

SCHEMA = 'native-main-demo-designer-v4'
VERSION = '8.3.27.1508'
IMAGE = 'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728'
ONEC = '/opt/1cv8t/x86_64/' + VERSION + '/1cv8t'
CHECK_FLAGS = ('-ConfigLogIntegrity', '-IncorrectReferences', '-ThinClient', '-Server',
               '-ThickClientManagedApplication', '-HandlersExistence', '-ExtendedModulesCheck')
SOURCE_ROOT = 'examples/demo'
MANIFEST = 'InventoryApplication.xml'
SOURCE_SHA256 = {'AccumulationRegisters/Stock.xml': 'a2816c3263ab8ea6bb82b299b27a5b18e6c2142c32f51d50da75a0a3d8ba7269',
 'Catalogs/ВидыНоменклатуры.xml': '723c973982629b92c183d68b24aef8fde1771b34e649e536749354d7a14cc2d0',
 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента.xml': 'ccf4960ad91cc507a0e8165c973f79d88c9fe5e1773d1bf8fd1bb90584275a28',
 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form.xml': '3d5d1cdf429fbc5ece392c4bc4df6621c8753f152c8260a1aa5a83557a2a088d',
 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form/Module.bsl': '1362d0c9ab909625f98648a719e87422dd7665634e2cc2e55ce01517a198f53f',
 'Catalogs/Номенклатура.xml': '6418b0b403932a38b24c75bb5db5496837cef396897225fa0bc5b80f905fa156',
 'Catalogs/Номенклатура/Ext/ObjectModule.bsl': 'b329bc9a92db51032415bc62f779672acff65beb081237105adedab0f16edec9',
 'Catalogs/Номенклатура/Forms/ФормаСписка.xml': 'ce2e8373aab443a70990c7c1a7f1166e2efc45f025952959ae48de4553f474c2',
 'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form.xml': '192dcb7c76a5805afdff477c9bc27f1f67149f1aa53be5a0894dcae931c4afc6',
 'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form/Module.bsl': 'cedc20b94809fc639f72ee65d180eb5e6dadb647e02a2ed02d85af7dd1533127',
 'Catalogs/Номенклатура/Forms/ФормаЭлемента.xml': '0d55e449ebff7d194f09af8c92dff5fd53c05db17927a0c478dfae9ad9a7dc6e',
 'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form.xml': 'ba70bc4129509c979033632d305d4866e0e311f5e25322369bdf3998b055add6',
 'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form/Module.bsl': '86bccc60f288b6d8bec57dd01701b3535a73c297b1a42a97d2f5528f066426e3',
 'Catalogs/Склады.xml': '3f123ebb7eed85b1b845ae8867749e91cde2d6154cd6e8b5da16a74c9658bb3a',
 'CommonForms/DraftDetails.xml': '23a9a7e2e6c5eb8a23da906adf306062ad6af71beb2ba30e63e617631e60f187',
 'CommonForms/DraftDetails/Ext/Form.xml': 'b192441d5e66a1349fea0b36fa22dd8d6ef2bb56e2a1a42aa3c1ce5ba9f5a13a',
 'CommonForms/DraftDetails/Ext/Form/Module.bsl': '7aa474668ff24b52d4ef601da73791768de3b15c14b92f982176d40b93c9bd12',
 'CommonForms/OperationDraft.xml': '833a48959f40084a5550d49236df256e44f4060cb9cc2235d9edb96ae7cf0dcb',
 'CommonForms/OperationDraft/Ext/Form.xml': '33e1afff136c3bbdda92121d31c298e520cbffe6171910c8fcd6804847c5f84d',
 'CommonForms/OperationDraft/Ext/Form/Module.bsl': '31f9f03370889fc262a13ca0f89375440ee9d26a4c4734583a47007dc92f7006',
 'CommonModules/DemoService.xml': '5f29f464788769b33615fe3920335842f58355ec5f23861b1c1018f1e4a70e36',
 'CommonModules/DemoService/Ext/Module.bsl': '6896d4e8cb17cb2740397209d9a7e0c630a8d6d7db483cb4ed7ba882074089cb',
 'CommonModules/DemoTools.xml': '0450279ff014eca7e30e2ea6d37b18e9c8942106c0b415225a2ffec246dac483',
 'CommonModules/DemoTools/Ext/Module.bsl': '6893ec3d0267cbf1cf115e4d9118ae13528a5562160f7e2bdd8bddb768a4f828',
 'Configuration.xml': 'df057ffe3a05f21397f27c02a694dc68901e44872d019b61bf957bce5f803079',
 'Documents/Issue.xml': '4dd45972011a1e375ec1ccb65f87cec79647692c699f8bd8feb0fc60b6f08b4a',
 'Documents/Issue/Ext/ObjectModule.bsl': 'c3fc50dc1b1fe476f5b98f9aba72d4b9b20adcf8b5f005114fcee115f0bb67f2',
 'Documents/Issue/Forms/Card.xml': '6c2569339a0a3ffde1d50f8bc571a992c3c4df98032a750216f4103b5032227a',
 'Documents/Issue/Forms/Card/Ext/Form.xml': '1ff3c095f98426f1179a3f8c51b82f6bd3bd4dbd906837ecdfe2b85fd2848d32',
 'Documents/Issue/Forms/Card/Ext/Form/Module.bsl': '91325955fd484c274c86d184373be334f64177cf843f68707f78fff719f0f682',
 'Documents/Receipt.xml': '60b3b1b0b8b86e38fa044284d7f00b2034a49353975f25f1f70cd2cd9a94f2f1',
 'Documents/Receipt/Ext/ObjectModule.bsl': 'ee0baf274a8788c263406d5d7a21628da643e087ae5d73d41554d2beda06dd39',
 'Documents/Receipt/Forms/Card.xml': '24d9c85bc1b51611525be52c2514c8de4c195f8c50913f6061f4e2d138f6db9d',
 'Documents/Receipt/Forms/Card/Ext/Form.xml': '989311102e980c2dcc9757c0a3a21e0e7137986faa128919b104e2c75061a687',
 'Documents/Receipt/Forms/Card/Ext/Form/Module.bsl': '91325955fd484c274c86d184373be334f64177cf843f68707f78fff719f0f682',
 'Enums/States.xml': '2b080e1e003c14407e5d1962224de589c70755f87af711fca2ebc6517f923fb5',
 'Enums/Units.xml': '1eaabc285e570e81cd61220bdf9fd6145fe571e60032e7ddc4d3da62cee5cf09',
 'Ext/ClientApplicationInterface.xml': '407d37fdc9c46dc9ef03573c8241f574c382e329cc9670bf5eba0d529860b16a',
 'Ext/CommandInterface.xml': 'b36fdd6e977f07daa40e5b4efd4bf8ad1c536f08402642df470587600848315a',
 'Ext/HomePageWorkArea.xml': '16188438d96e87c4103ba71fe773543c1b71f3ca98e93476f3174d816672010e',
 'Ext/ManagedApplicationModule.bsl': '54c591d67a643c1b201e814e51fa6be85f774f0a7ae90dae656a0efe82657311',
 'InventoryApplication.xml': 'f5e2f1e13d63484bf536d150b6e9eddbd83058f1422657d7aec11442a235993a',
 'Languages/Русский.xml': 'e0438b24e18c15da067173886270b2a4806aff1ea97031b2211c3f586181cf3c',
 'Subsystems/НормативнаяИнформация.xml': 'e824868068ac9018757c8fea8adbe4eee1c597a82e0fd6d8215c8d2f94858412'}
SOURCE_FILES = tuple(sorted(SOURCE_SHA256))
PLATFORM_FILES = tuple(n for n in SOURCE_FILES if n != MANIFEST)
INPUTS = ('scripts/native_1c_main_demo_designer.py', 'scripts/native_1c_main_demo_designer.sh',
          'scripts/native_1c_main_demo_diagnostics.py', 'scripts/native_1c_main_demo_ci_policy.py', 'scripts/native_1c_docker_lifecycle.py',
          'scripts/native_1c_smoke.py', '.github/workflows/native-1c-main-demo-designer.yml',
          *(SOURCE_ROOT + '/' + n for n in SOURCE_FILES))
PHASES = ('create', 'load', 'check', 'update')
FAILURES = ('none', 'invalid_input', 'process_failed', 'timeout', 'invalid_result')
MAX_REPORT = 32768

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
    source_files(root)  # Reject unexpected/missing source paths before staging.
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

def source_files(root=ROOT):
    files = dump_files(root / SOURCE_ROOT)
    require({n: digest(raw) for n, raw in files.items()} == SOURCE_SHA256)
    require(len(files) == 44 and len(PLATFORM_FILES) == 43 and MANIFEST in files)
    return files


def stage_source(destination, expected):
    require({n: digest(raw) for n, raw in expected.items()} == SOURCE_SHA256)
    destination.mkdir(mode=0o700, exist_ok=False)
    for name in PLATFORM_FILES:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as target:
            target.write(expected[name])
    require(dump_files(destination) == {n: expected[n] for n in PLATFORM_FILES})


def operations(root):
    db = root / 'db'
    common = ['/AppAutoCheckVersion-', '/DisableStartupDialogs', '/DisableStartupMessages', '/L', 'ru']
    result = [('create', [ONEC, 'CREATEINFOBASE', f'File="{db}";', '/Lru'])]
    for phase, flags in (
        ('load', ['/LoadConfigFromFiles', str(root / 'source')]),
        ('check', ['/CheckConfig', *CHECK_FLAGS]),
        ('update', ['/UpdateDBCfg'])):
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
    report = dict(schema=SCHEMA, nonce=nonce, status='failed', phase='inputs',
                  failure='invalid_input', input_sha256={}, source_sha256={},
                  platform_sha256={}, excluded_files=[MANIFEST],
                  check_flags=list(CHECK_FLAGS), completed=[], diagnostics=diagnostics.empty(), channels=diagnostics.channels_empty(), check_excerpt=diagnostics.check_empty())
    try:
        require(re.fullmatch('[0-9a-f]{32}', nonce) is not None and os.getuid() == 1000)
        report['input_sha256'] = inventory(ROOT)
        expected = source_files()
        report['source_sha256'] = {n: digest(raw) for n, raw in expected.items()}
        report['platform_sha256'] = {n: digest(expected[n]) for n in PLATFORM_FILES}
        root = Path('/tmp/main-demo-designer')
        root.mkdir(mode=0o700)
        stage_source(root / 'source', expected)
        for phase, command in operations(root):
            report['phase'] = phase
            require(not (root / (phase + '.result')).exists())
            # Native output remains in bounded-lived private tmpfs; never inherit
            # the host stdout/stderr used for the validated report.
            with (root / (phase + '.stdout')).open('xb') as out, (root / (phase + '.stderr')).open('xb') as err:
                try:
                    code = subprocess.run(['timeout', '--signal=TERM', '--kill-after=5s', '120s', *command],
                                          stdin=subprocess.DEVNULL, stdout=out,
                                          stderr=err, timeout=135).returncode
                except subprocess.TimeoutExpired:
                    out.flush(); err.flush()
                    report['channels'] = diagnostics.capture(root, phase, None)
                    raise
            report['channels'] = diagnostics.capture(root, phase, code)
            if phase == 'check':
                report['check_excerpt'] = diagnostics.check_excerpt(root / 'check.log', PLATFORM_FILES)
            if code != 0:
                report['diagnostics'] = diagnostics.classify(root / (phase + '.log'), PLATFORM_FILES)
            require(code == 0, 'timeout' if code in (124, 137) else 'process_failed')
            native_quiet()
            try:
                zero_result(root / (phase + '.result'))
            except DemoError:
                report['diagnostics'] = diagnostics.classify(root / (phase + '.log'), PLATFORM_FILES)
                raise
            if phase == 'create':
                info = (root / 'db/1Cv8.1CD').lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_size > 0, 'invalid_result')
            report['completed'].append(phase)
        require(inventory(ROOT) == report['input_sha256'])
        require(dump_files(root / 'source') == {n: expected[n] for n in PLATFORM_FILES})
        report.update(status='ok', phase='complete', failure='none')
    except subprocess.TimeoutExpired:
        report['failure'] = 'timeout'
    except Exception as error:
        report['failure'] = str(error) if isinstance(error, DemoError) and str(error) in FAILURES else 'invalid_input'
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'))
    require(len(encoded.encode()) <= MAX_REPORT, 'invalid_result')
    print(encoded)
    return 0 if report['status'] == 'ok' else 1


def container_command(staged, nonce):
    require(staged.is_absolute() and ',' not in str(staged) and re.fullmatch('[0-9a-f]{32}', nonce))
    return ['docker', 'create', '--name', 'onec-main-demo-designer-' + nonce,
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
            '/bin/bash', '--noprofile', '--norc', '/smoke/scripts/native_1c_main_demo_designer.sh', nonce]

def validate_report(raw, nonce, hashes):
    require(type(raw) is bytes and len(raw) <= MAX_REPORT, 'invalid_result')
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
    require(type(report) is dict and set(report) == {
        'schema', 'nonce', 'status', 'phase', 'failure', 'input_sha256',
        'source_sha256', 'platform_sha256', 'excluded_files', 'check_flags', 'completed', 'diagnostics', 'channels', 'check_excerpt'}, 'invalid_result')
    require(report['schema'] == SCHEMA and report['nonce'] == nonce
            and report['input_sha256'] == hashes and report['source_sha256'] == SOURCE_SHA256
            and report['platform_sha256'] == {n: SOURCE_SHA256[n] for n in PLATFORM_FILES}
            and report['excluded_files'] == [MANIFEST] and report['check_flags'] == list(CHECK_FLAGS),
            'invalid_result')
    require(diagnostics.channels_valid(report['channels']), 'invalid_result')
    require(diagnostics.check_valid(report['check_excerpt'], PLATFORM_FILES), 'invalid_result')
    require(report['phase'] in ('check', 'update', 'complete') or report['check_excerpt'] == diagnostics.check_empty(), 'invalid_result')
    require(diagnostics.valid(report['diagnostics'], len(PLATFORM_FILES)), 'invalid_result')
    require(type(report['completed']) is list and report['completed'] in
            [list(PHASES[:n]) for n in range(5)], 'invalid_result')
    if report['status'] == 'ok':
        require(report['phase'] == 'complete' and report['failure'] == 'none'
                and report['completed'] == list(PHASES)
                and report['diagnostics'] == diagnostics.empty()
                and report['channels']['exit_code'] == 0
                and report['channels']['channels'].get('result', {}).get('result') == 'zero', 'invalid_result')
    else:
        require(report['status'] == 'failed' and report['failure'] in FAILURES[1:]
                and report['phase'] in ('inputs', *PHASES), 'invalid_result')
        count = len(report['completed'])
        require((report['phase'] == 'inputs' and count == 0)
                or (count < 4 and report['phase'] == PHASES[count])
                or (count == 4 and report['phase'] == 'update'), 'invalid_result')
    return report


def revision():
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args],
            stderr=subprocess.DEVNULL, timeout=10).decode().strip()
    sha, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
    require(all(re.fullmatch('[0-9a-f]{40}', x) for x in (sha, tree)))
    require(not git('status', '--porcelain', '--untracked-files=all'))
    return sha, tree


def run_host():
    import native_1c_main_demo_ci_policy as policy
    import native_1c_docker_lifecycle as lifecycle
    import native_1c_smoke as smoke
    require(IMAGE == smoke.IMAGE and VERSION == smoke.EXPECTED_VERSION)
    source_sha, tree = revision()
    require(policy.check_environment() == source_sha)
    run_id, attempt = os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_RUN_ATTEMPT')
    require(all(type(x) is str and re.fullmatch('[1-9][0-9]{0,19}', x) for x in (run_id, attempt)))
    nonce = uuid.uuid4().hex
    token, actor = os.environ.pop('GHCR_TOKEN', ''), os.environ.pop('GHCR_USER', '')
    require(token and re.fullmatch('[A-Za-z0-9-]{1,39}', actor))
    with tempfile.TemporaryDirectory(prefix='onec-main-demo-designer-') as directory:
        work = Path(directory).resolve()
        staged = work / 'staged'
        hashes = stage_inputs(ROOT, staged)
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
            name='onec-main-demo-designer-' + nonce, nonce=nonce, image=IMAGE,
            seconds=900, output_limit=MAX_REPORT)
        report = validate_report(raw, nonce, hashes)
        require(code == (0 if report['status'] == 'ok' else 1), 'invalid_result')
        require(inventory(ROOT) == hashes and inventory(staged) == hashes
                and revision() == (source_sha, tree))
    # Only finite validated output escapes after owned-container/private-dir cleanup.
    report = dict(report)
    del report['nonce']
    return dict(schema=SCHEMA + '-host', source_sha=source_sha, source_tree=tree,
        github_run_id=run_id, github_run_attempt=attempt, image=IMAGE, expected_version=VERSION,
        native=report, container_cleanup_verified=True, docker_cli_reap_verified=True,
        private_payloads_removed=True, enterprise_executed=False, redump_executed=False,
        security_settings_changed=False)


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
        raise SystemExit('Explicit reviewed-source admission required.')
    try:
        value = run_host()
        print(json.dumps(value, sort_keys=True))
        raise SystemExit(0 if value['native']['status'] == 'ok' else 1)
    except Exception as error:
        print(json.dumps(failure_report(error)))
        raise SystemExit(1)
