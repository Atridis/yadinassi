"""Admission-only generated-source operand binding, without Python AST rebuilding.

Input is trusted compiler output, never BSL or host source. Token positions keep
strings, attributes and control syntax intact. Only constant operands and exact
compiler node handles are replaced; runtime code performs no syntax dispatch.
"""
import ast
import io
import tokenize

def bind_generated_source(source, nodes):
    tokens=list(tokenize.generate_tokens(io.StringIO(source).readline))
    offsets=[0]
    for line in source.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    operands=[];handles={};constants={};replacements=[]
    def bind(value,handle=False):
        mapping=handles if handle else constants
        key=id(value) if handle else (type(value),value)
        index=mapping.get(key)
        if index is None:
            index=len(operands);mapping[key]=index;operands.append(value)
        return f'_p[{index}]'
    def position(pair):return offsets[pair[0]-1]+pair[1]
    index=0
    while index<len(tokens):
        token=tokens[index]
        if (token.type==tokenize.NAME and token.string=='_nodes' and index+3<len(tokens)
                and tokens[index+1].string=='[' and tokens[index+2].type==tokenize.NUMBER
                and tokens[index+3].string==']'):
            slot=int(tokens[index+2].string)
            replacements.append((position(token.start),position(tokens[index+3].end),bind(nodes[slot],True)))
            index+=4;continue
        if token.type in (tokenize.STRING,tokenize.NUMBER):
            value=(int(token.string) if token.type==tokenize.NUMBER and token.string.isdecimal()
                   else ast.literal_eval(token.string))
            replacements.append((position(token.start),position(token.end),bind(value)))
        elif token.type==tokenize.NAME and token.string in ('True','False','None'):
            value={'True':True,'False':False,'None':None}[token.string]
            replacements.append((position(token.start),position(token.end),bind(value)))
        index+=1
    parts=[];cursor=0
    for start,stop,replacement in replacements:
        parts.extend((source[cursor:start],replacement));cursor=stop
    parts.append(source[cursor:])
    return ''.join(parts),tuple(operands)
