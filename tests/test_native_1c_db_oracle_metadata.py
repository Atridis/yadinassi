"""Synthetic source checks only: never claim native compilation or CRUD proof."""
from pathlib import Path
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
import uuid
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
        self.assertIn('ТипЗнч(До.same_reference) <> Тип("Неопределено")', text)
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

# These doubles exercise unchanged rendered BSL slices in the interpreter. They
# neither access a database nor establish native compilation or CRUD behavior.
# The serializer is the reviewed bounded automatic-JSON mapping double, not a
# runtime implementation. In particular it rejects BSL Null without coercion.
from decimal import Decimal
import json

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray, BSLObject, HostFunction, NULL
from test_native_async_error_transport import encode as transport_encode

sys.path.insert(0, str(ROOT / "scripts/native_1c_db_oracle"))
PROTOCOL_SPEC = importlib.util.spec_from_file_location(
    "db_oracle_transport_protocol", ROOT / "scripts/native_1c_db_oracle/protocol.py")
db_protocol = importlib.util.module_from_spec(PROTOCOL_SPEC)
PROTOCOL_SPEC.loader.exec_module(db_protocol)

TRANSPORT_ROOT = "/tmp/offline-controlled-db-oracle"  # Never opened on disk.
TRANSPORT_TOKEN = "b" * 32
STATE_FIELDS = ("count", "code", "payload", "amount", "deletion_mark", "same_reference")
METADATA_FIELDS = ("metadata_version", "payload_length", "amount_digits", "amount_scale")


def rendered_module(name):
    return m._module(name, NONCE, TRANSPORT_ROOT).decode("utf-8-sig")


def exact_slice(text, start, end):
    """Fail closed on changed anchors; do not reconstruct the BSL body."""
    assert text.count(start) == 1
    first = text.index(start)
    return text[first:text.index(end, first)]


def exact_routine(text, name, *, procedure=False):
    start = ("Процедура " if procedure else "Функция ") + name + "("
    end = "КонецПроцедуры" if procedure else "КонецФункции"
    return exact_slice(text, start, end) + end


def previous_defaults(text):
    """Negative control: exact inverse of just the transport-default change."""
    current = "Результат.Вставить(Поле, Неопределено);"
    assert text.count(current) == 1
    return text.replace(current, "Результат.Вставить(Поле, Null);")


class ControlledMembers(BSLObject):
    def __init__(self, **members):
        self.members = members

    def get_member(self, name):
        if name not in self.members:
            raise ValueError("Unexpected controlled member")
        return self.members[name]


class ControlledDBWriter(BSLObject):
    def __init__(self):
        self.path = None
        self.raw = None
        self.value = None
        self.closed = False

    def open_file(self, path):
        assert self.path is None and path in (
            TRANSPORT_ROOT + "/bootstrap.json", TRANSPORT_ROOT + "/result.json")
        self.path = path

    def write(self, value):
        assert self.path is not None and self.raw is None and not self.closed
        self.value = value
        self.raw = transport_encode(value)

    def close(self):
        assert self.raw is not None and not self.closed
        self.closed = True

    def get_member(self, name):
        methods = {"ОткрытьФайл": self.open_file, "Закрыть": self.close}
        assert name in methods
        return HostFunction(name, methods[name], returns_value=False)


def transport_vm():
    vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
    writer = ControlledDBWriter()
    vm.register_type("ЗаписьJSON", lambda: writer)
    vm.register_function("ЗаписатьJSON", lambda target, value: target.write(value),
                         returns_value=False)
    vm.register_type("СистемнаяИнформация", lambda: ControlledMembers(
        ВерсияПриложения=db_protocol.VERSION))

    def absent_file(path):
        assert path == TRANSPORT_ROOT + "/result.json"
        return ControlledMembers(Существует=HostFunction("Существует", lambda: False))

    vm.register_type("Файл", absent_file)
    vm.variables["контроль"] = BSLStructure("token,operation", TRANSPORT_TOKEN, "observe")
    vm.variables["путь"] = TRANSPORT_ROOT + "/bootstrap.json"
    return vm, writer


def catch_source(vm, source):
    vm.execute("Caught = False; Попытка\n" + source +
               "\nИсключение Caught = True; КонецПопытки;",
               source="synthetic-exact-db-transport-slice")
    return vm.execute("Caught")


def bootstrap_source(*, previous=False):
    text = rendered_module("SessionModule.bsl")
    if previous:
        text = previous_defaults(text)
    # Explicitly execute the real structure initialization. Only the three
    # metadata-property reads are replaced by declared controlled scalar inputs;
    # privileged user creation/checks before initialization are not executed.
    prefix = exact_slice(text, "    Результат = Новый Структура;", "    Длина = Метаданные.")
    suffix = exact_slice(text, "    Если Длина <> 32", "КонецПроцедуры")
    return prefix + "Длина = 32; Разрядность = 9; Масштаб = 2;\n" + suffix


def server_source(vm, *, previous=False):
    text = rendered_module("NativeOracleServer.bsl")
    result = exact_routine(text, "NativeНовыйРезультат")
    if previous:
        result = previous_defaults(result)
    vm.execute(result + "\n" + exact_routine(text, "NativeЗаписатьJSON", procedure=True),
               source="synthetic-exact-db-result-and-writer")
    vm.execute("Результат = NativeНовыйРезультат(Контроль);")


def write_result(vm):
    return catch_source(vm, 'NativeЗаписатьJSON("' + TRANSPORT_ROOT + '/result.json", Результат);')


class ControlledSelection(BSLObject):
    def __init__(self, rows):
        self.rows = rows
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_member(self, name):
        if name == "Следующий":
            return HostFunction(name, self.next)
        assert 0 <= self.index < len(self.rows)
        return self.rows[self.index][name]


