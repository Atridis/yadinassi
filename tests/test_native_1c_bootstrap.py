import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/native_1c_bootstrap"))
from inject_modules import (DraftError, MODULES, PROTOCOL, ROLE_NAME, ROLE_RIGHTS, ROLE_FILES,
                            add_role_reference, bsl_string, hashes, inject, inspect_native_dump,
                            inspect_disposable_role)
from evidence_gates import (require_epf, require_marker_pair, require_reimported_modules,
                            require_reimported_metadata, require_zero_result)

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

    def test_transform_preserves_native_bytes_except_exact_role_reference(self):
        before = hashes(self.source)
        manifest = self.inject()
        self.assertEqual(before, hashes(self.source))
        self.assertEqual(set(hashes(self.output)) - set(before), {"Ext/" + n for n in MODULES} | set(ROLE_FILES))
        for name, digest in before.items():
            if name != "Configuration.xml":
                self.assertEqual(digest, hashes(self.output)[name])
        original = (self.source / "Configuration.xml").read_bytes()
        self.assertEqual((self.output / "Configuration.xml").read_bytes(),
                         original.replace(b"<ChildObjects>", ("<ChildObjects><Role>" + ROLE_NAME + "</Role>").encode()))
        self.assertEqual(manifest["injected_role"]["rights"], sorted(ROLE_RIGHTS))
        inspect_disposable_role(self.output)
        self.assertEqual(manifest["native"]["format_version"], "2.20")
        self.assertIs(manifest["native_runtime_tested"], False)
        for name in MODULES:
            text = (self.output / "Ext" / name).read_text(encoding="utf-8-sig")
            self.assertNotIn("@@", text)
            self.assertIn(RUN, text)

    def test_retains_actual_format_instead_of_forcing_version(self):
        self.replace_xml('version="2.20"', 'version="2.21"')
        self.assertEqual(inspect_native_dump(self.source)["format_version"], "2.21")
        original = hashes(self.source)
        with self.assertRaises(DraftError): self.inject()
        self.assertEqual(hashes(self.source), original)
        self.assertFalse(self.output.exists())

    def test_namespace_prefix_is_not_assumed(self):
        xml = self.source / "Configuration.xml"
        text = xml.read_text().replace('xmlns="', 'xmlns:m="')
        xml.write_text(re.sub(r"<(\/?)([A-Za-z][A-Za-z0-9]*)(?=[\s/>])", r"<\1m:\2", text))
        self.assertEqual(inspect_native_dump(self.source)["default_run_mode"], "ManagedApplication")
        self.inject()
        self.assertIn(("<m:Role>" + ROLE_NAME + "</m:Role>").encode(),
                      (self.output / "Configuration.xml").read_bytes())

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

    def test_empty_child_objects_is_expanded_without_other_byte_changes(self):
        self.replace_xml("<ChildObjects><Language>Russian</Language></ChildObjects>", "<ChildObjects />")
        original = (self.source / "Configuration.xml").read_bytes()
        self.inject()
        self.assertEqual((self.output / "Configuration.xml").read_bytes(),
                         original.replace(b"<ChildObjects />", ("<ChildObjects ><Role>" + ROLE_NAME + "</Role></ChildObjects>").encode()))

    def test_byte_insertion_ignores_comment_decoys_and_preserves_bom_crlf(self):
        path = self.source / "Configuration.xml"
        text = path.read_text().replace("<!-- SYNTHETIC", "<!-- <ChildObjects/> decoy -->\n<!-- SYNTHETIC")
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8-sig"))
        original = path.read_bytes()
        self.inject()
        self.assertEqual((self.output / "Configuration.xml").read_bytes(),
                         original.replace(b"<ChildObjects>", ("<ChildObjects><Role>" + ROLE_NAME + "</Role>").encode()))

    def test_role_uuid_is_new_without_changing_native_identity(self):
        self.inject()
        first = (self.output / ROLE_FILES[0]).read_bytes()
        self.output = self.root / "second"
        self.inject()
        self.assertNotEqual(first, (self.output / ROLE_FILES[0]).read_bytes())
        source_uuid = inspect_native_dump(self.source)["configuration_uuid"]
        self.assertIn(source_uuid.encode(), (self.output / "Configuration.xml").read_bytes())
        self.assertNotIn(source_uuid.encode(), (self.output / ROLE_FILES[0]).read_bytes())

    def test_strict_metadata_roundtrip_and_rights_rejection(self):
        self.inject()
        redump = self.root / "redump"
        shutil.copytree(self.output, redump)
        require_reimported_metadata(self.output, redump)
        mutations = [
            (ROLE_FILES[1], "<setForNewObjects>false", "<setForNewObjects>true"),
            (ROLE_FILES[1], "<setForAttributesByDefault>false", "<setForAttributesByDefault>true"),
            (ROLE_FILES[1], "<independentRightsOfChildObjects>false", "<independentRightsOfChildObjects>true"),
            (ROLE_FILES[1], "<name>ThickClient</name>", "<name>ThinClient</name>"),
            (ROLE_FILES[1], "<name>ThickClient</name>", "<name>Administration</name>"),
            (ROLE_FILES[1], "<value>true</value>", "<value>false</value>"),
            (ROLE_FILES[1], "Configuration.DisposableFixture", "Configuration.Other"),
            (ROLE_FILES[1], "</object>", "<right><name>FullAccess</name><value>true</value></right></object>"),
            (ROLE_FILES[1], "</Rights>", "<object><name>Catalog.Any</name></object></Rights>"),
            (ROLE_FILES[1], "</Rights>", "<restrictions/></Rights>"),
            (ROLE_FILES[0], "<Name>" + ROLE_NAME, "<Name>Other"),
            ("Configuration.xml", "<DefaultRoles/>", "<DefaultRoles><Item>" + ROLE_NAME + "</Item></DefaultRoles>"),
            ("Configuration.xml", "<Language>Russian</Language>", "<Language>English</Language>"),
            ("Configuration.xml", "bd3814ed-1b7c-4f56-96b3-620fc5e32c44", "bd3814ed-1b7c-4f56-96b3-620fc5e32c45"),
            ("Configuration.xml", "</ChildObjects>", "<Role>Other</Role></ChildObjects>"),
        ]
        for name, before, after in mutations:
            with self.subTest(name=name, after=after):
                path = redump / name
                original = path.read_bytes()
                text = original.decode("utf-8-sig")
                self.assertIn(before, text)
                path.write_text(text.replace(before, after), encoding="utf-8")
                with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)
                path.write_bytes(original)
        for name in ("Roles/Unexpected.xml", "Ext/Unexpected.bsl", "Unexpected.xml"):
            path = redump / name
            path.write_text("unexpected")
            with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)
            path.unlink()
        unexpected = redump / "UnexpectedEmptyDirectory"
        unexpected.mkdir()
        with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)
        unexpected.rmdir()
        for name in ROLE_FILES:
            path = redump / name
            original = path.read_bytes()
            path.unlink()
            with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)
            path.write_bytes(original)

    def test_role_xml_guards_reject_unreviewed_structure_and_excessive_input(self):
        self.inject()
        redump = self.root / "redump"
        shutil.copytree(self.output, redump)
        for name, mutate in (
            (ROLE_FILES[1], lambda text: text.replace('version="2.20"', 'version="2.21"')),
            (ROLE_FILES[1], lambda text: text.replace('xsi:type="Rights"', 'xsi:type="Other"')),
            (ROLE_FILES[1], lambda text: text.replace('xmlns="http://v8.1c.ru/8.2/roles"', 'xmlns="https://unexpected.invalid/roles"')),
            (ROLE_FILES[1], lambda text: text.replace('<object>', '<object unexpected="true">')),
            (ROLE_FILES[1], lambda text: text.replace('<right>', '<right unexpected="true">')),
            (ROLE_FILES[1], lambda text: text.replace('<name>ThickClient</name>', '<name>ThickClient<extra/></name>')),
            (ROLE_FILES[1], lambda text: text.replace('</Rights>', 'opaque mixed text</Rights>')),
            (ROLE_FILES[1], lambda text: '<!DOCTYPE Rights [<!ENTITY x "true">]>' + text),
            (ROLE_FILES[0], lambda text: text.replace('<Synonym/>', '<Synonym>Unexpected</Synonym>')),
            (ROLE_FILES[0], lambda text: text.replace('uuid="', 'unexpected="true" uuid="')),
            (ROLE_FILES[0], lambda text: re.sub(r'uuid="[^"]+"', 'uuid="invalid"', text)),
            (ROLE_FILES[0], lambda text: re.sub(r'uuid="[^"]+"', 'uuid="bd3814ed-1b7c-4f56-96b3-620fc5e32c44"', text)),
            (ROLE_FILES[0], lambda text: text.replace('</Properties>', '<ChildObjects/></Properties>')),
            (ROLE_FILES[0], lambda text: text + ' ' * 1_048_576),
        ):
            with self.subTest(name=name, mutate=mutate):
                path = redump / name
                original = path.read_bytes()
                path.write_text(mutate(original.decode('utf-8-sig')), encoding='utf-8')
                with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)
                path.write_bytes(original)

    @unittest.skipIf(os.name == "nt", "Creating Windows symlinks may need extra privileges")
    def test_metadata_roundtrip_rejects_indirect_role_files(self):
        self.inject()
        redump = self.root / "redump"
        shutil.copytree(self.output, redump)
        path = redump / ROLE_FILES[1]
        path.unlink()
        path.symlink_to(self.output / ROLE_FILES[1])
        with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)

    def test_language_file_and_role_uuid_cannot_change_on_native_roundtrip(self):
        language = self.source / "Languages"
        language.mkdir()
        (language / "Russian.xml").write_text('<Language uuid="original"><Name>Russian</Name></Language>')
        self.inject()
        redump = self.root / "redump"
        shutil.copytree(self.output, redump)
        require_reimported_metadata(self.output, redump)
        path = redump / 'Languages/Russian.xml'
        original = path.read_bytes()
        path.write_text('<Language uuid="altered"><Name>Russian</Name></Language>')
        with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)
        path.write_bytes(original)
        path = redump / ROLE_FILES[0]
        text = path.read_text(encoding='utf-8-sig')
        path.write_text(re.sub(r'uuid="[^"]+"', 'uuid="bd3814ed-1b7c-4f56-96b3-620fc5e32c46"', text))
        with self.assertRaises(DraftError): require_reimported_metadata(self.output, redump)

    def test_metadata_roundtrip_allows_only_nonsemantic_serialization_changes(self):
        self.inject()
        redump = self.root / "redump"
        shutil.copytree(self.output, redump)
        for path in redump.rglob("*.xml"):
            if path.name == "ConfigDumpInfo.xml":
                path.write_bytes(b"new native bookkeeping")
            else:
                path.write_bytes(path.read_text(encoding="utf-8-sig").replace("\n", "\r\n").encode("utf-8-sig"))
        config = redump / "Configuration.xml"
        text = config.read_text(encoding="utf-8-sig")
        role = "<Role>" + ROLE_NAME + "</Role>"
        config.write_text(text.replace(role, "").replace("</ChildObjects>", role + "</ChildObjects>"))
        require_reimported_metadata(self.output, redump)

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
                      users_after=1, persisted_user=USER, persisted_protection_type="UnsafeOperationProtectionDescription",
                      persisted_warning_type="Boolean",
                      observed_protection_type="UnsafeOperationProtectionDescription",
                      observed_warning_type="Boolean",
                      persisted_warning=False, standard_authentication=True,
                      current_user_at_start=USER if stage == "verify" else "",
                      current_protection_verified=stage == "verify", persisted_roles=[ROLE_NAME])
        if stage == "verify": server.update(current_protection_type="UnsafeOperationProtectionDescription",
                                               current_warning_type="Boolean", current_warning=False,
                                               current_roles=[ROLE_NAME])
        else: server["assigned_roles"] = [ROLE_NAME]
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
        cases = [("persisted_warning", 0), ("persisted_warning", "false"),
                 ("current_warning", True), ("current_user_at_start", "WrongUser"),
                 ("current_protection_verified", 1), ("run_id", "old"),
                 ("status", "error"), ("error", "compile failed"), ("users_after", True),
                 ("persisted_protection_type", "Boolean")]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                server, client = self.markers()
                server[key] = value
                self.write_markers(server, client)
                with self.assertRaises(DraftError): self.verify()

    def test_exact_descriptor_and_inner_boolean_required_for_all_readbacks(self):
        cases = [("persisted_protection_type", value) for value in ("Boolean", "other", None, False)]
        cases += [("persisted_warning_type", value) for value in ("Number", None, False)]
        cases += [("persisted_warning", value) for value in (0, "false", None, True)]
        cases += [("observed_protection_type", value) for value in ("Boolean", "other", "not_observed")]
        cases += [("observed_warning_type", value) for value in ("Undefined", "other", "not_observed")]
        for stage in ("bootstrap", "verify"):
            checks = cases + ([("current_protection_type", "Boolean"), ("current_warning_type", "Number")]
                              + [("current_warning", v) for v in (0, "false", None, True)] if stage == "verify" else [])
            for key, value in checks:
                with self.subTest(stage=stage, key=key, value=value):
                    server, client = self.markers(stage)
                    self.verify(stage)
                    server[key] = value
                    self.write_markers(server, client, stage)
                    with self.assertRaises(DraftError): self.verify(stage)

    def test_missing_descriptor_observation_or_readback_fields_fail_closed(self):
        for stage in ("bootstrap", "verify"):
            server, _ = self.markers(stage)
            fields = [key for key in server if key.startswith(("observed_", "persisted_warning", "current_warning"))
                      or key in ("persisted_protection_type", "current_protection_type")]
            for key in fields:
                with self.subTest(stage=stage, key=key):
                    server, client = self.markers(stage)
                    del server[key]
                    self.write_markers(server, client, stage)
                    with self.assertRaises(DraftError): self.verify(stage)

    def test_legacy_whole_property_boolean_markers_are_rejected(self):
        for stage in ("bootstrap", "verify"):
            server, client = self.markers(stage)
            self.verify(stage)
            for key in list(server):
                if key.startswith(("persisted_warning", "observed_")) or key == "persisted_protection_type":
                    del server[key]
            server.update(protection_type="Boolean", persisted_protection=False)
            if stage == "verify":
                for key in ("current_protection_type", "current_warning_type", "current_warning"):
                    del server[key]
                server["current_protection"] = False
            self.write_markers(server, client, stage)
            with self.assertRaises(DraftError): self.verify(stage)

    def test_anonymous_bootstrap_cannot_claim_fresh_current_descriptor(self):
        server, client = self.markers("bootstrap")
        server.update(current_protection_type="UnsafeOperationProtectionDescription",
                      current_warning_type="Boolean", current_warning=False)
        self.write_markers(server, client, "bootstrap")
        with self.assertRaises(DraftError): self.verify("bootstrap")

    def test_singleton_role_guard_enumerates_without_unsupported_count(self):
        self.inject()
        source = (self.output / "Ext/SessionModule.bsl").read_text(encoding="utf-8-sig")
        helper = source.split('Функция NativeПроверитьПользователя(Пользователь)', 1)[1].split('КонецФункции', 1)[0]
        self.assertIn('Для Каждого Роль Из Пользователь.Роли Цикл', helper)
        self.assertIn('Если Не Пользователь.Роли.Содержит(Метаданные.Роли.' + ROLE_NAME + ') Тогда', helper)
        self.assertIn('Если КоличествоРолей <> 0 Тогда', helper)
        self.assertLess(helper.index('Если КоличествоРолей <> 1 Тогда'), helper.index('ПроверенныеРоли.Добавить('))
        self.assertIn('Если КоличествоРолей <> 1 Тогда', helper)
        self.assertNotIn('Пользователь.Роли.Количество()', source)
        self.assertEqual(source.count('Пользователь.Роли.Добавить('), 1)
        self.assertNotIn('Попытка', helper)
        self.assertNotIn('Исключение\n', helper)
        for name, field in (('Пользователь', 'assigned_roles'), ('Сохраненный', 'persisted_roles'), ('Текущий', 'current_roles')):
            self.assertIn('Результат.Вставить("' + field + '", NativeПроверитьПользователя(' + name + '));', source)
        self.assertLess(source.index('Пользователи.Количество() <> 0'), source.index('Пользователь.Роли.Добавить('))
        self.assertLess(source.index('"assigned_roles"'), source.index('Пользователь.Записать();'))

    def test_every_role_marker_requires_exact_singleton_identity(self):
        for stage in ("bootstrap", "verify"):
            for field in ("persisted_roles", "assigned_roles" if stage == "bootstrap" else "current_roles"):
                for value in ([], ["FullAccess"], [ROLE_NAME, ROLE_NAME], [ROLE_NAME, "Other"], ROLE_NAME, True, None):
                    with self.subTest(stage=stage, field=field, value=value):
                        server, client = self.markers(stage)
                        server[field] = value
                        self.write_markers(server, client, stage)
                        with self.assertRaises(DraftError): self.verify(stage)
                server, client = self.markers(stage)
                del server[field]
                self.write_markers(server, client, stage)
                with self.assertRaises(DraftError): self.verify(stage)

    def test_source_checks_actual_shape_before_narrow_assignment_and_all_readbacks(self):
        self.inject()
        source = (self.output / "Ext/SessionModule.bsl").read_text(encoding="utf-8-sig")
        sequence = ['Защита = NativeНаблюдатьЗащиту(Пользователь, Результат);',
                    'Если ТипЗнч(Защита) <> Тип("ОписаниеЗащитыОтОпасныхДействий") Тогда',
                    'Если ТипЗнч(Защита.ПредупреждатьОбОпасныхДействиях) <> Тип("Булево") Тогда',
                    'Защита.ПредупреждатьОбОпасныхДействиях = Ложь;',
                    'Пользователь.ЗащитаОтОпасныхДействий = Защита;',
                    'Результат.Вставить("assigned_roles", NativeПроверитьПользователя(Пользователь));', 'Пользователь.Записать();']
        positions = [source.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(source.count('Защита.ПредупреждатьОбОпасныхДействиях = Ложь;'), 1)
        self.assertNotIn('Новый ОписаниеЗащитыОтОпасныхДействий', source)
        self.assertNotIn('Пользователь.ЗащитаОтОпасныхДействий = Ложь;', source)
        for name in ('Текущий', 'Сохраненный'):
            self.assertIn('NativeПроверитьПользователя(' + name + '));', source)
            self.assertIn(name + '.ЗащитаОтОпасныхДействий.ПредупреждатьОбОпасныхДействиях', source)
        helper = source[source.index('Функция NativeПроверитьПользователя'):]
        for check in (sequence[1], sequence[2], 'Если Защита.ПредупреждатьОбОпасныхДействиях <> Ложь Тогда'):
            self.assertIn(check, helper)
        observation = source[source.index('Функция NativeНаблюдатьЗащиту'):source.index('Функция NativeПроверитьПользователя')]
        self.assertNotIn(' = Ложь;', observation)
        self.assertNotIn('.Записать()', observation)

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
