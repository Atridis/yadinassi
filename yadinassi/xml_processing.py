"""Native-backed XML character cleanup through its explicit read-only manager.

This filters literal characters only: it does not parse markup, expand entities,
escape text, normalize line endings, or read referenced documents.
"""

from dataclasses import dataclass

from .values import BSLObject, HostFunction


# A local work budget, not an inferred limit of native XML strings. Count UTF-16
# units, matching the public BSL string model, before allocating the result.
_MAX_TEXT_UNITS = 1024 * 1024


def delete_disallowed_xml_characters(text: object, version: object = "1.0") -> str:
    # Exact types prevent implicit String() conversions and arbitrary host hooks.
    if type(text) is not str:
        raise TypeError("УдалитьНедопустимыеСимволыXML: первый аргумент должен иметь тип Строка")
    if type(version) is not str:
        raise TypeError("УдалитьНедопустимыеСимволыXML: версия должна иметь тип Строка")
    if version not in ("1.0", "1.1"):
        raise ValueError("УдалитьНедопустимыеСимволыXML: ожидается версия 1.0 или 1.1")
    if len(text) > _MAX_TEXT_UNITS:
        raise ValueError("УдалитьНедопустимыеСимволыXML: превышен предел ресурсов Yadinassi")
    units = len(text)
    for char in text:
        units += ord(char) > 0xFFFF
        if units > _MAX_TEXT_UNITS:
            raise ValueError("УдалитьНедопустимыеСимволыXML: превышен предел ресурсов Yadinassi")

    result = []
    position = 0
    while position < len(text):
        char = text[position]
        code = ord(char)
        position += 1
        if 0xD800 <= code <= 0xDBFF:
            # Pair only neighbors in the original input. Filtering a separator
            # must never turn two formerly lone surrogates into a valid pair.
            if position < len(text) and 0xDC00 <= ord(text[position]) <= 0xDFFF:
                low = ord(text[position])
                position += 1
                result.append(chr(0x10000 + ((code - 0xD800) << 10) + low - 0xDC00))
            continue
        if 0xDC00 <= code <= 0xDFFF or code in (0xFFFE, 0xFFFF):
            continue
        if code < 0x20 and code not in (9, 10, 13):
            continue
        # XML 1.1's restricted characters cannot appear as literal characters.
        # Native controls.1.1 retains NEL (#x85) but strips these C1 ranges.
        if version == "1.1" and (0x7F <= code <= 0x84 or 0x86 <= code <= 0x9F):
            continue
        result.append(char)
    return "".join(result)


@dataclass(frozen=True, eq=False)
class BSLXMLStringProcessingManager(BSLObject):
    """Expose only the observed bilingual cleanup method, without reflection."""

    def __str__(self) -> str:
        return "МенеджерОбработкиСтрокиXML"

    def get_member(self, name: str) -> object:
        if name.casefold() in ("удалитьнедопустимыесимволыxml", "deletedisallowedxmlcharacters"):
            return HostFunction(name, delete_disallowed_xml_characters)
        return super().get_member(name)


XML_STRING_PROCESSING = BSLXMLStringProcessingManager()

__all__ = ["BSLXMLStringProcessingManager", "XML_STRING_PROCESSING",
           "delete_disallowed_xml_characters"]
