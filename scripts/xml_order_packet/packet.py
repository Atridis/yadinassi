"""Closed authored instrumentation and single-axis mutations; no source writes."""
import hashlib, json
from pathlib import Path
from .mutations import attributes, rearrange, projection
ROOT=Path(__file__).resolve().parent
FORM='CommonForms/DraftDetails/Ext/Form.xml'
META='CommonForms/DraftDetails.xml'
MODULE='CommonForms/DraftDetails/Ext/Form/Module.bsl'
CASES=('baseline','attributes','properties','events','handler_changed','duplicate_property','duplicate_event','ui_childitems')
POSITIVE=CASES[:4]
UI=('DraftTitleField','AmountField','CommentField','KeepOpenField','AcceptButton','CancelButton')

def replace_once(raw,old,new):
    if raw.count(old)!=1:raise ValueError('instrumentation anchor')
    return raw.replace(old,new,1)

def baseline(files):
    result=dict(files)
    result.pop('InventoryApplication.xml')
    result['Ext/ManagedApplicationModule.bsl']=(ROOT/'startup.bsl').read_bytes()
    result[FORM]=replace_once(result[FORM],b'</Events>',b'<Event name="OnOpen">XmlOrderOpen</Event><Event name="OnClose">XmlOrderClosed</Event></Events>')
    module=result[MODULE].decode('utf-8-sig')
    anchor='Процедура Created(Cancel, StandardProcessing)'
    module=replace_once(module,anchor,anchor+'\n A = New Array; A.Add(New FormAttribute("XmlOrderStage", New TypeDescription("Number")));\n ChangeAttributes(A); ThisObject.XmlOrderStage = 0; XmlOrderAppend("create");')
    # Observe after the original handler has assigned Cancel, retaining the original code.
    anchor='КонецЕсли;\nКонецПроцедуры\n'
    position=module.index('Процедура Closing(')
    module=module[:position]+replace_once(module[position:],anchor,'КонецЕсли;\n XmlOrderAppend(?(Cancel, "closing_blocked", "closing_allowed"));\nКонецПроцедуры\n')
    result[MODULE]=module.encode()+b'\n'+(ROOT/'observer.bsl').read_bytes()
    return result

def case_files(files,case):
    if case not in CASES:raise ValueError('case')
    out=baseline(files)
    if case=='attributes':out[FORM]=attributes(out[FORM])
    if case=='properties':out[META]=rearrange(out[META],'Properties')
    if case=='events':out[FORM]=rearrange(out[FORM],'Events')
    if case=='handler_changed':out[FORM]=replace_once(out[FORM],b'>Created</Event>',b'>Closing</Event>')
    if case=='duplicate_property':out[META]=rearrange(out[META],'Properties',True)
    if case=='duplicate_event':out[FORM]=rearrange(out[FORM],'Events',True)
    if case=='ui_childitems':out[FORM]=rearrange(out[FORM],'ChildItems')
    return out

def digest_files(files):
    return hashlib.sha256(json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in sorted(files.items())},sort_keys=True).encode()).hexdigest()

def redump_digest(files):
    result={}
    for name,raw in sorted(files.items()):
        if name=='ConfigDumpInfo.xml':continue
        if name.endswith('.bsl'):result[name]=raw.decode('utf-8-sig').replace('\r\n','\n')
        elif name.endswith('.xml'):result[name]=projection(raw,allow=name in (FORM,META))
        else:raise ValueError('unknown redump file')
    return hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def witness(raw,nonce,case):
    from native_1c_xml_order_ci_policy import unique
    if len(raw)>4096:raise ValueError('trace limit')
    t=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique)
    ui=list(UI)
    if case=='ui_childitems':ui[:2]=reversed(ui[:2])
    expected=['create','open_effect','items:'+','.join(ui),'closing_blocked','cancel_effect','closing_allowed','closed']
    if type(t)!=dict or set(t)!={'nonce','events'} or t['nonce']!=nonce or t['events']!=expected:
        raise ValueError('trace witness')
    return 'changed' if case=='ui_childitems' else 'baseline'
