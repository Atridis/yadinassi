"""Pure, fail-closed evidence gates. Does not execute processes or assert freshness.

Caller must create a never-used run directory and require each output absent before
the corresponding bounded process. A nonce alone does not make a reused file fresh.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from inject_modules import DraftError, MODULES, PROTOCOL


def bounded_bytes(path: Path, limit: int = 65536) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise DraftError(f"Missing, empty, non-regular or excessive evidence: {path}")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise DraftError(f"Oversized evidence: {path}")
    return data


def require_zero_result(path: Path, returncode: int, *, timed_out: bool = False) -> None:
    if timed_out or returncode != 0:
        raise DraftError("Native batch process failed or timed out")
    data = bounded_bytes(path, 128)
    try:
        value = data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig").strip()
    except UnicodeError as error:
        raise DraftError("Unreadable DumpResult") from error
    if not re.fullmatch(r"[+-]?[0-9]+", value) or int(value) != 0:
        raise DraftError(f"DumpResult is not numeric zero: {value!r}")


def require_epf(path: Path) -> None:
    if path.suffix.lower() != ".epf" or path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise DraftError("Expected nonempty EPF is absent")


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise DraftError(f"Duplicate JSON key: {name}")
        result[name] = value
    return result


def read_marker(path: Path) -> dict:
    try:
        value = json.loads(bounded_bytes(path).decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DraftError(f"Malformed marker: {path}") from error
    if not isinstance(value, dict):
        raise DraftError("Marker must be a JSON object")
    return value


def require_marker_pair(root: Path, stage: str, run_id: str, user: str,
                        *, returncode: int, timed_out: bool = False,
                        expected_version: str = "8.3.27.1508") -> dict:
    if stage not in ("bootstrap", "verify"):
        raise DraftError("Unsupported marker stage")
    if timed_out or returncode != 0:
        raise DraftError("Enterprise process failed or timed out, regardless of markers")
    session = read_marker(root / (stage + "-session.json"))
    managed = read_marker(root / (stage + "-managed.json"))
    for marker, hook in ((session, "session"), (managed, "managed")):
        expected = {"protocol": PROTOCOL, "run_id": run_id, "stage": stage,
                    "hook": hook, "user": user, "status": "ok", "error": ""}
        if any(marker.get(key) != value for key, value in expected.items()):
            raise DraftError(f"Wrong identity/stage or unsuccessful {hook} marker")
    common_keys = {"protocol", "run_id", "stage", "hook", "user", "status", "error"}
    session_keys = common_keys | {"persisted_user", "protection_type", "persisted_protection", "standard_authentication", "users_before", "users_after", "current_user_at_start", "current_protection_verified"}
    if stage == "verify":
        session_keys.add("current_protection")
    if set(session) != session_keys or set(managed) != common_keys | {"actual_version", "server_hook_verified"}:
        raise DraftError("Unexpected marker fields")
    if (session.get("persisted_user") != user
            or session.get("protection_type") != "Boolean"
            or session.get("persisted_protection") is not False
            or session.get("standard_authentication") is not True):
        raise DraftError("Persisted user Boolean false / standard authentication not proven")
    for key, count in (("users_before", 0 if stage == "bootstrap" else 1), ("users_after", 1)):
        if type(session.get(key)) is not int or session[key] != count:
            raise DraftError("Unexpected user count")
    if stage == "bootstrap" and session.get("current_user_at_start") != "":
        raise DraftError("Bootstrap startup must be anonymous")
    if not isinstance(session.get("current_user_at_start"), str):
        raise DraftError("CurrentUser startup identity is not reported")
    if stage == "verify":
        if (session.get("current_user_at_start") != user
                or session.get("current_protection_verified") is not True
                or session.get("current_protection") is not False):
            raise DraftError("Fresh named CurrentUser Boolean false not proven")
    elif session.get("current_protection_verified") is not False:
        raise DraftError("Anonymous bootstrap cannot prove changed CurrentUser state")
    version = managed.get("actual_version")
    if (managed.get("server_hook_verified") is not True or not isinstance(version, str)
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", version)
            or version != expected_version):
        raise DraftError("Actual SystemInfo.AppVersion is missing or unexpected")
    return {"stage": stage, "actual_version": version, "user": user}


def require_reimported_modules(injected: Path, redumped: Path) -> None:
    for name in MODULES:
        expected = (injected / "Ext" / name).read_text(encoding="utf-8-sig")
        actual_path = redumped / "Ext" / name
        if actual_path.is_symlink() or not actual_path.is_file():
            raise DraftError(f"Reimported module is absent: {name}")
        actual = actual_path.read_text(encoding="utf-8-sig")
        if actual != expected:
            raise DraftError(f"Reimport changed module content: {name}")