def state_source(vm, *, saved=None, rows=(), query_found=False, previous=False):
    source = exact_routine(rendered_module("NativeOracleServer.bsl"), "NativeСостояние")
    if previous:
        current = '0, Неопределено, Неопределено, Неопределено, Неопределено, Неопределено);'
        assert source.count(current) == 1
        source = source.replace(current, '0, Null, Null, Null, Null, Null);')
    events = []

    def saved_reference(root):
        assert root == TRANSPORT_ROOT
        events.append("saved_reference")
        return saved

    def query(text):
        assert saved is not None
        assert text == "ВЫБРАТЬ Ссылка ИЗ Справочник.NativeOracleItems ГДЕ Ссылка = &Ссылка"
        events.append("query")
        parameter_set = False

        def set_parameter(name, value):
            nonlocal parameter_set
            assert name == "Ссылка" and value is saved and not parameter_set
            parameter_set = True

        def execute():
            assert parameter_set
            events.append("query_execute")
            return ControlledMembers(Пустой=HostFunction("Пустой", lambda: not query_found))

        return ControlledMembers(
            УстановитьПараметр=HostFunction("УстановитьПараметр", set_parameter, returns_value=False),
            Выполнить=HostFunction("Выполнить", execute))

    def select():
        events.append("select")
        return ControlledSelection(rows)

    vm.register_function("NativeСохраненнаяСсылка", saved_reference)
    vm.register_type("Запрос", query)
    vm.execute("Перем Справочники;")
    vm.variables["справочники"] = ControlledMembers(NativeOracleItems=ControlledMembers(
        Выбрать=HostFunction("Выбрать", select)))
    vm.execute(source, source="synthetic-exact-db-state-routine")
    return events


def controlled_row(reference, *, payload="alpha", amount="1.25"):
    return {"Код": "K1", "ПометкаУдаления": False, "Ссылка": reference,
            "Payload": payload, "Amount": Decimal(amount)}


