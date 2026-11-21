"""Read-only structured exception information for the standalone BSL runtime.

The diagnostic source labels remain Yadinassi labels, not platform module names.
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .values import BSLObject, HostFunction


class BSLErrorCategory(Enum):
    ALL_ERRORS = "ВсеОшибки"
    OTHER_ERROR = "ПрочаяОшибка"
    SCRIPT_COMPILE_ERROR = "ОшибкаКомпиляцииВстроенногоЯзыка"
    SCRIPT_RUNTIME_ERROR = "ОшибкаВоВремяВыполненияВстроенногоЯзыка"
    EXCEPTION_RAISED_FROM_SCRIPT = "ИсключениеВызванноеИзВстроенногоЯзыка"
    CONFIGURATION_ERROR = "ОшибкаКонфигурации"

    def __str__(self) -> str:
        raise TypeError("Строковое представление КатегорияОшибки пока не поддерживается")


_CATEGORY_ALIASES = dict(zip(
    ("AllErrors", "OtherError", "ScriptCompileError", "ScriptRuntimeError",
     "ExceptionRaisedFromScript", "ConfigurationError"), BSLErrorCategory))
_MEMBERS = {name.casefold(): category
            for alias, category in _CATEGORY_ALIASES.items()
            for name in (alias, category.value)}
FORBIDDEN_RAISE_CATEGORIES = frozenset(BSLErrorCategory) - {BSLErrorCategory.CONFIGURATION_ERROR}


@dataclass(frozen=True, eq=False)
class BSLErrorCategories(BSLObject):
    def __str__(self) -> str:
        raise TypeError("Строковое представление перечисления КатегорияОшибки пока не поддерживается")

    def get_member(self, name: str) -> object:
        value = _MEMBERS.get(name.casefold())
        return super().get_member(name) if value is None else value


ERROR_CATEGORIES = BSLErrorCategories()


@dataclass(frozen=True, eq=False)
class BSLErrorInfo(BSLObject):
    description: str
    code: str = ""
    additional_information: str = ""
    cause: "BSLErrorInfo | None" = None
    categories: frozenset[BSLErrorCategory] = frozenset({
        BSLErrorCategory.ALL_ERRORS, BSLErrorCategory.SCRIPT_RUNTIME_ERROR})
    module_name: str = ""
    line_number: int = 0
    initial_string: str = ""
    _empty: bool = False

    def get_member(self, name: str) -> object:
        key = name.casefold()
        if key in {"описание", "description"}:
            return self.description
        if key in {"код", "code"}:
            return self.code
        if key in {"дополнительнаяинформация", "additionalinformation"}:
            return self.additional_information
        if key in {"причина", "cause"}:
            return self.cause
        if key in {"имямодуля", "modulename"}:
            return self.module_name
        if key in {"номерстроки", "linenumber"}:
            return Decimal(self.line_number)
        if key in {"исходнаястрока", "initialstring"}:
            return self.initial_string
        if key in {"являетсяошибкойкатегории", "iserrorofcategory"}:
            return HostFunction(name, self.is_error_of_category)
        return super().get_member(name)

    def __str__(self) -> str:
        raise TypeError("Строковое представление ИнформацияОбОшибке пока не поддерживается; "
                        "используйте Описание")

    def is_error_of_category(self, category: object) -> bool:
        if type(category) is not BSLErrorCategory:
            raise TypeError("Ожидается значение КатегорияОшибки")
        current = self
        while current is not None:
            if category in current.categories:
                return True
            current = current.cause
        return False


def empty_error_info() -> BSLErrorInfo:
    """Native empty diagnostic value, distinct from Undefined and Raise(\"\")."""
    return BSLErrorInfo("", categories=frozenset({BSLErrorCategory.ALL_ERRORS,
                                                BSLErrorCategory.OTHER_ERROR}), _empty=True)

# Definition-time identity and raw storage for direct scalar snapshots. Public
# aliases and constructor methods may be rebound by trusted host integrations.
_DIRECT_SNAPSHOT_ABI = (BSLErrorInfo, vars(BSLObject)['__dict__'],
    frozenset({BSLErrorCategory.ALL_ERRORS, BSLErrorCategory.SCRIPT_RUNTIME_ERROR}),
    frozenset({BSLErrorCategory.ALL_ERRORS, BSLErrorCategory.OTHER_ERROR}))

# Pin category singletons for direct validation without enum/hash/equality hooks.
_DIRECT_CATEGORY_ABI = tuple(BSLErrorCategory)
# All finite combinations are assembled before host callbacks can replace enum
# hashing. Direct code selects a prebuilt set by an identity-only bit mask.
_DIRECT_CATEGORY_SETS = tuple(frozenset(member for index,member in enumerate(_DIRECT_CATEGORY_ABI)
    if mask & (1 << index)) for mask in range(1 << len(_DIRECT_CATEGORY_ABI)))
