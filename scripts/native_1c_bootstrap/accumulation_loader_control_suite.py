"""One load/redump diagnostic after the unchanged NativeSmoke prerequisite."""
from pathlib import Path
import json
import os
import stat
import sys
import full_suite as full
import run_stage
import diagnostics
from accumulation_loader_control import fixture, contract


def empty_report(nonce):
    return dict(schema=contract.STAGE_SCHEMA, profile=contract.PROFILE, nonce=nonce,
        status='failed', failure_kind='prerequisites_failed', failure_phase='prerequisites',
        input_sha256={}, prepared_sha256=None, redump_sha256=None,
        target_input_schema_version=None, target_redump_schema_version=None,
        case_count=contract.COUNT, completed_case_count=0,
        configuration_validation=fixture.VALIDATION_MODE, redump_diagnostic=[],
        install_diagnostics=[], process_diagnostics=full.empty_process_diagnostics(),
        **{key: False for key in contract.FLAGS | contract.ACCEPTANCE_FLAGS})


def dump_files(root):
    result={};total=0;pending=[root];seen=0
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                seen+=1
                if seen>512:raise full.FullError('output_limit')
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path));continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise full.FullError('invalid_input')
                path=Path(entry.path);name=path.relative_to(root).as_posix()
                raw=full.secure_bytes(path,fixture.MAX_FILE,allow_empty=name.endswith('.bsl'))
                total+=len(raw)
                if total>fixture.MAX_TOTAL or len(result)>=256:raise full.FullError('output_limit')
                result[name]=raw
    fixture._files(result)
    return result


def input_hashes(inputs):
    # Manifest is supplied by the source-pinned host and contains paths only.
    value=full.strict_json(full.secure_bytes(inputs/contract.MANIFEST,32768))
    if type(value) is not dict or not 1<=len(value)<=64:raise full.FullError('invalid_input')
    result={}
    for source,target in value.items():
        if (type(source) is not str or not source.startswith('scripts/') and not source.startswith('integrational_tests/')
            or type(target) is not str or target.startswith('/') or any(p in ('','..','.') for p in target.split('/'))):
            raise full.FullError('invalid_input')
        result[source]=full.digest(full.secure_bytes(inputs/target,full.MAX_OUTPUT))
    return result


def run_suite(platform, root, inputs, nonce):
    report = empty_report(nonce)
    phase = 'inputs'
    baseline = None
    try:
        if (not full.valid_nonce(nonce) or platform.user != 'NativeSmoke'
                or platform.password is not None or platform.timeout != 120):
            raise full.FullError('invalid_input')
        hashes = input_hashes(inputs)
        report['input_sha256'] = hashes
        fixture.declarations()  # Verify the source-owned byte pins before invocation.
        full.absent(root)
        root.mkdir(mode=0o700)
        baseline = full.client_process_baseline(nonce)

        def designer(label, args):
            source_root = Path(args[1]) if label == 'load' else None
            facts = dict(
                source_root_present=None if source_root is None else
                    source_root.is_dir() and not source_root.is_symlink(),
                configuration_present=None if source_root is None else
                    (source_root / 'Configuration.xml').is_file()
                    and not (source_root / 'Configuration.xml').is_symlink())
            try:
                full.run_process(platform.command('DESIGNER') + args +
                    ['/Out', str(root / (label + '.log')),
                     '/DumpResult', str(root / (label + '.result'))],
                    root, root / (label + '-console.log'), 120, require_clean_tree=True)
            except Exception as error:
                code = getattr(error, 'exit_code', None)
                facts['exit_code'] = code if type(code) is int and -255 <= code <= 255 else None
                for name in (label + '.log', label + '-console.log'):
                    try:
                        raw = full.secure_bytes(root / name, 65536, allow_empty=True)
                        report['install_diagnostics'].append(contract.install_diagnostic(
                            diagnostics.native_text(raw), label, **facts))
                    except Exception:
                        pass
                if not report['install_diagnostics']:
                    report['install_diagnostics'].append(contract.install_diagnostic('', label, **facts))
                raise
            if not full.native_processes_quiet(platform.executable):
                raise full.FullError('process_failed')

        phase = 'baseline'
        before = root / 'before'
        before.mkdir()
        designer('before', ['/DumpConfigToFiles', str(before), '-Format', 'Hierarchical'])
        _, expected = fixture.prepare(dump_files(before))
        prepared = root / 'prepared'
        prepared.mkdir()
        for name, raw in expected.items():
            path = prepared / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
        fixture.verify_redump(expected, dump_files(prepared))
        report['prepared_sha256'] = fixture.inventory_digest(expected)
        report['target_input_schema_version'] = fixture.target_schema_version(expected)
        phase = 'load'
        report['entered'] = True
        designer('load', ['/LoadConfigFromFiles', str(prepared)])
        report['load_completed'] = True
        # Deliberately no database update or Enterprise invocation for this case.
        phase = 'redump'
        after = root / 'after'
        after.mkdir()
        designer('after', ['/DumpConfigToFiles', str(after), '-Format', 'Hierarchical'])
        report['redump_completed'] = True
        actual = dump_files(after)
        report['target_redump_schema_version'] = fixture.target_schema_version(actual)
        report['redump_sha256'] = fixture.inventory_digest(actual)
        report['redump_diagnostic'] = fixture.redump_diagnostic(expected, actual)
        try:
            fixture.verify_redump(expected, actual)
        except ValueError:
            raise full.FullError('output_mismatch') from None
        report['config_verified'] = True
        phase = 'final'
        if input_hashes(inputs) != hashes or dump_files(prepared) != expected:
            raise full.FullError('module_mismatch')
        report['source_verified'] = True
        survivors = full.client_process_snapshot() - baseline
        if survivors:
            raise full.ClientProcessError(full.unexpected_process_diagnostics(survivors, 'after_exit'))
        full.require_session_bus(run_stage.ROOT, nonce)
        report['quiet'] = full.native_processes_quiet(platform.executable)
        if not report['quiet']:
            raise full.FullError('process_failed')
        report['process_diagnostics'] = dict(full.empty_process_diagnostics(), stage='after_exit', reason='none')
        report.update(status='ok', failure_kind='none', failure_phase='final',
                      process_exited=True, completed=True, completed_case_count=contract.COUNT)
    except Exception as error:
        report['failure_kind'] = error.kind if isinstance(error, full.FullError) else 'unexpected_failure'
        report['failure_phase'] = phase
        if isinstance(error, full.ClientProcessError):
            report['process_diagnostics'] = error.diagnostics
    return report