class DBMarkerTransportTests(unittest.TestCase):
    def test_reviewed_serializer_preserves_null_false_and_missing_as_distinct(self):
        structure = BSLStructure("absent,flag", None, False)
        self.assertEqual(json.loads(transport_encode(structure)), {"absent": None, "flag": False})
        self.assertTrue(structure.property("absent"))
        self.assertFalse(structure.property("missing"))
        for value in (NULL, BSLStructure("absent", NULL), object()):
            with self.subTest(value=type(value).__name__), self.assertRaises(TypeError):
                transport_encode(value)

    def test_actual_bootstrap_initialization_writes_all_absent_keys_as_json_null(self):
        vm, writer = transport_vm()
        self.assertFalse(catch_source(vm, bootstrap_source()))
        self.assertTrue(writer.closed)
        marker = db_protocol.marker(writer.raw, nonce=NONCE, token=TRANSPORT_TOKEN, operation="bootstrap")
        self.assertEqual(set(marker), db_protocol.MARKER_KEYS)
        self.assertEqual({key: marker[key] for key in STATE_FIELDS}, dict.fromkeys(STATE_FIELDS))
        self.assertIs(marker["nonprivileged"], False)
        self.assertIs(marker["users_verified"], True)
        # None means a present JSON-null field, never permission to omit it.
        for key in STATE_FIELDS:
            missing = dict(marker)
            del missing[key]
            with self.subTest(missing=key), self.assertRaises(db_protocol.OracleError):
                db_protocol.marker(db_protocol.encode(missing), nonce=NONCE,
                                   token=TRANSPORT_TOKEN, operation="bootstrap")

    def test_actual_bootstrap_reader_comparison_and_rewrite_preserve_json_null_keys(self):
        seed_vm, seed_writer = transport_vm()
        self.assertFalse(catch_source(seed_vm, bootstrap_source()))
        bootstrap_marker = db_protocol.decode(seed_writer.raw)
        text = rendered_module("NativeOracleServer.bsl")

        def read_subset(value):
            # Bounded documented automatic read mapping. This is a controlled
            # reader, not proof of native ReadJSON or metadata behavior.
            if value is None or type(value) in (str, bool):
                return value
            if type(value) is int:
                return Decimal(value)
            if type(value) is dict:
                result = BSLStructure()
                for key, item in value.items():
                    result.insert(key, read_subset(item))
                return result
            raise TypeError("Outside this controlled JSON reader subset")

        for tampered in (False, True):
            with self.subTest(tampered_token=tampered):
                vm, writer = transport_vm()
                marker = dict(bootstrap_marker)
                if tampered:
                    marker["token"] = "c" * 32
                files = {
                    TRANSPORT_ROOT + "/control.json": db_protocol.encode({
                        "schema": 1, "nonce": NONCE, "token": TRANSPORT_TOKEN, "operation": "bootstrap"}),
                    TRANSPORT_ROOT + "/bootstrap.json": db_protocol.encode(marker),
                }
                readers = []
                metadata_checks = []

                class Reader(BSLObject):
                    def __init__(self):
                        self.path = None
                        self.closed = False
                        readers.append(self)

                    def open_file(self, path):
                        assert path in files and self.path is None
                        self.path = path

                    def read(self):
                        assert self.path is not None and not self.closed
                        return read_subset(json.loads(files[self.path]))

                    def close(self):
                        assert self.path is not None and not self.closed
                        self.closed = True

                    def get_member(self, name):
                        methods = {"ОткрытьФайл": self.open_file, "Закрыть": self.close}
                        assert name in methods
                        return HostFunction(name, methods[name], returns_value=False)

                def file(path):
                    assert path in files or path == TRANSPORT_ROOT + "/result.json"
                    return ControlledMembers(
                        Существует=HostFunction("Существует", lambda: path in files),
                        Размер=HostFunction("Размер", lambda: Decimal(len(files[path]))))

                def verified_metadata(result):
                    # Explicit controlled gap: do not exercise live metadata.
                    self.assertEqual(json.loads(transport_encode(result)), bootstrap_marker)
                    for key in STATE_FIELDS:
                        self.assertTrue(result.property(key))
                        self.assertIsNone(result.get(key))
                    metadata_checks.append(True)

                vm.register_type("Файл", file)
                vm.register_type("ЧтениеJSON", Reader)
                vm.register_function("ПрочитатьJSON", lambda reader: reader.read())
                vm.register_function("ПривилегированныйРежим", lambda: False)
                vm.register_function("NativeПроверитьМетаданные", verified_metadata, returns_value=False)
                vm.execute("\n".join((
                    exact_routine(text, "NativeПрочитатьJSON"),
                    exact_routine(text, "NativeЗаписатьJSON", procedure=True),
                    exact_routine(text, "NativeВыполнить"),
                    exact_routine(text, "NativeВыполнитьПроверенный", procedure=True),
                )), source="synthetic-exact-db-bootstrap-readback")
                invocation = 'Ответ = NativeВыполнить("' + TRANSPORT_TOKEN + '");'
                if tampered:
                    vm.execute(invocation)
                    self.assertEqual(json.loads(transport_encode(vm.execute("Ответ"))),
                                     {"status": "error", "operation": "bootstrap", "phase": "marker"})
                    self.assertEqual(metadata_checks, [])
                    self.assertIsNone(writer.path)
                    self.assertIsNone(writer.raw)
                else:
                    vm.execute(invocation)
                    self.assertEqual(json.loads(transport_encode(vm.execute("Ответ"))),
                                     {"status": "ok", "operation": "bootstrap", "phase": "complete"})
                    self.assertEqual(metadata_checks, [True])
                    self.assertTrue(writer.closed)
                    rewritten = db_protocol.marker(writer.raw, nonce=NONCE,
                                                   token=TRANSPORT_TOKEN, operation="bootstrap")
                    self.assertEqual(rewritten, bootstrap_marker)
                    self.assertEqual(set(rewritten), db_protocol.MARKER_KEYS)
                self.assertEqual([reader.path for reader in readers], list(files))
                self.assertTrue(all(reader.closed for reader in readers))

    def test_inverse_bootstrap_null_defaults_fail_the_actual_writer_path(self):
        vm, writer = transport_vm()
        self.assertTrue(catch_source(vm, bootstrap_source(previous=True)))
        self.assertEqual(writer.path, TRANSPORT_ROOT + "/bootstrap.json")
        self.assertFalse(writer.closed)
        self.assertIsNone(writer.raw)
        for key in STATE_FIELDS:
            self.assertIs(writer.value.get(key), NULL)

    def test_actual_new_result_keeps_ten_absent_keys_and_boolean_flags(self):
        vm, writer = transport_vm()
        server_source(vm)
        self.assertFalse(write_result(vm))
        self.assertTrue(writer.closed)
        marker = db_protocol.decode(writer.raw)
        self.assertEqual(set(marker), db_protocol.MARKER_KEYS)
        self.assertEqual({key: marker[key] for key in METADATA_FIELDS + STATE_FIELDS},
                         dict.fromkeys(METADATA_FIELDS + STATE_FIELDS))
        self.assertEqual(marker["status"], "error")
        self.assertIs(marker["role_verified"], False)
        self.assertIs(marker["users_verified"], False)
        self.assertIs(marker["nonprivileged"], True)
        # Default error markers must not become accepted success evidence.
        with self.assertRaises(db_protocol.OracleError):
            db_protocol.marker(writer.raw, nonce=NONCE, token=TRANSPORT_TOKEN, operation="observe")

    def test_inverse_new_result_null_defaults_fail_the_actual_writer_path(self):
        vm, writer = transport_vm()
        server_source(vm, previous=True)
        with self.assertRaises(TypeError):
            transport_encode(vm.execute("Результат"))
        self.assertTrue(write_result(vm))
        self.assertEqual(writer.path, TRANSPORT_ROOT + "/result.json")
        self.assertFalse(writer.closed)
        self.assertIsNone(writer.raw)

    def test_actual_state_and_marker_roundtrip_empty_deleted_and_populated_rows(self):
        reference = BSLObject()
        scenarios = (
            ("baseline", None, (), False),
            ("deleted", reference, (), False),
            ("created", reference, (controlled_row(reference),), True),
            ("updated", reference, (controlled_row(reference, payload="beta", amount="-2.50"),), True),
        )
        for identifier, saved, rows, found in scenarios:
            with self.subTest(identifier=identifier):
                vm, writer = transport_vm()
                server_source(vm)
                events = state_source(vm, saved=saved, rows=rows, query_found=found)
                self.assertFalse(catch_source(vm, 'После = NativeСостояние("' + TRANSPORT_ROOT + '");'))
                expected = db_protocol.expected_logical(identifier)
                state = json.loads(transport_encode(vm.execute("После")))
                self.assertEqual(state, {key: expected[key] for key in STATE_FIELDS})
                self.assertEqual(set(state), set(STATE_FIELDS))
                if identifier == "baseline":
                    self.assertIs(state["same_reference"], None)
                    self.assertEqual(events, ["saved_reference", "select"])
                else:
                    self.assertIs(state["same_reference"], identifier != "deleted")
                    self.assertEqual(events, ["saved_reference", "query", "query_execute", "select"])
                # Controlled success/metadata inputs, not native identity proof.
                vm.execute('Результат.status = "ok"; Результат.user = "NativeOracleCRUD"; '
                           'Результат.role_verified = Истина; Результат.metadata_version = 1; '
                           'Результат.payload_length = 32; Результат.amount_digits = 9; Результат.amount_scale = 2;')
                copy = exact_slice(rendered_module("NativeOracleServer.bsl"),
                                   "    Для Каждого Поле Из После Цикл", "КонецПроцедуры")
                vm.execute(copy, source="synthetic-exact-db-state-copy")
                self.assertFalse(write_result(vm))
                self.assertTrue(writer.closed)
                marker = db_protocol.marker(writer.raw, nonce=NONCE, token=TRANSPORT_TOKEN, operation="observe")
                self.assertEqual({key: marker[key] for key in STATE_FIELDS}, state)

    def test_inverse_state_null_defaults_reject_empty_but_not_fully_populated_rows(self):
        reference = BSLObject()
        for saved in (None, reference):
            with self.subTest(saved=saved is not None):
                vm, _ = transport_vm()
                state_source(vm, saved=saved, previous=True)
                vm.execute('После = NativeСостояние("' + TRANSPORT_ROOT + '");')
                with self.assertRaises(TypeError):
                    transport_encode(vm.execute("После"))
        # The change concerns absence transport, not semantic SQL Null handling.
        vm, _ = transport_vm()
        state_source(vm, saved=reference, rows=(controlled_row(reference),), query_found=True, previous=True)
        vm.execute('После = NativeСостояние("' + TRANSPORT_ROOT + '");')
        state = json.loads(transport_encode(vm.execute("После")))
        self.assertEqual(state, {"count": 1, "code": "K1", "payload": "alpha", "amount": "1.25",
                                 "deletion_mark": False, "same_reference": True})

    def test_actual_state_logic_still_rejects_inconsistent_controlled_observations(self):
        reference = BSLObject()
        good = controlled_row(reference)
        cases = (
            (reference, (), True),
            (None, (good,), False),
            (reference, ({**good, "Ссылка": BSLObject()},), True),
            (reference, ({**good, "ПометкаУдаления": True},), True),
            (reference, ({**good, "Код": "K2"},), True),
            (reference, ({**good, "Payload": "other"},), True),
            (reference, ({**good, "Amount": Decimal("1.26")},), True),
            (reference, (good, good), True),
        )
        for index, (saved, rows, found) in enumerate(cases):
            with self.subTest(case=index):
                vm, _ = transport_vm()
                state_source(vm, saved=saved, rows=rows, query_found=found)
                with self.assertRaisesRegex(BSLRuntimeError, "logical_mismatch"):
                    vm.execute('После = NativeСостояние("' + TRANSPORT_ROOT + '");')

    def test_actual_create_gate_requires_undefined_not_null_false_or_missing(self):
        gate = exact_slice(rendered_module("NativeOracleServer.bsl"),
                           '        Если До.count <> 0 Или ТипЗнч(До.same_reference)',
                           '        Контекст.phase = "begin";')
        self.assertIn('Тип("Неопределено")', gate)
        for value in (None, NULL, False, True, Decimal(0), ""):
            for count in (0, 1):
                with self.subTest(value=type(value).__name__, count=count):
                    vm, _ = transport_vm()
                    vm.variables["до"] = BSLStructure("count,same_reference", Decimal(count), value)
                    self.assertEqual(catch_source(vm, gate), not (value is None and count == 0))
        vm, _ = transport_vm()
        vm.variables["до"] = BSLStructure("count", Decimal(0))
        self.assertTrue(catch_source(vm, gate))
        # Demonstrate why changing the initializer alone is insufficient.
        old_gate = gate.replace('Тип("Неопределено")', 'Тип("Null")')
        for value in (None, NULL):
            vm, _ = transport_vm()
            vm.variables["до"] = BSLStructure("count,same_reference", Decimal(0), value)
            self.assertEqual(catch_source(vm, old_gate), value is not NULL)


