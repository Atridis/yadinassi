"""Execute the actual shell's Python emitter; no native process or shared fixture."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import test_native_tree_columns_move_profile as profile_test
from test_native_tree_profile_host import synthetic_producer_reader
from test_native_1c_smoke import bootstrap_report

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'scripts/native_1c_smoke_probe.sh').read_text(encoding='utf-8')
EMITTER=SOURCE.split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
MODES={'true':'tree-v1','copy':'tree-copy-v1','sort':'tree-sort-v1',
       'columns-move':'tree-columns-move-v1',
       'columns-move-boundary':'tree-columns-move-boundary-v1',
       'columns-move-tail':'tree-columns-move-tail-v1',
       'columns-clear':'tree-columns-clear-v1',
       'columns-clear-lifetime':'tree-columns-clear-lifetime-v1',
       'columns-clear-metadata':'tree-columns-clear-metadata-v1',
       'columns-delete':'tree-columns-delete-v1',
       'format-numbers':'format-numbers-v1', 'format-dates':'format-dates-v1', 'json-family':'json-family-v1', 'file-io-family':'file-io-family-v1', 'xml-workflow-family':'xml-workflow-family-v1'}
NONCE='f'*32


def arguments(mode):
    # Fixed current 19 positional arguments passed by finish(). Prerequisites
    # stay false so this isolated dispatch test never reads shared stage2 files.
    return ['0','complete',*(['false']*6),NONCE,*(['false']*9),mode]


def previous_emitter():
    return EMITTER.replace(', "xml-workflow-family"}', '}').replace(', "file-io-family"}', '}').replace(', "json-family"}', '}').replace(', "format-dates"}', '}').replace(', "format-numbers"}', '}').replace(', "columns-delete-string"}', '}').replace(', "columns-delete"}', '}').replace(', "columns-clear-metadata"}', '}').replace(', "columns-clear-lifetime"}', '}').replace(', "columns-clear"}', '}').replace(', "columns-move-tail"}', '}').replace(', "columns-move-boundary"}', '}').replace('{"false", "true", "copy", "sort", "columns-move"}',
                           '{"false", "true", "copy", "sort"}').replace(
        '{"true", "copy", "sort", "columns-move"}', '{"true", "copy", "sort"}')


def execute(args, finish, code=EMITTER):
    binary=io.BytesIO();output=io.TextIOWrapper(binary,encoding='utf-8',write_through=True)
    lane=types.ModuleType('tree_suite');lane.finish_report=finish
    full=types.ModuleType('full_suite');full.native_processes_quiet=lambda path:True
    error=None
    with mock.patch.object(sys,'argv',['emitter',*args]),mock.patch.object(sys,'stdout',output),\
         mock.patch.dict(sys.modules,{'tree_suite':lane,'full_suite':full}),\
         mock.patch.object(sys,'path',list(sys.path)),\
         mock.patch.object(os,'geteuid',return_value=1000,create=True),\
         mock.patch.object(os,'access',return_value=False):
        try:
            exec(compile(code,'native_1c_smoke_probe.sh:emitter','exec'),{})
        except (SystemExit,ValueError) as exc:
            error=exc
    result=binary.getvalue();output.detach()
    return result,error


class TreeEmitterDispatchTests(unittest.TestCase):
    def test_all_fixed_modes_reach_exact_profile_and_cleanup_arguments(self):
        for mode,profile in MODES.items():
            with self.subTest(mode=mode):
                finish=mock.Mock(return_value=b'fixed-synthetic-envelope\n')
                raw,error=execute(arguments(mode),finish)
                self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
                self.assertEqual(raw,b'fixed-synthetic-envelope\n')
                args,kwargs=finish.call_args
                self.assertEqual(args[1:],(NONCE,Path('/tmp/onec-smoke')/('stage3-'+NONCE)))
                self.assertEqual(kwargs,dict(quiet=True,bus_cleanup_failed=False,profile=profile))
                finish.assert_called_once()

    def test_prior_three_profiles_and_ordinary_false_are_byte_identical(self):
        for mode in ('false','true','copy','sort'):
            finish=mock.Mock(return_value=b'fixed-synthetic-envelope\n')
            old,old_error=execute(arguments(mode),finish,previous_emitter())
            new,new_error=execute(arguments(mode),finish)
            self.assertEqual(old,new)
            self.assertEqual(type(old_error),type(new_error))
            if mode=='false':
                finish.assert_not_called()
                self.assertFalse(json.loads(new)['native_tests_completed'])

    def test_unknown_duplicate_and_mixed_mode_arguments_fail_before_emission(self):
        variants=[arguments(x) for x in ('','arbitrary','columns_move','tree-columns-move-v1')]
        variants += [arguments('columns-move')+['columns-move'],
                     arguments('columns-move')+['sort'],arguments('sort')+['columns-move']]
        for args in variants:
            with self.subTest(args=args[-2:]):
                finish=mock.Mock(side_effect=AssertionError('invalid route executed'))
                raw,error=execute(args,finish)
                self.assertIsInstance(error,ValueError);self.assertEqual(raw,b'')
                finish.assert_not_called()

    def test_old_emitter_and_each_single_line_fix_are_negative_controls(self):
        old=previous_emitter()
        only_allowlist=old.replace('{"false", "true", "copy", "sort"}',
                                  '{"false", "true", "copy", "sort", "columns-move"}')
        only_dispatch=old.replace('if tree_mode in {"true", "copy", "sort"}:',
                                 'if tree_mode in {"true", "copy", "sort", "columns-move"}:')
        for code in (old,only_allowlist,only_dispatch):
            finish=mock.Mock(return_value=b'fixed-synthetic-envelope\n')
            raw,error=execute(arguments('columns-move'),finish,code)
            finish.assert_not_called()
            self.assertNotEqual(raw,b'fixed-synthetic-envelope\n')
            if code!=only_allowlist:
                self.assertIsInstance(error,ValueError);self.assertEqual(str(error),'tree mode')
                self.assertEqual(raw,b'')
            else:
                self.assertIsNone(error)
                self.assertFalse(json.loads(raw)['native_tests_completed'])

    def test_actual_emitter_to_real_producer_and_strict_host(self):
        host,tree,full,smoke=profile_test.host,profile_test.tree,profile_test.full,profile_test.smoke
        s=profile_test.spec();raw=profile_test.maximum_output()
        envelope,hashes,modules=profile_test.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(s.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=s.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                # Real producer runs on the private synthetic fixture. The
                # bootstrap prerequisite report is synthetic, never native proof.
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-move'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            accepted=host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=s.name)
            self.assertEqual(accepted[1],raw)
            with self.assertRaises(host.TreeError):
                host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile='tree-sort-v1')

    def test_boundary_mode_both_sets_required_and_prior_modes_unchanged(self):
        old=EMITTER.replace(', "xml-workflow-family"}', '}').replace(', "file-io-family"}', '}').replace(', "json-family"}', '}').replace(', "format-dates"}', '}').replace(', "format-numbers"}', '}').replace(', "columns-delete-string"}', '}').replace(', "columns-delete"}', '}').replace(', "columns-clear-metadata"}', '}').replace(', "columns-clear-lifetime"}', '}').replace(', "columns-clear"}', '}').replace(', "columns-move-tail"}', '}').replace(', "columns-move-boundary"}', '}')
        only_allowlist=old.replace('if tree_mode not in {"false", "true", "copy", "sort", "columns-move"}:',
            'if tree_mode not in {"false", "true", "copy", "sort", "columns-move", "columns-move-boundary"}:')
        only_dispatch=old.replace('if tree_mode in {"true", "copy", "sort", "columns-move"}:',
            'if tree_mode in {"true", "copy", "sort", "columns-move", "columns-move-boundary"}:')
        for code in (old,only_allowlist,only_dispatch):
            finish=mock.Mock(return_value=b'boundary-envelope')
            raw,error=execute(arguments('columns-move-boundary'),finish,code)
            finish.assert_not_called();self.assertNotEqual(raw,b'boundary-envelope')
            if code!=only_allowlist:self.assertIsInstance(error,ValueError)
        for mode in ('false','true','copy','sort','columns-move'):
            finish=mock.Mock(return_value=b'prior-envelope')
            previous,error=execute(arguments(mode),finish,old)
            current,new_error=execute(arguments(mode),finish)
            self.assertEqual(previous,current);self.assertEqual(type(error),type(new_error))
        for args in (arguments('columns-move-boundary')+['columns-move-boundary'],
                     arguments('columns-move-boundary')+['columns-move'],
                     arguments('columns-move')+['columns-move-boundary']):
            finish=mock.Mock();raw,error=execute(args,finish)
            self.assertIsInstance(error,ValueError);self.assertEqual(raw,b'');finish.assert_not_called()

    def test_boundary_actual_emitter_to_real_producer_and_strict_host(self):
        import test_native_tree_columns_move_boundary_profile as boundary
        host,tree,full,smoke=boundary.host,boundary.tree,boundary.full,boundary.smoke
        spec=boundary.spec();raw=boundary.maximum_output()
        envelope,hashes,modules=boundary.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(spec.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=spec.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-move-boundary'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            self.assertEqual(host.validate_envelope(emitted,NONCE,hashes,modules,
                smoke.validate_report,profile=spec.name)[1],raw)
            for profile in ('tree-columns-move-v1','tree-sort-v1'):
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=profile)

    def test_tail_mode_both_sets_required_and_prior_modes_unchanged(self):
        old=EMITTER.replace(', "xml-workflow-family"}', '}').replace(', "file-io-family"}', '}').replace(', "json-family"}', '}').replace(', "format-dates"}', '}').replace(', "format-numbers"}', '}').replace(', "columns-delete-string"}', '}').replace(', "columns-delete"}', '}').replace(', "columns-clear-metadata"}', '}').replace(', "columns-clear-lifetime"}', '}').replace(', "columns-clear"}', '}').replace(', "columns-move-tail"}', '}')
        only_allowlist=old.replace('if tree_mode not in {"false", "true", "copy", "sort", "columns-move", "columns-move-boundary"}:',
            'if tree_mode not in {"false", "true", "copy", "sort", "columns-move", "columns-move-boundary", "columns-move-tail"}:')
        only_dispatch=old.replace('if tree_mode in {"true", "copy", "sort", "columns-move", "columns-move-boundary"}:',
            'if tree_mode in {"true", "copy", "sort", "columns-move", "columns-move-boundary", "columns-move-tail"}:')
        for code in (old,only_allowlist,only_dispatch):
            finish=mock.Mock(return_value=b'boundary-envelope')
            raw,error=execute(arguments('columns-move-tail'),finish,code)
            finish.assert_not_called();self.assertNotEqual(raw,b'boundary-envelope')
            if code!=only_allowlist:self.assertIsInstance(error,ValueError)
        for mode in ('false','true','copy','sort','columns-move','columns-move-boundary'):
            finish=mock.Mock(return_value=b'prior-envelope')
            previous,error=execute(arguments(mode),finish,old)
            current,new_error=execute(arguments(mode),finish)
            self.assertEqual(previous,current);self.assertEqual(type(error),type(new_error))
        for args in (arguments('columns-move-tail')+['columns-move-tail'],
                     arguments('columns-move-tail')+['columns-move'],
                     arguments('columns-move')+['columns-move-tail']):
            finish=mock.Mock();raw,error=execute(args,finish)
            self.assertIsInstance(error,ValueError);self.assertEqual(raw,b'');finish.assert_not_called()

    def test_tail_actual_emitter_to_real_producer_and_strict_host(self):
        import test_native_tree_columns_move_tail_profile as boundary
        host,tree,full,smoke=boundary.host,boundary.tree,boundary.full,boundary.smoke
        spec=boundary.spec();raw=boundary.maximum_output()
        envelope,hashes,modules=boundary.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(spec.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=spec.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-move-tail'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            self.assertEqual(host.validate_envelope(emitted,NONCE,hashes,modules,
                smoke.validate_report,profile=spec.name)[1],raw)
            for profile in ('tree-columns-move-v1','tree-sort-v1'):
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=profile)

    def test_clear_mode_requires_both_closed_sets_and_preserves_all_prior_routes(self):
        old=EMITTER.replace(', "xml-workflow-family"}', '}').replace(', "file-io-family"}', '}').replace(', "json-family"}', '}').replace(', "format-dates"}', '}').replace(', "format-numbers"}', '}').replace(', "columns-delete-string"}', '}').replace(', "columns-delete"}', '}').replace(', "columns-clear-metadata"}', '}').replace(', "columns-clear-lifetime"}', '}').replace(', "columns-clear"}', '}')
        admission=next(line for line in EMITTER.replace(', "xml-workflow-family"}', '}').replace(', "file-io-family"}', '}').replace(', "json-family"}', '}').replace(', "format-dates"}', '}').replace(', "format-numbers"}', '}').replace(', "columns-delete-string"}', '}').replace(', "columns-delete"}', '}').replace(', "columns-clear-metadata"}', '}').replace(', "columns-clear-lifetime"}', '}').splitlines() if line.startswith('if tree_mode not in '))
        dispatch=next(line for line in EMITTER.replace(', "xml-workflow-family"}', '}').replace(', "file-io-family"}', '}').replace(', "json-family"}', '}').replace(', "format-dates"}', '}').replace(', "format-numbers"}', '}').replace(', "columns-delete-string"}', '}').replace(', "columns-delete"}', '}').replace(', "columns-clear-metadata"}', '}').replace(', "columns-clear-lifetime"}', '}').splitlines() if line.startswith('if tree_mode in '))
        only_admission=old.replace(admission.replace(', "columns-clear"}', '}'),admission)
        only_dispatch=old.replace(dispatch.replace(', "columns-clear"}', '}'),dispatch)
        for code in (old,only_admission,only_dispatch):
            finish=mock.Mock(return_value=b'clear-envelope')
            raw,error=execute(arguments('columns-clear'),finish,code)
            finish.assert_not_called();self.assertNotEqual(raw,b'clear-envelope')
            if code!=only_admission:self.assertIsInstance(error,ValueError)
        for mode in ('false','true','copy','sort','columns-move','columns-move-boundary','columns-move-tail'):
            finish=mock.Mock(return_value=b'prior-envelope')
            previous,error=execute(arguments(mode),finish,old)
            current,new_error=execute(arguments(mode),finish)
            self.assertEqual(previous,current);self.assertEqual(type(error),type(new_error))
        for args in (arguments('columns-clear')+['columns-clear'],
                     arguments('columns-clear')+['columns-move'],arguments('columns-move')+['columns-clear']):
            finish=mock.Mock();raw,error=execute(args,finish)
            self.assertIsInstance(error,ValueError);self.assertEqual(raw,b'');finish.assert_not_called()

    def test_clear_actual_emitter_to_real_producer_and_strict_host(self):
        import test_native_tree_columns_clear_profile as clear
        host,tree,full,smoke=clear.host,clear.tree,clear.full,clear.smoke
        spec=clear.spec();raw=clear.maximum_output()
        envelope,hashes,modules=clear.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(spec.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=spec.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-clear'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            self.assertEqual(host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=spec.name)[1],raw)
            for profile in ('tree-v1','tree-copy-v1','tree-sort-v1','tree-columns-move-v1','tree-columns-move-boundary-v1','tree-columns-move-tail-v1'):
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=profile)
    def test_clear_lifetime_actual_emitter_to_real_producer_and_strict_host(self):
        import test_native_tree_columns_clear_lifetime_profile as clear
        host,tree,full,smoke=clear.host,clear.tree,clear.full,clear.smoke
        spec=clear.spec();raw=clear.maximum_output()
        envelope,hashes,modules=clear.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(spec.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=spec.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-clear-lifetime'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            self.assertEqual(host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=spec.name)[1],raw)
            for profile in ('tree-v1','tree-copy-v1','tree-sort-v1','tree-columns-move-v1','tree-columns-move-boundary-v1','tree-columns-move-tail-v1'):
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=profile)
    def test_clear_metadata_actual_emitter_to_real_producer_and_strict_host(self):
        import test_native_tree_columns_clear_metadata_profile as clear
        host,tree,full,smoke=clear.host,clear.tree,clear.full,clear.smoke
        spec=clear.spec();raw=clear.maximum_output()
        envelope,hashes,modules=clear.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(spec.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=spec.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-clear-metadata'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            self.assertEqual(host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=spec.name)[1],raw)
            for profile in ('tree-v1','tree-copy-v1','tree-sort-v1','tree-columns-move-v1','tree-columns-move-boundary-v1','tree-columns-move-tail-v1'):
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=profile)

    def test_delete_actual_emitter_to_real_producer_and_strict_host(self):
        import test_native_tree_columns_delete_profile as clear
        host,tree,full,smoke=clear.host,clear.tree,clear.full,clear.smoke
        spec=clear.spec();raw=clear.maximum_output()
        envelope,hashes,modules=clear.success_envelope(raw)
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp).resolve(strict=True);capture=parent/'capture';capture.mkdir()
            (capture/(spec.case+'.out')).write_bytes(raw)
            tree.write_report(parent/'stage3-report.json',envelope['report']['stage3'],profile=spec.name)
            def finish(report,nonce,requested_root,**kwargs):
                self.assertEqual(requested_root,Path('/tmp/onec-smoke')/('stage3-'+NONCE))
                return tree.finish_report(bootstrap_report(),nonce,capture,**kwargs)
            with synthetic_producer_reader(tree.full),mock.patch.object(full,'final_client_process_census'):
                emitted,error=execute(arguments('columns-delete'),finish)
            self.assertIsInstance(error,SystemExit);self.assertEqual(error.code,0)
            self.assertEqual(host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=spec.name)[1],raw)
            for profile in ('tree-v1','tree-copy-v1','tree-sort-v1','tree-columns-move-v1','tree-columns-move-boundary-v1','tree-columns-move-tail-v1','tree-columns-clear-v1','tree-columns-clear-lifetime-v1','tree-columns-clear-metadata-v1'):
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(emitted,NONCE,hashes,modules,smoke.validate_report,profile=profile)

    def test_actual_bash_fixed_clear_setup_stage_flag_and_workflow_command(self):
        from test_native_catalog_description_rows_workflow import dispatch
        # Execute the actual bounded setup/flag fragments, never the native body.
        setup='tree_suite=false\n'+SOURCE.split('tree_suite=false\n',1)[1].split('if [ "$#" -ge 5 ]',1)[0]
        flags='tree_flag=--tree-suite\n'+SOURCE.split('tree_flag=--tree-suite\n',1)[1].split('        python3 /smoke/bootstrap/run_stage.py',1)[0]
        for token,mode in (('--tree-suite','true'),('--tree-copy-suite','copy'),('--tree-sort-suite','sort'),
                           ('--tree-columns-move-suite','columns-move'),('--tree-columns-move-boundary-suite','columns-move-boundary'),
                           ('--tree-columns-move-tail-suite','columns-move-tail'),('--tree-columns-clear-suite','columns-clear'),('--tree-columns-clear-lifetime-suite','columns-clear-lifetime'),('--tree-columns-clear-metadata-suite','columns-clear-metadata'),('--tree-columns-delete-suite','columns-delete')):
            script='set -- '+token+' --invocation-nonce '+NONCE+'\n'+setup+'printf "%s\\n" "$tree_suite" "$*"\n'+flags+'printf "%s\\n" "$tree_flag"'
            result=dispatch(script)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.splitlines(),[mode,'--full-suite --invocation-nonce '+NONCE+' --client-probe',token])
        for arguments_text in ('--tree-unknown-suite --invocation-nonce '+NONCE,
                               '--tree-columns-clear-suite --tree-columns-clear-suite --invocation-nonce '+NONCE,
                               '--tree-columns-clear-suite --tree-columns-move-suite --invocation-nonce '+NONCE):
            result=dispatch('set -- '+arguments_text+'\n'+setup+'printf "%s\\n" "$tree_suite"')
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'false')
        workflow=(ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        block=workflow.split('  tree_copy_smoke:\n',1)[1].split('  verdict:\n',1)[0]
        command=next(line.strip()[5:] for line in block.splitlines() if line.strip().startswith('run: python3 scripts/native_1c_tree_profile.py'))
        result=dispatch("TREE_PROFILE='tree-columns-clear-v1'\n"+command)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'scripts/native_1c_tree_profile.py --execute-approved-image --export-native-outputs --profile tree-columns-clear-v1')

    def test_shell_finish_passes_the_mode_after_preprocessor(self):
        self.assertIn('"$bus_cleanup_failed" "$preprocessor_measurement" "$tree_suite" <<\'PY\'',SOURCE)
        self.assertIn('if [ "$1" = --tree-columns-move-suite ]; then tree_suite=columns-move; fi',SOURCE)
        self.assertIn('if [ "$tree_suite" = columns-move ]; then tree_flag=--tree-columns-move-suite; fi',SOURCE)
        self.assertIn('if [ "$1" = --tree-columns-move-boundary-suite ]; then tree_suite=columns-move-boundary; fi',SOURCE)
        self.assertIn('if [ "$tree_suite" = columns-move-boundary ]; then tree_flag=--tree-columns-move-boundary-suite; fi',SOURCE)
        self.assertIn('if [ "$1" = --tree-columns-move-tail-suite ]; then tree_suite=columns-move-tail; fi',SOURCE)
        self.assertIn('if [ "$1" = --tree-columns-clear-suite ]; then tree_suite=columns-clear; fi',SOURCE)
        self.assertIn('if [ "$tree_suite" = columns-clear ]; then tree_flag=--tree-columns-clear-suite; fi',SOURCE)
        self.assertIn('if [ "$tree_suite" = columns-move-tail ]; then tree_flag=--tree-columns-move-tail-suite; fi',SOURCE)


if __name__=='__main__':unittest.main()
