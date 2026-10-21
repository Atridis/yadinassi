#!/usr/bin/env python3
"""Disposable smoke helper: copy a fresh native XML dump and add trusted internal BSL.

Preserves native Configuration.xml except one role reference; never executes 1C.
Fixture tests and source-code specimens are not native proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
from xml.parsers import expat
from xml.sax.saxutils import escape


PROTOCOL = "native-bootstrap-v1"
MODULES = ("SessionModule.bsl", "ManagedApplicationModule.bsl")
ROLE_NAME = "NativeSmokeBootstrapAdministrator"
METADATA_NAMESPACE = "http://v8.1c.ru/8.3/MDClasses"
RIGHTS_NAMESPACE = "http://v8.1c.ru/8.2/roles"
ROLE_FILES = ("Roles/" + ROLE_NAME + ".xml", "Roles/" + ROLE_NAME + "/Ext/Rights.xml")
# Explicit allowlist, not FullAccess. Administration depends on DataAdministration.
ROLE_RIGHTS = frozenset({"Administration", "DataAdministration", "ThickClient",
                         "MainWindowModeNormal", "InteractiveOpenExtDataProcessors"})


class DraftError(ValueError):
    pass


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if local_name(child.tag) == name]


def single(element: ET.Element, name: str) -> ET.Element:
    matches = children(element, name)
    if len(matches) != 1:
        raise DraftError(f"Expected one {name}; got {len(matches)}")
    return matches[0]


def read_xml(path: Path) -> tuple[bytes, ET.Element]:
    """Read only bounded regular XML; external declarations are never accepted."""
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1_048_576:
        raise DraftError("Missing, non-regular or excessive native XML")
    with path.open("rb") as stream:
        raw = stream.read(1_048_577)
    if len(raw) > 1_048_576:
        raise DraftError("Native XML is too large")
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", raw, re.I):
        raise DraftError("DTD/entity declarations are not expected in a native dump")
    try:
        raw.decode("utf-8-sig")
        xml = ET.fromstring(raw)
    except (UnicodeError, ET.ParseError) as error:
        raise DraftError("Invalid native UTF-8 XML") from error
    if len(list(xml.iter())) > 4096:
        raise DraftError("Too many native XML elements")
    return raw, xml


def add_role_reference(raw: bytes) -> bytes:
    """Insert one child reference without serializing any original XML node."""
    parser = expat.ParserCreate()
    stack = []
    spans = []

    def start(name, attributes):
        stack.append(name.split(":")[-1])
        if stack == ["MetaDataObject", "Configuration", "ChildObjects"]:
            if attributes:
                raise DraftError("ChildObjects attributes are unsupported")
            index = parser.CurrentByteIndex
            end = raw.find(b">", index)
            if end < 0:
                raise DraftError("Missing ChildObjects start tag")
            spans.append((index, end + 1, name))

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    try:
        parser.Parse(raw, True)
    except expat.ExpatError as error:
        raise DraftError("Cannot locate exact native ChildObjects") from error
    if len(spans) != 1:
        raise DraftError("Expected one unambiguous native ChildObjects")
    start, end, name = spans[0]
    prefix = name.rsplit(":", 1)[0] + ":" if ":" in name else ""
    role = ("<" + prefix + "Role>" + ROLE_NAME + "</" + prefix + "Role>").encode("utf-8")
    if raw[start:end].rstrip().endswith(b"/>"):
        # An empty element needs an explicit closing tag; no other bytes change.
        return raw[:end - 2] + b">" + role + ("</" + name + ">").encode("utf-8") + raw[end:]
    return raw[:end] + role + raw[end:]


def inspect_native_dump(root: Path) -> dict:
    """Conservative inspection only; never normalize native XML or guess UUIDs."""
    if not root.is_dir() or root.is_symlink():
        raise DraftError("Native source must be a real directory")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise DraftError(f"Refusing symlink/special entry: {path}")
    configuration = root / "Configuration.xml"
    raw, xml = read_xml(configuration)
    if local_name(xml.tag) != "MetaDataObject" or not xml.tag.startswith("{"):
        raise DraftError("Unrecognized namespaced metadata root; inspect actual dump")
    namespace = xml.tag[1:].split("}", 1)[0]
    if not namespace.startswith("http://v8.1c.ru/"):
        raise DraftError("Unexpected metadata namespace; inspect actual dump")
    if not xml.attrib.get("version"):
        raise DraftError("Missing native format version; inspect actual dump")
    if len(list(xml.iter())) > 4096:
        raise DraftError("Too many native XML elements")
    config = single(xml, "Configuration")
    if not config.attrib.get("uuid"):
        raise DraftError("Native configuration UUID is absent")
    properties = single(config, "Properties")
    mode = (single(properties, "DefaultRunMode").text or "").strip()
    if mode != "ManagedApplication":
        raise DraftError(f"Managed default mode required; got {mode!r}. Do not rewrite XML.")
    roles = children(properties, "DefaultRoles")
    if len(roles) > 1 or any(node.attrib or list(node) or (node.text or "").strip() for node in roles):
        raise DraftError("Default roles are not empty; do not broaden or alter permissions")
    child_objects = single(config, "ChildObjects")
    if child_objects.tag != "{" + namespace + "}ChildObjects" or child_objects.attrib:
        raise DraftError("Unexpected ChildObjects namespace or attributes")
    unexpected = [local_name(child.tag) for child in child_objects
                  if child.tag != "{" + namespace + "}Language" or child.attrib or list(child)]
    if unexpected:
        raise DraftError(f"Expected empty disposable configuration, found: {unexpected}")
    if (root / "Roles").exists():
        raise DraftError("Unexpected role metadata exists")
    if any(path.is_file() and path.suffix.lower() == ".bsl" for path in root.rglob("*")):
        raise DraftError("Fresh native dump must contain no pre-existing BSL modules")
    return {
        "namespace": namespace,
        "format_version": xml.attrib["version"],
        "configuration_uuid": config.attrib["uuid"],
        "configuration_name": (single(properties, "Name").text or ""),
        "default_run_mode": mode,
        "languages": [(child.text or "").strip() for child in child_objects],
        "configuration_sha256": hashlib.sha256(raw).hexdigest(),
    }


def role_documents(metadata: dict) -> dict[str, bytes]:
    """Narrow structural derivative of the cited 2.20 primary-source specimen.

    Never copy its FullAccess grants. Unknown schema versions fail closed.
    """
    if metadata["namespace"] != METADATA_NAMESPACE or metadata["format_version"] != "2.20":
        raise DraftError("No reviewed role serialization for the native metadata format")
    name = metadata["configuration_name"]
    if not re.fullmatch(r"[^\W\d]\w*", name):
        raise DraftError("Native configuration name is not a metadata identifier")
    role_uuid = str(uuid.uuid4())
    if role_uuid == metadata["configuration_uuid"]:
        raise DraftError("New role UUID unexpectedly collides with the configuration")
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    role = (header + '<MetaDataObject xmlns="' + METADATA_NAMESPACE + '" version="2.20">\n'
            + '  <Role uuid="' + role_uuid + '">\n    <Properties>\n'
            + '      <Name>' + ROLE_NAME + '</Name>\n      <Synonym/>\n      <Comment/>\n'
            + '    </Properties>\n  </Role>\n</MetaDataObject>\n')
    rights = (header + '<Rights xmlns="' + RIGHTS_NAMESPACE + '"'
              + ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
              + ' version="2.20" xsi:type="Rights">\n'
              + '  <setForNewObjects>false</setForNewObjects>\n'
              + '  <setForAttributesByDefault>false</setForAttributesByDefault>\n'
              + '  <independentRightsOfChildObjects>false</independentRightsOfChildObjects>\n'
              + '  <object>\n    <name>Configuration.' + escape(name) + '</name>\n'
              + ''.join('    <right><name>' + right + '</name><value>true</value></right>\n'
                        for right in sorted(ROLE_RIGHTS))
              + '  </object>\n</Rights>\n')
    return dict(zip(ROLE_FILES, (role.encode("utf-8-sig"), rights.encode("utf-8-sig"))))


def xml_signature(node: ET.Element) -> tuple:
    """Namespace-aware structural equality; ignore only formatting whitespace."""
    if node.tail and node.tail.strip():
        raise DraftError("Mixed-content native metadata is not expected")
    value = node.text or ""
    nested = tuple(xml_signature(child) for child in node)
    if nested:
        if value.strip():
            raise DraftError("Mixed-content native metadata is not expected")
        value = ""
    if node.tag == "{" + METADATA_NAMESPACE + "}ChildObjects":
        nested = tuple(sorted(nested))
    return node.tag, tuple(sorted(node.attrib.items())), value, nested


def inspect_disposable_role(root: Path) -> None:
    """Reject every grant, role, default and object outside the exact allowlist."""
    _, configuration = read_xml(root / "Configuration.xml")
    ns = "{" + METADATA_NAMESPACE + "}"
    if configuration.tag != ns + "MetaDataObject" or configuration.attrib != {"version": "2.20"}:
        raise DraftError("Unexpected role-bearing configuration format")
    config = single(configuration, "Configuration")
    properties = single(config, "Properties")
    defaults = children(properties, "DefaultRoles")
    if len(defaults) > 1 or any(node.attrib or list(node) or (node.text or "").strip() for node in defaults):
        raise DraftError("Default roles must remain empty")
    references = single(config, "ChildObjects")
    roles = [child for child in references if child.tag == ns + "Role"]
    if (len(roles) != 1 or roles[0].text != ROLE_NAME or roles[0].attrib or list(roles[0])
            or any(child.tag not in {ns + "Language", ns + "Role"} for child in references)):
        raise DraftError("Expected exactly one disposable role reference and native languages")
    role_root = root / "Roles"
    expected_paths = {ROLE_NAME + ".xml", ROLE_NAME, ROLE_NAME + "/Ext", ROLE_NAME + "/Ext/Rights.xml"}
    if role_root.is_symlink() or not role_root.is_dir():
        raise DraftError("Disposable role directory is absent")
    paths = set()
    for path in role_root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise DraftError("Unexpected role filesystem entry")
        paths.add(path.relative_to(role_root).as_posix())
    if paths != expected_paths:
        raise DraftError("Unexpected additional role files or directories")
    _, document = read_xml(root / ROLE_FILES[0])
    if (document.tag != ns + "MetaDataObject" or document.attrib != {"version": "2.20"}
            or [child.tag for child in document] != [ns + "Role"]):
        raise DraftError("Unexpected role metadata root")
    role = document[0]
    try:
        identity = role.attrib["uuid"]
        valid_identity = str(uuid.UUID(identity)) == identity
    except (KeyError, ValueError):
        valid_identity = False
    if (not valid_identity or set(role.attrib) != {"uuid"}
            or identity == config.attrib.get("uuid")
            or [child.tag for child in role] != [ns + "Properties"]):
        raise DraftError("Invalid new role identity or structure")
    props = role[0]
    if props.attrib or [child.tag for child in props] != [ns + key for key in ("Name", "Synonym", "Comment")]:
        raise DraftError("Unexpected role properties")
    if (props[0].text != ROLE_NAME or any(child.attrib or list(child) for child in props)
            or any((child.text or "") for child in props[1:])):
        raise DraftError("Unexpected role name or properties")
    _, rights = read_xml(root / ROLE_FILES[1])
    ns = "{" + RIGHTS_NAMESPACE + "}"
    if (rights.tag != ns + "Rights" or rights.attrib != {"version": "2.20",
            "{http://www.w3.org/2001/XMLSchema-instance}type": "Rights"}):
        raise DraftError("Unexpected rights metadata root")
    flags = {"setForNewObjects", "setForAttributesByDefault", "independentRightsOfChildObjects"}
    if len(rights) != 4 or {node.tag for node in rights} != {ns + name for name in flags | {"object"}}:
        raise DraftError("Unexpected role defaults or rights objects")
    for flag in flags:
        node = single(rights, flag)
        if node.attrib or list(node) or node.text != "false":
            raise DraftError("Role defaults must be explicitly false")
    obj = single(rights, "object")
    name = single(obj, "name")
    if (obj.attrib or name.attrib or list(name)
            or name.text != "Configuration." + (single(properties, "Name").text or "")):
        raise DraftError("Rights must target only the actual disposable configuration")
    granted = []
    if len(obj) != len(ROLE_RIGHTS) + 1 or any(node.tag not in {ns + "name", ns + "right"} for node in obj):
        raise DraftError("Unexpected rights entries")
    for right in children(obj, "right"):
        if right.attrib or [node.tag for node in right] != [ns + "name", ns + "value"]:
            raise DraftError("Unexpected right structure")
        if any(node.attrib or list(node) for node in right) or right[1].text != "true":
            raise DraftError("Reviewed rights must be explicit true values")
        granted.append(right[0].text)
    if len(granted) != len(ROLE_RIGHTS) or set(granted) != ROLE_RIGHTS:
        raise DraftError("Missing, duplicate or unexpected role rights")
    # Reject non-whitespace mixed content in every role XML element as well.
    xml_signature(document)
    xml_signature(rights)


def bsl_string(value: str) -> str:
    if any(ord(char) < 32 for char in value):
        raise DraftError("Control characters are forbidden in injected literals")
    return '"' + value.replace('"', '""') + '"'


def validate_parameters(run_id: str, user: str, evidence: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise DraftError("Use a fresh 32-lowercase-hex run ID, e.g. uuid.uuid4().hex")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", user):
        raise DraftError("Disposable test username must be a short ASCII identifier")
    path = PurePosixPath(evidence)
    if not path.is_absolute() or ".." in path.parts or str(path) != evidence or evidence == "/":
        raise DraftError("Evidence directory must be a normalized absolute POSIX path")
    bsl_string(evidence)


def render_module(template: Path, run_id: str, user: str, evidence: str) -> bytes:
    text = template.read_text(encoding="utf-8-sig")
    values = {"RUN_ID": run_id, "USER": user, "EVIDENCE": evidence, "ROLE": ROLE_NAME,
              "BOOTSTRAP_TOKEN": "native-bootstrap:" + run_id,
              "VERIFY_TOKEN": "native-verify:" + run_id}
    def substitute(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise DraftError("Unresolved template literal")
        return bsl_string(values[key])
    text = re.sub(r"@@([A-Z_]+)@@", substitute, text)
    return text.encode("utf-8-sig")


def hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def inject(source: Path, destination: Path, *, run_id: str, user: str,
           evidence: str) -> dict:
    validate_parameters(run_id, user, evidence)
    # Reject overlapping paths and all existing targets, even for reruns.
    if source.is_symlink() or destination.is_symlink():
        raise DraftError("Source/destination cannot be symlinks")
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise DraftError("Source and destination must be separate, non-overlapping trees")
    if destination.exists():
        raise DraftError("Destination must not already exist")
    metadata = inspect_native_dump(source)
    original = hashes(source)
    role_files = role_documents(metadata)
    configuration = add_role_reference((source / "Configuration.xml").read_bytes())
    templates = Path(__file__).parent / "modules"
    rendered = {name: render_module(templates / name, run_id, user, evidence)
                for name in MODULES}
    shutil.copytree(source, destination)
    (destination / "Configuration.xml").write_bytes(configuration)
    for name, data in role_files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    ext = destination / "Ext"
    ext.mkdir(exist_ok=True)
    for name, data in rendered.items():
        (ext / name).write_bytes(data)
    inspect_disposable_role(destination)
    copied = hashes(destination)
    if hashes(source) != original or any(copied.get(path) != digest
                                        for path, digest in original.items() if path != "Configuration.xml"):
        raise DraftError("Native source bytes changed during transform; discard output")
    return {"protocol": PROTOCOL, "run_id": run_id, "user": user,
            "native": metadata, "original_files": original,
            "injected_role": {"name": ROLE_NAME, "rights": sorted(ROLE_RIGHTS),
                              "files": {name: copied[name] for name in ROLE_FILES}},
            "injected_configuration_sha256": copied["Configuration.xml"],
            "injected_modules": {"Ext/" + name: copied["Ext/" + name] for name in MODULES},
            "evidence_root": evidence,
            "request_path": evidence + "/control.json",
            "bootstrap_token": "native-bootstrap:" + run_id,
            "verify_token": "native-verify:" + run_id,
            "native_runtime_tested": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--user", default="NativeSmoke")
    parser.add_argument("--evidence-root", required=True)
    args = parser.parse_args()
    try:
        manifest = inject(args.source, args.destination, run_id=args.run_id,
                          user=args.user, evidence=args.evidence_root)
    except (DraftError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    # Save stdout OUTSIDE the dump; never invent a metadata file for 1C to import.
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