# These doubles execute the rendered completion/measurement routines unchanged.
# They establish controlled source behavior only: not native client-server
# transport, file-move atomicity, native transaction semantics, or real DB CRUD.
COMPLETION_PATH = TRANSPORT_ROOT + "/completion.json"
PENDING_PATH = TRANSPORT_ROOT + "/completion.pending.json"
ERROR_CANARY = "RAW_ERROR_TEXT_MUST_NOT_ESCAPE"


def completion_vm(reply=None, *, fail=None, existing=None, token=TRANSPORT_TOKEN,
                  appear_at_close=False, shutdown_error=False):
    vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
    events, files = [], dict(existing or {})

    def event(name):
        events.append(name)
        if fail == name:
            raise ValueError(ERROR_CANARY)

    class Writer(BSLObject):
        def open(self, path):
            assert path == PENDING_PATH and path not in files
            event("open")
            files[path] = b""

        def write(self, data):
            event("write")
            files[PENDING_PATH] = transport_encode(data)

        def close(self):
            event("close")
            if appear_at_close:
                files[COMPLETION_PATH] = b"prior completion must not be replaced"

        def get_member(self, name):
            return HostFunction(name, {"ОткрытьФайл": self.open, "Закрыть": self.close}[name],
                                returns_value=False)

    def file(path):
        assert path in (COMPLETION_PATH, PENDING_PATH)
        return ControlledMembers(ПолноеИмя=path,
                                 Существует=HostFunction("Существует", lambda: path in files))

    def server(token_value):
        assert token_value == TRANSPORT_TOKEN
        event("server")
        return reply

    def move(source, target):
        assert source == PENDING_PATH and target == COMPLETION_PATH
        event("move")
        # This controlled publication model is NOT a native MoveFile guarantee.
        assert target not in files
        files[target] = files.pop(source)

    def shutdown(confirm):
        assert confirm is False
        events.append("shutdown")
        if shutdown_error:
            raise ValueError(ERROR_CANARY)

    vm.execute("Перем ПараметрЗапуска, NativeOracleServer;")
    vm.variables["параметрзапуска"] = token
    vm.variables["nativeoracleserver"] = ControlledMembers(
        NativeВыполнить=HostFunction("NativeВыполнить", server))
    vm.register_type("Файл", file)
    vm.register_type("ЗаписьJSON", Writer)
    vm.register_function("ЗаписатьJSON", lambda writer, data: writer.write(data), returns_value=False)
    vm.register_function("ПереместитьФайл", move, returns_value=False)
    vm.register_function("ЗавершитьРаботуСистемы", shutdown, returns_value=False)
    vm.execute(rendered_module("ManagedApplicationModule.bsl"), source="exact-managed-completion-routines")
    return vm, events, files


def finite_reply(status="ok", operation="create", phase="complete"):
    return BSLStructure("status,operation,phase", status, operation, phase)


