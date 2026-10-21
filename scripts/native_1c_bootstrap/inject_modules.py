#!/usr/bin/env python3
"""Disposable smoke helper: copy a fresh native XML dump and add trusted internal BSL.

Never creates Configuration.xml or executes 1C. Fixture tests are not native proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET


PROTOCOL = "native-bootstrap-v1"
MODULES = ("SessionModule.bsl", "ManagedApplicationModule.bsl")


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


def inspect_native_dump(root: Path) -> dict:
    """Conservative inspection only; never normalize native XML or guess UUIDs."""
    if not root.is_dir() or root.is_symlink():
        raise DraftError("Native source must be a real directory")
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise DraftError(f"Refusing symlink/special entry: {path}")
    configuration = root / "Configuration.xml"
    if not configuration.is_file():
        raise DraftError("Native Configuration.xml is missing")
    if configuration.stat().st_size > 1_048_576:
        raise DraftError("Native Configuration.xml is too large")
    raw = configuration.read_bytes()
    # xml.etree does not fetch external entities. Also reject any DTD explicitly.
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", raw, re.I):
        raise DraftError("DTD/entity declarations are not expected in a native dump")
    try:
        xml = ET.fromstring(raw)
    except ET.ParseError as error:
        raise DraftError(f"Invalid native XML: {error}") from error
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
    if len(roles) > 1 or any(list(node) or (node.text or "").strip() for node in roles):
        raise DraftError("Default roles are not empty; do not broaden or alter permissions")
    child_objects = single(config, "ChildObjects")
    unexpected = [local_name(child.tag) for child in child_objects
                  if local_name(child.tag) != "Language"]
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
        "default_run_mode": mode,
        "languages": [(child.text or "").strip() for child in child_objects],
        "configuration_sha256": hashlib.sha256(raw).hexdigest(),
    }


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
    values = {"RUN_ID": run_id, "USER": user, "EVIDENCE": evidence,
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
    templates = Path(__file__).parent / "modules"
    rendered = {name: render_module(templates / name, run_id, user, evidence)
                for name in MODULES}
    shutil.copytree(source, destination)
    ext = destination / "Ext"
    ext.mkdir(exist_ok=True)
    for name, data in rendered.items():
        (ext / name).write_bytes(data)
    copied = hashes(destination)
    if hashes(source) != original or any(copied.get(path) != digest
                                        for path, digest in original.items()):
        raise DraftError("Native source bytes changed during transform; discard output")
    return {"protocol": PROTOCOL, "run_id": run_id, "user": user,
            "native": metadata, "original_files": original,
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
