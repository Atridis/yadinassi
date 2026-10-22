"""Offline artifact contracts; synthetic bytes are not native execution evidence."""
import contextlib
import base64
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from test_native_1c_full_host import encode, fixture, full, NONCE, smoke, validate, SyntheticFilesystemCase

PAYLOAD = b' test bytes \r\n\x00\xff\nintentional scenario error\n\n'


def accepted_report(*, mismatch=False):
    envelope, inputs, modules = fixture(PAYLOAD)
    report, _ = validate(envelope, inputs, modules)
    report.update(invocation_nonce=NONCE, container_exit_code=0,
        repository={"commit":"c"*40, "tree":"d"*40, "github_run_id":"123", "github_run_attempt":"1"},
        interpreter={"python_version":"3.12.10", "dependencies":dict(full.DEPENDENCIES),
            "source_file_count":33, "source_sha256":"e"*64, "comparison_driver_sha256":"f"*64, "map_contract_sha256":"1"*64},
        configured_timezone="Etc/UTC", configured_native_locale="ru_RU",
        native_target=full.WINDOWS_TARGET, comparison_mode=full.BYTE_EXACT,
        image=smoke.IMAGE, platform="linux/amd64", trusted_input_sha256=inputs,
        container_cleanup_verified=True, native_cases_completed=True,
        native_transport_validated=True, native_evidence_accepted=True,
        private_payloads_removed=True, windows_goldens_unchanged=True,
        comparison={"schema":2, "configured_timezone":"Etc/UTC", "configured_locale":"C.UTF-8",
            "native_target":full.WINDOWS_TARGET, "comparison_mode":full.BYTE_EXACT,
            "status":"failed" if mismatch else "ok", "acceptance_status":"rejected" if mismatch else "accepted", "cases":[
            {"name":name, "status":"mismatched" if mismatch and index == 0 else "matched",
             "failure_kind":"none", "semantic":None,
             "acceptance_status":"rejected" if mismatch and index == 0 else "accepted",
             "mismatch":full.mismatch_metadata(PAYLOAD, b"x"*len(PAYLOAD)) if mismatch and index == 0 else None,
             "native_size":len(PAYLOAD), "native_sha256":full.digest(PAYLOAD),
             "interpreter_size":len(PAYLOAD),
             "interpreter_sha256":"0"*64 if mismatch and index == 0 else full.digest(PAYLOAD)}
            for index, name in enumerate(full.SCENARIOS)]})
    return report


def artifact_files(report=None):
    return full.output_artifact_files(dict.fromkeys(full.ARTIFACT_FILES[:-1], PAYLOAD),
                                      report or accepted_report(), smoke.IMAGE)


