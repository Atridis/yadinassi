"""Explicit source-profile preflight and fresh database creation.

No profile discovery, module execution, migration, SQL maintenance or source
rewriting. A preparation is a report, not an execution/transaction capability.
Creation revalidates its immutable bytes through the selected closed importer.
"""
from dataclasses import dataclass
from hashlib import sha256
from .catalog_backend import BackendError
from .configuration_diagnostics import (ImportDiagnostic, ImportRefusal,
    activation_diagnostics, location)
from .configuration_xml import ConfigurationImport, import_configuration, _accept_source_files
from .configuration_posting import PROFILE as POSTING
from .configuration_posting_application import PROFILE as POSTING_FORMS, import_variant
from .configuration_accumulation import PROFILE as ACCUMULATION, import_accumulation_configuration

LEGACY = 'legacy'
PROFILES = (LEGACY, POSTING, POSTING_FORMS, ACCUMULATION)


@dataclass(frozen=True, slots=True)
class PreparedConfiguration:
    profile: str
    files: tuple
    numbering_policy: str
    module_runtime: str | None
    activate: bool
    configuration: object
    diagnostics: tuple
    format_version: int

    def report(self):
        config = self.configuration
        catalogs = config.catalogs if self.profile == LEGACY else ()
        documents = config.documents
        registers = config.information_registers if self.profile == LEGACY else config.registers
        digest = sha256(b''.join(path.encode('utf-8') + b'\0' + sha256(raw).digest()
                                for path, raw in self.files)).hexdigest()
        return {'format': 'configuration_preflight_v1', 'profile': self.profile,
            'ready': not self.diagnostics, 'activated': self.activate,
            'storage_format': self.format_version, 'source_digest': digest,
            'source_files': len(self.files), 'source_bytes': sum(len(raw) for _, raw in self.files),
            'catalogs': len(catalogs), 'documents': len(documents), 'registers': len(registers),
            'diagnostics': [d.as_dict() for d in self.diagnostics]}


def _options(profile, numbering_policy, module_runtime, activate):
    if type(profile) is not str or profile not in PROFILES or type(activate) is not bool:
        raise ImportRefusal(ImportDiagnostic('profile_unsupported', 'schema'))
    if profile != LEGACY and (numbering_policy != 'explicit' or module_runtime is not None or not activate):
        raise ImportRefusal(ImportDiagnostic('profile_options_unsupported', 'schema'))


def _prepare_imported(config, profile, numbering_policy, module_runtime, activate):
    diagnostics = ()
    if profile == LEGACY:
        if type(config) is not ConfigurationImport:
            raise ImportRefusal(ImportDiagnostic('profile_unsupported', 'schema'))
        if activate and config.activation_issues:
            diagnostics = activation_diagnostics(config)
        # An activation refusal can still explain a valid inactive archive.
        # This calls precisely the existing preallocation checks, without a file.
        from .sqlite_catalog import _preflight_create
        with location(stage='storage'):
            state = _preflight_create(config, activate=activate and not diagnostics)
        version = state[6]
        files = tuple((f.path, f.content) for f in config.files)
    elif profile in (POSTING, POSTING_FORMS):
        from .sqlite_posting_profile import preflight_configuration
        config = preflight_configuration(config)
        files = config.files
        version = 13
    else:
        from .document_posting_program import compile_handlers
        from .sqlite_accumulation_profile import _preflight_config
        # Preserve source-aware compilation diagnostics before the storage
        # boundary's intentionally generic BackendError translation.
        compile_handlers(config)
        _preflight_config(config)
        files = config.files
        version = 14
    return PreparedConfiguration(profile, tuple(sorted(files)), numbering_policy,
        module_runtime, activate, config, diagnostics, version)


def prepare_files(files, *, profile=LEGACY, numbering_policy='explicit', module_runtime=None, activate=True):
    _options(profile, numbering_policy, module_runtime, activate)
    # The host entry point requires the same bounded no-extra-file interchange
    # envelope for every profile; the legacy low-level posting API is unchanged.
    with location(stage='schema'):
        _accept_source_files(files)
        if profile == LEGACY:
            config = import_configuration(files, numbering_policy=numbering_policy, module_runtime=module_runtime)
        elif profile in (POSTING, POSTING_FORMS):
            config = import_variant(files, profile)
        else:
            config = import_accumulation_configuration(files, accumulation_runtime=profile)
        return _prepare_imported(config, profile, numbering_policy, module_runtime, activate)


def prepare_directory(directory, *, profile=LEGACY, numbering_policy='explicit', module_runtime=None, activate=True):
    _options(profile, numbering_policy, module_runtime, activate)
    from .configuration_import import load_configuration_directory, read_configuration_directory
    if profile == LEGACY:
        # Keep the established reader API and its no-link/race checks. Read once.
        config = load_configuration_directory(directory, numbering_policy=numbering_policy, module_runtime=module_runtime)
        return _prepare_imported(config, profile, numbering_policy, module_runtime, activate)
    return prepare_files(read_configuration_directory(directory), profile=profile,
        numbering_policy=numbering_policy, module_runtime=module_runtime, activate=activate)


def create_prepared(path, prepared):
    if type(prepared) is not PreparedConfiguration:
        raise ImportRefusal(ImportDiagnostic('profile_unsupported', 'schema'))
    # A forged/stale report never bypasses admission. Reimport exact retained
    # bytes, not the directory (which may have changed after the inspection).
    fresh = prepare_files(dict(prepared.files), profile=prepared.profile,
        numbering_policy=prepared.numbering_policy, module_runtime=prepared.module_runtime,
        activate=prepared.activate)
    if fresh.diagnostics:
        raise ImportRefusal(fresh.diagnostics[0])
    from .database_context import SQLiteDBContext
    if fresh.profile == LEGACY:
        return SQLiteDBContext.create(path, fresh.configuration, activate=fresh.activate)
    if fresh.profile in (POSTING, POSTING_FORMS):
        return SQLiteDBContext.create_posting(path, fresh.configuration)
    return SQLiteDBContext.create_accumulation(path, fresh.configuration)
