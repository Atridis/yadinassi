"""Closed schema-backed document preparation; no CONFIG/storage admission."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from linked_card_packet import linked

ROOT=Path(__file__).resolve().parents[1]
MD='{http://v8.1c.ru/8.3/MDClasses}'
BLOCKS=('identity','header','fields','cursor')
STATES=('empty','filled')
SOURCE='f1549f9a53fb12d5d6ceca02d3bc78e5d17e2955'
SCHEMA_SHA='8569cd5d718b4009e09c2fa43a21e0bac6811d78018da0e8ec234b2a38101827'
PROFILE_SHA='20463712c9ba91dccbe4098e103437144947b27e4fd81187020162fea91b36d5'

# Native 41255615774, exact source-owned Document redump (report SHA256
# 388c35d9d6dba1bedff803e480ff499d248f08bd86c13c84ee607e908115070c).
# Identity-independent complete StandardAttributes subtree. This corrects the
# generated INPUT; redump validation still compares the complete semantic tree.
DOCUMENT_STANDARD_ATTRIBUTES = '<StandardAttributes><xr:StandardAttribute name="Posted"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="Ref"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="DeletionMark"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="Date"><xr:LinkByType/><xr:FillChecking>ShowError</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="Number"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute></StandardAttributes>'
DOCUMENT_STANDARD_ATTRIBUTES_SHA256 = 'ec28e4a88df41269c39955d19eefadca34696069851f52190682b393e0fc9d1a'
DOCUMENT_OMITTED_PROPERTIES = frozenset((
    'ObjectBelonging', 'ObjectModule', 'ManagerModule', 'Help', 'AdditionalIndexes'))

def profile(s, catalog_request):
    # Saved linked identities are reused only as input identity containers.
    # Document metadata/Ref TypeId remain independent from record and target IDs.
    linked.validate_request(s,catalog_request)
    return dict(source=SOURCE,status='schema-backed-not-native-applied',
        document_name='D'+s.base.names[0][1:],catalog_name=s.base.names[1],
        document_uuid=s.base.metadata_ids[0],catalog_uuid=s.base.metadata_ids[1],
        posting='Allow',number_type='String',number_length=8,
        number_periodicity='Nonperiodical',attributes=5,
        linked_schema=catalog_request)

def validate_profile(s,request):
    if type(request) is not dict or type(request.get('linked_schema')) is not dict:
        raise ValueError('document-profile')
    # Bound the finite JSON tree before touching the saved schema. This refuses
    # cycles, non-JSON aliases (tuple/list, float/int), and extra key types.
    def finite(value,depth=0):
        if depth>16:return False
        if type(value) is dict:
            return len(value)<=64 and all(type(k) is str and len(k)<=128 and finite(v,depth+1) for k,v in value.items())
        if type(value) is list:return len(value)<=64 and all(finite(v,depth+1) for v in value)
        if type(value) is str:return len(value)<=4096
        return type(value) in (int,bool) or value is None
    if not finite(request):raise ValueError('document-profile')
    expected=profile(s,request['linked_schema'])
    if json.dumps(request,sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False):
        raise ValueError('document-profile')
    return request


def document_xml(s, request):
    validate_profile(s,request)
    schema=Path(__file__).with_name('document_schema.json').read_bytes()
    if hashlib.sha256(schema).hexdigest()!=PROFILE_SHA:raise ValueError('schema-provenance')
    rendered=linked.render_catalog_xml(s,request['linked_schema'])
    source=rendered['Catalogs/'+s.base.names[0]+'.xml'].decode()
    root=ET.fromstring(source);props=root.find(MD+'Catalog/'+MD+'Properties')
    original={n.tag.removeprefix(MD):n for n in props}
    overrides=dict(Name=request['document_name'],Numerator='',
        NumberType='String',NumberLength='8',NumberAllowedLength='Variable',
        NumberPeriodicity='Nonperiodical',CheckUnique='true',Autonumbering='false',
        InputByString='',Posting='Allow',RealTimePosting='Deny',
        RegisterRecordsDeletion='AutoDeleteOff',RegisterRecordsWritingOnPost='WriteSelected',
        SequenceFilling='AutoFillOff',RegisterRecords='',PostInPrivilegedMode='false',
        UnpostInPrivilegedMode='false')
    definition=json.loads(schema)['required_properties']
    # Exact schema ordering, shared catalog properties keep their existing shapes.
    parts=[]
    if hashlib.sha256(DOCUMENT_STANDARD_ATTRIBUTES.encode()).hexdigest()!=DOCUMENT_STANDARD_ATTRIBUTES_SHA256:
        raise ValueError('document-standard-attributes-provenance')
    for name in definition:
        if name in DOCUMENT_OMITTED_PROPERTIES:
            continue
        if name == 'StandardAttributes':
            parts.append(DOCUMENT_STANDARD_ATTRIBUTES)
        elif name in overrides:
            value=overrides[name];parts.append(f'<{name}>{value}</{name}>')
        elif name in original:
            # Shared simple/empty property only; no QName-bearing subtree rewrite.
            node=original[name]
            if len(node) or node.attrib:raise ValueError('shared-complex-property:'+name)
            parts.append(f'<{name}>{node.text or ""}</{name}>')
        else:raise ValueError('unreviewed-document-property:'+name)
    internal=source[source.index('<InternalInfo>'):source.index('</InternalInfo>')+len('</InternalInfo>')]
    internal=internal.replace('Catalog', 'Document').replace(s.base.names[0],request['document_name'])
    children=source[source.index('<ChildObjects>'):source.index('</ChildObjects>')+len('</ChildObjects>')]
    # Native Document attributes omit Catalog-only Use=ForItem; exact five inputs.
    if children.count('<Use>ForItem</Use>') != 5:raise ValueError('document-attribute-use-profile')
    children=children.replace('<Use>ForItem</Use>', '')
    opening=source[:source.index('<Catalog ')]
    xml=opening+f'<Document uuid="{request["document_uuid"]}">'+internal+'<Properties>'+''.join(parts)+'</Properties>'+children+'</Document></MetaDataObject>'
    raw=xml.encode()
    if len(raw)>65536:raise ValueError('document-xml-budget')
    # !todo Second identity apply/redump and full native card/CONFIG/physical
    # capture remain pending; this one native XML result does not admit rows.
    return {'Documents/'+request['document_name']+'.xml':raw,
            'Catalogs/'+s.base.names[1]+'.xml':rendered['Catalogs/'+s.base.names[1]+'.xml']}

def validate_xml(s,request,artifacts):
    expected=document_xml(s,request)
    if type(artifacts) is not dict or set(artifacts)!=set(expected):raise ValueError('document-fragments')
    for name in expected:
        if linked._xml_signature(expected[name])!=linked._xml_signature(artifacts[name]):
            raise ValueError('document-xml-profile')
    return True

def extend_rights(s,request,baseline):
    """Exact reviewed baseline plus one catalog and one inert document object."""
    validate_profile(s,request)
    # Existing helper validates the entire baseline, including Configuration
    # and new-object/attribute flags. Its generated additions are discarded.
    linked.setup_adapter.add_rights(baseline,s.base)
    anchor=b'<object><name>Catalog.NativeOracleItems</name>'
    start=baseline.index(anchor);end=baseline.index(b'</object>',start)+len(b'</object>')
    category=baseline[start:end].replace(b'NativeOracleItems',request['catalog_name'].encode())
    document=('<object><name>Document.'+request['document_name']+'</name>'+
        ''.join('<right><name>'+right+'</name><value>true</value></right>'
            for right in ('Read','Insert','Update','Posting'))+'</object>').encode()
    return baseline.replace(b'</Rights>',category+document+b'</Rights>')

def validate_rights(s,request,baseline,actual):
    expected=extend_rights(s,request,baseline)
    if type(actual) is not bytes or len(actual)>65536 or b'<!' in actual:
        raise ValueError('document-rights-bound')
    def signature(n):
        return n.tag,tuple(sorted(n.attrib.items())),(n.text or '').strip(),(n.tail or '').strip(),tuple(sorted(signature(c) for c in n))
    if signature(ET.fromstring(actual))!=signature(ET.fromstring(expected)):
        raise ValueError('document-rights-profile')
    return True


def cases(s,p,block):
    validate_profile(s,p)
    d='Documents.'+p['document_name'];c='Catalogs.'+p['catalog_name']
    u,absent=s.base.record_ids;a=s.attrs
    ref=f'{d}.GetRef(New UUID("{u}"))'
    result=[('control.document',d+'.EmptyRef().Metadata().Name'),('control.catalog',c+'.EmptyRef().Metadata().Name')]
    if block=='identity':
        result += [('global.type','String(TypeOf(Documents))'),('manager.type',f'String(TypeOf({d}))'),
            ('ref.type',f'String(TypeOf({ref}))'),('ref.metadata',ref+'.Metadata().FullName()'),
            ('uuid',f'String({ref}.UUID())'),('cross.kind',f'{ref} = {c}.GetRef(New UUID("{u}"))'),
            ('ref.type.identity',f'TypeOf({ref}) = Type("DocumentRef.{p["document_name"]}")'),
            ('empty',d+'.EmptyRef().IsEmpty()'),('missing',d+'.FindByNumber("MISSING").IsEmpty()'),
            ('empty.number',d+'.FindByNumber("") = Undefined'),('ref.ref',ref+'.Ref = '+ref)]
        for role in linked.ROLES:result.append((role+'.type',f'String(TypeOf({ref}.{a[role]}))'))
        result += [('fresh.omitted.uuid','String(F.UUID())'),('fresh.undefined.uuid','String(G.UUID())'),
            ('fresh.distinct','F <> G'),('fresh.filled','ValueIsFilled(F) And ValueIsFilled(G) And Not F.IsEmpty() And Not G.IsEmpty()'),
            ('empty.uuid',f'String({d}.EmptyRef().UUID())'),
            ('empty.type.filled',f'TypeOf({d}.EmptyRef()) = TypeOf({ref}) And Not ValueIsFilled({d}.EmptyRef())')]
    elif block=='header':
        for number in ('30','10','20'):
            r=f'{d}.FindByNumber("{number}")'
            result += [(number+'.number',r+'.Number'),(number+'.date',f'XMLString({r}.Date)'),
                (number+'.posted',r+'.Posted'),(number+'.deleted',r+'.DeletionMark'),
                (number+'.uuid',f'String({r}.UUID())')]
        result += [('present',f'{d}.FindByNumber("30") = {ref}'),
            ('dated.lookup',f'{d}.FindByNumber("30", Date(2024,2,29)) = {ref}')]
        absent_ref=f'{d}.GetRef(New UUID("{absent}"))'
        result += [('absent.number',absent_ref+'.Number'),('absent.date',f'XMLString({absent_ref}.Date)'),
            ('absent.posted',absent_ref+'.Posted')]

    elif block=='fields':
        for number in ('30','10','20'):
            r=f'{d}.FindByNumber("{number}")'
            result += [(number+'.text',r+'.'+a['text']),
                (number+'.number',f'XMLString({r}.{a["number"]})'),
                (number+'.boolean',r+'.'+a['boolean']),
                (number+'.datetime',f'XMLString({r}.{a["datetime"]})'),
                (number+'.target.uuid',f'String({r}.{a["reference"]}.UUID())'),
                (number+'.target.description',r+'.'+a['reference']+'.Description')]
        result += [('target.type',f'TypeOf({ref}.{a["reference"]}) = Type("CatalogRef.{p["catalog_name"]}")')]
    elif block=='cursor':
        result += [('selection.type','String(TypeOf(S))'),('before.number','S.Number')]
        for i in range(3):
            result += [(f'{i}.next','S.Next()'),(f'{i}.number','S.Number'),
                (f'{i}.date','XMLString(S.Date)'),
                (f'{i}.target',f'S.{a["reference"]}.Description')]
        result += [('exhaust','S.Next()'),('retained','S.Number'),('after.exhaust','S.Next()'),
            ('range.first','T.Next()'),('range.number','T.Number'),('range.exhaust','T.Next()'),('empty.range','E.Next()')]
    else:raise ValueError('block')
    while len(result)<24:result.append(('control.pad'+str(len(result)),d+'.EmptyRef().IsEmpty()'))
    if len(result)!=24:raise ValueError('case-count')
    return result

def render_block(s,p,block):
    validate_profile(s,p)
    if type(block) is not str or block not in BLOCKS:raise ValueError('block')
    text=linked.observer()
    if block=='identity':
        manager='Documents.'+p['document_name']
        text+=f'F = Undefined; G = Undefined; Try F = {manager}.GetRef(); Except EndTry;\n'
        text+=f'Try G = {manager}.GetRef(Undefined); Except EndTry;\n'
    if block=='cursor':
        manager='Documents.'+p['document_name']
        text+=f'S = Undefined; Try S = {manager}.Select(); Except EndTry;\n'
        text+=f'T = Undefined; Try T = {manager}.Select(Date(2024,2,29,12,34,56),Date(2024,2,29,12,34,56)); Except EndTry;\n'
        text+=f'E = Undefined; Try E = {manager}.Select(Date(1999,1,1),Date(1999,1,2)); Except EndTry;\n'
    for i,(key,expression) in enumerate(cases(s,p,block),1):
        text+=linked.emit(i,expression)+'// '+key+'\n'
    if len(text.encode())>8192:raise ValueError('block-budget')
    return text

def render_setup(s,p,state):
    validate_profile(s,p)
    if type(state) is not str or state not in STATES:raise ValueError('state')
    d='Documents.'+p['document_name'];c='Catalogs.'+p['catalog_name'];a=s.attrs;u,absent=s.base.record_ids
    # Source-controlled object identifiers only. No user-supplied Query text.
    counter='''Function DCCount(TableName)
Q = New Query; Q.Text = "SELECT COUNT(*) AS N FROM " + TableName;
W = Q.Execute().Select(); W.Next(); Return W.N;
EndFunction
'''
    obs=linked.observer();split=obs.index('Сообщить("CR-C1:')
    text=obs[:split]+counter+obs[split:]
    tables=('Document.'+p['document_name'],'Catalog.'+p['catalog_name'])
    for table in tables:text+=f'If DCCount("{table}") <> 0 Then Raise "setup-not-empty"; EndIf;\n'
    if state=='filled':
        text+=f'C = {c}.CreateItem(); C.SetNewObjectRef({c}.GetRef(New UUID("{u}"))); C.Code = "10"; C.Description = "Category"; C.Write();\n'
        for ident,number,date,label,price,flag,target in (
            (u,'30','Date(2024,2,29,12,34,56)','third','12.50','True',f'{c}.GetRef(New UUID("{u}"))'),
            (s.product_rows[0],'10','Date(2024,3,1,1,2,3)','','0','False',c+'.EmptyRef()'),
            (s.product_rows[1],'20','Date(2001,1,1,0,0,1)','first','-7.25','True',f'{c}.GetRef(New UUID("{absent}"))')):
            text+=f'P = {d}.CreateDocument(); P.SetNewObjectRef({d}.GetRef(New UUID("{ident}"))); P.Number = "{number}"; P.Date = {date};\n'
            text+=f'P.{a["text"]} = "{label}"; P.{a["number"]} = {price}; P.{a["boolean"]} = {flag}; P.{a["datetime"]} = {date}; P.{a["reference"]} = {target};\n'
            text+='P.Write(DocumentWriteMode.Posting, DocumentPostingMode.Regular);\n' if number=='30' else 'P.Write(DocumentWriteMode.Write);\n'
    # Setup-only independent persisted Query witnesses; no runtime Query promise.
    text+=f'Q = New Query; Q.Text = "SELECT Number, Date, Posted, {a["reference"]} AS Target FROM {tables[0]} ORDER BY Date"; W = Q.Execute().Select();\n'
    witness=[d+'.EmptyRef().Metadata().Name',c+'.EmptyRef().Metadata().Name']+[f'DCCount("{t}")' for t in tables]
    for date in ('Date(2001,1,1,0,0,1)','Date(2024,2,29,12,34,56)','Date(2024,3,1,1,2,3)'):
        witness+=['W.Next()','W.Number','W.Date = '+date,'W.Posted','String(W.Target.UUID())']
    witness+=['W.Next()']
    while len(witness)<24:witness.append(d+'.EmptyRef().IsEmpty()')
    for i,expr in enumerate(witness,1):text+=linked.emit(i,expr)
    if len(text.encode())>8192:raise ValueError('setup-budget')
    return text,witness

def require_capture(raw,s,p):
    validate_profile(s,p)
    rows=linked.scalar_wire.validate_output(raw)
    for row,name in zip(rows,(p['document_name'],p['catalog_name'])):
        if row!=dict(id=row['id'],status='ok',kind='string',value=tuple(map(ord,name))):
            raise ValueError('document-availability-control')
    if any(r['status']=='observer-error' for r in rows):raise ValueError('document-observer-error')
    return rows

def require_setup_evidence(raw,s,p,state):
    validate_profile(s,p)
    if type(state) is not str or state not in STATES:raise ValueError('state')
    rows=require_capture(raw,s,p)
    u,absent=s.base.record_ids
    values=[p['document_name'],p['catalog_name'],3 if state=='filled' else 0,1 if state=='filled' else 0]
    if state=='filled':
        for number,target in (('20',absent),('30',u),('10',str(linked.uuid.UUID(int=0)))):
            values += [True,number,True,number=='30',target]
        values += [False]+[True]*4
    # In empty state, unpositioned Query getters are preserved but not assumed.
    expected=dict(enumerate(values,1))
    if state=='empty':
        expected.update({i:False for i in (5,10,15,20)})
        expected.update({i:True for i in range(21,25)})
    for i,v in expected.items():
        kind='boolean' if type(v) is bool else 'number' if type(v) is int else 'string'
        value=tuple(map(ord,v)) if type(v) is str else v
        if rows[i-1]!=dict(id=i,status='ok',kind=kind,value=value):
            raise ValueError('document-setup-witness')
    return rows


def generate(destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('destination-exists')
    destination.mkdir(parents=True)
    for repeat in (1,2):
        s=linked.fresh(reverse=repeat==2);r=linked.schema_request(s);p=profile(s,r)
        root=destination/f'repeat-{repeat}';root.mkdir()
        for name,raw in document_xml(s,p).items():
            f=root/name;f.parent.mkdir(exist_ok=True);f.write_bytes(raw)
        for state in STATES:(root/f'setup-{state}.bsl').write_text(render_setup(s,p,state)[0],encoding='utf-8')
        for block in BLOCKS:(root/f'{block}.bsl').write_text(render_block(s,p,block),encoding='utf-8')
        manifest=dict(profile=p,names=s.base.names,metadata_ids=s.base.metadata_ids,record_ids=s.base.record_ids,
            product_rows=s.product_rows,attribute_names=s.attribute_names,attribute_ids=s.attribute_ids,order=s.order,
            cases={b:cases(s,p,b) for b in BLOCKS})
        manifest['files']={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
