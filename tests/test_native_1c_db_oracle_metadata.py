"""Synthetic source checks only: never claim native compilation or CRUD proof."""
from pathlib import Path
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/native_1c_bootstrap"))
SPEC = importlib.util.spec_from_file_location("db_oracle_metadata", ROOT / "scripts/native_1c_db_oracle/inject_metadata.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
NONCE = "0123456789abcdef" * 2


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        shutil.copyfile(ROOT / "tests/fixtures/native_bootstrap/Configuration.xml", self.source / "Configuration.xml")
        (self.source / "ConfigDumpInfo.xml").write_text("synthetic bookkeeping")
        self.target = self.root / "v1"

    def inject(self, **kwargs):
        return m.inject(self.source, self.target, nonce=kwargs.get("nonce", NONCE),
                        evidence=kwargs.get("evidence", Path("/tmp/onec-db-oracle/evidence")))

    def mutate(self, root, path, old, new):
        file = root / path
        data = file.read_text(encoding="utf-8-sig")
        self.assertIn(old, data)
        file.write_text(data.replace(old, new, 1), encoding="utf-8-sig")

    def test_injection_preserves_native_bytes_and_separates_roles(self):
        before = m._hashes(self.source)
        manifest = self.inject()
        self.assertEqual(before, m._hashes(self.source))
        after = m._hashes(self.target)
        self.assertEqual(set(after)-set(before), m.INJECTED_FILES)
        self.assertIs(manifest["native_runtime_tested"], False)
        self.assertEqual(manifest["setup_user"], m.SETUP_USER)
        self.assertEqual(manifest["crud_user"], m.CRUD_USER)
        for name in before:
            if name != "Configuration.xml":
                self.assertEqual(before[name], after[name])
        expected = b"<Role>NativeOracleSetupAdministrator</Role><Role>NativeOracleCatalogCRUD</Role><CommonModule>NativeOracleServer</CommonModule><Catalog>NativeOracleItems</Catalog>"
        original = (self.source / "Configuration.xml").read_bytes()
        self.assertEqual((self.target / "Configuration.xml").read_bytes(), original.replace(b"<ChildObjects>", b"<ChildObjects>"+expected))
        self.assertEqual(m.inspect(self.target, 1)["payload_length"], 32)

    def test_uuid_isolation_and_v2_single_byte_range_delta(self):
        self.inject()
        before = m._hashes(self.target)
        v2 = self.root / "v2"
        m.promote_v2(self.target, v2)
        self.assertEqual(m._hashes(self.target), before)
        diff = [name for name, digest in before.items() if m._hashes(v2)[name] != digest]
        self.assertEqual(diff, ["Catalogs/NativeOracleItems.xml"])
        old = (self.target / diff[0]).read_bytes()
        self.assertEqual((v2 / diff[0]).read_bytes(), old.replace(b"<v8:Length>32</v8:Length>", b"<v8:Length>64</v8:Length>"))
        self.assertEqual(m.inspect(v2, 2)["payload_length"], 64)
        m.verify_redump(v2, v2, 2)
        with self.assertRaises(m.DraftError): m.inspect(v2, 1)

    def test_all_modules_render_only_fixed_nonce_path_and_identity(self):
        self.inject()
        for path in m.MODULE_FILES.values():
            text = (self.target / path).read_text(encoding="utf-8-sig")
            self.assertNotIn("@@", text)
            self.assertNotIn("УстановитьПривилегированныйРежим", text)
            self.assertNotIn("SetPrivilegedMode", text)
            self.assertNotIn("АутентификацияСтандартная =", text)
            self.assertNotIn("ЗащитаОтОпасныхДействий =", text)
            self.assertNotIn("ПредупреждатьОбОпасныхДействиях =", text)
            self.assertNotIn("ПодробноеПредставлениеОшибки", text)
            self.assertNotIn("ОписаниеОшибки", text)

    def test_rendered_modules_parse_without_native_execution(self):
        from yadinassi.parser import parse
        for name in m.MODULE_FILES:
            with self.subTest(name=name):
                text = m._module(name, NONCE, "/tmp/onec-db-oracle/evidence").decode("utf-8-sig")
                self.assertTrue(parse(text, source=name))

    def test_source_and_redump_reject_symlinked_ancestor(self):
        self.inject()
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(m.DraftError):
            m.verify_redump(self.target, alias / "v1", 1)
        with self.assertRaises(m.DraftError):
            m.inject(alias / "source", self.root / "other", nonce=NONCE, evidence=Path("/tmp/evidence"))

    def test_privileged_hook_never_performs_catalog_crud(self):
        text = (m.ROOT / "modules/SessionModule.bsl").read_text()
        self.assertNotIn("Справочники.NativeOracleItems", text.replace("Метаданные.Справочники.NativeOracleItems", ""))
        for forbidden in ("СоздатьЭлемент", "Новый Запрос", "НачатьТранзакцию", "ПолучитьОбъект", "NativeOracleServer."):
            self.assertNotIn(forbidden, text)
        self.assertIn('Контроль.operation <> "bootstrap"', text)
        self.assertIn('ПользователиИнформационнойБазы.ПолучитьПользователей().Количество() <> 0', text)

    def test_dispatch_is_nonprivileged_and_values_are_canonical_strings(self):
        text = (m.ROOT / "modules/NativeOracleServer.bsl").read_text()
        managed = (m.ROOT / "modules/ManagedApplicationModule.bsl").read_text()
        self.assertIn("NativeOracleServer.NativeВыполнить(ПараметрЗапуска)", managed)
        self.assertGreaterEqual(text.count("Если ПривилегированныйРежим()"), 2)
        self.assertIn('Результат.amount = "1.25"', text)
        self.assertIn('Результат.amount = "-2.50"', text)
        self.assertIn("Объект.Удалить()", text)
        self.assertNotIn("УстановитьПометкуУдаления", text)
        self.assertIn('Результат.users_verified = Ложь', text)
        self.assertIn('ТипЗнч(До.same_reference) <> Тип("Null")', text)
        self.assertIn('ГДЕ Ссылка = &Ссылка', text)
        self.assertIn('Контроль.token <> ТокенЗапуска', text)
        self.assertIn('ВызватьИсключение "stale_evidence"', text)

    def test_no_unrequested_role_grants(self):
        self.inject()
        for role in (m.SETUP_ROLE, m.CRUD_ROLE):
            root = m.read_xml(self.target / f"Roles/{role}/Ext/Rights.xml")[1]
            for flag in ("setForNewObjects", "setForAttributesByDefault", "independentRightsOfChildObjects"):
                self.assertEqual(m.single(root, flag).text, "false")
        crud = (self.target / f"Roles/{m.CRUD_ROLE}/Ext/Rights.xml").read_text()
        for forbidden in ("Administration", "FullAccess", "Interactive", "ExternalConnection"):
            self.assertNotIn(forbidden, crud)
        setup = (self.target / f"Roles/{m.SETUP_ROLE}/Ext/Rights.xml").read_text()
        self.assertNotIn("Catalog.", setup)

    def test_exact_schema_pin_and_original_name_validation(self):
        for old, new in [('version="2.20"', 'version="2.21"'), ('/8.3/MDClasses', '/8.4/MDClasses'), ('DisposableFixture', 'Invalid.Name'), ('ManagedApplication', 'OrdinaryApplication')]:
            with self.subTest(new=new):
                file = self.source / "Configuration.xml"
                initial = file.read_bytes()
                self.mutate(self.source, "Configuration.xml", old, new)
                with self.assertRaises(m.DraftError): self.inject()
                self.assertFalse(self.target.exists())
                file.write_bytes(initial)

    def test_reject_invalid_nonces_and_non_tmpfs_paths(self):
        for nonce in ("", NONCE.upper(), NONCE+"x", True, 1, "x"*32):
            with self.subTest(nonce=nonce), self.assertRaises(m.DraftError): self.inject(nonce=nonce)
        for path in ("relative", "/home/private", "/tmp/../private", "/", "/tmp/a\nb"):
            with self.subTest(path=path), self.assertRaises(m.DraftError): self.inject(evidence=Path(path))

    def test_no_existing_or_overlapping_destination(self):
        self.target.mkdir()
        with self.assertRaises(m.DraftError): self.inject()
        self.target.rmdir()
        for target in (self.source, self.source / "child", self.root):
            with self.subTest(target=target), self.assertRaises(m.DraftError):
                m.inject(self.source, target, nonce=NONCE, evidence=Path("/tmp/evidence"))

    def test_reject_unrequested_source_entries(self):
        for name in ("private.txt", "Ext/Module.bsl", "Catalogs/Other.xml"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private fixture must never be accepted")
            with self.subTest(name=name), self.assertRaises(m.DraftError): self.inject()
            path.unlink()

    def test_reject_source_hardlink_symlink_and_special_file(self):
        path = self.source / "extra"
        for kind in ("hardlink", "symlink", "fifo"):
            if kind == "hardlink": os.link(self.source / "Configuration.xml", path)
            elif kind == "symlink": path.symlink_to(self.source / "Configuration.xml")
            else: os.mkfifo(path)
            with self.subTest(kind=kind), self.assertRaises(m.DraftError): self.inject()
            path.unlink()

    def test_reject_source_xml_entity_and_oversize(self):
        file = self.source / "Configuration.xml"
        initial = file.read_bytes()
        for data in (b'<!DOCTYPE x [<!ENTITY y "z">]>'+initial, b"x"*1_048_577):
            file.write_bytes(data)
            with self.assertRaises(m.DraftError): self.inject()
        file.write_bytes(initial)

    def test_prefix_and_self_closing_children_are_preserved(self):
        file = self.source / "Configuration.xml"
        text = file.read_text().replace('<ChildObjects><Language>Russian</Language></ChildObjects>', '<ChildObjects/>')
        text = text.replace('xmlns="', 'xmlns:m="')
        text = re.sub(r"<(\/?)([A-Za-z][A-Za-z0-9]*)(?=[\s/>])", r"<\1m:\2", text)
        file.write_text(text)
        self.inject()
        self.assertIn("<m:Catalog>NativeOracleItems</m:Catalog>", (self.target / "Configuration.xml").read_text())

    def test_roundtrip_accepts_only_formatting_and_right_order(self):
        self.inject()
        copy = self.root / "redump"
        shutil.copytree(self.target, copy)
        (copy / "ConfigDumpInfo.xml").write_text("different synthetic dump bookkeeping")
        path = copy / f"Roles/{m.CRUD_ROLE}/Ext/Rights.xml"
        tree = ET.fromstring(path.read_bytes())
        tree[:] = reversed(list(tree))
        for obj in tree:
            if obj.tag.endswith("}object"):
                obj[:] = reversed(list(obj))
        path.write_bytes(ET.tostring(tree, encoding="utf-8"))
        m.verify_redump(self.target, copy, 1)

    def test_roundtrip_rejects_widened_role_and_schema_module_changes(self):
        self.inject()
        cases = [
            (f"Roles/{m.CRUD_ROLE}/Ext/Rights.xml", '<name>Read</name>', '<name>Administration</name>'),
            (f"Roles/{m.CRUD_ROLE}/Ext/Rights.xml", '<setForAttributesByDefault>false', '<setForAttributesByDefault>true'),
            (f"Roles/{m.CRUD_ROLE}/Ext/Rights.xml", '<name>Catalog.NativeOracleItems</name>', '<name>Catalog.Other</name>'),
            (f"Roles/{m.SETUP_ROLE}/Ext/Rights.xml", '</object>', '<right><name>FullAccess</name><value>true</value></right></object>'),
            ('CommonModules/NativeOracleServer.xml', '<Privileged>false', '<Privileged>true'),
            ('CommonModules/NativeOracleServer.xml', '<ServerCall>true', '<ServerCall>false'),
            ('Catalogs/NativeOracleItems.xml', '<v8:Digits>9', '<v8:Digits>10'),
            ('Catalogs/NativeOracleItems.xml', '<v8:FractionDigits>2', '<v8:FractionDigits>3'),
            ('Catalogs/NativeOracleItems.xml', '<v8:Length>32', '<v8:Length>64'),
            ('Catalogs/NativeOracleItems.xml', '<Hierarchical>false', '<Hierarchical>true'),
            ('Configuration.xml', '<DefaultRoles/>', '<DefaultRoles>Role.NativeOracleCatalogCRUD</DefaultRoles>'),
            ('Configuration.xml', '</ChildObjects>', '<Document>Unrequested</Document></ChildObjects>'),
            ('Ext/ManagedApplicationModule.bsl', 'ЗавершитьРаботуСистемы(Ложь)', 'ЗавершитьРаботуСистемы(Истина)'),
        ]
        for index, (path, old, new) in enumerate(cases):
            target = self.root / f"bad{index}"
            shutil.copytree(self.target, target)
            self.mutate(target, path, old, new)
            with self.subTest(path=path, old=old), self.assertRaises(m.DraftError): m.verify_redump(self.target, target, 1)

    def test_reject_extra_files_dirs_missing_modules_and_uuid_collision(self):
        self.inject()
        for kind in ("extra_file", "extra_dir", "missing_module", "uuid_collision"):
            target = self.root / kind
            shutil.copytree(self.target, target)
            if kind == "extra_file": (target / "leak.txt").write_text("private")
            elif kind == "extra_dir": (target / "Unexpected").mkdir()
            elif kind == "missing_module": (target / "Ext/SessionModule.bsl").unlink()
            else:
                config = m.read_xml(target / "Configuration.xml")[1]
                identity = m.single(config, "Configuration").attrib["uuid"]
                file = target / f"Roles/{m.CRUD_ROLE}.xml"
                data = file.read_text()
                file.write_text(re.sub(r'uuid="[^"]+"', f'uuid="{identity}"', data))
            with self.subTest(kind=kind), self.assertRaises(m.DraftError): m.verify_redump(self.target, target, 1)

    def test_bad_version_types_do_not_equal_one(self):
        self.inject()
        for value in (True, False, 1.0, "1", None, 0, 3):
            with self.subTest(value=value), self.assertRaises(m.DraftError): m.inspect(self.target, value)

    def test_promotion_refuses_v2_and_preexisting_or_nested_target(self):
        self.inject()
        v2 = self.root / "v2"
        m.promote_v2(self.target, v2)
        for source, target in ((v2, self.root / "v3"), (self.target, v2), (self.target, self.target / "nested")):
            with self.subTest(source=source, target=target), self.assertRaises(m.DraftError): m.promote_v2(source, target)


if __name__ == "__main__": unittest.main()