class ManifestTests(SyntheticFilesystemCase):
    def test_exact_bytes_and_allowlisted_bounded_provenance(self):
        report = accepted_report(mismatch=True)
        report.update(raw_log="NOT ALLOWED", exception="NOT ALLOWED")
        files = artifact_files(report)
        self.assertEqual(tuple(files), full.ARTIFACT_FILES)
        self.assertTrue(all(files[name] == PAYLOAD for name in full.ARTIFACT_FILES[:-1]))
        metadata = json.loads(files["provenance.json"])
        self.assertEqual(metadata["image"], smoke.IMAGE)
        self.assertEqual(metadata["runtime_version"], smoke.EXPECTED_VERSION)
        self.assertEqual(metadata["runtime_version_source"], "SystemInfo.AppVersion")
        self.assertEqual(metadata["comparison_status"], "failed")
        self.assertEqual(metadata["repository"], report["repository"])
        self.assertEqual(metadata["configured_timezone"], "Etc/UTC")
        self.assertNotIn(b"NOT ALLOWED", files["provenance.json"])
        self.assertNotIn(b"intentional scenario error", files["provenance.json"])
        self.assertLess(len(files["provenance.json"]), full.MAX_REPORT)
        for case in metadata["cases"]:
            self.assertEqual(case["output_sha256"], full.digest(PAYLOAD))
            self.assertEqual(case["source_sha256"], report["stage3"]["input_sha256"][f'integrational_tests/tests/{case["name"]}.bsl'])

    def test_every_evidence_cleanup_and_integrity_gate_required(self):
        for gate in ("native_evidence_accepted", "native_transport_validated", "native_cases_completed",
                     "container_cleanup_verified", "private_payloads_removed", "windows_goldens_unchanged"):
            for value in (False, None, 1):
                report = accepted_report(); report[gate] = value
                with self.subTest(gate=gate, value=value), self.assertRaises(full.FullError): artifact_files(report)

    def test_invalid_provenance_or_comparison_fails_closed(self):
        edits = [lambda r:r.update(status="failed"), lambda r:r.update(container_exit_code=1),
            lambda r:r.update(runtime_version="PRIVATE"), lambda r:r.update(runtime_version_source="label"),
            lambda r:r.update(invocation_nonce="x"), lambda r:r.update(configured_timezone="Europe/Warsaw"),
            lambda r:r["repository"].update(secret="PRIVATE"), lambda r:r["repository"].update(commit="x"*40),
            lambda r:r["repository"].update(github_run_id="PRIVATE"),
            lambda r:r["interpreter"].update(source_file_count=513),
            lambda r:r["interpreter"]["dependencies"].update(tzdata="PRIVATE"),
            lambda r:r["interpreter"].update(extra="PRIVATE"),
            lambda r:r["stage3"]["cases"][0].update(output_sha256="0"*64),
            lambda r:r["stage3"]["cases"][0].update(source_sha256="0"*64),
            lambda r:r["stage3"]["cases"][0].update(module_sha256="PRIVATE"),
            lambda r:r["stage3"]["cases"].reverse(), lambda r:r["comparison"]["cases"].pop(),
            lambda r:r["comparison"]["cases"][0].update(status="error"),
            lambda r:r["comparison"]["cases"][0].update(native_sha256="0"*64),
            lambda r:r["comparison"]["cases"][0].update(interpreter_sha256="0"*64),
            lambda r:r["comparison"].update(status="failed")]
        for edit in edits:
            report = accepted_report(); edit(report)
            with self.subTest(edit=edit), self.assertRaisesRegex(full.FullError, '^native_artifact_evidence_invalid$'): artifact_files(report)

    def test_empty_capture_boolean_sizes_are_not_integer_evidence(self):
        report=accepted_report()
        for native,compared in zip(report["stage3"]["cases"],report["comparison"]["cases"]):
            native.update(output_size=False,output_sha256=full.digest(b""),message_count=0)
            compared.update(native_size=False,native_sha256=full.digest(b""),
                            interpreter_size=0,interpreter_sha256=full.digest(b""))
        with self.assertRaisesRegex(full.FullError,"^native_artifact_evidence_invalid$"):
            full.output_artifact_files(dict.fromkeys(full.ARTIFACT_FILES[:-1],b""),report,smoke.IMAGE)

    def test_capture_rechecks_exact_names_hashes_sizes_and_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = full.quarantine_outputs(Path(temporary).resolve(), dict.fromkeys(full.SCENARIOS, PAYLOAD))
            stage3 = accepted_report()["stage3"]
            self.assertEqual(full.retain_output_bytes(capture, stage3), dict.fromkeys(full.ARTIFACT_FILES[:-1], PAYLOAD))
            (capture / "extra.log").write_bytes(b"PRIVATE")
            with self.assertRaises(full.FullError): full.retain_output_bytes(capture, stage3)
            (capture / "extra.log").unlink()
            path = capture / "collections.out"; path.chmod(0o600)
            for bad in (b"changed", b"x"*(full.MAX_FILE+1)):
                path.write_bytes(bad)
                with self.assertRaises(full.FullError): full.retain_output_bytes(capture, stage3)

    def test_manifest_rejects_path_extra_payload_and_limits(self):
        for payloads in ({"../collections.out":PAYLOAD}, {**dict.fromkeys(full.ARTIFACT_FILES[:-1],PAYLOAD),"log":PAYLOAD},
                         dict.fromkeys(full.ARTIFACT_FILES[:-1],b"x"*(full.MAX_FILE+1)),
                         dict.fromkeys(full.ARTIFACT_FILES[:-1],b"x"*(full.MAX_TOTAL//6+1))):
            with self.assertRaises(full.FullError): full.output_artifact_files(payloads, accepted_report(), smoke.IMAGE)


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux descriptor and renameat2 boundary used only on Ubuntu")
class AtomicTests(unittest.TestCase):
    def test_complete_atomic_exact_files_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); files = artifact_files()
            original = full._rename_artifact_exclusive
            def promote(parent, source, destination):
                self.assertFalse((root / full.ARTIFACT_DIRECTORY).exists())
                stage = root / "native-smoke" / source
                self.assertEqual({p.name:p.read_bytes() for p in stage.iterdir()}, files)
                original(parent, source, destination)
            with mock.patch.object(full, "_rename_artifact_exclusive", side_effect=promote): full.export_output_artifact(root, files)
            target = root / full.ARTIFACT_DIRECTORY
            self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()}, files)
            full.verify_output_artifact(root, {name:full.digest(data) for name,data in files.items()})
            with self.assertRaisesRegex(full.FullError, "native_artifact_target_exists"): full.export_output_artifact(root, files)
            self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()}, files)

    def test_raced_empty_target_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); original = full._rename_artifact_exclusive; inode = []
            def race(parent, source, destination):
                target = root / full.ARTIFACT_DIRECTORY; target.mkdir(); inode.append(target.stat().st_ino)
                original(parent, source, destination)
            with mock.patch.object(full,"_rename_artifact_exclusive",side_effect=race), self.assertRaises(full.FullError): full.export_output_artifact(root,artifact_files())
            target = root / full.ARTIFACT_DIRECTORY
            self.assertEqual(target.stat().st_ino,inode[0]); self.assertEqual(list(target.iterdir()),[])
            self.assertEqual([p.name for p in target.parent.iterdir()],["native-outputs"])

    def test_parent_and_stage_swaps_cannot_claim_success_or_delete_replacements(self):
        for kind in ("parent","stage"):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve(); original=full._rename_artifact_exclusive
                def swap(parent,source,destination):
                    if kind == "parent":
                        (root/"native-smoke").rename(root/"old-parent")
                        replacement=root/full.ARTIFACT_DIRECTORY; replacement.mkdir(parents=True)
                        for name in full.ARTIFACT_FILES: (replacement/name).write_bytes(b"replacement")
                    else:
                        (root/"native-smoke"/source).rename(root/"old-stage")
                        replacement=root/"native-smoke"/source; replacement.mkdir()
                        for name in full.ARTIFACT_FILES: (replacement/name).write_bytes(b"replacement")
                    original(parent,source,destination)
                with mock.patch.object(full,"_rename_artifact_exclusive",side_effect=swap), self.assertRaises(full.FullError): full.export_output_artifact(root,artifact_files())
                # Never traverse/delete a namespace replacement while cleaning our pinned stage.
                target=root/full.ARTIFACT_DIRECTORY
                self.assertTrue(all((target/name).read_bytes()==b"replacement" for name in full.ARTIFACT_FILES))

    def test_write_readback_and_rename_failures_leave_no_partial_final(self):
        for failure in ("write","read","rename"):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve()
                patch=(mock.patch.object(full.os,"fsync",side_effect=OSError("PRIVATE")) if failure=="write" else
                       mock.patch.object(full,"read_regular",side_effect=full.FullError("invalid_private_file")) if failure=="read" else
                       mock.patch.object(full,"_rename_artifact_exclusive",side_effect=full.FullError("native_artifact_promotion_failed")))
                with patch,self.assertRaises(full.FullError) as caught: full.export_output_artifact(root,artifact_files())
                self.assertNotIn("PRIVATE",str(caught.exception)); self.assertFalse((root/full.ARTIFACT_DIRECTORY).exists())
                self.assertEqual(list((root/"native-smoke").iterdir()),[])

    def test_cleanup_fault_preserves_primary_and_closes_descriptors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); descriptors=[]; original_open=full.os.open
            def opened(*args,**kwargs):
                fd=original_open(*args,**kwargs); descriptors.append(fd); return fd
            with mock.patch.object(full.os,"open",side_effect=opened), mock.patch.object(full.os,"fsync",side_effect=OSError("PRIVATE")), \
                    mock.patch.object(full.os,"unlink",side_effect=OSError("PRIVATE cleanup")), self.assertRaises(full.FullError) as caught:
                full.export_output_artifact(root,artifact_files())
            self.assertEqual(str(caught.exception),"native_artifact_export_failed")
            self.assertEqual(caught.exception.cleanup_error,"native_artifact_cleanup_unverified")
            self.assertFalse((root/full.ARTIFACT_DIRECTORY).exists())
            for fd in set(descriptors):
                with self.assertRaises(OSError): os.fstat(fd)

    def test_links_special_files_and_visible_final_tampering_rejected(self):
        for kind in ("symlink","hardlink","fifo"):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve(); capture=full.quarantine_outputs(root,dict.fromkeys(full.SCENARIOS,PAYLOAD))
                selected=capture/"collections.out"; selected.unlink(); other=root/"other"; other.write_bytes(PAYLOAD)
                if kind=="symlink": selected.symlink_to(other)
                elif kind=="hardlink": os.link(other,selected)
                else: os.mkfifo(selected)
                with self.assertRaises(full.FullError): full.retain_output_bytes(capture,accepted_report()["stage3"])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); outside=root/"outside"; outside.mkdir()
            (root/"native-smoke").symlink_to(outside,target_is_directory=True)
            with self.assertRaises(full.FullError): full.export_output_artifact(root,artifact_files())
            self.assertEqual(list(outside.iterdir()),[]); (root/"native-smoke").unlink()
            files=artifact_files(); full.export_output_artifact(root,files)
            path=root/full.ARTIFACT_DIRECTORY/"collections.out"; path.chmod(0o600); path.write_bytes(b"changed")
            with self.assertRaises(full.FullError): full.verify_output_artifact(root,{n:full.digest(b) for n,b in files.items()})


