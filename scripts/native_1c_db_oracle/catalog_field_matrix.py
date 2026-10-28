"""Closed metadata-only fixture matrix. No general caller-supplied schema API.

The existing CRUD Catalog is untouched. Two empty Catalogs vary one standard
property at a time. Number(2) native validity is deliberately not claimed here.
"""
VARIANTS = (("NativeOracleStringDescription", "String"),
            ("NativeOracleNumberDescription", "Number"))
FILES = frozenset(f"Catalogs/{name}.xml" for name, _ in VARIANTS)
UUID_KEYS = ("CATALOG_UUID",) + tuple(
    f"{category}_{suffix}_UUID"
    for category in ("OBJECT", "REF", "SELECTION", "LIST", "MANAGER")
    for suffix in ("TYPE", "VALUE"))


def catalog(template, name, kind, error):
    """Transform only the two closed profiles; exact original anchors required."""
    if (name, kind) not in VARIANTS:
        raise error("Unknown fixed Catalog variant")
    text = template.decode("utf-8-sig")
    if text.count("<ChildObjects>") != 1 or text.count("</ChildObjects>") != 1:
        raise error("Unexpected original Catalog children")
    start, end = text.index("<ChildObjects>"), text.index("</ChildObjects>")
    text = text[:start] + "<ChildObjects/>" + text[end+len("</ChildObjects>"):]
    if text.count("NativeOracleItems") != 6:
        raise error("Unexpected original Catalog identities")
    text = text.replace("NativeOracleItems", name)
    for old, new in (("<DescriptionLength>0</DescriptionLength>",
                      "<DescriptionLength>16</DescriptionLength>"),
                     ("<CodeType>String</CodeType>", f"<CodeType>{kind}</CodeType>")):
        if text.count(old) != 1:
            raise error("Unexpected original Catalog scalar")
        text = text.replace(old, new)
    return text.encode("utf-8-sig")


def server_module(raw, error):
    """The sole old-fixture runtime relaxation is its fixed metadata count."""
    text = raw.decode("utf-8-sig")
    old = "Метаданные.Справочники.Количество() <> 1"
    if text.count(old) != 1:
        raise error("Unexpected original Catalog count guard")
    return text.replace(old, "Метаданные.Справочники.Количество() <> 3").encode("utf-8-sig")