class DBControlledCompletionTests(unittest.TestCase):
    def test_exact_managed_module_publishes_six_fields_only_after_close_then_stops(self):
        vm, events, files = completion_vm(finite_reply())
        vm.execute("ПриНачалеРаботыСистемы();")
        self.assertEqual(events, ["server", "open", "write", "close", "move", "shutdown"])
        self.assertNotIn(PENDING_PATH, files)
        self.assertEqual(json.loads(files[COMPLETION_PATH]), {
            "schema": 1, "nonce": NONCE, "token": TRANSPORT_TOKEN,
            "operation": "create", "phase": "complete", "status": "ok"})

    def test_returned_error_remains_error_even_with_existing_success_result(self):
        result_path = TRANSPORT_ROOT + "/result.json"
        vm, events, files = completion_vm(finite_reply("error", "create", "write"),
                                         existing={result_path: b'{"status":"ok"}'})
        vm.execute("ПриНачалеРаботыСистемы();")
        self.assertEqual(json.loads(files[COMPLETION_PATH])["status"], "error")
        self.assertEqual(json.loads(files[COMPLETION_PATH])["phase"], "write")
        self.assertEqual(files[result_path], b'{"status":"ok"}')
        self.assertEqual(events.count("shutdown"), 1)
        self.assertNotIn(ERROR_CANARY.encode(), files[COMPLETION_PATH])

    def test_transport_exception_and_invalid_returns_publish_only_dispatch_error(self):
        cases = [None, False, NULL, "unbounded_native_text", BSLStructure(),
                 finite_reply("error", "create", "complete"),
                 finite_reply("ok", "dispatch", "complete"),
                 finite_reply("ok", "create", "write"),
                 finite_reply("unknown", "create", "write"),
                 finite_reply("error", "arbitrary", "write"),
                 finite_reply("error", "create", "arbitrary"),
                 BSLStructure("status,operation,phase,extra", "ok", "create", "complete", ERROR_CANARY),
                 BSLStructure("status,operation,unexpected", "ok", "create", "complete")]
        for reply in cases:
            with self.subTest(reply=type(reply).__name__):
                vm, events, files = completion_vm(reply)
                vm.execute("ПриНачалеРаботыСистемы();")
                self.assertEqual(json.loads(files[COMPLETION_PATH]), {
                    "schema": 1, "nonce": NONCE, "token": TRANSPORT_TOKEN,
                    "operation": "dispatch", "phase": "dispatch", "status": "error"})
                self.assertEqual(events[-1], "shutdown")
        vm, events, files = completion_vm(finite_reply(), fail="server")
        vm.execute("ПриНачалеРаботыСистемы();")
        self.assertEqual(json.loads(files[COMPLETION_PATH])["status"], "error")
        self.assertNotIn(ERROR_CANARY.encode(), files[COMPLETION_PATH])
        self.assertEqual(events.count("shutdown"), 1)

    def test_invalid_token_never_serializes_unvalidated_input_and_still_stops(self):
        for token in (None, False, "", "A" * 32, "x" * 32, "a" * 33, ERROR_CANARY):
            with self.subTest(token=token):
                vm, events, files = completion_vm(finite_reply(), token=token)
                vm.execute("ПриНачалеРаботыСистемы();")
                self.assertEqual(events, ["shutdown"])
                self.assertEqual(files, {})

    def test_publication_errors_leave_no_new_completion_but_still_attempt_shutdown(self):
        for failure in ("open", "write", "close", "move"):
            with self.subTest(failure=failure):
                vm, events, files = completion_vm(finite_reply(), fail=failure)
                vm.execute("ПриНачалеРаботыСистемы();")
                self.assertNotIn(COMPLETION_PATH, files)
                self.assertEqual(events[-1], "shutdown")
                self.assertEqual(events.count("shutdown"), 1)
                self.assertEqual(events.count(failure), 1)
                self.assertNotIn(ERROR_CANARY.encode(), b"".join(files.values()))

    def test_preexisting_pending_and_completed_files_are_not_overwritten(self):
        for path in (COMPLETION_PATH, PENDING_PATH):
            with self.subTest(path=path):
                vm, events, files = completion_vm(finite_reply(), existing={path: b"prior"})
                vm.execute("ПриНачалеРаботыСистемы();")
                self.assertEqual(files, {path: b"prior"})
                self.assertEqual(events, ["server", "shutdown"])
        vm, events, files = completion_vm(finite_reply(), appear_at_close=True)
        vm.execute("ПриНачалеРаботыСистемы();")
        self.assertEqual(files[COMPLETION_PATH], b"prior completion must not be replaced")
        self.assertNotIn("move", events)
        self.assertEqual(events[-1], "shutdown")

    def test_shutdown_failure_is_not_caught_or_retried(self):
        vm, events, files = completion_vm(finite_reply("error", "create", "write"),
                                         shutdown_error=True)
        with self.assertRaises(BSLRuntimeError):
            vm.execute("ПриНачалеРаботыСистемы();")
        self.assertEqual(events.count("shutdown"), 1)
        self.assertEqual(json.loads(files[COMPLETION_PATH])["status"], "error")

    def test_actual_dispatch_control_prefix_binds_only_after_exact_validation(self):
        source = rendered_module("NativeOracleServer.bsl")
        prefix = exact_slice(source, "Процедура NativeВыполнитьПроверенный(",
                             '    ФайлРезультата = Новый Файл(') + "КонецПроцедуры"
        good = {"schema": Decimal(1), "nonce": NONCE,
                "token": TRANSPORT_TOKEN, "operation": "create"}
        cases = [good, {**good, "nonce": "c" * 32}, {**good, "token": "c" * 32},
                 {**good, "schema": True}, {**good, "schema": Decimal(2)},
                 {**good, "operation": "unknown"}, {**good, "extra": False},
                 {key: value for key, value in good.items() if key != "operation"}]
        for fields in cases:
            with self.subTest(fields=fields):
                vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
                control = BSLStructure()
                for key, value in fields.items():
                    control.insert(key, value)
                vm.register_function("ПривилегированныйРежим", lambda: False)
                vm.register_function("NativeПрочитатьJSON", lambda _: control)
                vm.execute(exact_routine(source, "NativeВыполнить") + "\n" + prefix)
                vm.execute('Ответ = NativeВыполнить("' + TRANSPORT_TOKEN + '");')
                expected = ({"status": "ok", "operation": "create", "phase": "complete"}
                            if fields is good else
                            {"status": "error", "operation": "dispatch", "phase": "control"})
                self.assertEqual(json.loads(transport_encode(vm.execute("Ответ"))), expected)

    def test_source_phases_cover_operations_and_preserve_original_rollback_order(self):
        source = rendered_module("NativeOracleServer.bsl")
        wrapper = exact_routine(source, "NativeВыполнить")
        self.assertLess(wrapper.index("NativeВыполнитьПроверенный("),
                        wrapper.index('Контекст.status = "ok";'))
        self.assertLess(wrapper.index("Исключение"), wrapper.index("Возврат Контекст;"))
        measurement = exact_routine(source, "NativeИзмерить", procedure=True)
        rollback = 'Исключение\n            ОтменитьТранзакцию();\n            ВызватьИсключение "process_failed";'
        self.assertEqual(measurement.count(rollback), 2)
        self.assertEqual(measurement.count('Контекст.phase = "begin";\n        НачатьТранзакцию();\n        Попытка'), 2)
        for phase, action in (("create_object", "Объект = Справочники.NativeOracleItems.СоздатьЭлемент();"),
                              ("set_code", 'Объект.Код = "K1";'),
                              ("set_payload", 'Объект.Payload = "alpha";'),
                              ("set_amount", "Объект.Amount = 1.25;"),
                              ("write", "Объект.Записать();"),
                              ("reference_capture", "Ссылка = Объект.Ссылка;"),
                              ("commit", "ЗафиксироватьТранзакцию();"),
                              ("reference_uuid", "ЗначениеСсылки = Строка(Ссылка.УникальныйИдентификатор());"),
                              ("reference_read", "Ссылка = NativeСохраненнаяСсылка(Корень);"),
                              ("get_object", "Объект = Ссылка.ПолучитьОбъект();"),
                              ("delete_object", "Объект.Удалить();")):
            self.assertRegex(measurement, re.escape('Контекст.phase = "' + phase + '";') +
                             r"\s+" + re.escape(action))
        self.assertIn('Контекст.phase = "reference_write";\n        ДанныеСсылки', measurement)
        self.assertLess(measurement.index("ЗафиксироватьТранзакцию();"),
                        measurement.index('Контекст.phase = "reference_uuid";'))
        self.assertLess(measurement.index('Контекст.phase = "reference_uuid";'),
                        measurement.index('Контекст.phase = "reference_write";'))
        self.assertIn('Контекст.phase = "readback";\n    После = NativeСостояние', measurement)
        managed = rendered_module("ManagedApplicationModule.bsl")
        allowed = set(re.search(r'СтрРазделить\("([a-z_,]+)"', managed).group(1).split(","))
        assigned = set(re.findall(r'Контекст.phase = "([a-z_]+)";', source)) | {"dispatch"}
        self.assertEqual(allowed, assigned)
        for forbidden in ("ИнформацияОбОшибке", "ОписаниеОшибки", "ПодробноеПредставлениеОшибки",
                          "ErrorInfo", "ErrorDescription"):
            self.assertNotIn(forbidden, source + managed)


