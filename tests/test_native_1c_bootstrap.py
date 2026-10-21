import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/native_1c_bootstrap"))
from inject_modules import DraftError, MODULES, PROTOCOL, bsl_string, hashes, inject, inspect_native_dump
from evidence_gates import require_epf, require_marker_pair, require_reimported_modules, require_zero_result

RUN = "1234567890abcdef1234567890abcdef"
USER = "NativeSmoke"


class DraftTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "native"
        self.source.mkdir()
        shutil.copyfile(Path(__file__).parent / "fixtures/native_bootstrap/Configuration.xml", self.source / "Configuration.xml")
        (self.source / "ConfigDumpInfo.xml").write_bytes(b"opaque native dump info\r\n")
        self.output = self.root / "injected"

    def inject(self, **extra):
        options = dict(run_id=RUN, user=USER, evidence="/work/evidence/" + RUN)
        options.update(extra)
        return inject(self.source, self.output, **options)

    def replace_xml(self, old, new):
        path = self.source / "Configuration.xml"
        path.write_text(path.read_text().replace(old, new))

    def test_transform_preserves_all_original_bytes_and_only_adds_two_modules(self):
        before = hashes(self.source)
        manifest = self.inject()
        self.assertEqual(before, hashes(self.source))
        self.assertEqual(set(hashes(self.output)) - set(before), {"Ext/" + n for n in MODULES})
        for name, digest in before.items():
            self.assertEqual(digest, hashes(self.output)[name])
        self.assertEqual(manifest["native"]["format_version"], "2.20")
        self.assertIs(manifest["native_runtime_tested"], False)
        for name in MODULES:
            text = (self.output / "Ext" / name).read_text(encoding="utf-8-sig")
            self.assertNotIn("@@", text)
            self.assertIn(RUN, text)

    def test_retains_actual_format_instead_of_forcing_version(self):
        self.replace_xml('version="2.20"', 'version="2.21"')
        self.assertEqual(self.inject()["native"]["format_version"], "2.21")

    def test_namespace_prefix_is_not_assumed(self):
        xml = self.source / "Configuration.xml"
        xml.write_text(xml.read_text().replace('xmlns="', 'xmlns:m="').replace("<MetaDataObject", "<m:MetaDataObject").replace("</MetaDataObject", "</m:MetaDataObject"))
        self.assertEqual(inspect_native_dump(self.source)["default_run_mode"], "ManagedApplication")

    def test_reject_nonmanaged_without_rewriting(self):
        self.replace_xml("ManagedApplication", "OrdinaryApplication")
        with self.assertRaises(DraftError): self.inject()
        self.assertFalse(self.output.exists())

    def test_reject_roles_and_objects(self):
        for child in ("Role", "CommonModule", "Catalog"):
            with self.subTest(child=child):
                xml = self.source / "Configuration.xml"
                original = xml.read_bytes()
                self.replace_xml("</ChildObjects>", f"<{child}>Unexpected</{child}></ChildObjects>")
                with self.assertRaises(DraftError): self.inject()
                xml.write_bytes(original)

    def test_reject_nonempty_default_roles(self):
        self.replace_xml("<DefaultRoles/>", "<DefaultRoles><Item>Admin</Item></DefaultRoles>")
        with self.assertRaises(DraftError): self.inject()

    def test_refuses_existing_modules_even_empty(self):
        (self.source / "Ext").mkdir()
        (self.source / "Ext/SessionModule.bsl").touch()
        with self.assertRaises(DraftError): self.inject()

    @unittest.skipIf(os.name == "nt", "Creating Windows symlinks may need extra privileges")
    def test_refuses_symlinks(self):
        (self.source / "linked").symlink_to(self.root)
        with self.assertRaises(DraftError): self.inject()

    def test_refuses_dtd(self):
        self.replace_xml("<!-- SYNTHETIC", '<!DOCTYPE x [<!ENTITY y "z">]>\n<!-- SYNTHETIC')
        with self.assertRaises(DraftError): self.inject()

    def test_refuses_existing_and_overlapping_destination(self):
        self.output.mkdir()
        with self.assertRaises(DraftError): self.inject()
        self.output = self.source / "child"
        with self.assertRaises(DraftError): self.inject()

    def test_rejects_bad_parameters_and_escapes_quotes(self):
        for extra in ({"run_id": "stale"}, {"user": "A\nB"}, {"evidence": "/work/../real"}, {"evidence": "relative"}):
            with self.subTest(extra=extra), self.assertRaises(DraftError): self.inject(**extra)
        self.assertEqual(bsl_string('A"B'), '"A""B"')

    def test_placeholder_text_in_value_is_not_substituted_recursively(self):
        self.inject(evidence="/work/@@BOOTSTRAP_TOKEN@@")
        text = (self.output / "Ext/SessionModule.bsl").read_text(encoding="utf-8-sig")
        self.assertIn('Корень = "/work/@@BOOTSTRAP_TOKEN@@";', text)

    def test_rejects_any_existing_bsl_not_only_injected_modules(self):
        ext = self.source / "Ext"
        ext.mkdir()
        (ext / "ExternalConnectionModule.bsl").write_text("// unexpected")
        with self.assertRaises(DraftError): self.inject()

    def test_marker_schema_and_anonymous_identity_are_strict(self):
        for stage in ("bootstrap", "verify"):
            server, client = self.markers(stage)
            server["unexpected"] = "private data"
            self.write_markers(server, client, stage)
            with self.assertRaises(DraftError): self.verify(stage)
        server, client = self.markers("bootstrap")
        server["current_user_at_start"] = "UnexpectedNamedIdentity"
        self.write_markers(server, client, "bootstrap")
        with self.assertRaises(DraftError): self.verify("bootstrap")

    def test_redump_requires_both_unchanged_modules(self):
        self.inject()
        redump = self.root / "redump"
        shutil.copytree(self.output, redump)
        require_reimported_modules(self.output, redump)
        (redump / "Ext/SessionModule.bsl").write_text("// lost module")
        with self.assertRaises(DraftError): require_reimported_modules(self.output, redump)

    def test_dump_result_and_epf_are_independent_required_gates(self):
        result = self.root / "result.txt"
        for data in (b"0\n", "0\r\n".encode("utf-16")):
            result.write_bytes(data)
            require_zero_result(result, 0)
        for data in (b"1", b"", b"OK", b"0 error"):
            result.write_bytes(data)
            with self.assertRaises(DraftError): require_zero_result(result, 0)
        result.write_bytes(b"0")
        with self.assertRaises(DraftError): require_zero_result(result, 1)
        with self.assertRaises(DraftError): require_zero_result(result, 0, timed_out=True)
        epf = self.root / "Launcher.epf"
        with self.assertRaises(DraftError): require_epf(epf)
        epf.touch()
        with self.assertRaises(DraftError): require_epf(epf)
        epf.write_bytes(b"fixture only")
        require_epf(epf)

    def markers(self, stage="verify"):
        common = dict(protocol=PROTOCOL, run_id=RUN, stage=stage, user=USER, status="ok", error="")
        server = dict(common, hook="session", users_before=1 if stage == "verify" else 0,
                      users_after=1, persisted_user=USER, protection_type="Boolean",
                      persisted_protection=False, standard_authentication=True,
                      current_user_at_start=USER if stage == "verify" else "",
                      current_protection_verified=stage == "verify")
        if stage == "verify": server["current_protection"] = False
        client = dict(common, hook="managed", actual_version="8.3.27.1508", server_hook_verified=True)
        self.write_markers(server, client, stage)
        return server, client

    def write_markers(self, server, client, stage="verify"):
        (self.root / (stage + "-session.json")).write_text(json.dumps(server))
        (self.root / (stage + "-managed.json")).write_text(json.dumps(client))

    def verify(self, stage="verify", **extra):
        return require_marker_pair(self.root, stage, RUN, USER, returncode=0, **extra)

    def test_both_positive_marker_pairs(self):
        for stage in ("bootstrap", "verify"):
            self.markers(stage)
            self.assertEqual(self.verify(stage)["actual_version"], "8.3.27.1508")

    def test_rejects_false_success_cases(self):
        cases = [("persisted_protection", 0), ("persisted_protection", "false"),
                 ("current_protection", True), ("current_user_at_start", "WrongUser"),
                 ("current_protection_verified", 1), ("run_id", "old"),
                 ("status", "error"), ("error", "compile failed"), ("users_after", True),
                 ("protection_type", "UnsafeOperationProtectionDescription")]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                server, client = self.markers()
                server[key] = value
                self.write_markers(server, client)
                with self.assertRaises(DraftError): self.verify()

    def test_rejects_missing_hooks_wrong_version_or_timeout(self):
        server, client = self.markers()
        (self.root / "verify-session.json").unlink()
        with self.assertRaises(DraftError): self.verify()
        client["actual_version"] = "8.3.26.0000"
        self.write_markers(server, client)
        with self.assertRaises(DraftError): self.verify()
        self.markers()
        with self.assertRaises(DraftError): self.verify(timed_out=True)

    def test_rejects_oversized_and_duplicate_key_markers(self):
        self.markers()
        path = self.root / "verify-managed.json"
        path.write_text('{"status":"error","status":"ok"}')
        with self.assertRaises(DraftError): self.verify()
        path.write_bytes(b" " * 65537)
        with self.assertRaises(DraftError): self.verify()

    def test_modules_leave_client_server_boundaries_and_regular_launcher_intact(self):
        self.inject()
        client = (self.output / "Ext/ManagedApplicationModule.bsl").read_text(encoding="utf-8-sig")
        server = (self.output / "Ext/SessionModule.bsl").read_text(encoding="utf-8-sig")
        self.assertNotIn("ПользователиИнформационнойБазы.", client)
        self.assertNotIn("ПараметрЗапуска", server)
        self.assertIn("ТребуемыеПараметры <> Неопределено", server)
        self.assertIn("Версия = Информация.ВерсияПриложения", client)
        self.assertIn("Иначе\n        // The existing EPF launcher", client)


if __name__ == "__main__":
    unittest.main()