def finish_report(report, nonce, root, *, quiet, bus_cleanup_failed):
    suite = empty_report(nonce)
    try:
        suite = full.strict_json(full.secure_bytes(root.parent / 'stage3-report.json', 16384))
        if (type(suite) is not dict or set(suite) != contract.STAGE_KEYS
                or suite['schema'] != contract.STAGE_SCHEMA or suite['profile'] != contract.PROFILE
                or suite['nonce'] != nonce or any(suite[key] is not False for key in contract.ACCEPTANCE_FLAGS)):
            raise full.FullError('invalid_result')
        if not quiet or bus_cleanup_failed:
            raise full.FullError('process_failed')
        full.final_client_process_census(nonce)
        if report['status'] != 'ok' or suite['status'] != 'ok':
            report['status'] = 'stage3_failed' if (report.get('stage2') or {}).get('status') == 'ok' else report['status']
    except Exception:
        suite = empty_report(nonce)
        suite.update(failure_kind='export_failed')
    if suite['status'] != 'ok' and report.get('stage2') and report['stage2']['status'] == 'ok':
        report['status'] = 'stage3_failed'
    # The bootstrap smoke is a prerequisite, not semantic measurement acceptance.
    report['native_tests_completed'] = False
    report['stage3'] = suite
    raw = json.dumps(dict(schema=contract.SCHEMA, profile=contract.PROFILE, nonce=nonce,
                          report=report, outputs=[]), sort_keys=True, separators=(',', ':')).encode() + b'\n'
    if len(raw) > contract.MAX_TRANSPORT:
        raise full.FullError('export_failed')
    return raw


def main(args):
    if len(args) != 2 or args[0] != '--invocation-nonce' or not full.valid_nonce(args[1]):
        return 2
    nonce = args[1]
    # This is the already-approved setup/simple-smoke prerequisite only.
    if run_stage.main([]) != 0:
        return 1
    report = empty_report(nonce)
    try:
        launcher = run_stage.load_launcher()
        platform = launcher.Platform(run_stage.ONEC, run_stage.ROOT / 'db', 120, 'NativeSmoke')
        report = run_suite(platform, run_stage.ROOT / ('stage3-' + nonce), run_stage.INPUTS, nonce)
    except Exception:
        pass
    raw = json.dumps(report, sort_keys=True, separators=(',', ':')).encode()
    if len(raw) > 16384:
        return 1
    with (run_stage.ROOT / 'stage3-report.json').open('xb') as stream:
        stream.write(raw)
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