# The private codec tests below execute the actual rendered reader/writer and
# create-tail source. JSON I/O and UUID construction are bounded host doubles,
# not a claim about native parser EOF/duplicate-key handling or UUID behavior.
PRIVATE_REFERENCE_PATH = TRANSPORT_ROOT + "/reference.json"
PRIVATE_UUID = "12345678-abcd-1234-abcd-1234567890ab"


def private_reference_bytes(**changes):
    return json.dumps({"nonce": NONCE, "reference": PRIVATE_UUID, **changes},
                      separators=(",", ":")).encode("utf-8")


def private_reference_vm(raw=None):
    vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
    events = []
    files = {} if raw is None else {PRIVATE_REFERENCE_PATH: raw}

    def file(path):
        assert path == PRIVATE_REFERENCE_PATH

        def exists():
            events.append("exists")
            return path in files

        def size():
            events.append("size")
            return Decimal(len(files[path]))

        return ControlledMembers(Существует=HostFunction("Существует", exists),
                                 Размер=HostFunction("Размер", size))

    def read_subset(value):
        if value is None or type(value) in (str, bool):
            return value
        if type(value) is int:
            return Decimal(value)
        if type(value) is dict:
            result = BSLStructure()
            for key, item in value.items():
                result.insert(key, read_subset(item))
            return result
        if type(value) is list:
            result = BSLArray()
            result.items[:] = [read_subset(item) for item in value]
            return result
        raise TypeError("Outside controlled private JSON subset")

    class Reader(BSLObject):
        def __init__(self):
            self.path = None

        def open(self, path):
            assert path == PRIVATE_REFERENCE_PATH and self.path is None
            events.append("read_open")
            self.path = path

        def read(self):
            assert self.path is not None
            events.append("read")
            return read_subset(json.loads(files[self.path].decode("utf-8-sig")))

        def close(self):
            assert self.path is not None
            events.append("read_close")

        def get_member(self, name):
            return HostFunction(name, {"ОткрытьФайл": self.open, "Закрыть": self.close}[name],
                                returns_value=False)

    class Writer(BSLObject):
        def __init__(self):
            self.path = None

        def open(self, path):
            assert path == PRIVATE_REFERENCE_PATH and path not in files and self.path is None
            events.append("write_open")
            self.path = path
            files[path] = b""

        def write(self, data):
            assert self.path is not None and files[self.path] == b""
            events.append("write")
            files[self.path] = transport_encode(data)

        def close(self):
            assert self.path is not None and files[self.path]
            events.append("write_close")

        def get_member(self, name):
            return HostFunction(name, {"ОткрытьФайл": self.open, "Закрыть": self.close}[name],
                                returns_value=False)

    def captured_uuid():
        events.append("uuid_capture")
        return uuid.UUID(PRIVATE_UUID)

    reference = ControlledMembers(УникальныйИдентификатор=HostFunction(
        "УникальныйИдентификатор", captured_uuid))

    def parse_uuid(value):
        events.append("uuid_parse")
        return uuid.UUID(value)

    def get_reference(identifier):
        assert type(identifier) is uuid.UUID and str(identifier) == PRIVATE_UUID
        events.append("get_reference")
        return reference

    vm.execute("Перем Справочники, Ссылка, Контекст, Корень;")
    vm.variables["справочники"] = ControlledMembers(NativeOracleItems=ControlledMembers(
        ПолучитьСсылку=HostFunction("ПолучитьСсылку", get_reference)))
    vm.variables["ссылка"] = reference
    vm.variables["контекст"] = finite_reply("error", "create", "commit")
    vm.variables["корень"] = TRANSPORT_ROOT
    vm.register_type("Файл", file)
    vm.register_type("ЧтениеJSON", Reader)
    vm.register_type("ЗаписьJSON", Writer)
    vm.register_type("УникальныйИдентификатор", parse_uuid)
    vm.register_function("ПрочитатьJSON", lambda reader: reader.read())
    vm.register_function("ЗаписатьJSON", lambda writer, data: writer.write(data), returns_value=False)
    source = rendered_module("NativeOracleServer.bsl")
    vm.execute(exact_routine(source, "NativeСохраненнаяСсылка") + "\n" +
               exact_routine(source, "NativeПрочитатьJSON") + "\n" +
               exact_routine(source, "NativeЗаписатьJSON", procedure=True))
    return vm, events, files, reference


def private_reference_write_source():
    return exact_slice(rendered_module("NativeOracleServer.bsl"),
                       '        Контекст.phase = "reference_uuid";',
                       '    ИначеЕсли Операция = "update" Или Операция = "delete" Тогда')


