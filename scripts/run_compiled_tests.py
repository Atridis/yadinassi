"""Run existing tests under strict policy; never report fallback as compiled.

Exit 2 when even a caught backend rejection or old-backend node execution occurs.
Pure helper/subprocess tests without in-process compiled events are listed as
unobserved, not counted as compiled coverage. Ordinary assertion failures exit 1.
"""
import argparse
import atexit
import copy
import os
import threading
import json
import math
from pathlib import Path
import sys
import time
import unittest
import weakref
from contextlib import ExitStack
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.execution_policy import execution_backend_policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', action='append', default=[])
    parser.add_argument('--pattern', default='test_*.py')
    parser.add_argument('--lowering', choices=('node', 'inline', 'inline-fast'), default='node')
    parser.add_argument('--detailed-node-stats', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--diagnostic-heartbeat-seconds', type=float, default=0,
                        help='Optional CPU/stack diagnostics; not benchmark mode')
    args = parser.parse_args(argv)
    if not math.isfinite(args.diagnostic_heartbeat_seconds) or args.diagnostic_heartbeat_seconds < 0:
        parser.error('diagnostic heartbeat must be nonnegative')
    diagnostic_stop = threading.Event()
    diagnostic_thread = None
    if args.diagnostic_heartbeat_seconds:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        diagnostic_main_thread = threading.get_ident()
        def heartbeat():
            while not diagnostic_stop.wait(args.diagnostic_heartbeat_seconds):
                frame = sys._current_frames().get(diagnostic_main_thread)
                trace = []
                while frame is not None and len(trace) < 80:
                    trace.append([frame.f_code.co_filename, frame.f_code.co_name, frame.f_lineno])
                    frame = frame.f_back
                del frame
                args.report.with_suffix('.health.json').write_text(json.dumps({
                    'pid': os.getpid(), 'monotonic': time.monotonic(),
                    'process_cpu_seconds': time.process_time(), 'stack': trace,
                }), encoding='utf-8')
        diagnostic_thread = threading.Thread(target=heartbeat, daemon=True,
                                              name='compiled-test-diagnostics')
        diagnostic_thread.start()
        def close_diagnostics():
            diagnostic_stop.set()
            diagnostic_thread.join(timeout=1)
        atexit.register(close_diagnostics)
    Engine.INLINE = args.lowering != 'node'
    Engine.FAST_INLINE = args.lowering == 'inline-fast'
    Engine.DETAILED_INLINE_STATS = args.detailed_node_stats
    live = weakref.WeakSet()
    records = []
    active = None
    outside = {'strict_rejections': 0, 'legacy_visitor_calls': 0, 'old_backend_nodes': 0, 'strict_entry_calls': 0}
    original_init = Engine.__init__
    original_visit = Interpreter._visit
    original_reject = CompiledUnsupported.__init__

    def reject(error, node, reason):
        (active if active is not None else outside)['strict_rejections'] += 1
        original_reject(error, node, reason)

    def initialize(engine, vm):
        original_init(engine, vm)
        live.add(engine)
        if active is not None:
            active['engines'].append((id(engine.stats), engine.stats))

    def visit(vm, node):
        if vm.execution_backend != 'compiled-strict':
            (active if active is not None else outside)['old_backend_nodes'] += 1
        elif active is None:
            outside['strict_entry_calls'] += 1
        return (yield from original_visit(vm, node))

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            nonlocal active
            active = {'test': test.id(), 'started': time.monotonic(), 'engines': [(id(e.stats), e.stats) for e in live],
                      'before': {id(e.stats): copy.deepcopy(e.stats) for e in live},
                      'old_backend_nodes': 0, 'strict_rejections': 0, 'legacy_visitor_calls': 0}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.with_suffix('.progress.json').write_text(
                json.dumps({'running_test': test.id(), 'completed': len(records)}), encoding='utf-8')
            super().startTest(test)

        def _record_failure(self, test, error, kind):
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.with_suffix('.failures.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'test': test.id(), 'kind': kind,
                    'trace': self._exc_info_to_string(error, test)}, ensure_ascii=False) + '\n')

        def addFailure(self, test, error):
            self._record_failure(test, error, 'failure')
            super().addFailure(test, error)

        def addError(self, test, error):
            self._record_failure(test, error, 'error')
            super().addError(test, error)

        def stopTest(self, test):
            nonlocal active
            record = {'test': active['test'], 'seconds': time.monotonic() - active['started'], 'old_backend_nodes': active['old_backend_nodes'],
                      'strict_rejections': active['strict_rejections'],
                      'legacy_visitor_calls': active['legacy_visitor_calls'],
                      'emitted_executions': 0, 'helper_executions': 0,
                      'python_translated_blocks': 0, 'python_translated_nodes': 0,
                      'inline_blocks': 0, 'inline_fragments': 0, 'metadata_block_executions': 0, 'node_coverage_modes': [],
                      'rejected_units': 0, 'unsupported_executions': 0,
                      'interpreter_fallbacks': 0, 'node_kinds': {}, 'observed_execution_contracts': []}
            for identity, stats in active['engines']:
                before = active['before'].get(identity, {})
                activity = any(stats.get(key, 0) - before.get(key, 0) for key in
                    ('emitted_executions', 'helper_executions', 'inline_blocks', 'inline_fragments', 'metadata_block_executions', 'python_translated_blocks',
                     'rejected_units', 'unsupported_executions', 'interpreter_fallbacks'))
                translated_nodes=sum(stats.get('python_translated_node_kinds',{}).values())-sum(before.get('python_translated_node_kinds',{}).values())
                record['python_translated_nodes'] += translated_nodes
                if activity or translated_nodes:
                    contract = {'owned_snapshot': stats.get('owned_snapshot', False),
                                'origin_mutation_monitor': stats.get('origin_mutation_monitor', 'full'),
                                'active_ast_contract': stats.get('active_ast_contract', 'fail-closed')}
                    if contract not in record['observed_execution_contracts']:
                        record['observed_execution_contracts'].append(contract)
                for key in ('emitted_executions', 'helper_executions', 'inline_blocks', 'inline_fragments', 'metadata_block_executions', 'python_translated_blocks', 'rejected_units',
                            'unsupported_executions', 'interpreter_fallbacks'):
                    record[key] += stats.get(key, 0) - before.get(key, 0)
                coverage = stats.get('node_coverage', 'observed')
                if coverage not in record['node_coverage_modes']:
                    record['node_coverage_modes'].append(coverage)
                for kind, count in stats.get('node_kinds', {}).items():
                    delta = count - before.get('node_kinds', {}).get(kind, 0)
                    if delta:
                        record['node_kinds'][kind] = record['node_kinds'].get(kind, 0) + delta
            record['compiled_execution_observed'] = bool(record['emitted_executions'] or record['helper_executions'] or record['inline_blocks'] or record['inline_fragments'] or record['metadata_block_executions'] or record['python_translated_blocks'] or record['python_translated_nodes'])
            records.append(record)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.with_suffix('.cases.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            active = None
            super().stopTest(test)

    def observe_legacy(method):
        def observed(vm, *args, **kwargs):
            (active if active is not None else outside)['legacy_visitor_calls'] += 1
            return method(vm, *args, **kwargs)
        return observed

    loader = unittest.TestLoader()
    with ExitStack() as observation:
        observation.enter_context(patch.object(Engine, '__init__', initialize))
        observation.enter_context(patch.object(Interpreter, '_visit', visit))
        observation.enter_context(patch.object(CompiledUnsupported, '__init__', reject))
        from yadinassi.configuration_source_runtime import _SourceInterpreter
        from yadinassi.form_runtime import _FormInterpreter
        from yadinassi.catalog_object_preparation import _ObjectInterpreter
        from yadinassi.document_posting import _PostingInterpreter
        from yadinassi.form_event_simulation import _EventInterpreter
        from yadinassi.source_constant_managers import _ValueInterpreter
        for cls in (Interpreter, _SourceInterpreter, _FormInterpreter, _ObjectInterpreter, _PostingInterpreter, _EventInterpreter, _ValueInterpreter):
            for name, method in vars(cls).items():
                if name.startswith('visit_'):
                    observation.enter_context(patch.object(cls, name, observe_legacy(method)))
        with execution_backend_policy('compiled-strict'):
            suite = (loader.loadTestsFromNames(args.module) if args.module else
                     loader.discover(str(ROOT / 'tests'), pattern=args.pattern))
            result = unittest.TextTestRunner(verbosity=1, resultclass=Result).run(suite)
    gaps = [r for r in records if any(r[k] for k in
            ('old_backend_nodes', 'legacy_visitor_calls', 'strict_rejections', 'rejected_units', 'unsupported_executions', 'interpreter_fallbacks'))]
    unseen = [r['test'] for r in records if not r['compiled_execution_observed']]
    report = {'backend': 'compiled-strict', 'lowering': args.lowering,
              'owned_snapshot_experiment': getattr(Engine, 'OWNED_SNAPSHOT', False),
              'origin_mutation_monitor': getattr(Engine, 'ORIGIN_MUTATION_MONITOR', True),
              'detailed_node_stats': args.detailed_node_stats, 'tests_run': result.testsRun,
              'outside_test_execution': outside,
              'test_assertions_passed': result.wasSuccessful(),
              'strict_coverage_gaps': gaps, 'without_observed_compiled_execution': unseen,
              'executed_node_kinds': sorted({k for r in records for k in r['node_kinds']}),
              'note': 'Helper-backed executions are separate; unobserved tests and subprocesses do not prove compiled coverage.',
              'failures': [{'test': t.id(), 'trace': text} for t, text in result.failures],
              'errors': [{'test': t.id(), 'trace': text} for t, text in result.errors],
              'cases': records}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Strict: tests={result.testsRun}, gaps={len(gaps)}, unobserved={len(unseen)}; report={args.report}')
    if diagnostic_thread is not None:
        close_diagnostics()
        atexit.unregister(close_diagnostics)
    outside_gap = any(outside[k] for k in ('strict_rejections', 'legacy_visitor_calls', 'old_backend_nodes'))
    return 1 if not result.wasSuccessful() else 2 if gaps or outside_gap else 0

if __name__ == '__main__':
    raise SystemExit(main())
