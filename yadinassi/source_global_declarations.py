"""Index source common-module declarations without compiling unused bodies.

The normal lexer owns strings, comments and preprocessing. Only routine bodies
are omitted for discovery; the selected module is still fully compiled before
execution. Invalid boundaries/headers are not guessed or silently ignored.
"""
from .configuration_modules import MAX_ROUTINES, _ANNOTATIONS
from .syntax.lexer import Lexer
from .syntax.parser import Parser
from .syntax import ast
from .errors import BSLError


def exported_names(content, path, side, compilation_profile):
    tokens = Lexer(content.decode('utf-8-sig'), '<configuration:' + path + '>',
                   execution_context=side, compilation_profile=compilation_profile).tokens()
    output = []; index = 0; count = 0
    def fail(token, message):
        raise BSLError(message, token.source, token.line, token.column)
    while index < len(tokens):
        token = tokens[index]
        if token.kind in _ANNOTATIONS or token.kind == 'IMPORT':
            fail(token, 'Source global declaration: unsupported annotation/import')
        output.append(token); index += 1
        if token.kind not in ('FUNCTION', 'PROCEDURE'):
            continue
        count += 1
        if count > MAX_ROUTINES:
            fail(token, 'Source global declaration: routine bound')
        # Let the ordinary parser validate identifier/parameters/defaults below.
        # Locate the closing parameter parenthesis, without interpreting a body.
        depth = 0; opened = False
        while index < len(tokens):
            header = tokens[index]; index += 1; output.append(header)
            if header.kind == '(':
                depth += 1; opened = True
            elif header.kind == ')':
                depth -= 1
                if opened and depth == 0: break
            elif header.kind in ('EOF','FUNCTION','PROCEDURE','ENDFUNCTION','ENDPROCEDURE'):
                fail(header, 'Source global declaration: incomplete routine header')
        else:
            fail(token, 'Source global declaration: missing parameter list')
        if index < len(tokens) and tokens[index].kind == 'EXPORT':
            output.append(tokens[index]); index += 1
        ending = 'ENDFUNCTION' if token.kind == 'FUNCTION' else 'ENDPROCEDURE'
        while index < len(tokens):
            body = tokens[index]; index += 1
            if body.kind == ending:
                output.append(body)
                break
            if body.kind in ('FUNCTION','PROCEDURE','ENDFUNCTION','ENDPROCEDURE','EOF'):
                fail(body, 'Source global declaration: invalid routine boundary')
        else:
            fail(token, 'Source global declaration: unterminated routine')
    program = Parser(output).parse()
    if any(type(node) is not ast.Routine for node in program):
        raise ValueError('Source global declarations: common modules contain only routines')
    # Async server declarations still fail when their module is selected.
    return tuple(routine.name for routine in program if routine.exported)