class DBPrivateReferenceJSONTests(unittest.TestCase):
    def test_exact_create_tail_writes_only_bound_nonce_and_canonical_uuid_once(self):
        vm, events, files, reference = private_reference_vm()
        self.assertFalse(catch_source(vm, private_reference_write_source()))
        self.assertEqual(files, {PRIVATE_REFERENCE_PATH: private_reference_bytes()})
        self.assertEqual(events, ["uuid_capture", "exists", "write_open", "write", "write_close"])
        self.assertEqual(vm.execute("Контекст.phase"), "reference_write")
        self.assertIs(vm.execute("NativeСохраненнаяСсылка(Корень)"), reference)
        before = dict(files)
        self.assertTrue(catch_source(vm, private_reference_write_source()))
        self.assertEqual(files, before)
        self.assertEqual(events.count("write_open"), 1)
        self.assertEqual(events.count("write"), 1)

    def test_preexisting_reference_is_never_opened_or_overwritten(self):
        vm, events, files, _ = private_reference_vm(b"prior private evidence")
        self.assertTrue(catch_source(vm, private_reference_write_source()))
        self.assertEqual(files, {PRIVATE_REFERENCE_PATH: b"prior private evidence"})
        self.assertEqual(events, ["uuid_capture", "exists"])

    def test_exact_codec_byte_budget_and_preread_boundary(self):
        compact = private_reference_bytes()
        self.assertEqual(len(compact), 32 + 36 + 27)
        self.assertTrue(compact.isascii())
        pretty_bom = b"\xef\xbb\xbf" + json.dumps(json.loads(compact), indent=4).replace("\n", "\r\n").encode("ascii")
        self.assertEqual(len(pretty_bom), 114)
        maximum = b"\xef\xbb\xbf" + compact + b" " * 30
        self.assertEqual(len(maximum), 128)
        for raw in (compact, b"\xef\xbb\xbf" + compact, pretty_bom, maximum):
            with self.subTest(length=len(raw)):
                vm, events, _, reference = private_reference_vm(raw)
                self.assertIs(vm.execute("NativeСохраненнаяСсылка(Корень)"), reference)
                self.assertLess(events.index("size"), events.index("read_open"))
                self.assertEqual(events[-3:], ["read_close", "uuid_parse", "get_reference"])
        for raw in (b"", maximum + b" ", b" " * 4097):
            with self.subTest(rejected_length=len(raw)):
                vm, events, _, _ = private_reference_vm(raw)
                self.assertTrue(catch_source(vm, "NativeСохраненнаяСсылка(Корень);"))
                self.assertNotIn("read_open", events)
                self.assertNotIn("uuid_parse", events)
        vm, events, _, _ = private_reference_vm()
        self.assertIsNone(vm.execute("NativeСохраненнаяСсылка(Корень)"))
        self.assertEqual(events, ["exists"])

    def test_exact_parsed_object_rejects_extra_missing_and_wrong_keys(self):
        good = json.loads(private_reference_bytes())
        bad = [None, False, [], "reference", {**good, "extra": False}, {},
               {"nonce": NONCE}, {"reference": PRIVATE_UUID},
               {"nonce": NONCE, "unexpected": PRIVATE_UUID},
               {"unexpected": NONCE, "reference": PRIVATE_UUID},
               {"NONCE": NONCE, "reference": PRIVATE_UUID},
               {"nonce": NONCE, "Reference": PRIVATE_UUID},
               {"NONCE": NONCE, "REFERENCE": PRIVATE_UUID}]
        for value in bad:
            with self.subTest(value=value):
                raw = json.dumps(value, separators=(",", ":")).encode("ascii")
                self.assertLessEqual(len(raw), 128)
                vm, events, _, _ = private_reference_vm(raw)
                self.assertTrue(catch_source(vm, "NativeСохраненнаяСсылка(Корень);"))
                self.assertIn("read_close", events)
                self.assertNotIn("uuid_parse", events)
                self.assertNotIn("get_reference", events)

    def test_nonce_is_source_bound_and_both_values_must_be_strings(self):
        for key, value in (("nonce", "f" * 32), ("nonce", NONCE.upper()),
                           ("nonce", ""), ("nonce", None), ("nonce", False),
                           ("nonce", 32), ("nonce", []), ("reference", None),
                           ("reference", False), ("reference", 36), ("reference", {})):
            with self.subTest(key=key, value=value):
                vm, events, _, _ = private_reference_vm(private_reference_bytes(**{key: value}))
                self.assertTrue(catch_source(vm, "NativeСохраненнаяСсылка(Корень);"))
                self.assertIn("read_close", events)
                self.assertNotIn("uuid_parse", events)
                self.assertNotIn("get_reference", events)

    def test_uuid_length_parse_and_canonical_roundtrip_precede_getref(self):
        for value in ("", PRIVATE_UUID.replace("-", ""), "{" + PRIVATE_UUID + "}",
                      " " + PRIVATE_UUID, PRIVATE_UUID + " ", "x" * 36,
                      PRIVATE_UUID.upper()):
            with self.subTest(value=value):
                vm, events, _, _ = private_reference_vm(private_reference_bytes(reference=value))
                self.assertTrue(catch_source(vm, "NativeСохраненнаяСсылка(Корень);"))
                self.assertEqual("uuid_parse" in events, len(value) == 36)
                self.assertNotIn("get_reference", events)

    def test_reader_parse_failures_never_reach_uuid_or_getref(self):
        for raw in (b"{", b"\xff"):
            with self.subTest(raw=raw):
                vm, events, _, _ = private_reference_vm(raw)
                self.assertTrue(catch_source(vm, "NativeСохраненнаяСсылка(Корень);"))
                self.assertEqual(events[-2:], ["read_open", "read"])
                self.assertNotIn("uuid_parse", events)
                self.assertNotIn("get_reference", events)

    def test_textdocument_dependency_removed_without_raising_shared_reader_cap(self):
        source = rendered_module("NativeOracleServer.bsl")
        self.assertNotIn("ТекстовыйДокумент", source)
        self.assertNotIn("reference.txt", source)
        private = exact_routine(source, "NativeСохраненнаяСсылка")
        generic = exact_routine(source, "NativeПрочитатьJSON")
        self.assertIn("Файл.Размер() > 128", private)
        self.assertLess(private.index("Файл.Размер() > 128"), private.index("NativeПрочитатьJSON("))
        self.assertIn("Файл.Размер() > 4096", generic)
        self.assertIn('Если Строка(Идентификатор) <> Значение Тогда', private)
        self.assertIn('ПолучитьСсылку(Идентификатор)', private)


