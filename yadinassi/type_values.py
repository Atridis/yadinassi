from .http_security import (BSLOpenSSLSecureConnection, BSLFileCertificationAuthorityCertificates,
                            BSLOSCertificationAuthorityCertificates, BSLInternetProxy)
from .query_packages import BSLTempTablesManager
from .queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection
from .http_client import BSLHTTPConnection, BSLHTTPRequest, BSLHTTPResponse, BSLByteOrderMarkUse
from .form_tables import BSLFormDataCollection, BSLFormDataCollectionItem
from .form_model import BSLClientApplicationForm, BSLFormAttribute, BSLFormField, BSLFormButton, BSLFormTable, BSLFormCommand, BSLFormFieldView, BSLFormItems, BSLFormCommands
from .xdto_values import (BSLXDTODataObject, BSLXDTODataValue, BSLXDTOList, BSLXDTOValueType, BSLXDTOObjectType, BSLXDTOProperty, BSLXDTOPropertyCollection, BSLXDTOPackage, BSLXDTOPackageCollection)
from .xdto_io import BSLXDTOFactory, BSLXMLForm, XML_FORMS, create_xdto_factory
from .dom_nodes import (BSLDOMDocument, BSLDOMElement, BSLDOMAttribute, BSLDOMText, BSLDOMCDATASection, BSLDOMComment, BSLDOMProcessingInstruction, BSLDOMDocumentFragment, BSLDOMNodeList, BSLDOMElementList, BSLDOMAttributeMap, BSLDOMNodeType, DOM_NODE_TYPES)
from .dom_io import BSLDOMBuilder, BSLDOMWriter
from .data_hashing import BSLDataHashing, BSLHashFunction
from .data_io import BSLDataReader, BSLDataWriter, BSLReadDataResult
from .regex_functions import BSLRegexResult, BSLRegexGroup
from .zip_archives import (BSLZipFileReader, BSLZipFileWriter, BSLZipFileEntry, BSLZipFileEntries, BSLZIPCompressionMethod, BSLZIPCompressionLevel, BSLZIPStorePathMode, BSLZIPSubDirProcessingMode, BSLZIPRestoreFilePathsMode, BSLZIPEncryptionMethod, BSLFileNamesEncodingInZipFile)
from .binary_streams import (BSLBinaryDataBuffer, BSLMemoryStream, BSLFileStream, BSLStream, BSLByteOrder, BSLFileOpenMode, BSLFileAccess, BSLPositionInStream)
"""Type/TypeOf for the explicit standalone BSL value model, not Python reflection."""

from decimal import Decimal
from .xml_io import (BSLXMLReader, BSLXMLReaderSettings, BSLXMLNodeType, BSLXMLSpace,
                     BSLXMLValidationType, BSLXMLNamespaceContext, XML_NODE_TYPES, XML_SPACES, XML_VALIDATION_TYPES)
from .xml_writer import BSLXMLWriter, BSLXMLWriterSettings


from .catalogs import BSLCatalogs
from .documents import BSLDocuments
from .information_registers import (BSLInformationRegisters, BSLInformationRegisterType,
    BSLInformationRegisterManager, BSLInformationRegisterSelection, BSLInformationRegisterRecordManager, BSLInformationRegisterRecordSet, BSLInformationRegisterRecord)
from .document_types import BSLDocumentReference, BSLDocumentType
from .document_lines import BSLDocumentLinesType, BSLDocumentLines, BSLDocumentLine, BSLDocumentSectionType
from .catalog_types import BSLCatalogReference, BSLCatalogType

from .file_io import BSLFile, BSLTextReader, BSLTextWriter, BSLBinaryData, BSLTextEncoding
from .text_documents import BSLTextDocument
from .user_messages import BSLUserMessage
from .value_storage import BSLValueStorage
from .data_compression import BSLDeflation
from .json_dates import BSLJSONSerializerSettings, BSLJSONDateFormat, BSLJSONDateWritingVariant
from .json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONValueType, BSLJSONWriterSettings, BSLJSONLineBreak
from .unique_identifiers import BSLUUID
from .dates import BSLDate
from .error_info import BSLErrorInfo, BSLErrorCategory
from .xml_processing import BSLXMLStringProcessingManager

from .maps import BSLFixedMap, BSLMap
from .numeric.round_modes import BSLRoundMode, BSLRoundModes
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
from .accumulation_movements import AccumulationDirection
from .value_trees import (BSLValueTree, BSLValueTreeColumnCollection, BSLValueTreeColumn,
                          BSLValueTreeRow, BSLValueTreeRowCollection)
