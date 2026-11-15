"""Static XML-to-module name inventory, never a runtime binding guarantee."""
import xml.etree.ElementTree as ET
import json
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
              'omitted_signature_issues': 0, 'signature_references': 0,
              'attribute_issues': [], 'omitted_attribute_issues': 0}
    try:
        if raw is None:
            raise ValueError('declared form XML is missing')
        root = ET.fromstring(project_source_form(raw).xml)
        declarations = tuple(node for side in (program.client, program.server, program.nocontext)
                             for node in side.program())
        routines = {node.name.casefold(): node for node in declarations if isinstance(node, ast.Routine)}
        declared_names = {value.casefold() for node in declarations
                          for value in ([node.name] if isinstance(node, ast.Routine) else node.names)}
        attribute_issues = []
        for attribute in root.findall('./'+L+'Attributes/'+L+'Attribute'):
            attribute_name = attribute.get('name')
            key = attribute_name.casefold()
            if key in ('object','объект','writeobject') or key.startswith('objectfield'):
                attribute_issues.append(attribute_name+': reserved object form attribute')
            elif key in declared_names:
                attribute_issues.append(attribute_name+': form attribute shadows module declaration')
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
                      omitted_signature_issues=max(0, len(issues)-16), signature_references=len(contracts),
                      attribute_issues=attribute_issues[:16], omitted_attribute_issues=max(0,len(attribute_issues)-16))
        # Snapshot shares a bounded transport packet with navigation and previews.
        # Bound UTF-8 JSON bytes, not just Unicode character counts.
        budget = 6144
        for field, omitted in (('missing','omitted_missing'),
                               ('signature_issues','omitted_signature_issues'),
                               ('attribute_issues','omitted_attribute_issues')):
            kept = []
            for value in result[field]:
                cost = len(json.dumps(value,ensure_ascii=False).encode('utf-8')) + 1
                if cost > budget:
                    result[omitted] += 1
                else:
                    kept.append(value);budget -= cost
            result[field] = kept
    except (ValueError, TypeError, RecursionError, ET.ParseError) as error:
        result['error'] = str(error)[:256]
    return result
