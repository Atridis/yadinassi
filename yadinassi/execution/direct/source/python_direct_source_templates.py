"""Owned source resource markers, admitted before argument effects."""
import weakref
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.configuration import common_templates as templates
from . import python_direct_source_resources as resources


def captured(boundary, function, *, require_value=False, allow_references=False,
             argument_count=None):
    if type(function) is not HostFunction or type(function.function) is not templates.SourceTemplateCall:
        return None
    marker=function.function;owner=marker.owner
    entries=(owner._direct_source_entries if type(owner) is templates.SourceCommonTemplates else None)

    def authorize(count=None):
        boundary._check()
        if (function.function is not marker or marker.owner is not owner
                or type(owner) is not templates.SourceCommonTemplates
                or owner is not boundary.app.common_templates
                or type(owner._app) is not weakref.ReferenceType
                or owner._app() is not boundary.app
                or type(owner._entries) is not dict or type(owner._loaded) is not dict
                or type(owner._bytes) is not int):
            raise BoundaryViolation('source template marker owner changed')
        for cls,name,expected in templates._DIRECT_SOURCE_TEMPLATE_ABI:
            instance=marker if cls is templates.SourceTemplateCall else owner
            if name in vars(instance) or getattr(cls,name) is not expected:
                raise BoundaryViolation('custom source template hooks are not integrated')
        if (type(entries) is not tuple or owner._direct_source_entries is not entries
                or len(owner._entries)!=len(entries)
                or any(owner._entries.get(key) is not entry for key,entry in entries)):
            raise BoundaryViolation('source template inventory changed')
        from yadinassi.configuration.configuration_templates import CommonTemplateDefinition
        from uuid import UUID
        retained=0
        for key,definition in owner._loaded.items():
            if (type(key) is not str or key not in owner._entries
                    or type(definition) is not CommonTemplateDefinition
                    or type(definition.name) is not str or type(definition.kind) is not str
                    or type(definition.identity) is not UUID or type(definition.content) is not bytes
                    or definition.kind not in ('TextDocument','BinaryData')
                    or definition.name.casefold()!=key
                    or definition.identity!=owner._entries[key].identity
                    or len(definition.content)>1024*1024):
                raise BoundaryViolation('source template cached resource changed')
            retained+=len(definition.content)
        if len(owner._loaded)>128 or retained>8*1024*1024 or owner._bytes!=retained:
            raise BoundaryViolation('source template resource accounting changed')
        owner.authorize(boundary.vm)
        boundary._validate_host_function(function,require_value,allow_references)
        if count is not None and count!=1:
            raise TypeError('GetCommonTemplate requires one argument')
        resources.check_factories()

    authorize(argument_count)
    def call(*values):
        authorize(len(values))
        from yadinassi.configuration.configuration_source_metadata import SourceMetadataObject
        if type(values[0]) is SourceMetadataObject:
            metadata=values[0]
            if (metadata._root is not boundary.app.metadata
                    or not any(metadata._entry is entry for _,entry in entries)):
                raise BoundaryViolation('source template metadata argument changed')
        try:return marker.invoke(boundary.vm,list(values))
        finally:authorize()
    if allow_references:call.requires_reference=lambda index:False
    return call
