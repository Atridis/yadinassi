"""Closed preparation adapter for review; no subprocess/native execution API.

This is deliberately separate from historical OnOpen-only client_wiring and
all-client helper injection. The future runner must use existing owned fixture,
process/session-bus/timeout/cleanup guards, never infer a new execution permission.
"""
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from . import ROOT, SOURCE_SHA256, MAX_SOURCE, MAX_OUTPUT, source, parse_records, require_available

SCHEMA = 'native-managed-form-programmatic-v1'
MAX_MARKER = 8192
FORM_SHA256 = '7b05662c5ce6bdee78893db6f1456054ceedcc3f43082c8a58367191211a5ebc'

# Only reviewed private request fields supply paths. The runner must create the
# request exclusively under its fresh owned root and pass that exact path in /C.
# No paths/nonce/error descriptions from this private marker enter public goldens.
_WRAPPER = '''
&AtClient
Procedure FormOpen(Cancel)
 Try
  Reader=New JSONReader; Reader.OpenFile(ПараметрЗапуска);
  Request=ReadJSON(Reader); Reader.Close();
  FormMarker(Request.entered,Request.nonce,"entered","");
  Try
   FormObserve(Cancel);
   FormMarker(Request.completed,Request.nonce,"completed",ThisObject.FLog);
  Except
   FormMarker(Request.completed,Request.nonce,"error","");
  EndTry;
 Except
  // Missing/partial markers fail closed; never export error text.
 EndTry;
 ЗавершитьРаботуСистемы(Ложь);
EndProcedure
&AtClient
Procedure FormMarker(Path,Nonce,Phase,Records)
 Writer=New JSONWriter;
 Settings=New JSONWriterSettings(ПереносСтрокJSON.Нет," ",True);
 Writer.OpenFile(Path,,,Settings);
 Value=New Structure("schema,nonce,phase,source_sha256,form_sha256,records",
 "SCHEMA_VALUE",Nonce,Phase,"SOURCE_VALUE","FORM_VALUE",Records);
 WriteJSON(Writer,Value); Writer.Close();
EndProcedure
'''


def form_xml():
    raw=(ROOT/'form.xml').read_bytes()
    if len(raw)>MAX_SOURCE or hashlib.sha256(raw).hexdigest()!=FORM_SHA256:
        raise ValueError('form XML identity mismatch')
    return raw


def module():
    value=source()
    declaration='&AtClient\nProcedure FormOpen(Cancel)'
    message=' Message(ThisObject.FLog);'
    if value.count(declaration)!=1 or value.count(message)!=1:
        raise ValueError('form source adapter mismatch')
    value=value.replace(declaration,'&AtClient\nProcedure FormObserve(Cancel)',1).replace(message,' // Captured by the fixed owned marker wrapper.',1)
    wrapper=_WRAPPER.replace('SCHEMA_VALUE',SCHEMA).replace('SOURCE_VALUE',SOURCE_SHA256).replace('FORM_VALUE',FORM_SHA256)
    result=(value+wrapper).encode('utf-8')
    if len(result)>MAX_SOURCE:raise ValueError('form module budget')
    return result


def _xml(raw):
    if type(raw) is not bytes or len(raw)>MAX_SOURCE:
        raise ValueError('invalid managed form XML')
    try:decoded=raw.decode('utf-8-sig')
    except UnicodeError:raise ValueError('invalid managed form XML encoding') from None
    if '\x00' in decoded or '<!' in decoded:raise ValueError('invalid managed form XML')
    declaration=re.match(r'^<\?xml\s+[^?]*\?>',decoded)
    if declaration:
        encoding=re.search(r'encoding\s*=\s*[\"\']([^\"\']+)',declaration.group())
        if encoding and encoding.group(1).lower()!='utf-8':raise ValueError('invalid managed form XML encoding')
    rest=decoded[declaration.end():] if declaration else decoded
    if '<?' in rest:raise ValueError('invalid managed form XML instruction')
    try:return ET.fromstring(decoded)
    except ET.ParseError:raise ValueError('invalid managed form XML') from None


def _canonical_xml(raw):
    root = _xml(raw)
    rows = []
    stack = [(root,0)]
    while stack:
        node,depth = stack.pop()
        if depth>16 or len(rows)>=128:raise ValueError('invalid form XML structure budget')
        rows.append((depth,node.tag,tuple(sorted(node.attrib.items())),
                     (node.text or '').strip(),(node.tail or '').strip(),len(node)))
        stack.extend((child,depth+1) for child in reversed(list(node)))
    bindings=[]; started=False
    for event,value in ET.iterparse(io.BytesIO(raw),events=('start-ns','start')):
        if event=='start':started=True
        else:
            if started:raise ValueError('nested form namespace declarations unsupported')
            bindings.append(value)
    return tuple(sorted(bindings)),tuple(rows)


