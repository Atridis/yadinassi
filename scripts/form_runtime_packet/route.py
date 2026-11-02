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

# Failed-only structural vocabulary: reviewed public source names/literals.
# Zero means redacted, never a run-learned token. No arbitrary strings escape.
DIAGNOSTIC_TAGS=(
    '{http://v8.1c.ru/8.3/xcf/logform}Form',
    '{http://v8.1c.ru/8.3/xcf/logform}AutoCommandBar',
    '{http://v8.1c.ru/8.3/xcf/logform}Events',
    '{http://v8.1c.ru/8.3/xcf/logform}Event',
    '{http://v8.1c.ru/8.3/xcf/logform}Attributes',
    '{http://v8.1c.ru/8.3/xcf/logform}Attribute',
    '{http://v8.1c.ru/8.3/xcf/logform}Type',
    '{http://v8.1c.ru/8.1/data/core}Type',
    '{http://v8.1c.ru/8.3/xcf/logform}MainAttribute')
DIAGNOSTIC_ATTRIBUTES=('version','name','id')
# 2.20 is an existing public owned XML version in periodic_packet.py, not run-derived.
DIAGNOSTIC_LITERALS=('', '2.4','FormCommandBar','-1','OnCreateAtServer','FormCreate',
    'OnOpen','FormOpen','BeforeClose','FormBeforeClose','Object','1',
    'cfg:ExternalDataProcessorObject.Launcher','true','false','2.20')
DIAGNOSTIC_PREFIXES=('', 'cfg','v8')
DIAGNOSTIC_URIS=('http://v8.1c.ru/8.3/xcf/logform',
    'http://v8.1c.ru/8.1/data/enterprise/current-config','http://v8.1c.ru/8.1/data/core')
DIAGNOSTIC_PHASES=('inventory','metadata','form_xml','module','other')
DIAGNOSTIC_FILES=('Launcher.xml','Launcher/Forms/Main.xml','Launcher/Forms/Main/Ext/Form.xml',
    'Launcher/Forms/Main/Ext/Form/Module.bsl','Launcher/Ext/ObjectModule.bsl')


def redump_projection(files,subphase,*,extra_count=0):
    """Bounded numeric projection only; cannot admit or repair a failed dump."""
    def token(value,values):
        try:return values.index(value)+1
        except ValueError:return 0
    result={'schema':1,'subphase':subphase if subphase in DIAGNOSTIC_PHASES else 'other',
            'presence':sum(1<<i for i,name in enumerate(DIAGNOSTIC_FILES) if name in files),
            'extra_count':min(32,max(0,extra_count)),'xml_status':'absent','row_count':0,
            'rows':[],'rows_truncated':False,'namespaces':[],'form_sha256':None}
    raw=files.get(DIAGNOSTIC_FILES[2])
    if type(raw) is not bytes:return result
    if len(raw)>MAX_SOURCE:result['xml_status']='budget';return result
    result['form_sha256']=hashlib.sha256(raw).hexdigest()
    try:
        root=_xml(raw)  # strict UTF8/no DTD/PI guard precedes all parsing
        rows=[];stack=[(root,0)];total=0
        while stack:
            node,depth=stack.pop();total+=1
            if total>128 or depth>16 or len(node.attrib)>8 or len(node)>128:raise ValueError('budget')
            if len(rows)<32:
                tag=token(node.tag,DIAGNOSTIC_TAGS)
                attrs=[]
                for k,v in sorted(node.attrib.items()):
                    key=token(k,DIAGNOSTIC_ATTRIBUTES) if tag else 0
                    attrs.append([key,token(v,DIAGNOSTIC_LITERALS) if key else 0])
                rows.append([depth,tag,attrs,
                    token((node.text or '').strip(),DIAGNOSTIC_LITERALS) if tag else 0,
                    token((node.tail or '').strip(),DIAGNOSTIC_LITERALS) if tag else 0,len(node)])
            stack.extend((child,depth+1) for child in reversed(list(node)))
        bindings=[]
        for event,value in ET.iterparse(io.BytesIO(raw),events=('start-ns',)):
            if len(bindings)>=32:raise ValueError('budget')
            prefix,uri=value;prefix_id=token(prefix,DIAGNOSTIC_PREFIXES)
            bindings.append([prefix_id,token(uri,DIAGNOSTIC_URIS) if prefix_id else 0])
        result.update(xml_status='parsed',row_count=total,rows=rows,rows_truncated=total>32,namespaces=bindings)
        if len(json.dumps(result,separators=(',',':')).encode())>4096:raise ValueError('budget')
    except (ValueError,ET.ParseError,UnicodeError):
        result.update(xml_status='rejected',row_count=0,rows=[],rows_truncated=False,namespaces=[])
    return result


def validate_redump_projection(value):
    keys={'schema','subphase','presence','extra_count','xml_status','row_count','rows','rows_truncated','namespaces','form_sha256'}
    def integer(v,limit):return type(v) is int and 0<=v<=limit
    if (type(value) is not dict or set(value)!=keys or type(value['schema']) is not int or value['schema']!=1
            or type(value['subphase']) is not str or value['subphase'] not in DIAGNOSTIC_PHASES
            or not integer(value['presence'],31) or not integer(value['extra_count'],32)
            or type(value['xml_status']) is not str or value['xml_status'] not in ('absent','budget','parsed','rejected')
            or not integer(value['row_count'],128) or type(value['rows_truncated']) is not bool
            or type(value['rows']) is not list or len(value['rows'])>32
            or type(value['namespaces']) is not list or len(value['namespaces'])>32
            or value['form_sha256'] is not None and (type(value['form_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',value['form_sha256']) is None)):
        raise ValueError('invalid redump projection')
    for row in value['rows']:
        if (type(row) is not list or len(row)!=6 or not integer(row[0],16)
                or not integer(row[1],len(DIAGNOSTIC_TAGS)) or type(row[2]) is not list or len(row[2])>8
                or not integer(row[3],len(DIAGNOSTIC_LITERALS)) or not integer(row[4],len(DIAGNOSTIC_LITERALS))
                or not integer(row[5],128)):
            raise ValueError('invalid redump projection row')
        for pair in row[2]:
            if type(pair) is not list or len(pair)!=2 or not integer(pair[0],len(DIAGNOSTIC_ATTRIBUTES)) or not integer(pair[1],len(DIAGNOSTIC_LITERALS)):
                raise ValueError('invalid redump projection attribute')
    for pair in value['namespaces']:
        if type(pair) is not list or len(pair)!=2 or not integer(pair[0],len(DIAGNOSTIC_PREFIXES)) or not integer(pair[1],len(DIAGNOSTIC_URIS)):
            raise ValueError('invalid redump projection namespace')
    if value['xml_status']=='parsed':
        if len(value['rows'])!=min(32,value['row_count']) or value['rows_truncated']!=(value['row_count']>32):raise ValueError('invalid redump projection count')
    elif value['rows'] or value['namespaces'] or value['row_count'] or value['rows_truncated']:
        raise ValueError('invalid redump projection state')
    if len(json.dumps(value,separators=(',',':')).encode())>4096:raise ValueError('redump projection budget')
    return value
