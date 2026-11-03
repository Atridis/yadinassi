"""Nonce-bound scalar transport for one owned catalog query session."""
import json
from decimal import Decimal
import re
from .packet import render_program, validate_observations, helper_source

PROFILE='catalog-query-behavior-v1'
SCHEMA='native-1c-catalog-query-v1'
STAGE_SCHEMA='native-1c-catalog-query-stage-v1'
MAX_OUTPUT=8192


def program(setup,nonce):
    if type(nonce) is not str or re.fullmatch('[0-9a-f]{32}',nonce) is None:
        raise ValueError('nonce')
    prefix='''Procedure CQEmit(Val N,Val V)
    If TypeOf(V)=Type("Boolean") Then
        If V Then Text="1";Else Text="0";EndIf;
        Tag="B";
    ElsIf TypeOf(V)=Type("Number") Then
        If V<0 Or V>3 Or V<>Int(V) Then Raise "CQ scalar unsupported";EndIf;
        Text=String(V);Tag="N";
    ElsIf TypeOf(V)=Type("String") Then
        If StrLen(V)>64 Or Find(V,"|")>0 Or Find(V,Chars.LF)>0 Or Find(V,Chars.CR)>0 Then
            Raise "CQ scalar unsupported";
        EndIf;
        Text=V;Tag="S";
    Else
        Raise "CQ scalar unsupported";
    EndIf;
    Message("CQ|@@NONCE@@|"+String(N)+"|"+Tag+"|"+Text);
EndProcedure
Message("CQ|@@NONCE@@|entered");
'''
    source=render_program(setup);helper=helper_source()
    if not source.startswith(helper):raise ValueError('helper source')
    result=helper+prefix.replace('@@NONCE@@',nonce)+source[len(helper):]+'Message("CQ|'+nonce+'|completed");\n'
    raw=result.encode('utf-8')
    if len(raw)>MAX_OUTPUT:raise ValueError('source bound')
    return raw


def parse_wire(raw,nonce):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT or type(nonce) is not str or re.fullmatch('[0-9a-f]{32}',nonce) is None:
        raise ValueError('wire bound')
    try:text=raw.decode('utf-8')
    except UnicodeError:raise ValueError('wire encoding') from None
    if '\r' in text or not text.endswith('\n'):raise ValueError('wire lines')
    lines=text.splitlines();prefix='CQ|'+nonce+'|'
    if len(lines)!=26 or lines[0]!=prefix+'entered' or lines[-1]!=prefix+'completed':raise ValueError('wire markers')
    values=[]
    for index,line in enumerate(lines[1:-1],1):
        pieces=line.split('|')
        if len(pieces)!=5 or pieces[:3]!=['CQ',nonce,str(index)]:raise ValueError('wire identity')
        if pieces[3]=='B' and pieces[4] in ('0','1'):value=pieces[4]=='1'
        elif pieces[3]=='N' and pieces[4] in ('0','1','2','3'):
            value=Decimal(pieces[4])
        elif pieces[3]=='S':value=pieces[4]
        else:raise ValueError('wire type')
        values.append(value)
    validate_observations(values)
    return values


def canonical(values):
    if type(values) is not list or len(values)!=24:raise ValueError('canonical observations')
    normalized=[Decimal(value) if type(value) is int else value for value in values]
    validate_observations(normalized)
    encoded=[int(v) if type(v) is Decimal else v for v in normalized]
    return (json.dumps(encoded,ensure_ascii=True,separators=(',',':'))+'\n').encode('ascii')