class OrchestrationTests(SyntheticFilesystemCase):
    def invoke(self,*,opt_in=True,mismatch=False,cleanup_bad=False,golden_changed=False,private_cleanup_bad=False,tamper=False,
               post_create=None,through_main=False,final_changed=False,comparison_mode=full.BYTE_EXACT,
               collections_payload=None):
        operations=[]; exported=[]; retained=[]; original_retain=full.retain_output_bytes
        original_temporary=tempfile.TemporaryDirectory; good=accepted_report(mismatch=mismatch)
        original_compare=full.compare_outputs; original_export=full.export_output_artifact
        original_verify=full.verify_output_artifact; final_verifications=[]
        def silent(args,env,seconds,input_bytes=None): operations.append(args[1])
        def bounded(args,env,seconds,limit=smoke.MAX_OUTPUT):
            operations.append(args[1])
            if args[1]=="image": return 0,b"linux/amd64|0\n"
            if args[1]=="ps": return (0,b"exists") if cleanup_bad else (0,b"")
            directory=Path(args[args.index("--mount")+1].split("src=",1)[1].split(",dst=",1)[0])
            inputs={src:full.digest((directory/dst).read_bytes()) for src,dst in smoke.FULL_STAGED_FILES.items()}
            modules={name:full.digest(full.generated_module((directory/f"scenarios/{name}.bsl").read_bytes())) for name in full.SCENARIOS}
            data=fixture(PAYLOAD,input_hashes=inputs,modules=modules)[0]; data["nonce"]=data["report"]["stage3"]["nonce"]=args[-1]
            if post_create is not None:
                replacements={2:post_create[0]}
                if collections_payload is not None: replacements[0]=collections_payload
                for index,payload in replacements.items():
                    data["report"]["stage3"]["cases"][index].update(output_sha256=full.digest(payload),
                        output_size=len(payload),message_count=payload.count(b"\n"))
                    data["outputs"][index].update(sha256=full.digest(payload),size=len(payload),
                        data_b64=base64.b64encode(payload).decode("ascii"))
            return 0,encode(data)
        def compare(root,capture,stage3,inputs,**kwargs):
            self.assertEqual(operations[-1],"ps"); self.assertTrue(capture.is_dir())
            if tamper:
                path=capture/"collections.out"; path.chmod(0o600); path.write_bytes(b"changed")
            if post_create is not None:
                return original_compare(root,capture,stage3,inputs,runner=lambda args,cwd:
                    post_create[1] if Path(args[-2]).stem == "functions" else
                    (0,collections_payload if Path(args[-2]).stem == "collections" and collections_payload is not None
                     else PAYLOAD,b""),**kwargs)
            return good["comparison"]
        def retain(capture,stage3): retained.append(capture); return original_retain(capture,stage3)
        def export(root,files):
            self.assertTrue(all(not path.exists() for path in retained)); self.assertEqual(list(temp_path.iterdir()),[])
            self.assertEqual(tuple(files),full.ARTIFACT_FILES); exported.append(files)
            if through_main:
                original_export(artifact_root,files)
                if final_changed:
                    path=artifact_root/full.ARTIFACT_DIRECTORY/"functions.out"
                    path.chmod(0o600); path.write_bytes(b"changed after export")
        def verify(root,hashes):
            final_verifications.append(hashes)
            original_verify(artifact_root,hashes)
        class BrokenCleanup:
            def __init__(self,**kwargs): self.context=original_temporary(**kwargs)
            def __enter__(self): return self.context.__enter__()
            def __exit__(self,*args): self.context.__exit__(*args); raise OSError("PRIVATE CLEANUP")
        with original_temporary() as temporary,original_temporary() as artifacts:
            temp_path=Path(temporary).resolve()
            artifact_root=Path(artifacts).resolve()
            with mock.patch.dict(os.environ,{"GHCR_USER":"Atridis","GHCR_TOKEN":"PRIVATE TOKEN"}), \
                    mock.patch.object(smoke,"run_silent",side_effect=silent),mock.patch.object(smoke,"bounded_run",side_effect=bounded), \
                    mock.patch.object(full,"repository_provenance",return_value=good["repository"]), \
                    mock.patch.object(full,"interpreter_provenance",return_value=good["interpreter"]), \
                    mock.patch.object(full,"windows_fingerprints",side_effect=[{"old":"a"},{"old":"b" if golden_changed else "a"},{"old":"a"}]), \
                    mock.patch.object(full,"compare_outputs",side_effect=compare),mock.patch.object(full,"retain_output_bytes",side_effect=retain), \
                    mock.patch.object(full,"export_output_artifact",side_effect=export), \
                    mock.patch.object(full,"verify_output_artifact",side_effect=verify), \
                    mock.patch.object(smoke.tempfile,"TemporaryDirectory",BrokenCleanup if private_cleanup_bad else original_temporary):
                if through_main:
                    output=artifact_root/"action-output"; summary=artifact_root/"summary.json"
                    args=["--execute-approved-image","--full-suite","--output",str(summary)]
                    if opt_in: args.append("--export-native-outputs")
                    if comparison_mode == full.MAP_MODE:
                        args += ["--native-target",full.LINUX_TARGET,"--comparison-mode",comparison_mode]
                    with mock.patch.dict(os.environ,{"RUNNER_TEMP":str(temp_path),"GITHUB_OUTPUT":str(output)}), \
                            contextlib.redirect_stdout(io.StringIO()):
                        code=smoke.main(args)
                    result={"exit_code":code,"summary":json.loads(summary.read_text()),
                            "ready":output.read_text() if output.exists() else "",
                            "final_verifications":len(final_verifications)}
                else:
                    try: result=smoke.run_smoke(temp_path,full_suite=True,export_native_outputs=opt_in,
                        native_target=full.LINUX_TARGET if comparison_mode == full.MAP_MODE else full.WINDOWS_TARGET,
                        comparison_mode=comparison_mode)
                    except smoke.SmokeError as error: result=error
            self.assertEqual(list(temp_path.iterdir()),[])
        return result,exported,retained

    def test_opt_in_exports_after_private_cleanup_mismatch_stays_failure(self):
        for mismatch in (False,True):
            report,exported,retained=self.invoke(mismatch=mismatch)
            self.assertEqual((len(exported),len(retained)),(1,1)); self.assertTrue(report["native_output_artifact_ready"])
            self.assertEqual(report["comparison"]["status"],"failed" if mismatch else "ok")

    def test_default_never_retains_or_exports(self):
        report,exported,retained=self.invoke(opt_in=False)
        self.assertEqual((exported,retained),([],[])); self.assertNotIn("native_output_artifact_ready",report)

    def test_cleanup_golden_and_capture_failures_never_export(self):
        for key in ("cleanup_bad","golden_changed","private_cleanup_bad","tamper"):
            result,exported,_=self.invoke(**{key:True})
            self.assertIsInstance(result,smoke.SmokeError); self.assertEqual(exported,[]); self.assertNotIn("PRIVATE",str(result))

    def test_main_ready_signal_requires_opt_in_and_final_verification(self):
        for enabled,changed in ((False,False),(True,False),(True,True)):
            report=accepted_report(mismatch=True); report["native_output_artifact_ready"]=True
            report["native_output_artifact_sha256"]={n:full.digest(b) for n,b in artifact_files(report).items()}
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve(); output=root/"action-output"; summary=root/"summary.json"
                args=["--execute-approved-image","--full-suite","--output",str(summary)]+(["--export-native-outputs"] if enabled else [])
                with mock.patch.object(smoke,"run_smoke",return_value=report),mock.patch.dict(os.environ,{"GITHUB_OUTPUT":str(output)}), \
                        mock.patch.object(full,"verify_output_artifact",side_effect=full.FullError("native_artifact_final_verification_failed") if changed else None) as verify, \
                        contextlib.redirect_stdout(io.StringIO()): self.assertEqual(smoke.main(args),1)
                self.assertEqual(output.read_text() if output.exists() else "","native_outputs_ready=true\n" if enabled and not changed else "")
                self.assertFalse(json.loads(summary.read_text())["smoke_completed"])
                self.assertEqual(verify.call_count,1 if enabled else 0)

    def test_oversized_summary_never_signals_upload_readiness(self):
        report = accepted_report()
        report["native_output_artifact_ready"] = True
        report["oversized"] = "x" * smoke.MAX_OUTPUT
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with mock.patch.object(smoke, "run_smoke", return_value=report), \
                    mock.patch.dict(os.environ, {"GITHUB_OUTPUT":str(root / "ready")}), \
                    mock.patch.object(full, "verify_output_artifact") as verify, \
                    contextlib.redirect_stdout(io.StringIO()):
                result = smoke.main(["--execute-approved-image", "--full-suite", "--export-native-outputs",
                                     "--output", str(root / "summary.json")])
            self.assertEqual(result, 1)
            self.assertFalse((root / "ready").exists())
            self.assertEqual(json.loads((root / "summary.json").read_text())["error"], "public_report_limit")
            self.assertLess((root / "summary.json").stat().st_size, smoke.MAX_OUTPUT)
            verify.assert_not_called()

    def test_invalid_mode_never_invokes_image(self):
        with mock.patch.object(smoke,"run_smoke") as run,contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            smoke.main(["--execute-approved-image","--export-native-outputs"])
        run.assert_not_called()

    def test_workflow_seven_literals_and_explicit_ready_gate(self):
        text=(smoke.ROOT/".github/workflows/native-1c-isolated-smoke.yml").read_text()
        section=text.split("- name: Upload explicitly approved exact native test outputs",1)[1]
        self.assertIn("--export-native-outputs",text); self.assertIn("steps.native.outputs.native_outputs_ready == 'true'",section)
        self.assertIn("name: native-1c-six-scenario-outputs",section); self.assertIn("retention-days: 7",section)
        block=section.split("path: |\n",1)[1].split("          if-no-files-found:",1)[0]
        self.assertEqual([line.strip() for line in block.splitlines()],[full.ARTIFACT_DIRECTORY+"/"+name for name in full.ARTIFACT_FILES])
        self.assertNotIn("*",block)