from .value_tables import (BSLValueTable, BSLValueTableColumnCollection,
                           BSLValueTableColumn, BSLValueTableRow,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .value_lists import BSLValueList, BSLValueListItem


from .async_runtime import Promise
from .callbacks import BSLCallbackDescription


_VALUE_TYPES = (
    (AccumulationDirection, BSLType.ACCUMULATION_RECORD_TYPE, "AccumulationRecordType"),
    (BSLOpenSSLSecureConnection, BSLType.OPENSSL_SECURE_CONNECTION, "OpenSSLSecureConnection"),
    (BSLFileCertificationAuthorityCertificates, BSLType.FILE_CA_CERTIFICATES, "FileCertificationAuthorityCertificates"),
    (BSLOSCertificationAuthorityCertificates, BSLType.OS_CA_CERTIFICATES, "OSCertificationAuthorityCertificates"),
    (BSLInternetProxy, BSLType.INTERNET_PROXY, "InternetProxy"),
    (BSLUserMessage, BSLType.USER_MESSAGE, "UserMessage"),
    (BSLTempTablesManager, BSLType.TEMP_TABLES_MANAGER, "TempTablesManager"),
    (BSLQuery, BSLType.QUERY, "Query"),
    (BSLQueryResult, BSLType.QUERY_RESULT, "QueryResult"),
    (BSLQueryResultSelection, BSLType.QUERY_RESULT_SELECTION, "QueryResultSelection"),
    (BSLHTTPConnection, BSLType.HTTP_CONNECTION, "HTTPConnection"),
    (BSLHTTPRequest, BSLType.HTTP_REQUEST, "HTTPRequest"),
    (BSLHTTPResponse, BSLType.HTTP_RESPONSE, "HTTPResponse"),
    (BSLByteOrderMarkUse, BSLType.BYTE_ORDER_MARK_USE, "ByteOrderMarkUse"),
    (BSLClientApplicationForm, BSLType.FORM, "ClientApplicationForm"),
    (BSLFormAttribute, BSLType.FORM_ATTRIBUTE, "FormAttribute"),
    (BSLFormField, BSLType.FORM_FIELD, "FormField"),
    (BSLFormTable, BSLType.FORM_TABLE, "FormTable"),
    (BSLFormDataCollection, BSLType.FORM_DATA_COLLECTION, "FormDataCollection"),
    (BSLFormDataCollectionItem, BSLType.FORM_DATA_COLLECTION_ITEM, "FormDataCollectionItem"),
    (BSLFormButton, BSLType.FORM_BUTTON, "FormButton"),
    (BSLFormCommand, BSLType.FORM_COMMAND, "FormCommand"),
    (BSLFormItems, BSLType.FORM_ITEMS, "FormAllItems"),
    (BSLFormCommands, BSLType.FORM_COMMANDS, "FormCommands"),
    (BSLFormFieldView, BSLType.FORM_FIELD_VIEW, "FormFieldType"),
    (BSLXDTOFactory, BSLType.XDTO_FACTORY, "XDTOFactory"),
    (BSLXDTODataObject, BSLType.XDTO_OBJECT, "XDTODataObject"),
    (BSLXDTODataValue, BSLType.XDTO_VALUE, "XDTODataValue"),
    (BSLXDTOList, BSLType.XDTO_LIST, "XDTOList"),
    (BSLXDTOValueType, BSLType.XDTO_VALUE_TYPE, "XDTOValueType"),
    (BSLXDTOObjectType, BSLType.XDTO_OBJECT_TYPE, "XDTOObjectType"),
    (BSLXDTOProperty, BSLType.XDTO_PROPERTY, "XDTOProperty"),
    (BSLXDTOPropertyCollection, BSLType.XDTO_PROPERTIES, "XDTOPropertyCollection"),
    (BSLXDTOPackage, BSLType.XDTO_PACKAGE, "XDTOPackage"),
    (BSLXDTOPackageCollection, BSLType.XDTO_PACKAGES, "XDTOPackageCollection"),
    (BSLXMLForm, BSLType.XML_FORM, "XMLForm"),

    (BSLDOMDocument, BSLType.DOM_DOCUMENT, "DOMDocument"),
    (BSLDOMElement, BSLType.DOM_ELEMENT, "DOMElement"),
    (BSLDOMAttribute, BSLType.DOM_ATTRIBUTE, "DOMAttribute"),
    (BSLDOMText, BSLType.DOM_TEXT, "DOMText"),
    (BSLDOMCDATASection, BSLType.DOM_CDATA, "DOMCDATASection"),
    (BSLDOMComment, BSLType.DOM_COMMENT, "DOMComment"),
    (BSLDOMProcessingInstruction, BSLType.DOM_PI, "DOMProcessingInstruction"),
    (BSLDOMDocumentFragment, BSLType.DOM_FRAGMENT, "DOMDocumentFragment"),
    (BSLDOMNodeList, BSLType.DOM_NODE_LIST, "DOMNodeList"),
    (BSLDOMElementList, BSLType.DOM_ELEMENT_LIST, "DOMElementList"),
    (BSLDOMAttributeMap, BSLType.DOM_ATTRIBUTE_MAP, "DOMAttributeMap"),
    (BSLDOMNodeType, BSLType.DOM_NODE_TYPE, "DOMNodeType"),
    (BSLDOMBuilder, BSLType.DOM_BUILDER, "DOMBuilder"),
    (BSLDOMWriter, BSLType.DOM_WRITER, "DOMWriter"),

    (BSLDataHashing, BSLType.DATA_HASHING, "DataHashing"),
    (BSLHashFunction, BSLType.HASH_FUNCTION, "HashFunction"),
    (BSLDataReader, BSLType.DATA_READER, "DataReader"),
    (BSLDataWriter, BSLType.DATA_WRITER, "DataWriter"),
    (BSLReadDataResult, BSLType.READ_DATA_RESULT, "ReadDataResult"),
    (BSLRegexResult, BSLType.REGEX_RESULT, "ResultOfSearchByRegularExpression"),
    (BSLRegexGroup, BSLType.REGEX_GROUP, "ResultOfSearchByRegularExpressionGroup"),
    (BSLZipFileReader, BSLType.ZIP_READER, "ZipFileReader"),
    (BSLZipFileWriter, BSLType.ZIP_WRITER, "ZipFileWriter"),
    (BSLZipFileEntry, BSLType.ZIP_ENTRY, "ZipFileEntry"),
    (BSLZipFileEntries, BSLType.ZIP_ENTRIES, "ZipFileEntries"),
    (BSLZIPCompressionMethod, BSLType.ZIP_COMPRESSION_METHOD, "ZIPCompressionMethod"),
    (BSLZIPCompressionLevel, BSLType.ZIP_COMPRESSION_LEVEL, "ZIPCompressionLevel"),
    (BSLZIPStorePathMode, BSLType.ZIP_STORE_PATH_MODE, "ZIPStorePathMode"),
    (BSLZIPSubDirProcessingMode, BSLType.ZIP_SUBDIR_MODE, "ZIPSubDirProcessingMode"),
    (BSLZIPRestoreFilePathsMode, BSLType.ZIP_RESTORE_MODE, "ZIPRestoreFilePathsMode"),
    (BSLZIPEncryptionMethod, BSLType.ZIP_ENCRYPTION_METHOD, "ZIPEncryptionMethod"),
    (BSLFileNamesEncodingInZipFile, BSLType.ZIP_NAMES_ENCODING, "FileNamesEncodingInZipFile"),

    (BSLBinaryDataBuffer, BSLType.BINARY_DATA_BUFFER, "BinaryDataBuffer"),
    (BSLMemoryStream, BSLType.MEMORY_STREAM, "MemoryStream"),
    (BSLFileStream, BSLType.FILE_STREAM, "FileStream"),
    (BSLStream, BSLType.STREAM, "Stream"),
    (BSLByteOrder, BSLType.BYTE_ORDER, "ByteOrder"),
    (BSLFileOpenMode, BSLType.FILE_OPEN_MODE, "FileOpenMode"),
    (BSLFileAccess, BSLType.FILE_ACCESS, "FileAccess"),
    (BSLPositionInStream, BSLType.POSITION_IN_STREAM, "PositionInStream"),

    (BSLDocuments, BSLType.DOCUMENTS_MANAGER, None),
    (BSLInformationRegisters, BSLType.INFORMATION_REGISTERS_MANAGER, None),
    (BSLCatalogs, BSLType.CATALOGS_MANAGER, None),
    (BSLXMLReader, BSLType.XML_READER, "XMLReader"),
    (BSLXMLWriter, BSLType.XML_WRITER, "XMLWriter"),
    (BSLXMLReaderSettings, BSLType.XML_READER_SETTINGS, "XMLReaderSettings"),
    (BSLXMLWriterSettings, BSLType.XML_WRITER_SETTINGS, "XMLWriterSettings"),
    (BSLXMLNodeType, BSLType.XML_NODE_TYPE, "XMLNodeType"),
    (BSLXMLSpace, BSLType.XML_SPACE, "XMLSpace"),
    (BSLXMLValidationType, BSLType.XML_VALIDATION_TYPE, "XMLValidationType"),
    (BSLXMLNamespaceContext, BSLType.XML_NAMESPACE_CONTEXT, "XMLNamespaceContext"),

    (BSLFile, BSLType.FILE, "File"),
    (BSLTextReader, BSLType.TEXT_READER, "TextReader"),
    (BSLTextWriter, BSLType.TEXT_WRITER, "TextWriter"),
    (BSLBinaryData, BSLType.BINARY_DATA, "BinaryData"),
    (BSLTextEncoding, BSLType.TEXT_ENCODING, "TextEncoding"),
    (BSLJSONSerializerSettings, BSLType.JSON_SERIALIZER_SETTINGS, "JSONSerializerSettings"),
    (BSLJSONDateFormat, BSLType.JSON_DATE_FORMAT, "JSONDateFormat"),
    (BSLJSONDateWritingVariant, BSLType.JSON_DATE_WRITING_VARIANT, "JSONDateWritingVariant"),
    (BSLJSONWriterSettings, BSLType.JSON_WRITER_SETTINGS, "JSONWriterSettings"),
    (BSLJSONLineBreak, BSLType.JSON_LINE_BREAK, "JSONLineBreak"),
    (BSLJSONReader, BSLType.JSON_READER, "JSONReader"),
    (BSLJSONWriter, BSLType.JSON_WRITER, "JSONWriter"),
    (BSLJSONValueType, BSLType.JSON_VALUE_TYPE, "JSONValueType"),
    (BSLTextDocument, BSLType.TEXT_DOCUMENT, "TextDocument"),
    (BSLValueStorage, BSLType.VALUE_STORAGE, "ValueStorage"),
    (BSLDeflation, BSLType.DEFLATION, "Deflation"),
    (BSLUUID, BSLType.UUID, "UUID"),
    (Promise, BSLType.PROMISE, "Promise"),
    (BSLCallbackDescription, BSLType.CALLBACK_DESCRIPTION, "CallbackDescription"),
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


def type_of(value: object) -> BSLType | BSLCatalogType:
    from .enum_types import BSLEnumType, BSLEnumReference
    from .enumerations import BSLEnumManager
    if type(value) is BSLEnumType: return BSLType.TYPE
    if type(value) is BSLEnumReference: return value.value_type
    if type(value) is BSLEnumManager: return value._manager_type
    if type(value) is BSLInformationRegisterType:
        return BSLType.TYPE
    if type(value) is BSLInformationRegisterManager:
        return value._manager_type
    if type(value) is BSLInformationRegisterRecordSet:
        return value._set_type
    if type(value) is BSLInformationRegisterRecord:
        return value._row_type
    if type(value) is BSLInformationRegisterRecordManager:
        return value._record_type
    if type(value) is BSLInformationRegisterSelection:
        return value._selection_type
    if (type(value) is BSLDocumentLinesType or type(value) is BSLDocumentSectionType):
        return BSLType.TYPE
    if type(value) is BSLDocumentLines or type(value) is BSLDocumentLine:
        descriptor = value._value_type if type(value) is BSLDocumentLines else value._section._row_type
        if (type(descriptor) is not BSLDocumentLinesType and type(descriptor) is not BSLDocumentSectionType):
            raise TypeError('document line type is unavailable')
        return descriptor
    if (type(value) is BSLCatalogReference or type(value) is BSLDocumentReference):
        return value.value_type
    if (type(value) is BSLCatalogType or type(value) is BSLDocumentType):
        return BSLType.TYPE
    # Lazy import avoids the catalog adapter/type registry import cycle.
    from .catalogs import BSLCatalogManager, BSLCatalogSelection, BSLCatalogs, BSLCatalogObject
    if type(value) is BSLCatalogs:
        return BSLType.CATALOGS_MANAGER
    if type(value) is BSLCatalogObject:
        return value._object_type
    if type(value) is BSLCatalogManager:
        return value._manager_type
    if type(value) is BSLCatalogSelection:
        return value._selection_type
    from .documents import BSLDocumentManager, BSLDocumentSelection, BSLDocumentObject
    if type(value) is BSLDocumentObject:
        return value._object_type
    if type(value) is BSLDocumentManager:
        return value._manager_type
    if type(value) is BSLDocumentSelection:
        return value._selection_type
    # Exact identity keeps bool distinct from numbers and rejects arbitrary host
    # objects/subclasses without invoking their metaclass equality or hash hooks.
    for python_type, value_type, _ in _VALUE_TYPES:
        if type(value) is python_type:
            return value_type
    raise TypeError("ТипЗнч для этого значения пока не поддерживается")
