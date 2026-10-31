"""Original bounded file-DB oracle metadata, pinned to native XML format 2.20.

This only constructs and checks source trees. A unit fixture is not native proof.
Catalog/common-module serialization follows linked primary structural specimens in
metadata/SOURCES.md, with original names, values and UUIDs and no borrowed code.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import stat
import sys
import uuid
from pathlib import Path, PurePosixPath
from xml.parsers import expat
import xml.etree.ElementTree as ET

try:
    from inject_modules import (DraftError, read_xml, xml_signature, single,
                                inspect_native_dump, bsl_string)
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native_1c_bootstrap"))
    from inject_modules import (DraftError, read_xml, xml_signature, single,
                                inspect_native_dump, bsl_string)

SETUP_USER = "NativeOracleSetup"
CRUD_USER = "NativeOracleCRUD"
SETUP_ROLE = "NativeOracleSetupAdministrator"
CRUD_ROLE = "NativeOracleCatalogCRUD"
CATALOG = "NativeOracleItems"
SERVER = "NativeOracleServer"
NS = "http://v8.1c.ru/8.3/MDClasses"
RNS = "http://v8.1c.ru/8.2/roles"
V8 = "http://v8.1c.ru/8.1/data/core"
XR = "http://v8.1c.ru/8.3/xcf/readable"
FORMAT = "2.20"
ROOT = Path(__file__).resolve().parent
MODULE_FILES = {"SessionModule.bsl": "Ext/SessionModule.bsl",
                "ManagedApplicationModule.bsl": "Ext/ManagedApplicationModule.bsl",
                "NativeOracleServer.bsl": "CommonModules/NativeOracleServer/Ext/Module.bsl"}
INJECTED_FILES = frozenset(MODULE_FILES.values()) | {
    "Catalogs/NativeOracleItems.xml", "CommonModules/NativeOracleServer.xml",
    f"Roles/{SETUP_ROLE}.xml", f"Roles/{CRUD_ROLE}.xml",
    f"Roles/{SETUP_ROLE}/Ext/Rights.xml", f"Roles/{CRUD_ROLE}/Ext/Rights.xml"}
SETUP_RIGHTS = frozenset({"Administration", "DataAdministration", "ThickClient", "MainWindowModeNormal"})
CRUD_RIGHTS = frozenset({"Read", "Insert", "Update", "Delete"})



def _matrix(enabled):
    if type(enabled) is not bool:
        raise DraftError("Invalid fixed Catalog matrix selector")
    if enabled:
        import catalog_field_matrix
        return catalog_field_matrix
    return None


def _description_mode(case, matrix, reference=None):
    if case is not None:
        from catalog_description_measurement import CASES
        if type(case) is not str or case not in CASES or matrix or reference is not None:
            raise DraftError("Invalid closed Description case")


def _inventory(root: Path) -> dict[str, str]:
    if any(path.is_symlink() for path in (root, *root.parents)) or not root.is_dir():
        raise DraftError("Metadata tree must be a real directory")
    result, total = {}, 0
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            if not 0 < info.st_size <= 1_048_576:
                raise DraftError("Metadata file limit")
            total += info.st_size
            result[path.relative_to(root).as_posix()] = "file"
        elif stat.S_ISDIR(info.st_mode):
            result[path.relative_to(root).as_posix()] = "directory"
        else:
            raise DraftError("Indirect or special metadata entry")
        if len(result) > 128 or total > 4_194_304:
            raise DraftError("Metadata tree limit")
    return result


def _hashes(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name, kind in _inventory(root).items() if kind == "file"}


def _separate(source: Path, target: Path) -> tuple[Path, Path]:
    for path in (source, target):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise DraftError("Indirect metadata path")
    source, target = source.resolve(), target.resolve()
    if source == target or source in target.parents or target in source.parents or target.exists():
        raise DraftError("Metadata destination must be fresh and non-overlapping")
    return source, target


def _template(name: str, values: dict[str, str], *, description_case=None, numeric_case=None, zero_case=None) -> bytes:
    if zero_case is not None:
        _zero_mode(zero_case, numeric_case=numeric_case, description_case=description_case)
        from catalog_zero_code_measurement import transform
        source = (ROOT / "metadata" / name).read_bytes()
        raw = transform(source,name='metadata/'+name,case=zero_case).decode('utf-8-sig')
    elif numeric_case is not None:
        _numeric_mode(numeric_case, description_case=description_case)
        from catalog_numeric_code_measurement import transform
        source = (ROOT / "metadata" / name).read_bytes()
        raw = transform(source, name="metadata/" + name, case=numeric_case).decode("utf-8-sig")
    elif description_case is None:
        raw = (ROOT / "metadata" / name).read_text(encoding="utf-8-sig")
    else:
        from catalog_description_measurement import transform
        source = (ROOT / "metadata" / name).read_bytes()
        raw = transform(source, name="metadata/" + name, case=description_case).decode("utf-8-sig")
    def replace(match):
        if match[1] not in values:
            raise DraftError("Unknown metadata template literal")
        value = values[match[1]]
        if not re.fullmatch(r"[\w.-]+", value):
            raise DraftError("Invalid metadata template literal")
        return value
    return re.sub(r"@@([A-Z_]+)@@", replace, raw).encode("utf-8-sig")


def _module(name: str, nonce: str, evidence: str, *, metadata_catalog_probe=False, reference_case=None, description_case=None, description_rows=False, numeric_case=None, zero_case=None) -> bytes:
    values = {"NONCE": nonce, "EVIDENCE": evidence, "SETUP_USER": SETUP_USER,
              "CRUD_USER": CRUD_USER, "SETUP_ROLE": SETUP_ROLE, "CRUD_ROLE": CRUD_ROLE}
    if zero_case is not None and name in ('NativeOracleServer.bsl', 'ManagedApplicationModule.bsl'):
        _zero_mode(zero_case,numeric_case=numeric_case,description_case=description_case,reference_case=reference_case)
        from catalog_zero_code_measurement import instrument_module
        source = (ROOT / "modules" / name).read_bytes()
        raw = instrument_module(source,name=name,case=zero_case).decode('utf-8-sig')
    elif numeric_case is not None and name == "NativeOracleServer.bsl":
        _numeric_mode(numeric_case, description_case=description_case, reference_case=reference_case)
        from catalog_numeric_code_measurement import transform
        source = (ROOT / "modules" / name).read_bytes()
        raw = transform(source, name="modules/" + name, case=numeric_case).decode("utf-8-sig")
    elif description_case is not None and name == "NativeOracleServer.bsl":
        if reference_case is not None:
            raise DraftError("Incompatible closed Catalog cases")
        from catalog_description_measurement import transform
        source = (ROOT / "modules" / name).read_bytes()
        raw = transform(source, name="modules/" + name, case=description_case, rows=description_rows).decode("utf-8-sig")
    else:
        raw = (ROOT / "modules" / name).read_text(encoding="utf-8-sig")
    if metadata_catalog_probe:
        if any((reference_case is not None, description_case is not None, numeric_case is not None, zero_case is not None)):
            raise DraftError("Incompatible metadata probe")
        if name in ('NativeOracleServer.bsl', 'ManagedApplicationModule.bsl'):
            from metadata_catalog_instrument import instrument
            raw = instrument(raw.encode('utf-8'), name=name,
                probe=(ROOT / 'modules' / 'MetadataCatalogProbe.bsl').read_bytes()).decode('utf-8')
    if reference_case is not None:
        from catalog_reference_native import render_template
        if name == "NativeOracleServer.bsl":
            raw = render_template(raw, reference_case, DraftError)
    def replace(match):
        if match[1] not in values:
            raise DraftError("Unknown module template literal")
        return bsl_string(values[match[1]])
    return re.sub(r"@@([A-Z_]+)@@", replace, raw).encode("utf-8-sig")


def _add_references(raw: bytes, *, catalog_field_matrix=False) -> bytes:
    matrix = _matrix(catalog_field_matrix)
    parser, stack, spans = expat.ParserCreate(), [], []
    def start(name, attrs):
        stack.append(name.split(":")[-1])
        if stack == ["MetaDataObject", "Configuration", "ChildObjects"]:
            if attrs:
                raise DraftError("Unexpected child-object attributes")
            index = parser.CurrentByteIndex
            end = raw.find(b">", index)
            spans.append((index, end + 1, name))
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    parser.Parse(raw, True)
    if len(spans) != 1:
        raise DraftError("Ambiguous native child references")
    start, end, name = spans[0]
    prefix = name.rsplit(":", 1)[0] + ":" if ":" in name else ""
    refs = [("Role", SETUP_ROLE), ("Role", CRUD_ROLE), ("CommonModule", SERVER), ("Catalog", CATALOG)]
    if matrix:
        refs.extend(("Catalog", name) for name, _ in matrix.VARIANTS)
    text = "".join(f"<{prefix}{kind}>{value}</{prefix}{kind}>" for kind, value in refs).encode()
    if raw[start:end].rstrip().endswith(b"/>"):
        return raw[:end-2] + b">" + text + f"</{name}>".encode() + raw[end:]
    return raw[:end] + text + raw[end:]


def _canonical(node: ET.Element) -> tuple:
    """Namespace-sensitive equality, permitting only native ordering of rights."""
    if node.tag.startswith("{" + RNS + "}"):
        if node.tail and node.tail.strip():
            raise DraftError("Unexpected mixed-content rights")
        value = node.text or ""
        nested = [_canonical(child) for child in node]
        if nested:
            if value.strip():
                raise DraftError("Unexpected mixed-content rights")
            value = ""
        return node.tag, tuple(sorted(node.attrib.items())), value, tuple(sorted(nested))
    return xml_signature(node)


def _uuid(value: str) -> str:
    try:
        if str(uuid.UUID(value)) == value:
            return value
    except (ValueError, TypeError, AttributeError):
        pass
    raise DraftError("Invalid metadata UUID")


def _zero_mode(zero_case, *, numeric_case=None, description_case=None, reference_case=None, catalog_field_matrix=False):
    if zero_case is not None and (type(zero_case) is not str or zero_case not in ('zero0','zero8')
            or numeric_case is not None or description_case is not None or reference_case is not None or catalog_field_matrix):
        raise ValueError('invalid_zero_code_case')


def _numeric_mode(numeric_case, *, description_case=None, reference_case=None, catalog_field_matrix=False):
    if numeric_case is not None and (type(numeric_case) is not str or numeric_case not in ('number3','number6')
            or description_case is not None or reference_case is not None or catalog_field_matrix):
        raise DraftError("Incompatible closed Numeric Code case")


def inspect(root: Path, version: int, *, catalog_field_matrix=False, description_case=None, numeric_case=None, zero_case=None) -> dict:
    """Exact original fixture/security scope. Unknown defaults or grants fail closed."""
    if type(version) is not int or version not in (1, 2):
        raise DraftError("Unsupported oracle metadata version")
    matrix = _matrix(catalog_field_matrix)
    _description_mode(description_case, catalog_field_matrix)
    _numeric_mode(numeric_case, description_case=description_case, catalog_field_matrix=catalog_field_matrix)
    _zero_mode(zero_case, numeric_case=numeric_case, description_case=description_case, catalog_field_matrix=catalog_field_matrix)
    inventory = _inventory(root)
    _, xml = read_xml(root / "Configuration.xml")
    ns = "{" + NS + "}"
    if xml.tag != ns + "MetaDataObject" or xml.attrib != {"version": FORMAT}:
        raise DraftError("Unreviewed native metadata format")
    config = single(xml, "Configuration")
    config_uuid = _uuid(config.attrib.get("uuid"))
    props, child = single(config, "Properties"), single(config, "ChildObjects")
    name = single(props, "Name").text or ""
    if not re.fullmatch(r"[^\W\d]\w*", name):
        raise DraftError("Invalid configuration name")
    if single(props, "DefaultRunMode").text != "ManagedApplication":
        raise DraftError("Unexpected application mode")
    defaults = [node for node in props if node.tag == ns + "DefaultRoles"]
    if len(defaults) > 1 or any(node.attrib or list(node) or (node.text or "").strip() for node in defaults):
        raise DraftError("Unexpected default roles")
    refs = [(node.tag, node.text) for node in child]
    if child.attrib or any(node.attrib or list(node) for node in child):
        raise DraftError("Unexpected child references")
    expected = {(ns+"Role", SETUP_ROLE), (ns+"Role", CRUD_ROLE), (ns+"Catalog", CATALOG), (ns+"CommonModule", SERVER)}
    languages = [value for tag, value in refs if tag == ns+"Language"]
    if matrix:
        expected.update((ns+"Catalog", name) for name, _ in matrix.VARIANTS)
    if len(refs) != len(set(refs)) or set(refs) != expected | {(ns+"Language", value) for value in languages}:
        raise DraftError("Unexpected metadata object")
    if any(not value or not re.fullmatch(r"[^\W\d]\w*", value) for value in languages):
        raise DraftError("Invalid language reference")
    allowed = INJECTED_FILES | {"Configuration.xml", "ConfigDumpInfo.xml"} | {f"Languages/{value}.xml" for value in languages}
    if matrix:
        allowed |= matrix.FILES
    files = {path for path, kind in inventory.items() if kind == "file"}
    if files - allowed or not (INJECTED_FILES | (matrix.FILES if matrix else set())) <= files:
        raise DraftError("Unexpected or missing metadata file")
    expected_dirs = {str(parent) for path in files for parent in Path(path).parents if str(parent) != "."}
    if {path for path, kind in inventory.items() if kind == "directory"} != expected_dirs:
        raise DraftError("Unexpected metadata directory")
    values = {"CONFIGURATION_NAME": name, "PAYLOAD_LENGTH": "32" if version == 1 else "64"}
    ids = [config_uuid]
    for role, rights_template in [(SETUP_ROLE, "SetupRights.xml"), (CRUD_ROLE, "CRUDRights.xml")]:
        _, role_xml = read_xml(root / f"Roles/{role}.xml")
        identity = _uuid(single(role_xml, "Role").attrib.get("uuid"))
        ids.append(identity)
        values.update(ROLE_NAME=role, ROLE_UUID=identity)
        if _canonical(role_xml) != _canonical(ET.fromstring(_template("Role.xml", values))):
            raise DraftError("Unexpected role metadata")
        _, rights = read_xml(root / f"Roles/{role}/Ext/Rights.xml")
        if _canonical(rights) != _canonical(ET.fromstring(_template(rights_template, values))):
            raise DraftError("Unexpected role grant or rights default")
    _, common = read_xml(root / "CommonModules/NativeOracleServer.xml")
    identity = _uuid(single(common, "CommonModule").attrib.get("uuid"))
    ids.append(identity)
    values["MODULE_UUID"] = identity
    if xml_signature(common) != xml_signature(ET.fromstring(_template("CommonModule.xml", values))):
        raise DraftError("Unexpected common-module privileges or context")
    _, catalog = read_xml(root / "Catalogs/NativeOracleItems.xml")
    obj = single(catalog, "Catalog")
    values["CATALOG_UUID"] = _uuid(obj.attrib.get("uuid"))
    ids.append(values["CATALOG_UUID"])
    attributes = list(single(obj, "ChildObjects"))
    if len(attributes) != 2:
        raise DraftError("Unexpected catalog children")
    for attr, key in zip(attributes, ("PAYLOAD_UUID", "AMOUNT_UUID")):
        values[key] = _uuid(attr.attrib.get("uuid"))
        ids.append(values[key])
    generated = list(single(obj, "InternalInfo"))
    if len(generated) != 5:
        raise DraftError("Unexpected catalog generated types")
    for node, category in zip(generated, ("OBJECT", "REF", "SELECTION", "LIST", "MANAGER")):
        for field, suffix in (("TypeId", "TYPE"), ("ValueId", "VALUE")):
            values[f"{category}_{suffix}_UUID"] = _uuid(single(node, field).text)
            ids.append(values[f"{category}_{suffix}_UUID"])
    if matrix:
        for extra_name, kind in matrix.VARIANTS:
            _, extra = read_xml(root / f"Catalogs/{extra_name}.xml")
            item = single(extra, "Catalog")
            extra_values = dict(values)
            extra_values["CATALOG_UUID"] = _uuid(item.attrib.get("uuid"))
            ids.append(extra_values["CATALOG_UUID"])
            generated_extra = list(single(item, "InternalInfo"))
            if len(generated_extra) != 5:
                raise DraftError("Unexpected fixed Catalog generated types")
            for node, category in zip(generated_extra, ("OBJECT", "REF", "SELECTION", "LIST", "MANAGER")):
                for field, suffix in (("TypeId", "TYPE"), ("ValueId", "VALUE")):
                    key = f"{category}_{suffix}_UUID"
                    extra_values[key] = _uuid(single(node, field).text)
                    ids.append(extra_values[key])
            expected_extra = matrix.catalog(_template("Catalog.xml", extra_values), extra_name, kind, DraftError)
            if xml_signature(extra) != xml_signature(ET.fromstring(expected_extra)):
                raise DraftError("Unexpected fixed Catalog schema")
    if len(ids) != len(set(ids)):
        raise DraftError("Metadata UUID collision")
    if xml_signature(catalog) != xml_signature(ET.fromstring(_template("Catalog.xml", values, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case))):
        raise DraftError("Unexpected catalog schema or qualifier")
    xml_signature(xml)
    return {"version": version, "payload_length": int(values["PAYLOAD_LENGTH"]),
            "amount_digits": 9, "amount_scale": 2, "roles_verified": True,
            "nonprivileged_module": True}


def inject(native_dump: Path, target: Path, *, nonce: str, evidence: Path, metadata_catalog_probe=False, catalog_field_matrix=False, reference_case=None, description_case=None, description_rows=False, numeric_case=None, zero_case=None) -> dict:
    matrix = _matrix(catalog_field_matrix)
    if type(description_rows) is not bool or description_rows and description_case is None:
        raise DraftError('Invalid closed Description rows mode')
    _description_mode(description_case, catalog_field_matrix, reference_case)
    _numeric_mode(numeric_case, description_case=description_case, reference_case=reference_case, catalog_field_matrix=catalog_field_matrix)
    _zero_mode(zero_case, numeric_case=numeric_case, description_case=description_case, reference_case=reference_case, catalog_field_matrix=catalog_field_matrix)
    if type(nonce) is not str or not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise DraftError("Invalid oracle nonce")
    ep = str(evidence)
    path = PurePosixPath(ep)
    if not path.is_absolute() or str(path) != ep or ".." in path.parts or path.parts[:2] != ("/", "tmp"):
        raise DraftError("Oracle evidence must be a normalized tmpfs path")
    bsl_string(ep)
    native_dump, target = _separate(native_dump, target)
    original = _hashes(native_dump)
    native = inspect_native_dump(native_dump)
    if not re.fullmatch(r"[^\W\d]\w*", native["configuration_name"]):
        raise DraftError("Invalid configuration name")
    if native["namespace"] != NS or native["format_version"] != FORMAT:
        raise DraftError("No reviewed native schema")
    allowed = {"Configuration.xml", "ConfigDumpInfo.xml"} | {f"Languages/{name}.xml" for name in native["languages"]}
    if set(original) - allowed:
        raise DraftError("Unexpected original native source file")
    source_dirs = {path for path, kind in _inventory(native_dump).items() if kind == "directory"}
    expected_dirs = {str(parent) for path in original for parent in Path(path).parents if str(parent) != "."}
    if source_dirs != expected_dirs:
        raise DraftError("Unexpected original native source directory")
    values = {"CONFIGURATION_NAME": native["configuration_name"], "PAYLOAD_LENGTH": "32"}
    keys = {"CATALOG_UUID", "PAYLOAD_UUID", "AMOUNT_UUID", "MODULE_UUID"} | {
        f"{category}_{suffix}_UUID" for category in ("OBJECT", "REF", "SELECTION", "LIST", "MANAGER") for suffix in ("TYPE", "VALUE")}
    values.update({key: str(uuid.uuid4()) for key in keys})
    added = {"Catalogs/NativeOracleItems.xml": _template("Catalog.xml", values, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case),
             "CommonModules/NativeOracleServer.xml": _template("CommonModule.xml", values)}
    for role, template in ((SETUP_ROLE, "SetupRights.xml"), (CRUD_ROLE, "CRUDRights.xml")):
        values.update(ROLE_NAME=role, ROLE_UUID=str(uuid.uuid4()))
        added[f"Roles/{role}.xml"] = _template("Role.xml", values)
        added[f"Roles/{role}/Ext/Rights.xml"] = _template(template, values)
    if type(metadata_catalog_probe) is not bool or (metadata_catalog_probe and catalog_field_matrix):
        raise DraftError("Incompatible metadata probe")
    added.update({path: _module(name, nonce, ep, metadata_catalog_probe=metadata_catalog_probe, reference_case=reference_case, description_case=description_case, description_rows=description_rows, numeric_case=numeric_case, zero_case=zero_case) for name, path in MODULE_FILES.items()})
    if matrix:
        for extra_name, kind in matrix.VARIANTS:
            extra_values = dict(values)
            extra_values.update({key: str(uuid.uuid4()) for key in matrix.UUID_KEYS})
            added[f"Catalogs/{extra_name}.xml"] = matrix.catalog(
                _template("Catalog.xml", extra_values), extra_name, kind, DraftError)
        server = MODULE_FILES["NativeOracleServer.bsl"]
        added[server] = matrix.server_module(added[server], DraftError)
    configuration = _add_references((native_dump / "Configuration.xml").read_bytes(),
                                    catalog_field_matrix=catalog_field_matrix)
    shutil.copytree(native_dump, target)
    (target / "Configuration.xml").write_bytes(configuration)
    for path, data in added.items():
        out = target / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    inspect(target, 1, catalog_field_matrix=catalog_field_matrix, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case)
    written = _hashes(target)
    if original != _hashes(native_dump) or any(written.get(path) != digest for path, digest in original.items() if path != "Configuration.xml"):
        raise DraftError("Native source changed during injection")
    return {"schema": 1, "nonce": nonce, "metadata_version": 1,
            "setup_user": SETUP_USER, "crud_user": CRUD_USER,
            "original_files": original, "injected_files": written,
            "native_runtime_tested": False}


def promote_v2(v1: Path, v2: Path, *, catalog_field_matrix=False, description_case=None, numeric_case=None, zero_case=None) -> None:
    _matrix(catalog_field_matrix)
    _description_mode(description_case, catalog_field_matrix)
    _numeric_mode(numeric_case, description_case=description_case, catalog_field_matrix=catalog_field_matrix)
    _zero_mode(zero_case, numeric_case=numeric_case, description_case=description_case, catalog_field_matrix=catalog_field_matrix)
    v1, v2 = _separate(v1, v2)
    inspect(v1, 1, catalog_field_matrix=catalog_field_matrix, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case)
    before = _hashes(v1)
    path = "Catalogs/NativeOracleItems.xml"
    raw = (v1 / path).read_bytes()
    token = b"<v8:Length>32</v8:Length>"
    if raw.count(token) != 1:
        raise DraftError("Ambiguous v1 payload qualifier")
    shutil.copytree(v1, v2)
    (v2 / path).write_bytes(raw.replace(token, b"<v8:Length>64</v8:Length>", 1))
    inspect(v2, 2, catalog_field_matrix=catalog_field_matrix, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case)
    after = _hashes(v2)
    if before != _hashes(v1) or {key for key in before if before[key] != after[key]} != {path}:
        raise DraftError("Unexpected v2 source change")


def verify_redump(expected: Path, actual: Path, version: int, *, catalog_field_matrix=False, description_case=None, numeric_case=None, zero_case=None) -> None:
    inspect(expected, version, catalog_field_matrix=catalog_field_matrix, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case)
    inspect(actual, version, catalog_field_matrix=catalog_field_matrix, description_case=description_case, numeric_case=numeric_case, zero_case=zero_case)
    left, right = _inventory(expected), _inventory(actual)
    if left != right:
        raise DraftError("Reimport changed metadata file inventory")
    for path, kind in left.items():
        if kind == "directory" or path == "ConfigDumpInfo.xml":
            continue
        a, b = expected / path, actual / path
        if path.endswith(".xml"):
            if _canonical(read_xml(a)[1]) != _canonical(read_xml(b)[1]):
                raise DraftError("Reimport changed reviewed metadata")
        elif a.read_text(encoding="utf-8-sig") != b.read_text(encoding="utf-8-sig"):
            raise DraftError("Reimport changed trusted module")
