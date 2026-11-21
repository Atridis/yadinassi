"""Explicit typed catalog-reference application source; no legacy grant expansion.

Reference fields target declared catalogs in this same canonical configuration.
The form transport is a private capability protocol, not generic Invocation or
native managed-form transport parity. Historical scalar sources retain their
original admission and do not gain implicit conversion/migration authority.
"""
REFERENCE_PROFILE = 'configuration_references_v1'
REFERENCE_SOURCE_ISSUE = 'explicit configuration reference application source:v1'


def reference_configuration(files):
    from .configuration_business_profile import business_configuration
    return business_configuration(files, _reference_fields=True)


def import_reference_configuration(files):
    return reference_configuration(files)[0]
