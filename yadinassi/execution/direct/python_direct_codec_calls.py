"""Canonical codecs for the Python representations emitted by BSL."""
from yadinassi.formats.storage.serialization import (
    _DIRECT_VALUE_TO_STRING_ABI,
    _direct_value_to_string_internal,
)


def implementation(function):
    # test_bsl_nested_mutable_collections_roundtrip_without_aliases:
    # generated lists and structures still have their BSL wire representation.
    if function is _DIRECT_VALUE_TO_STRING_ABI:
        return _direct_value_to_string_internal
    return function
