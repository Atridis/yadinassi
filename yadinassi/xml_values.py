"""A bounded XML lexical conversion pair, not an XML document parser."""

from .values import BSLType


def xml_string(value: object) -> str:
    # Exact types: no host hooks, implicit String(), escaping or entity parsing.
    if type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    raise TypeError("XMLСтрока: пока поддерживаются только Строка и Булево")


def xml_value(value_type: object, text: object) -> object:
    if type(value_type) is not BSLType:
        raise TypeError("XMLЗначение: первый аргумент должен иметь тип Тип")
    if type(text) is not str:
        raise TypeError("XMLЗначение: второй аргумент должен иметь тип Строка")
    if value_type is BSLType.STRING:
        return text
    if value_type is BSLType.BOOLEAN:
        # XSD Boolean lexical space; collapse only XML whitespace. Internal
        # whitespace cannot occur in any of the four valid tokens.
        token = text.strip(" \t\r\n")
        if token in ("true", "1"):
            return True
        if token in ("false", "0"):
            return False
        raise ValueError("XMLЗначение: неверное XML-представление Булево")
    raise TypeError("XMLЗначение: пока поддерживаются только Строка и Булево")


BUILTINS = (("XMLСтрока", xml_string, "XMLString"),
            ("XMLЗначение", xml_value, "XMLValue"))
