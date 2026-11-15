"""Static XML-to-module name inventory, never a runtime binding guarantee."""
import xml.etree.ElementTree as ET
from .configuration_forms import L
from .source_form_projection import project_source_form
from .syntax import ast


def audit_handler_names(raw, program):
    """Check only retained progressive Action/Event references against routines.

    Context, arity, argument types, permissions, lifecycle and bodies are not
    evaluated. Removed unsupported controls/events must not become capabilities.
    """
    result = {'status': 'unavailable', 'referenced': 0, 'missing': [],
              'omitted_missing': 0, 'error': None}
    try:
        if raw is None:
            raise ValueError('declared form XML is missing')
        root = ET.fromstring(project_source_form(raw).xml)
        names = {node.name.casefold() for side in (program.client, program.server, program.nocontext)
                 for node in side.program() if isinstance(node, ast.Routine)}
        references = set()
        for node in root.iter():
            if node.tag in (L+'Action', L+'Event'):
                if (set(node.attrib) - ({'name'} if node.tag == L+'Event' else set())
                        or len(node) or (node.tail or '').strip()):
                    raise ValueError('invalid handler reference envelope')
                value = (node.text or '').strip()
                if not value or len(value) > 128:
                    raise ValueError('invalid handler reference name')
                references.add(value)
        missing = sorted(value for value in references if value.casefold() not in names)
        result.update(status='names-checked', referenced=len(references), missing=missing[:16],
                      omitted_missing=max(0, len(missing)-16))
    except (ValueError, TypeError, RecursionError, ET.ParseError) as error:
        result['error'] = str(error)[:256]
    return result
