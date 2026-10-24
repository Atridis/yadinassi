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
from yadinassi.values import BSLObject, HostFunction, NULL
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
                    exact_routine(text, "NativeВыполнить", procedure=True),
                )), source="synthetic-exact-db-bootstrap-readback")
                invocation = 'NativeВыполнить("' + TRANSPORT_TOKEN + '");'
                if tampered:
                    with self.assertRaisesRegex(BSLRuntimeError, "invalid_marker"):
                        vm.execute(invocation)
                    self.assertEqual(metadata_checks, [])
                    self.assertIsNone(writer.path)
                    self.assertIsNone(writer.raw)
                else:
                    vm.execute(invocation)
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
                           '        НачатьТранзакцию();')
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


if __name__ == "__main__": unittest.main()
