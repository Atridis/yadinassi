"""Closed event-wiring experiment: identical authored modules, one changed binding."""
import json,re,xml.etree.ElementTree as ET
from . import packet
FORM_NS='{http://v8.1c.ru/8.3/xcf/logform}'
CASES=('baseline1','baseline2','handler_compatible')
EVENTS={'OnCreateAtServer':'Created','BeforeClose':'Closing','OnOpen':'XmlOrderOpen','OnClose':'XmlOrderClosed'}

def files(source,case):
    if case not in CASES:raise ValueError('case')
    out=packet.baseline(source)
    module=out[packet.MODULE].decode()
    match=re.search(r'Процедура Created\(Cancel, StandardProcessing\).*?КонецПроцедуры',module,re.S)
    if not match:raise ValueError('authored handler anchor')
    changed=packet.replace_once(match.group(), 'Процедура Created(', 'Процедура ChangedCreated(')
    changed=packet.replace_once(changed,'XmlOrderAppend("create")','XmlOrderAppend("create_changed")')
    changed=packet.replace_once(changed,'КонецПроцедуры',' DraftTitle = "XML-order changed";\nКонецПроцедуры')
    module+='\n&НаСервере\n'+changed+'\n'
    old=''' If DraftTitle <> "XML-order witness" Or Amount <> 17 Or Comment <> "scope-check" Then
  Raise "xml order initial effect mismatch";
 EndIf;
 XmlOrderAppend("open_effect");'''
    new=''' If Amount <> 17 Or Comment <> "scope-check" Then
  Raise "xml order initial effect mismatch";
 EndIf;
 If DraftTitle = "XML-order witness" Then
  XmlOrderAppend("open_effect");
 ElsIf DraftTitle = "XML-order changed" Then
  XmlOrderAppend("open_effect_changed");
 Else
  Raise "xml order unexpected title effect";
 EndIf;'''
    module=packet.replace_once(module,old,new);out[packet.MODULE]=module.encode()
    if case=='handler_compatible':out[packet.FORM]=packet.replace_once(out[packet.FORM],b'>Created</Event>',b'>ChangedCreated</Event>')
    return out

def bindings(raw):
    root=ET.fromstring(raw)
    if root.tag!=FORM_NS+'Form':raise ValueError('form root')
    groups=root.findall(FORM_NS+'Events')
    if len(groups)!=1:raise ValueError('events singleton')
    mapping={}
    for e in groups[0]:
        if e.tag!=FORM_NS+'Event' or set(e.attrib)!={'name'} or len(e) or e.get('name') in mapping:raise ValueError('event shape/duplicate')
        name,value=e.get('name'),e.text or ''
        if name not in EVENTS or value not in {*EVENTS.values(),'ChangedCreated'}:raise ValueError('unknown binding')
        mapping[name]=value
    if set(mapping)!=set(EVENTS):raise ValueError('event inventory')
    return mapping

def expected_bindings(case):
    if case not in CASES:raise ValueError('case')
    out=dict(EVENTS)
    if case=='handler_compatible':out['OnCreateAtServer']='ChangedCreated'
    return out

def expected_trace(case):
    if case not in CASES:raise ValueError('case')
    negative=case=='handler_compatible'
    return ['create_changed' if negative else 'create','open_effect_changed' if negative else 'open_effect',
        'items:'+','.join(packet.UI),'closing_blocked','cancel_effect','closing_allowed','closed']

def trace(raw,nonce):
    from native_1c_xml_order_ci_policy import unique
    if raw is None:return dict(state='missing',codes=[])
    if type(raw)!=bytes or len(raw)>4096:return dict(state='invalid',codes=[])
    try:
        r=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique)
        if type(r)!=dict or set(r)!={'nonce','events'} or r['nonce']!=nonce or type(r['events'])!=list or len(r['events'])>12:raise ValueError('trace shape')
        allowed=set(expected_trace('baseline1')+expected_trace('handler_compatible'))
        if any(type(c)!=str or c not in allowed for c in r['events']):raise ValueError('unknown trace')
        return dict(state='observed' if r['events'] else 'empty',codes=r['events'])
    except (ValueError,UnicodeError):return dict(state='invalid',codes=[])
