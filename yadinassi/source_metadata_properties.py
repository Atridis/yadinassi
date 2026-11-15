"""Read-only enumerated metadata properties backed by admitted XML values."""
from enum import Enum
from .values import BSLObject


class SourceScriptVariant(Enum):
    ENGLISH = 'English'
    RUSSIAN = 'Russian'


class SourcePropertyDomain(BSLObject):
    def __init__(self, values):
        self._values = dict(values)

    def get_member(self, name):
        if type(name) is not str or name.casefold() not in self._values:
            raise ValueError('unknown metadata property enumeration value: ' + str(name))
        return self._values[name.casefold()]

    def get_index(self, name):
        return self.get_member(name)


_SCRIPT_VARIANT = SourcePropertyDomain({
    'english': SourceScriptVariant.ENGLISH, 'английский': SourceScriptVariant.ENGLISH,
    'russian': SourceScriptVariant.RUSSIAN, 'русский': SourceScriptVariant.RUSSIAN,
})


class _CanonicalSourceEnum(Enum):
    def __str__(self):
        # Source-host representation preserves the XML token; native localized
        # presentations are not claimed by this experimental facade.
        return self.value


_COMPATIBILITY_NAMES = ('DontUse', 'Version8_1', 'Version8_2_13', 'Version8_2_16') + tuple(
    'Version8_3_' + str(n) for n in range(1, 25))
SourceCompatibilityMode = _CanonicalSourceEnum('SourceCompatibilityMode',
    {name: name for name in _COMPATIBILITY_NAMES})
_COMPATIBILITY = SourcePropertyDomain({alias: value
    for value in SourceCompatibilityMode
    for alias in (value.value.casefold(), ('неиспользовать' if value.value == 'DontUse'
                                         else value.value.replace('Version', 'Версия').casefold()))})


def compatibility_mode(xml_value):
    try:
        return SourceCompatibilityMode(xml_value)
    except ValueError:
        raise ValueError('unknown source CompatibilityMode value: ' + xml_value) from None


class SourceObjectProperties(BSLObject):
    def get_member(self, name):
        if name.casefold() in ('compatibilitymode', 'режимсовместимости'):
            return _COMPATIBILITY
        if name.casefold() in ('scriptvariant', 'вариантвстроенногоязыка'):
            return _SCRIPT_VARIANT
        raise ValueError('source metadata property enumeration is not supported: ' + name)


def script_variant(xml_value):
    try:
        return SourceScriptVariant(xml_value)
    except ValueError:
        raise ValueError('unknown source ScriptVariant value: ' + xml_value) from None