def semantic_report(*, equal=False):
    report = accepted_report(mismatch=not equal)
    report.update(native_target=full.LINUX_TARGET, comparison_mode=full.MAP_MODE)
    source_key = "integrational_tests/tests/collections.bsl"
    report["stage3"]["input_sha256"][source_key] = full.COLLECTIONS_SOURCE_SHA256
    report["stage3"]["cases"][0]["source_sha256"] = full.COLLECTIONS_SOURCE_SHA256
    report["trusted_input_sha256"] = dict(report["stage3"]["input_sha256"])
    comparison = report["comparison"]
    comparison.update(native_target=full.LINUX_TARGET, comparison_mode=full.MAP_MODE,
                      acceptance_status="accepted")
    comparison["cases"][0].update(acceptance_status="accepted", semantic={
        "status":"equivalent", "profile":full.MAP_MODE, "records":841,
        "byte_equal_records":841 if equal else 840,
        "accepted_labels":[] if equal else [full.map_contract().ELIGIBLE_LABELS[0]], "reason":"none"})
    return report


class SemanticManifestTests(SyntheticFilesystemCase):
    def test_typed_manifest_records_acceptance_without_relabeling_raw_difference(self):
        report=semantic_report()
        files=artifact_files(report)
        manifest=json.loads(files["provenance.json"])
        self.assertEqual(tuple(files),full.ARTIFACT_FILES)
        self.assertEqual(manifest["schema"],"native-1c-outputs-v2")
        self.assertEqual(manifest["native_target"],full.LINUX_TARGET)
        self.assertEqual(manifest["comparison_mode"],full.MAP_MODE)
        self.assertEqual(manifest["acceptance_status"],"accepted")
        self.assertEqual(manifest["comparison_status"],"failed")
        self.assertEqual(manifest["cases"][0]["comparison_status"],"mismatched")
        self.assertEqual(manifest["cases"][0]["mismatch"],report["comparison"]["cases"][0]["mismatch"])
        self.assertEqual(manifest["interpreter"]["map_contract_sha256"],report["interpreter"]["map_contract_sha256"])
        self.assertEqual(files["collections.out"],PAYLOAD)
        self.assertTrue(all(case["semantic"] is None for case in manifest["cases"][1:]))

    def test_manifest_rejects_missing_inconsistent_stale_and_unbounded_claims(self):
        edits=[lambda r:r.pop("comparison_mode"),lambda r:r.update(native_target=full.WINDOWS_TARGET),
            lambda r:r.update(comparison_mode="typed-map-order-v2"),lambda r:r.update(platform="linux/arm64"),
            lambda r:r.update(image=smoke.IMAGE[:-1]+"0"),lambda r:r.update(runtime_version="8.3.27.2342"),
            lambda r:r["stage2"].update(actual_version="8.3.27.2342"),
            lambda r:r["interpreter"].pop("map_contract_sha256"),lambda r:r["interpreter"].update(map_contract_sha256="PRIVATE"),
            lambda r:r["comparison"].pop("acceptance_status"),lambda r:r["comparison"].update(acceptance_status="rejected"),
            lambda r:r["comparison"]["cases"][0].pop("semantic"),lambda r:r["comparison"]["cases"][0].update(semantic=None),
            lambda r:r["comparison"]["cases"][0]["semantic"].update(records=840),
            lambda r:r["comparison"]["cases"][0]["semantic"].update(accepted_labels=["PRIVATE"]),
            lambda r:r["comparison"]["cases"][0]["semantic"].update(extra="PRIVATE"),
            lambda r:r["comparison"]["cases"][1].update(semantic=r["comparison"]["cases"][0]["semantic"]),
            lambda r:r["comparison"]["cases"][0].update(mismatch=None),
            lambda r:r["stage3"]["input_sha256"].update({"integrational_tests/tests/collections.bsl":"a"*64}),
            lambda r:r.update(container_cleanup_verified=False),lambda r:r.update(private_payloads_removed=False),
            lambda r:r.update(native_transport_validated=False)]
        for edit in edits:
            report=semantic_report();edit(report)
            with self.subTest(edit=edit),self.assertRaisesRegex(full.FullError,"^native_artifact_evidence_invalid$"):
                artifact_files(report)

    def test_typed_main_success_reports_raw_mismatch_and_separate_acceptance(self):
        report=semantic_report()
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"report.json"
            with mock.patch.object(smoke,"run_smoke",return_value=report),contextlib.redirect_stdout(io.StringIO()):
                code=smoke.main(["--execute-approved-image","--full-suite","--native-target",full.LINUX_TARGET,
                                 "--comparison-mode",full.MAP_MODE,"--output",str(output)])
            public=json.loads(output.read_text())
        self.assertEqual(code,0)
        self.assertTrue(public["smoke_completed"])
        self.assertTrue(public["interpreter_acceptance_completed"])
        self.assertFalse(public["interpreter_comparison_completed"])
        self.assertEqual(public["probe"]["comparison"]["status"],"failed")

    def test_main_rejects_unvalidated_or_cleanup_failed_semantic_acceptance(self):
        for mutate in (lambda r:r["comparison"]["cases"][0].update(semantic=None),
                       lambda r:r.update(container_cleanup_verified=False),
                       lambda r:r.update(private_payloads_removed=False),
                       lambda r:r["comparison"].update(comparison_mode=full.BYTE_EXACT)):
            report=semantic_report();mutate(report)
            with tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary)/"report.json"
                with mock.patch.object(smoke,"run_smoke",return_value=report),contextlib.redirect_stdout(io.StringIO()):
                    code=smoke.main(["--execute-approved-image","--full-suite","--native-target",full.LINUX_TARGET,
                                    "--comparison-mode",full.MAP_MODE,"--output",str(output)])
                public=json.loads(output.read_text())
            self.assertEqual(code,1)
            self.assertFalse(public["smoke_completed"])
            self.assertFalse(public["interpreter_acceptance_completed"])

    def test_main_requires_exact_postcleanup_booleans_not_truthy_values(self):
        for key in ("private_payloads_removed","windows_goldens_unchanged"):
            for value in (1,"false",None):
                report=semantic_report();report[key]=value
                with tempfile.TemporaryDirectory() as temporary:
                    output=Path(temporary)/"report.json"
                    with mock.patch.object(smoke,"run_smoke",return_value=report),contextlib.redirect_stdout(io.StringIO()):
                        code=smoke.main(["--execute-approved-image","--full-suite","--native-target",full.LINUX_TARGET,
                            "--comparison-mode",full.MAP_MODE,"--output",str(output)])
                    public=json.loads(output.read_text())
                with self.subTest(key=key,value=value):
                    self.assertEqual(code,1)
                    self.assertFalse(public["smoke_completed"])
                    self.assertFalse(public["interpreter_acceptance_completed"])

    def test_invalid_semantic_claim_cannot_keep_artifact_ready_signal(self):
        for mutate in (lambda r:r["comparison"]["cases"][0].update(semantic=None),
                       lambda r:r.update(private_payloads_removed=False)):
            report=semantic_report();report["native_output_artifact_ready"]=True;mutate(report)
            with tempfile.TemporaryDirectory() as temporary:
                output=Path(temporary)/"report.json";ready=Path(temporary)/"ready"
                with mock.patch.object(smoke,"run_smoke",return_value=report), \
                        mock.patch.object(full,"verify_output_artifact") as verify, \
                        mock.patch.dict(os.environ,{"GITHUB_OUTPUT":str(ready)}),contextlib.redirect_stdout(io.StringIO()):
                    code=smoke.main(["--execute-approved-image","--full-suite","--export-native-outputs",
                        "--native-target",full.LINUX_TARGET,"--comparison-mode",full.MAP_MODE,"--output",str(output)])
                self.assertEqual(code,1)
                self.assertFalse(json.loads(output.read_text())["probe"]["native_output_artifact_ready"])
                self.assertFalse(ready.exists());verify.assert_not_called()

    def test_cli_defaults_remain_windows_byte_exact_and_invalid_combination_never_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(smoke,"run_smoke",return_value=accepted_report()) as run,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(smoke.main(["--execute-approved-image","--full-suite","--output",str(Path(temporary)/"report.json")]),0)
            self.assertEqual(run.call_args.kwargs["native_target"],full.WINDOWS_TARGET)
            self.assertEqual(run.call_args.kwargs["comparison_mode"],full.BYTE_EXACT)
        for args in (["--full-suite","--comparison-mode",full.MAP_MODE],
                     ["--native-target",full.LINUX_TARGET],
                     ["--full-suite","--native-target","auto"],
                     ["--full-suite","--comparison-mode","typed-map-order-v2"]):
            with mock.patch.object(smoke,"run_smoke") as run,contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                smoke.main(["--execute-approved-image",*args])
            run.assert_not_called()


if __name__ == "__main__": unittest.main()
