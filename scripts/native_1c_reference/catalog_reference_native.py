"""Closed native reference hook and bounded, private observation decoder.

No predicate truth values are prescribed here. This is not a UUID storage codec.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

CASES = MappingProxyType({
    "distinct_a": "00112233-4455-4677-8899-aabbccddeeff",
    "distinct_b": "d3a17c09-e652-4b8f-95c0-2e74b836fa61",
})
WITNESS_LIMIT = 1024
PROBES = (
    "empty_uuid_zero", "empty_empty", "empty_filled", "zero_equals_empty",
    "zero_empty", "zero_filled", "fixed_uuid_roundtrip", "fixed_empty",
    "fixed_filled", "committed_uuid_roundtrip", "committed_empty", "committed_filled",
)
_TEMPLATE_SHA256 = "5700a4f2f44574e47afdcea4d3ecb136436715a1391e945a8de31d5f45cfe69b"
_OPERATIONS = frozenset(("create", "update", "delete", "observe"))


def render_template(raw: str, case: str, error=ValueError) -> str:
    """Transform only the pinned canonical template, before literal substitution."""
    if type(raw) is not str or type(case) is not str or case not in CASES:
        raise error("reference_template_invalid")
    raw = raw.replace("\r\n", "\n")
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != _TEMPLATE_SHA256:
        raise error("reference_template_invalid")
    replacements = (
        ("NativeИзмерить(Контроль.operation, Результат, Корень, Контекст);",
         "NativeИзмерить(Контроль.operation, Результат, Корень, Контекст, ТокенЗапуска);"),
        ("Процедура NativeИзмерить(Операция, Результат, Корень, Контекст)\n"
         '    Контекст.phase = "readback";\n    До = NativeСостояние(Корень);',
         "Процедура NativeИзмерить(Операция, Результат, Корень, Контекст, ТокенЗапуска)\n"
         '    Контекст.phase = "readback";\n    До = NativeСостояние(Корень);\n'
         "    НаблюдениеДо = NativeReferenceProbe(Корень);"),
        ("            Объект = Справочники.NativeOracleItems.СоздатьЭлемент();",
         "            Объект = Справочники.NativeOracleItems.СоздатьЭлемент();\n"
         '            Контекст.phase = "reference_uuid";\n'
         "            NativeReferenceInstall(Объект, Корень, ТокенЗапуска, Операция);"),
        ("    Для Каждого Поле Из После Цикл\n"
         "        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;",
         "    Для Каждого Поле Из После Цикл\n"
         "        Результат[Поле.Ключ] = Поле.Значение;\n    КонецЦикла;\n"
         "    NativeReferenceFinish(Корень, ТокенЗапуска, Операция, НаблюдениеДо);"),
    )
    for old, new in replacements:
        if raw.count(old) != 1:
            raise error("reference_template_invalid")
        raw = raw.replace(old, new)
    hook = (Path(__file__).parent / "modules" / "CatalogReferenceObservation.bsl").read_text(encoding="utf-8-sig")
    hook = hook.replace("@@CASE_UUID@@", CASES[case]).replace("@@CASE@@", case)
    return raw + "\n" + hook


@dataclass(frozen=True)
class ReferenceWitness:
    status: str
    before_present: bool | None = None
    after_present: bool | None = None
    before: str = ""
    after: str = ""
    actual_uuid: str = ""
    phase: str = ""
    code: str = ""


def validate_witness(raw: bytes, *, nonce: str, token: str, case: str,
                     operation: str, error=ValueError) -> ReferenceWitness:
    """Decode a private sidecar; callers bind raw digest to source/image/lifecycle.

    Read via the host's regular_bytes/O_NOFOLLOW guard, then unlink. Never expose
    the raw sidecar or actual_uuid in public artifacts.
    """
    def fail():
        raise error("reference_witness_invalid")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail()
            out[key] = value
        return out

    if (type(raw) is not bytes or not 1 <= len(raw) <= WITNESS_LIMIT
            or type(case) is not str or case not in CASES
            or type(operation) is not str or operation not in _OPERATIONS
            or type(nonce) is not str or not re.fullmatch(r"[0-9a-f]{32}", nonce)
            or type(token) is not str or not re.fullmatch(r"[0-9a-f]{32}", token)):
        fail()
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=lambda _: fail())
    except (ValueError, UnicodeError, RecursionError):
        fail()
    if type(data) is not dict:
        fail()
    common = {"schema", "status", "nonce", "token", "case", "operation"}
    if (type(data.get("schema")) is not int or data["schema"] != 1
            or data.get("nonce") != nonce or data.get("token") != token
            or data.get("case") != case or data.get("operation") != operation):
        fail()
    if data.get("status") == "error":
        if (set(data) != common | {"phase", "code"} or operation != "create"
                or type(data["phase"]) is not str
                or data["phase"] not in {"case_uuid", "get_reference", "set_reference"}
                or data["code"] != "native_api_error"):
            fail()
        return ReferenceWitness("error", phase=data["phase"], code=data["code"])
    if data.get("status") != "ok" or set(data) != common | {
            "before_present", "after_present", "before", "after", "actual_uuid"}:
        fail()
    for stage in ("before", "after"):
        present, codes = data[stage + "_present"], data[stage]
        if type(present) is not bool or type(codes) is not str:
            fail()
        pattern = r"[TFE]{12}" if present else r"[TFE]{9}NNN"
        if not re.fullmatch(pattern, codes):
            fail()
    if type(data["actual_uuid"]) is not str or data["actual_uuid"] != (
            CASES[case] if data["after_present"] else ""):
        fail()
    return ReferenceWitness("ok", data["before_present"], data["after_present"],
                            data["before"], data["after"], data["actual_uuid"])
