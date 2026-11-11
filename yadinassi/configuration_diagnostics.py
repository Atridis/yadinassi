"""Bounded import diagnostics, independent of stored source and admission grants.

Only closed reason strings and validated source-relative metadata locations are
rendered. Never stringify arbitrary exceptions or emit source/property values.
Location scopes attach context while an exception unwinds; no global request
state, mutable parser annotations or persisted diagnostic fields are needed.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from .errors import BSLError, BSLRuntimeError, IncompleteInput
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

# Additional fixed source-validator categories; never runtime-derived text.
_REASONS.update({
    'QName': 'source_qname',
    'UUID': 'source_uuid',
    'accumulation configuration required': 'source_accumulation_configuration_required',
    'all posting forms require explicit host commands': 'source_all_posting_forms_require_explicit_host_commands',
    'attribute child object unsupported': 'source_attribute_child_object_unsupported',
    'catalog child object unsupported': 'source_catalog_child_object_unsupported',
    'catalog inventory': 'source_catalog_inventory',
    'catalog shape': 'source_catalog_shape',
    'child object unsupported': 'source_child_object_unsupported',
    'common module child objects': 'source_common_module_child_objects',
    'common module filename/name mismatch': 'source_common_module_filename_name_mismatch',
    'common module has no supported execution side': 'source_common_module_has_no_supported_execution_side',
    'common module inventory': 'source_common_module_inventory',
    'common module return-value reuse unsupported': 'source_common_module_return_value_reuse_unsupported',
    'common modules contain only procedures and functions': 'source_common_modules_contain_only_procedures_and_functions',
    'configuration module routine bound': 'source_configuration_module_routine_bound',
    'configuration runtime routine bound': 'source_configuration_runtime_routine_bound',
    'configured module annotations/imports are outside this profile': 'source_configured_module_annotations_imports_are_outside_this_profile',
    'demo_directories_v1 warehouse semantics': 'source_demo_directories_v1_warehouse_semantics',
    'demo_kinds_v1 catalog semantics': 'source_demo_kinds_v1_catalog_semantics',
    'demo_kinds_v1 source mismatch': 'source_demo_kinds_v1_source_mismatch',
    'demo_products_v1 product semantics': 'source_demo_products_v1_product_semantics',
    'document child object unsupported': 'source_document_child_object_unsupported',
    'document field bound': 'source_document_field_bound',
    'document inventory': 'source_document_inventory',
    'duplicate declaration': 'source_duplicate_declaration',
    'duplicate identity': 'source_duplicate_identity',
    'duplicate posting application metadata identity': 'source_duplicate_posting_application_metadata_identity',
    'duplicate posting declaration': 'source_duplicate_posting_declaration',
    'duplicate posting form': 'source_duplicate_posting_form',
    'duplicate posting generated identity': 'source_duplicate_posting_generated_identity',
    'embedded executable component unsupported': 'source_embedded_executable_component_unsupported',
    'empty accumulation movements': 'source_empty_accumulation_movements',
    'empty posting movements': 'source_empty_posting_movements',
    'exact declared posting form required': 'source_exact_declared_posting_form_required',
    'exact source-granted posting command required': 'source_exact_source_granted_posting_command_required',
    'explicit accumulation source grant required': 'source_explicit_accumulation_source_grant_required',
    'explicit posting application source grant required': 'source_explicit_posting_application_source_grant_required',
    'explicit posting command manifest required': 'source_explicit_posting_command_manifest_required',
    'explicit posting source grant required': 'source_explicit_posting_source_grant_required',
    'field count': 'source_field_count',
    'field name': 'source_field_name',
    'field name collision': 'source_field_name_collision',
    'form definition envelope': 'source_form_definition_envelope',
    'form filename/name mismatch': 'source_form_filename_name_mismatch',
    'form inventory': 'source_form_inventory',
    'generated identities': 'source_generated_identities',
    'incomplete generated identities': 'source_incomplete_generated_identities',
    'incomplete posting generated identities': 'source_incomplete_posting_generated_identities',
    'inert ChildObjects envelope': 'source_inert_childobjects_envelope',
    'inert declaration envelope': 'source_inert_declaration_envelope',
    'inert scalar envelope': 'source_inert_scalar_envelope',
    'invalid canonical source': 'source_invalid_canonical_source',
    'invalid common module server-call combination': 'source_invalid_common_module_server_call_combination',
    'invalid path type': 'source_invalid_path_type',
    'length': 'source_length',
    'metadata bound': 'source_metadata_bound',
    'metadata inventory': 'source_metadata_inventory',
    'missing Name': 'source_missing_name',
    'missing common module XML': 'source_missing_common_module_xml',
    'missing configuration ChildObjects': 'source_missing_configuration_childobjects',
    'missing form source': 'source_missing_form_source',
    'missing or invalid common module source': 'source_missing_or_invalid_common_module_source',
    'mixed XML': 'source_mixed_xml',
    'mixed content': 'source_mixed_content',
    'name': 'source_name',
    'periodic recorder profile unsupported': 'source_periodic_recorder_profile_unsupported',
    'posting application configuration required': 'source_posting_application_configuration_required',
    'posting application source/schema divergence': 'source_posting_application_source_schema_divergence',
    'posting configuration required': 'source_posting_configuration_required',
    'posting declaration envelope': 'source_posting_declaration_envelope',
    'posting declaration shape': 'source_posting_declaration_shape',
    'posting declarations missing': 'source_posting_declarations_missing',
    'posting default object form required': 'source_posting_default_object_form_required',
    'posting document inventory': 'source_posting_document_inventory',
    'posting form declaration shape': 'source_posting_form_declaration_shape',
    'posting metadata bound': 'source_posting_metadata_bound',
    'posting source budget': 'source_posting_source_budget',
    'posting source count': 'source_posting_source_count',
    'posting source shape': 'source_posting_source_shape',
    'posting source/schema divergence': 'source_posting_source_schema_divergence',
    'profile mode': 'source_profile_mode',
    'properties': 'source_properties',
    'recorder declaration': 'source_recorder_declaration',
    'recorder declarations missing': 'source_recorder_declarations_missing',
    'recorder scalar fields only': 'source_recorder_scalar_fields_only',
    'recorder target': 'source_recorder_target',
    'register child object unsupported': 'source_register_child_object_unsupported',
    'register dimension count': 'source_register_dimension_count',
    'register field count': 'source_register_field_count',
    'register inventory': 'source_register_inventory',
    'scalar attribute': 'source_scalar_attribute',
    'scalar attribute profile': 'source_scalar_attribute_profile',
    'scalar fields only': 'source_scalar_fields_only',
    'scalar inventory': 'source_scalar_inventory',
    'scalar type': 'source_scalar_type',
    'section field bound': 'source_section_field_bound',
    'section field count': 'source_section_field_count',
    'section name collision': 'source_section_name_collision',
    'server common modules cannot contain Async routines': 'source_server_common_modules_cannot_contain_async_routines',
    'source/schema divergence': 'source_source_schema_divergence',
    'structured scalar property': 'source_structured_scalar_property',
    'tabular section count': 'source_tabular_section_count',
    'type attributes': 'source_type_attributes',
    'type identity': 'source_type_identity',
    'unbound default object form': 'source_unbound_default_object_form',
    'unbound posting form': 'source_unbound_posting_form',
    'undeclared posting default form': 'source_undeclared_posting_default_form',
    'unknown or duplicate recorder target': 'source_unknown_or_duplicate_recorder_target',
    'unknown posting QName namespace': 'source_unknown_posting_qname_namespace',
    'unknown recorder XML grant': 'source_unknown_recorder_xml_grant',
    'unsupported accumulation field': 'source_unsupported_accumulation_field',
    'unsupported common module execution mode': 'source_unsupported_common_module_execution_mode',
    'unsupported container': 'source_unsupported_container',
    'unsupported demo source profile': 'source_unsupported_demo_source_profile',
    'unsupported document child': 'source_unsupported_document_child',
    'unsupported document numbering': 'source_unsupported_document_numbering',
    'unsupported generated UUID': 'source_unsupported_generated_uuid',
    'unsupported generated identity': 'source_unsupported_generated_identity',
    'unsupported inert form type': 'source_unsupported_inert_form_type',
    'unsupported metadata document envelope': 'source_unsupported_metadata_document_envelope',
    'unsupported module runtime profile': 'source_unsupported_module_runtime_profile',
    'unsupported numbering policy': 'source_unsupported_numbering_policy',
    'unsupported object components': 'source_unsupported_object_components',
    'unsupported object envelope': 'source_unsupported_object_envelope',
    'unsupported posting controls': 'source_unsupported_posting_controls',
    'unsupported posting declaration': 'source_unsupported_posting_declaration',
    'unsupported posting document child': 'source_unsupported_posting_document_child',
    'unsupported posting generated identity': 'source_unsupported_posting_generated_identity',
    'unsupported posting internal envelope': 'source_unsupported_posting_internal_envelope',
    'unsupported posting passive property': 'source_unsupported_posting_passive_property',
    'unsupported presentation metadata': 'source_unsupported_presentation_metadata',
    'unsupported property': 'source_unsupported_property',
    'unsupported recorder declaration': 'source_unsupported_recorder_declaration',
    'unsupported section field': 'source_unsupported_section_field',
    'unsupported type components': 'source_unsupported_type_components',
    'unsupported type envelope': 'source_unsupported_type_envelope',
})

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
    if type(error) in (BSLError, BSLRuntimeError, IncompleteInput):
        diagnostic = error.__dict__.get('_configuration_import_diagnostic')
        if type(diagnostic) is ImportDiagnostic:
            try:
                diagnostic.__post_init__()
                return diagnostic
            except ValueError:
                pass
    code = 'import_refused'
    if type(error) is KeyError and len(error.args) == 1 and safe_path(error.args[0]) is not None:
        return ImportDiagnostic('source_file_missing', stage if stage in STAGES else 'schema', file=safe_path(error.args[0]))
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
        if type(error) is BackendError:
            candidate = error.__dict__.get('code')
            if type(candidate) is str and candidate in _BACKEND:
                code = 'backend_' + candidate
        elif issubclass(type(error), OSError):
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
    except (ValueError, BSLError, KeyError, TypeError) as error:
        if issubclass(type(error), BSLError) and type(error) not in (BSLError, BSLRuntimeError, IncompleteInput):
            # Unknown exception implementations retain their identity and are
            # never annotated or inspected through subclass attribute hooks.
            raise
        diagnostic = from_exception(error, stage or 'schema')
        changes = {}
        for name, value in (('file', safe_path(file)), ('object', safe_identifier(object)),
                            ('field', safe_identifier(field)),
                            ('property', property if type(property) is str and property in _PROPERTIES else None)):
            if value is not None and getattr(diagnostic, name) is None:
                changes[name] = value
        if stage in STAGES and type(error) is not ImportRefusal and diagnostic.stage != 'compile':
            changes['stage'] = stage
        enriched = replace(diagnostic, **changes)
        if type(error) in (BSLError, BSLRuntimeError, IncompleteInput):
            # Existing compile/runtime callers rely on BSLError identity/family.
            # This ephemeral host-only annotation is never part of a schema,
            # stored source, BSL descriptor or interpreter value.
            error.__dict__['_configuration_import_diagnostic'] = enriched
            raise
        args = error.args if type(error) in (ValueError, ImportRefusal) else ()
        raise ImportRefusal(enriched, args) from None


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
