"""Bounded import diagnostics, independent of stored source and admission grants.

Only closed reason strings and validated source-relative metadata locations are
rendered. Never stringify arbitrary exceptions or emit source/property values.
Location scopes attach context while an exception unwinds; no global request
state, mutable parser annotations or persisted diagnostic fields are needed.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from .errors import BSLError
import re

MAX_DIAGNOSTICS = 32
STAGES = frozenset(('read', 'xml', 'schema', 'activation', 'compile', 'storage'))
_PROPERTIES = frozenset(('Type', 'Name', 'Properties', 'ChildObjects',
    'StringQualifiers', 'NumberQualifiers', 'DateQualifiers', 'CodeLength',
    'DescriptionLength', 'NumberLength', 'Posting', 'RegisterType',
    'InformationRegisterPeriodicity', 'AllowedSign', 'Digits', 'FractionDigits',
    'UseInTotals', 'DefaultObjectForm', 'Autonumbering', 'NumberType',
    'NumberPeriodicity', 'CheckUnique', 'RealTimePosting', 'RegisterRecordsDeletion',
    'RegisterRecordsWritingOnPost', 'PostInPrivilegedMode', 'UnpostInPrivilegedMode'))

# This vocabulary is deliberately source-owned, not exception-message passthrough.
_REASONS = {
    'invalid configuration directory': 'source_directory_invalid',
    'configuration source unavailable': 'source_unavailable',
    'configuration source changed': 'source_changed',
    'unexpected system directory alias': 'source_alias_unsupported',
    'directory aliases unsupported': 'source_alias_unsupported',
    'configuration reparse point unsupported': 'source_alias_unsupported',
    'directory depth bound': 'source_budget_exceeded',
    'configuration directory bound': 'source_budget_exceeded',
    'configuration directory entry bound': 'source_budget_exceeded',
    'configuration file bound': 'source_budget_exceeded',
    'unsupported configuration file': 'source_file_unsupported',
    'unsafe configuration path': 'source_path_invalid',
    'unsafe path': 'source_path_invalid',
    'case-colliding paths': 'source_path_collision',
    'file count': 'source_budget_exceeded',
    'file byte bound': 'source_budget_exceeded',
    'total byte bound': 'source_budget_exceeded',
    'only XML/BSL interchange supported': 'source_file_unsupported',
    'non UTF-8 source': 'source_encoding_invalid',
    'malformed UTF-8 XML': 'xml_malformed',
    'DTD/entities forbidden': 'xml_dtd_forbidden',
    'processing instructions forbidden': 'xml_processing_instruction_forbidden',
    'XML structure bound': 'xml_budget_exceeded',
    'metadata object shape': 'metadata_envelope_unsupported',
    'invalid name': 'metadata_name_invalid',
    'missing UUID': 'metadata_identity_missing',
    'invalid UUID': 'metadata_identity_invalid',
    'duplicate metadata UUID': 'metadata_identity_collision',
    'duplicate generated metadata UUID': 'metadata_identity_collision',
    'noncanonical or duplicate UUID': 'metadata_identity_invalid',
    'field identity/name collision': 'field_identity_collision',
    'section identity/name collision': 'section_identity_collision',
    'duplicate property': 'property_duplicate',
    'missing Properties': 'properties_missing',
    'missing field type': 'field_type_missing',
    'composite or absent field type unsupported': 'field_type_unsupported',
    'unsupported field type': 'field_type_unsupported',
    'unbound type QName': 'field_type_namespace_invalid',
    'unknown reference target': 'field_reference_unbound',
    'missing qualifiers': 'field_qualifiers_missing',
    'string qualifiers': 'field_qualifiers_unsupported',
    'number qualifiers': 'field_qualifiers_unsupported',
    'date fractions': 'field_qualifiers_unsupported',
    'string length': 'field_qualifiers_unsupported',
    'number precision': 'field_qualifiers_unsupported',
    'unsupported qualifier envelope': 'field_qualifiers_unsupported',
    'structured qualifier': 'field_qualifiers_unsupported',
    'missing Configuration.xml': 'source_file_missing',
    'Configuration.xml missing': 'source_file_missing',
    'missing catalog XML': 'source_file_missing',
    'declared metadata missing': 'source_file_missing',
    'posting XML missing': 'source_file_missing',
    'posting metadata missing': 'source_file_missing',
    'posting handler source missing': 'handler_source_missing',
    'document handler source missing': 'handler_source_missing',
    'posting command manifest missing': 'posting_manifest_missing',
    'catalog filename/name mismatch': 'metadata_name_mismatch',
    'document filename/name mismatch': 'metadata_name_mismatch',
    'register filename/name mismatch': 'metadata_name_mismatch',
    'filename/name mismatch': 'metadata_name_mismatch',
    'unsupported catalog semantics': 'catalog_semantics_unsupported',
    'unsupported catalog hierarchy': 'catalog_hierarchy_unsupported',
    'catalog owners unsupported': 'catalog_owners_unsupported',
    'unsupported document semantics': 'document_semantics_unsupported',
    'unsupported register semantics': 'register_semantics_unsupported',
    'unsupported source or executable grant': 'source_grant_mismatch',
    'unsupported posting source or executable grant': 'source_grant_mismatch',
    'unexpected or missing posting application source': 'source_grant_mismatch',
    'unsupported declaration': 'metadata_family_unsupported',
    'posting application metadata family': 'metadata_family_unsupported',
    'unowned accumulation register': 'recorder_unbound',
    'unowned recorder register': 'recorder_unbound',
    'numeric accumulation resources required': 'resource_type_unsupported',
    'unsupported accumulation schema': 'register_schema_unsupported',
    'document source binding': 'handler_source_mismatch',
    'duplicate document routine': 'handler_routine_duplicate',
    'duplicate document handler': 'handler_duplicate',
    'document handler signature': 'handler_signature_unsupported',
    'posting host command requires an empty synchronous client handler': 'posting_command_handler_unsupported',
}
_BACKEND = frozenset(('unsupported', 'invalid_input', 'not_found', 'conflict',
    'busy', 'closed', 'integrity', 'storage_error', 'uncertain_commit', 'schema_changed'))
_ACTIVATION = frozenset(('unsupported metadata family', 'unsupported object envelope',
    'unsupported metadata mixed content', 'unsupported object component',
    'unsupported internal metadata', 'unsupported metadata container',
    'unsupported attribute child objects', 'unsupported property mixed content',
    'unsupported metadata property', 'unsupported property attributes',
    'unsupported presentation metadata', 'unsupported child metadata envelope',
    'unsupported metadata document envelope', 'required field validation unsupported',
    'automatic metadata behavior unsupported', 'missing document XML',
    'missing information register XML', 'module execution unsupported',
    'unsupported configuration file', 'unsupported module path', 'unsupported module paths'))


def safe_identifier(value):
    return value if type(value) is str and 1 <= len(value) <= 128 and value.isidentifier() else None


def safe_path(value):
    if type(value) is not str or not 1 <= len(value) <= 256:
        return None
    parts = value.split('/')
    if (len(parts) > 9 or any(not part or part in ('.', '..') for part in parts)
            or any(not re.fullmatch(r'[\w.\-]+', part, re.UNICODE) for part in parts)
            or not value.endswith(('.xml', '.bsl'))):
        return None
    return value


@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    code: str
    stage: str
    file: str | None = None
    object: str | None = None
    field: str | None = None
    property: str | None = None
    line: int | None = None
    column: int | None = None

    def __post_init__(self):
        codes = set(_REASONS.values()) | {'property_unsupported', 'import_refused',
            'source_unavailable', 'storage_unavailable', 'module_compile_refused',
            'profile_unsupported', 'profile_options_unsupported', 'activation_unsupported'}
        codes.update('backend_' + code for code in _BACKEND)
        codes.update(reason.replace(' ', '_') for reason in _ACTIVATION)
        if type(self.code) is not str or self.code not in codes or type(self.stage) is not str or self.stage not in STAGES:
            raise ValueError('invalid import diagnostic')
        if self.file is not None and safe_path(self.file) != self.file:
            raise ValueError('invalid import diagnostic')
        if any(value is not None and safe_identifier(value) != value for value in (self.object, self.field)):
            raise ValueError('invalid import diagnostic')
        if self.property is not None and (type(self.property) is not str or self.property not in _PROPERTIES):
            raise ValueError('invalid import diagnostic')
        if any(value is not None and (type(value) is not int or not 1 <= value <= 1000000) for value in (self.line, self.column)):
            raise ValueError('invalid import diagnostic')

    def as_dict(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__
                if getattr(self, name) is not None}

    def text(self):
        return '; '.join(name + '=' + str(value) for name, value in self.as_dict().items())


class ImportRefusal(ValueError):
    """Still a ValueError for existing importer callers and canonical guards."""
    def __init__(self, diagnostic, original_args=()):
        super().__init__(*original_args)
        if type(diagnostic) is not ImportDiagnostic:
            raise ValueError('invalid import diagnostic')
        diagnostic.__post_init__()
        self.diagnostic = diagnostic


def from_exception(error, stage='schema'):
    # Exact classes only: subclasses may execute arbitrary __str__/attribute hooks.
    if type(error) is ImportRefusal:
        diagnostic = error.__dict__.get('diagnostic')
        if type(diagnostic) is ImportDiagnostic:
            try:
                diagnostic.__post_init__()
                return diagnostic
            except ValueError:
                pass
        return ImportDiagnostic('import_refused', stage if stage in STAGES else 'schema')
    code = 'import_refused'
    if type(error) is ValueError:
        args = error.args
        if len(args) == 1 and type(args[0]) is str:
            reason = args[0]
            for prefix in ('configuration XML: ', 'accumulation source: '):
                if reason.startswith(prefix): reason = reason[len(prefix):]; break
            code = _REASONS.get(reason, code)
            for prefix in ('unsupported control ', 'structured scalar ', 'unsupported ', 'invalid '):
                prop = reason.removeprefix(prefix)
                if reason.startswith(prefix) and prop in _PROPERTIES:
                    return ImportDiagnostic('property_unsupported', stage, property=prop)
    else:
        from .catalog_backend import BackendError
        from .errors import BSLError, BSLRuntimeError, IncompleteInput
        if type(error) is BackendError:
            candidate = error.__dict__.get('code')
            if type(candidate) is str and candidate in _BACKEND:
                code = 'backend_' + candidate
        elif isinstance(error, OSError):
            code = 'source_unavailable' if stage == 'read' else 'storage_unavailable'
        # Do not copy a parser's message, token spelling, source text or host path.
        elif type(error) in (BSLError, BSLRuntimeError, IncompleteInput):
            line = error.__dict__.get('line'); column = error.__dict__.get('column')
            return ImportDiagnostic('module_compile_refused', 'compile',
                line=line if type(line) is int and 1 <= line <= 1000000 else None,
                column=column if type(column) is int and 1 <= column <= 1000000 else None)
    return ImportDiagnostic(code, stage if stage in STAGES else 'schema')


@contextmanager
def location(*, stage=None, file=None, object=None, field=None, property=None):
    try:
        yield
    except (ValueError, BSLError) as error:
        diagnostic = from_exception(error, stage or 'schema')
        changes = {}
        for name, value in (('file', safe_path(file)), ('object', safe_identifier(object)),
                            ('field', safe_identifier(field)),
                            ('property', property if property in _PROPERTIES else None)):
            if value is not None and getattr(diagnostic, name) is None:
                changes[name] = value
        if stage in STAGES and type(error) is not ImportRefusal and diagnostic.stage != 'compile':
            changes['stage'] = stage
        args = error.args if type(error) in (ValueError, ImportRefusal) else ()
        raise ImportRefusal(replace(diagnostic, **changes), args) from None


def activation_diagnostics(configuration):
    files = {entry.path for entry in configuration.files}
    objects = {obj.name: prefix + obj.name + '.xml'
        for prefix, values in (('Catalogs/', configuration.catalogs),
                               ('Documents/', configuration.documents),
                               ('InformationRegisters/', configuration.information_registers))
        for obj in values}
    result = []
    for issue in configuration.activation_issues[:MAX_DIAGNOSTICS]:
        # Existing immutable issue strings remain untouched in the stored schema.
        # Parse only known prefixes, never render arbitrary suffixes/namespaces.
        reason, _, detail = issue.partition(':')
        code = reason.replace(' ', '_') if reason in _ACTIVATION else 'activation_unsupported'
        owner, _, prop = detail.partition(':')
        file = detail if detail in files else objects.get(owner)
        property_name = prop.rsplit('}', 1)[-1]
        result.append(ImportDiagnostic(code, 'activation', safe_path(file),
            safe_identifier(owner) if owner in objects else None,
            property=property_name if property_name in _PROPERTIES else None))
    return tuple(result)


def metadata_name(node):
    """Optional location only; never makes a malformed name admissible."""
    props = node.find('{http://v8.1c.ru/8.3/MDClasses}Properties')
    name = None if props is None else props.find('{http://v8.1c.ru/8.3/MDClasses}Name')
    return None if name is None else safe_identifier(name.text)
