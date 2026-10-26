"""Type/TypeOf for the explicit standalone BSL value model, not Python reflection."""

from decimal import Decimal

from .text_documents import BSLTextDocument
from .unique_identifiers import BSLUUID
from .dates import BSLDate
from .error_info import BSLErrorInfo, BSLErrorCategory
from .xml_processing import BSLXMLStringProcessingManager

from .maps import BSLFixedMap, BSLMap
from .round_modes import BSLRoundMode, BSLRoundModes
from .search_directions import BSLSearchDirection, BSLSearchDirections
from .sort_directions import BSLSortDirection
from .structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (
    BSLAllowedLength, BSLAllowedLengths, BSLAllowedSign, BSLAllowedSigns,
    BSLBinaryDataQualifiers, BSLDateFractions, BSLDateFractionsNamespace,
    BSLDateQualifiers, BSLNumberQualifiers, BSLStringQualifiers,
)
from .values import BSLArray, BSLFixedArray, BSLNull, BSLType
from .value_trees import (BSLValueTree, BSLValueTreeColumnCollection, BSLValueTreeColumn,
                          BSLValueTreeRow, BSLValueTreeRowCollection)
from .value_tables import (BSLValueTable, BSLValueTableColumnCollection,
                           BSLValueTableColumn, BSLValueTableRow,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .value_lists import BSLValueList, BSLValueListItem


from .async_runtime import Promise


_VALUE_TYPES = (
    (BSLTextDocument, BSLType.TEXT_DOCUMENT, "TextDocument"),
    (BSLUUID, BSLType.UUID, "UUID"),
    (Promise, BSLType.PROMISE, "Promise"),
    (BSLErrorInfo, BSLType.ERROR_INFO, "ErrorInfo"),
    (BSLErrorCategory, BSLType.ERROR_CATEGORY, "ErrorCategory"),
    (BSLXMLStringProcessingManager, BSLType.XML_STRING_PROCESSING_MANAGER, "XMLStringProcessingManager"),
    (BSLNull, BSLType.NULL, "Null"),
    (type(None), BSLType.UNDEFINED, "Undefined"),
    (bool, BSLType.BOOLEAN, "Boolean"),
    (Decimal, BSLType.NUMBER, "Number"),
    (str, BSLType.STRING, "String"),
    (BSLDate, BSLType.DATE, "Date"),
    (BSLArray, BSLType.ARRAY, "Array"),
    (BSLStructure, BSLType.STRUCTURE, "Structure"),
    (BSLMap, BSLType.MAP, "Map"),
    (BSLFixedArray, BSLType.FIXED_ARRAY, "FixedArray"),
    (BSLFixedStructure, BSLType.FIXED_STRUCTURE, "FixedStructure"),
    (BSLFixedMap, BSLType.FIXED_MAP, "FixedMap"),
    (BSLKeyAndValue, BSLType.KEY_AND_VALUE, "KeyAndValue"),
    (BSLType, BSLType.TYPE, "Type"),
    (BSLRoundMode, BSLType.ROUND_MODE, "RoundMode"),
    # EnumRoundMode is the official EDT type-name metadata, rather than a
    # separately observed native Type("EnumRoundMode") call.
    (BSLRoundModes, BSLType.ROUND_MODES, "EnumRoundMode"),
    (BSLSearchDirection, BSLType.SEARCH_DIRECTION, "SearchDirection"),
    # Native search.enum.namespace-type-{ru,en} both fail. TypeOf still has
    # this identity, but neither presentation nor English name resolves it.
    (BSLSearchDirections, BSLType.SEARCH_DIRECTIONS, None),
    # SortDirection's namespace presentation/iteration are observed, but its
    # TypeOf identity and codec are not. Do not infer either from SearchDirection.
    (BSLSortDirection, BSLType.SORT_DIRECTION, "SortDirection"),
    (BSLNumberQualifiers, BSLType.NUMBER_QUALIFIERS, "NumberQualifiers"),
    (BSLStringQualifiers, BSLType.STRING_QUALIFIERS, "StringQualifiers"),
    (BSLDateQualifiers, BSLType.DATE_QUALIFIERS, "DateQualifiers"),
    (BSLBinaryDataQualifiers, BSLType.BINARY_DATA_QUALIFIERS, "BinaryDataQualifiers"),
    (BSLAllowedSign, BSLType.ALLOWED_SIGN, "AllowedSign"),
    (BSLAllowedLength, BSLType.ALLOWED_LENGTH, "AllowedLength"),
    (BSLDateFractions, BSLType.DATE_FRACTIONS, "DateFractions"),
    # Owner evidence establishes the namespace TypeOf identities, but not
    # namespace type-name lookup. Do not infer aliases from presentations.
    (BSLAllowedSigns, BSLType.ALLOWED_SIGNS, None),
    (BSLAllowedLengths, BSLType.ALLOWED_LENGTHS, None),
    (BSLDateFractionsNamespace, BSLType.DATE_FRACTIONS_NAMESPACE, None),
    (BSLTypeDescription, BSLType.TYPE_DESCRIPTION, "TypeDescription"),
    (BSLValueTree, BSLType.VALUE_TREE, "ValueTree"),
    (BSLValueTreeColumnCollection, BSLType.VALUE_TREE_COLUMN_COLLECTION, "ValueTreeColumnCollection"),
    (BSLValueTreeColumn, BSLType.VALUE_TREE_COLUMN, "ValueTreeColumn"),
    (BSLValueTreeRow, BSLType.VALUE_TREE_ROW, "ValueTreeRow"),
    (BSLValueTreeRowCollection, BSLType.VALUE_TREE_ROW_COLLECTION, "ValueTreeRowCollection"),
    (BSLValueTable, BSLType.VALUE_TABLE, "ValueTable"),
    (BSLValueTableColumnCollection, BSLType.VALUE_TABLE_COLUMN_COLLECTION, "ValueTableColumnCollection"),
    (BSLValueTableColumn, BSLType.VALUE_TABLE_COLUMN, "ValueTableColumn"),
    (BSLValueTableRow, BSLType.VALUE_TABLE_ROW, "ValueTableRow"),
    (BSLCollectionIndexes, BSLType.COLLECTION_INDEXES, "CollectionIndexes"),
    (BSLCollectionIndex, BSLType.COLLECTION_INDEX, "CollectionIndex"),
    # Lookup names are unspaced; __str__ presentations are not extra aliases.
    (BSLValueList, BSLType.VALUE_LIST, "ValueList"),
    (BSLValueListItem, BSLType.VALUE_LIST_ITEM, "ValueListItem"),
)
_BY_NAME = {name.casefold(): value_type
            for _, value_type, alias in _VALUE_TYPES
            if alias is not None
            for name in (value_type.value, alias)}


def type_by_name(name: object) -> BSLType:
    if type(name) is not str:
        raise TypeError("Имя типа должно быть строкой")
    value_type = _BY_NAME.get(name.casefold())
    if value_type is None:
        raise ValueError(f"Тип не поддерживается: {name}")
    return value_type


def type_of(value: object) -> BSLType:
    # Exact identity keeps bool distinct from numbers and rejects arbitrary host
    # objects/subclasses without invoking their metaclass equality or hash hooks.
    for python_type, value_type, _ in _VALUE_TYPES:
        if type(value) is python_type:
            return value_type
    raise TypeError("ТипЗнч для этого значения пока не поддерживается")