def measurement_vm(operation, *, failure=None, rollback_error=False):
    """Exact measured routine + wrapper; explicit synthetic dispatcher/DB gap."""
    vm = Interpreter(lambda _: None, native_target=LINUX_8_3_27_1508)
    events = []
    reads = 0

    def event(name):
        events.append(name)
        if failure == name or (name == "rollback" and rollback_error):
            raise ValueError(ERROR_CANARY)

    class Item(BSLObject):
        def set_member(self, name, value):
            phase = {"Код": "set_code", "Payload": "set_payload", "Amount": "set_amount"}[name]
            event(phase)

        def get_member(self, name):
            if name == "Ссылка":
                event("reference_capture")
                return reference
            return HostFunction(name, lambda: event({"Записать": "write", "Удалить": "delete_object"}[name]),
                                returns_value=False)

    item = Item()

    def get_object():
        event("get_object")
        return item

    def reference_uuid():
        event("reference_uuid")
        return uuid.UUID(PRIVATE_UUID)

    reference = ControlledMembers(
        ПолучитьОбъект=HostFunction("ПолучитьОбъект", get_object),
        УникальныйИдентификатор=HostFunction("УникальныйИдентификатор", reference_uuid))

    def state(root):
        nonlocal reads
        assert root == TRANSPORT_ROOT
        reads += 1
        event("readback_before" if reads == 1 else "readback_after")
        empty = (operation == "create" and reads == 1) or (operation == "delete" and reads == 2)
        alpha = (operation == "create" and reads == 2) or (operation == "update" and reads == 1)
        return BSLStructure(",".join(STATE_FIELDS), Decimal(0 if empty else 1),
                            None if empty else "K1", None if empty else ("alpha" if alpha else "beta"),
                            None if empty else ("1.25" if alpha else "-2.50"),
                            None if empty else False,
                            (None if operation == "create" else False) if empty else True)

    def create():
        event("create_object")
        return item

    def saved(root):
        assert root == TRANSPORT_ROOT
        event("reference_read")
        return reference

    def file(path):
        assert path == PRIVATE_REFERENCE_PATH
        event("reference_write")
        return ControlledMembers(ПолноеИмя=path, Существует=HostFunction("Существует", lambda: False))

    class Writer(BSLObject):
        def __init__(self):
            self.path = self.raw = None

        def open(self, path):
            assert path == PRIVATE_REFERENCE_PATH and self.path is None
            self.path = path

        def write(self, data):
            assert self.path is not None and self.raw is None
            self.raw = transport_encode(data)
            assert json.loads(self.raw) == {"nonce": NONCE, "reference": PRIVATE_UUID}

        def close(self):
            assert self.raw is not None

        def get_member(self, name):
            return HostFunction(name, {"ОткрытьФайл": self.open, "Закрыть": self.close}[name],
                                returns_value=False)

    vm.execute("Перем Справочники;")
    vm.variables["справочники"] = ControlledMembers(NativeOracleItems=ControlledMembers(
        СоздатьЭлемент=HostFunction("СоздатьЭлемент", create)))
    vm.register_function("NativeСостояние", state)
    vm.register_function("NativeСохраненнаяСсылка", saved)
    vm.register_function("НачатьТранзакцию", lambda: event("begin"), returns_value=False)
    vm.register_function("ЗафиксироватьТранзакцию", lambda: event("commit"), returns_value=False)
    vm.register_function("ОтменитьТранзакцию", lambda: event("rollback"), returns_value=False)
    vm.register_type("Файл", file)
    vm.register_type("ЗаписьJSON", Writer)
    vm.register_function("ЗаписатьJSON", lambda writer, data: writer.write(data), returns_value=False)
    source = rendered_module("NativeOracleServer.bsl")
    vm.execute(exact_routine(source, "NativeВыполнить") + "\n" +
               exact_routine(source, "NativeЗаписатьJSON", procedure=True) + "\n" +
               exact_routine(source, "NativeИзмерить", procedure=True))
    # The real control/identity dispatcher is tested independently. This declared
    # bridge supplies only the approved operation and initially absent result.
    vm.execute('Процедура NativeВыполнитьПроверенный(ТокенЗапуска, Контекст)\n'
               'Контекст.operation = "' + operation + '";\n'
               'Результат = Новый Структура("' + ",".join(STATE_FIELDS) + '");\n'
               'NativeИзмерить("' + operation + '", Результат, "' + TRANSPORT_ROOT + '", Контекст);\n'
               'КонецПроцедуры')
    return vm, events


class DBControlledTransactionCompletionTests(unittest.TestCase):
    def test_actual_measurement_faults_keep_the_last_phase_and_original_rollback(self):
        transactional = {
            "create": ("create_object", "set_code", "set_payload", "set_amount", "write", "reference_capture", "commit"),
            "update": ("reference_read", "get_object", "set_payload", "set_amount", "write", "commit"),
            "delete": ("reference_read", "get_object", "delete_object", "commit"),
        }
        for operation, inside in transactional.items():
            phases = ("readback_before", "begin") + inside
            if operation == "create":
                phases += ("reference_uuid", "reference_write")
            phases += ("readback_after",)
            for failure in phases:
                with self.subTest(operation=operation, failure=failure):
                    vm, events = measurement_vm(operation, failure=failure)
                    vm.execute('Ответ = NativeВыполнить("' + TRANSPORT_TOKEN + '");')
                    wire = transport_encode(vm.execute("Ответ"))
                    phase = "readback" if failure.startswith("readback_") else failure
                    self.assertEqual(json.loads(wire),
                                     {"status": "error", "operation": operation, "phase": phase})
                    self.assertEqual(events.count("rollback"), int(failure in inside))
                    self.assertEqual(events[-1], "rollback" if failure in inside else failure)
                    self.assertNotIn(ERROR_CANARY.encode(), wire)
                    self.assertNotIn(PRIVATE_UUID.encode(), wire)

    def test_rollback_failure_cannot_erase_error_or_report_success(self):
        for operation in ("create", "update", "delete"):
            with self.subTest(operation=operation):
                failure = "delete_object" if operation == "delete" else "write"
                vm, events = measurement_vm(operation, failure=failure, rollback_error=True)
                vm.execute('Ответ = NativeВыполнить("' + TRANSPORT_TOKEN + '");')
                self.assertEqual(json.loads(transport_encode(vm.execute("Ответ"))),
                                 {"status": "error", "operation": operation, "phase": failure})
                self.assertEqual(events[-2:], [failure, "rollback"])
                self.assertNotIn("commit", events)

    def test_successful_controlled_measurement_returns_complete_after_readback(self):
        for operation in ("create", "update", "delete", "observe"):
            with self.subTest(operation=operation):
                vm, events = measurement_vm(operation)
                vm.execute('Ответ = NativeВыполнить("' + TRANSPORT_TOKEN + '");')
                self.assertEqual(json.loads(transport_encode(vm.execute("Ответ"))),
                                 {"status": "ok", "operation": operation, "phase": "complete"})
                self.assertEqual(events[-1], "readback_after")
                self.assertNotIn("rollback", events)
                self.assertEqual(events.count("commit"), int(operation != "observe"))


if __name__ == "__main__": unittest.main()