def validate_redump(files):
    """Caller supplies secure bounded reads, not arbitrary path following.

    Source module equality permits only the historical BOM/newline normalization.
    Module source is never repaired or injected after this check.
    """
    expected={'Launcher.xml','Launcher/Forms/Main.xml','Launcher/Forms/Main/Ext/Form.xml',
              'Launcher/Forms/Main/Ext/Form/Module.bsl','Launcher/Ext/ObjectModule.bsl'}
    if type(files) is not dict or set(files)!=expected:raise ValueError('invalid form redump files')
    for raw in files.values():
        if type(raw) is not bytes or len(raw)>MAX_MARKER:raise ValueError('invalid form redump budget')
    md='{http://v8.1c.ru/8.3/MDClasses}'
    roots={path:_xml(files[path]) for path in ('Launcher.xml','Launcher/Forms/Main.xml')}
    for root in roots.values():
        if root.tag!=md+'MetaDataObject' or len(root)!=1:
            raise ValueError('invalid managed metadata namespace')
    def one(path,parts,value):
        matches=roots[path].findall('/'.join(md+part for part in parts))
        if len(matches)!=1 or matches[0].text!=value:
            raise ValueError('invalid form metadata binding')
    one('Launcher.xml',('ExternalDataProcessor','Properties','Name'),'Launcher')
    one('Launcher.xml',('ExternalDataProcessor','Properties','DefaultForm'),'ExternalDataProcessor.Launcher.Form.Main')
    one('Launcher.xml',('ExternalDataProcessor','ChildObjects','Form'),'Main')
    children=roots['Launcher.xml'].findall(md+'ExternalDataProcessor/'+md+'ChildObjects')
    if len(children)!=1 or len(children[0])!=1:raise ValueError('invalid form registration')
    one('Launcher/Forms/Main.xml',('Form','Properties','Name'),'Main')
    one('Launcher/Forms/Main.xml',('Form','Properties','FormType'),'Managed')
    if _canonical_xml(files['Launcher/Forms/Main/Ext/Form.xml'])!=_canonical_xml(form_xml()):
        raise ValueError('form XML structure mismatch')
    form_root=_xml(files['Launcher/Forms/Main/Ext/Form.xml'])
    ns='{http://v8.1c.ru/8.3/xcf/logform}'
    events=form_root.findall(ns+'Events/'+ns+'Event')
    expected_events=[('OnCreateAtServer','FormCreate'),('OnOpen','FormOpen'),('BeforeClose','FormBeforeClose')]
    if [(n.attrib.get('name'),n.text) for n in events]!=expected_events or any(set(n.attrib)!={'name'} for n in events):
        raise ValueError('invalid form event wiring')
    # No third-party object-module behavior accompanies the owned form module.
    object_source=files['Launcher/Ext/ObjectModule.bsl'].decode('utf-8-sig')
    if any(line.strip() and not line.lstrip().startswith('//') for line in object_source.splitlines()):
        raise ValueError('unexpected object module')
    actual=files['Launcher/Forms/Main/Ext/Form/Module.bsl'].decode('utf-8-sig').replace('\r\n','\n')
    if actual.encode('utf-8')!=module():raise ValueError('form module mismatch')
    return hashlib.sha256(module()).hexdigest()


def marker(raw, nonce, phase):
    if (type(raw) is not bytes or len(raw)>MAX_MARKER or type(nonce) is not str
            or re.fullmatch(r'[0-9a-f]{32}',nonce) is None or phase not in ('entered','completed')):
        raise ValueError('invalid form marker')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate marker key')
            result[key]=value
        return result
    try:
        value=json.loads(raw,object_pairs_hook=unique)
    except (ValueError,UnicodeError,RecursionError):raise ValueError('invalid form marker') from None
    keys={'schema','nonce','phase','source_sha256','form_sha256','records'}
    if (type(value) is not dict or set(value)!=keys or value['schema']!=SCHEMA
            or value['nonce']!=nonce or value['phase']!=phase
            or value['source_sha256']!=SOURCE_SHA256 or value['form_sha256']!=FORM_SHA256
            or type(value['records']) is not str):raise ValueError('invalid form marker binding')
    if phase=='entered':
        if value['records']!='':raise ValueError('invalid entered form marker')
        return ()
    try:raw=value['records'].encode('ascii')
    except UnicodeError:raise ValueError('invalid form marker records') from None
    values=require_available(parse_records(raw))
    # The actual platform-dispatched create/open order is distinct from direct
    # field/command/BeforeClose calls. This is required but not sufficient proof:
    # the runner must also verify exact re-dump/module/launch provenance.
    if values[23:25]!=('server-create','server-create:client-open'):
        raise ValueError('invalid form lifecycle witness')
    return values
