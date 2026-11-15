"""Static XML-to-module name inventory, never a runtime binding guarantee."""
import xml.etree.ElementTree as ET
from .configuration_forms import L, _events, _value, name
from .form_model import BSLClientApplicationForm
from .source_form_projection import project_source_form
from .syntax import ast


def audit_handler_names(raw, program):
    """Check only retained progressive Action/Event references against routines.

    Static context/arity checks follow the current form binder contract.
    Argument values, permissions, lifecycle and bodies are not evaluated. Removed unsupported controls/events must not become capabilities.
    """
    result = {'status': 'unavailable', 'referenced': 0, 'missing': [],
              'omitted_missing': 0, 'error': None, 'signature_issues': [],
              'omitted_signature_issues': 0, 'signature_references': 0}
    try:
        if raw is None:
            raise ValueError('declared form XML is missing')
        root = ET.fromstring(project_source_form(raw).xml)
        routines = {node.name.casefold(): node for side in (program.client, program.server, program.nocontext)
                    for node in side.program() if isinstance(node, ast.Routine)}
        contracts = []
        for event, handler in _events(root.find(L+'Events'), BSLClientApplicationForm.EVENTS).items():
            side, arity = BSLClientApplicationForm.EVENTS[event]
            contracts.append(('Form.'+event, handler, side, arity))
        for command in root.findall('./'+L+'Commands/'+L+'Command'):
            handler = name(_value({L+'Action':command.find(L+'Action')}, 'Action'))
            contracts.append(('Command.'+command.get('name'), handler, 'client', 1))
        for kind in ('InputField','LabelField','CheckBoxField'):
            for item in root.iter(L+kind):
                for event, handler in _events(item.find(L+'Events'), {'onchange'}).items():
                    contracts.append(('Item.'+item.get('name')+'.'+event, handler, 'client', 1))
        references = {handler for _, handler, _, _ in contracts}
        names = set(routines)
        issues = []
        for path, handler, side, arity in contracts:
            node = routines.get(handler.casefold())
            if node is None:
                continue  # Missing declarations are reported separately.
            if (node.is_function or node.is_async or node.is_dual or not node.module_context
                    or node.execution_context != side or len(node.parameters) != arity):
                issues.append((path+': '+handler+' requires '+side+' procedure('+str(arity)+')')[:256])
        missing = sorted(value for value in references if value.casefold() not in names)
        result.update(status='names-checked', referenced=len(references), missing=missing[:16],
                      omitted_missing=max(0, len(missing)-16), signature_issues=issues[:16],
                      omitted_signature_issues=max(0, len(issues)-16), signature_references=len(contracts))
    except (ValueError, TypeError, RecursionError, ET.ParseError) as error:
        result['error'] = str(error)[:256]
    return result
