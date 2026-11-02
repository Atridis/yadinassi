"""Prospective Second-periodic owned InformationRegister INPUT packet; no storage admission."""
from pathlib import Path
import json,hashlib,re,uuid,xml.etree.ElementTree as ET
from decimal import Decimal
from linked_card_packet import linked
BASE='12083d565752333cb641bd05c5d4740bfd45bd7f'
FIELDS=('Product','Variant','Price','Available','ValidUntil','Note')
FAMILIES=('Manager','Selection','List','RecordSet','RecordManager','RecordKey','Record')
BLOCKS=('get','slices','cursor','edges')
STATES=('empty','filled')
SCHEMA=Path(__file__).with_name('schema_facts.json')
SCHEMA_SHA='9638f2218c77f854f3dc051f860bdeea7f9dd6dd95c7aa9d5549af8b3f947c2c'
ID_KEYS={*FIELDS,'product2',*(f'{f}.{k}' for f in FAMILIES for k in ('TypeId','ValueId'))}

# Exact identity-free Designer output observed in owned run 41310112812.
# Report SHA256 50fe46b8311a365ff46ee1067334654075cfa8d798fb12971cdd70293848fb94.
# These are generated INPUT literals, not a redump normalizer or storage proof.
NATIVE_FAMILIES=('Record','Manager','Selection','List','RecordSet','RecordKey','RecordManager')
REGISTER_PROPERTIES='<Name>@@REGISTER@@</Name><Synonym/><Comment/><UseStandardCommands>false</UseStandardCommands><EditType>InList</EditType><DefaultRecordForm/><DefaultListForm/><AuxiliaryRecordForm/><AuxiliaryListForm/><StandardAttributes><xr:StandardAttribute name="Active"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="LineNumber"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="Recorder"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute><xr:StandardAttribute name="Period"><xr:LinkByType/><xr:FillChecking>ShowError</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute></StandardAttributes><InformationRegisterPeriodicity>Second</InformationRegisterPeriodicity><WriteMode>Independent</WriteMode><MainFilterOnPeriod>false</MainFilterOnPeriod><IncludeHelpInContents>false</IncludeHelpInContents><DataLockControlMode>Automatic</DataLockControlMode><FullTextSearch>DontUse</FullTextSearch><EnableTotalsSliceFirst>false</EnableTotalsSliceFirst><EnableTotalsSliceLast>false</EnableTotalsSliceLast><RecordPresentation/><ExtendedRecordPresentation/><ListPresentation/><ExtendedListPresentation/><Explanation/><DataHistory>DontUse</DataHistory><UpdateDataHistoryImmediatelyAfterWrite>false</UpdateDataHistoryImmediatelyAfterWrite><ExecuteAfterWriteDataHistoryVersionProcessing>false</ExecuteAfterWriteDataHistoryVersionProcessing>'
RESOURCE_DEFAULTS='<PasswordMode>false</PasswordMode><Format/><EditFormat/><ToolTip/><MarkNegatives>false</MarkNegatives><Mask/><MultiLine>false</MultiLine><ExtendedEdit>false</ExtendedEdit><MinValue xsi:nil="true"/><MaxValue xsi:nil="true"/><FillFromFillingValue>false</FillFromFillingValue><FillValue xsi:nil="true"/><FillChecking>DontCheck</FillChecking><ChoiceFoldersAndItems>Items</ChoiceFoldersAndItems><ChoiceParameterLinks/><ChoiceParameters/><QuickChoice>Auto</QuickChoice><CreateOnInput>Auto</CreateOnInput><ChoiceForm/><LinkByType/><ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput><Indexing>DontIndex</Indexing><FullTextSearch>Use</FullTextSearch><DataHistory>Use</DataHistory>'
ATTRIBUTE_DEFAULTS='<PasswordMode>false</PasswordMode><Format/><EditFormat/><ToolTip/><MarkNegatives>false</MarkNegatives><Mask/><MultiLine>false</MultiLine><ExtendedEdit>false</ExtendedEdit><MinValue xsi:nil="true"/><MaxValue xsi:nil="true"/><FillFromFillingValue>false</FillFromFillingValue><FillValue xsi:type="xs:string"/><FillChecking>DontCheck</FillChecking><ChoiceFoldersAndItems>Items</ChoiceFoldersAndItems><ChoiceParameterLinks/><ChoiceParameters/><QuickChoice>Auto</QuickChoice><CreateOnInput>Auto</CreateOnInput><ChoiceForm/><LinkByType/><ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput><Indexing>DontIndex</Indexing><FullTextSearch>Use</FullTextSearch><DataHistory>Use</DataHistory>'
DIMENSION_DEFAULTS='<PasswordMode>false</PasswordMode><Format/><EditFormat/><ToolTip/><MarkNegatives>false</MarkNegatives><Mask/><MultiLine>false</MultiLine><ExtendedEdit>false</ExtendedEdit><MinValue xsi:nil="true"/><MaxValue xsi:nil="true"/><FillFromFillingValue>false</FillFromFillingValue><FillValue xsi:nil="true"/><FillChecking>DontCheck</FillChecking><ChoiceFoldersAndItems>Items</ChoiceFoldersAndItems><ChoiceParameterLinks/><ChoiceParameters/><QuickChoice>Auto</QuickChoice><CreateOnInput>Auto</CreateOnInput><ChoiceForm/><LinkByType/><ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput><Master>false</Master><MainFilter>false</MainFilter><DenyIncompleteValues>false</DenyIncompleteValues><Indexing>DontIndex</Indexing><FullTextSearch>Use</FullTextSearch><DataHistory>Use</DataHistory><TypeReductionMode>TransformValues</TypeReductionMode>'

def fresh(reverse=False):
    s=linked.fresh(reverse)
    return s,dict(register='I'+s.base.names[0][1:],catalog=s.base.names[1],
        metadata_uuid=s.base.metadata_ids[0],periodicity='Second',write_mode='Independent',
        columns=list(reversed(FIELDS)) if reverse else list(FIELDS),
        catalog_schema=linked.schema_request(s),ids={k:str(uuid.uuid4()) for k in sorted(ID_KEYS)},
        status='periodic-v1-prospective-not-native-applied')

def validate(s,p):
    def finite(v,depth=0):
        if depth>16:return False
        if type(v) is dict:return len(v)<=64 and all(type(k) is str and len(k)<128 and finite(x,depth+1) for k,x in v.items())
        if type(v) is list:return len(v)<=64 and all(finite(x,depth+1) for x in v)
        if type(v) is str:return len(v)<=4096
        return type(v) in (int,bool) or v is None
    if not finite(p) or type(p) is not dict or set(p)!={'register','catalog','metadata_uuid','periodicity','write_mode','columns','catalog_schema','ids','status'}:raise ValueError('register-profile')
    linked.validate_request(s,p['catalog_schema'])
    required={'register':'I'+s.base.names[0][1:],'catalog':s.base.names[1],'metadata_uuid':s.base.metadata_ids[0],
        'periodicity':'Second','write_mode':'Independent','status':'periodic-v1-prospective-not-native-applied'}
    if any(type(p[k]) is not str or p[k]!=v for k,v in required.items()):raise ValueError('register-profile')
    if type(p['columns']) is not list or p['columns'] not in (list(FIELDS),list(reversed(FIELDS))):raise ValueError('register-columns')
    if type(p['ids']) is not dict or set(p['ids'])!=ID_KEYS:raise ValueError('register-identities')
    prior=json.dumps(p['catalog_schema'])+json.dumps([s.base.record_ids,s.product_rows])
    for v in p['ids'].values():
        if type(v) is not str or str(uuid.UUID(v))!=v or not uuid.UUID(v).int or v in prior:raise ValueError('register-identity')
    if len(set(p['ids'].values()))!=len(ID_KEYS):raise ValueError('register-identity-collision')
    return p

def xml(s,p):
    validate(s,p);facts=SCHEMA.read_bytes()
    if hashlib.sha256(facts).hexdigest()!=SCHEMA_SHA:raise ValueError('schema-provenance')
    ns=' '.join(('xmlns' if not k else 'xmlns:'+k)+'="'+v+'"' for k,v in linked.NAMESPACES.items())
    text='<?xml version="1.0" encoding="UTF-8"?>'+f'<MetaDataObject {ns} version="2.20"><InformationRegister uuid="{p["metadata_uuid"]}"><InternalInfo>'
    for family in NATIVE_FAMILIES:
        text+=f'<xr:GeneratedType name="InformationRegister{family}.{p["register"]}" category="{family}"><xr:TypeId>{p["ids"][family+".TypeId"]}</xr:TypeId><xr:ValueId>{p["ids"][family+".ValueId"]}</xr:ValueId></xr:GeneratedType>'
    text+='</InternalInfo><Properties>'+REGISTER_PROPERTIES.replace('@@REGISTER@@',p['register'])+'</Properties><ChildObjects>'
    number='<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>9</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'
    types={'Product':'<v8:Type>cfg:CatalogRef.'+p['catalog']+'</v8:Type>',
        'Variant':number.replace('<v8:FractionDigits>2','<v8:FractionDigits>0'),'Price':number,
        'Available':'<v8:Type>xs:boolean</v8:Type>',
        'ValidUntil':'<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>',
        'Note':'<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>32</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'}
    for family,names in (('Resource',('Price','Available','ValidUntil')),('Attribute',('Note',)),('Dimension',('Product','Variant'))):
        for name in p['columns']:
            if name not in names:continue
            text+=f'<{family} uuid="{p["ids"][name]}"><Properties><Name>{name}</Name><Synonym/><Comment/><Type>{types[name]}</Type>'
            defaults={'Resource':RESOURCE_DEFAULTS,'Attribute':ATTRIBUTE_DEFAULTS,'Dimension':DIMENSION_DEFAULTS}[family]
            if name=='Product':defaults=defaults.replace('<Indexing>DontIndex</Indexing>','<Indexing>Index</Indexing>')
            text+=defaults
            text+='</Properties></'+family+'>'
    text+='</ChildObjects></InformationRegister></MetaDataObject>'
    target=linked.render_catalog_xml(s,p['catalog_schema'])['Catalogs/'+p['catalog']+'.xml']
    result={'InformationRegisters/'+p['register']+'.xml':text.encode(),'Catalogs/'+p['catalog']+'.xml':target}
    if any(len(v)>65536 for v in result.values()):raise ValueError('register-xml-budget')
    # !todo Repeat2 reordered input still requires native apply/redump. No
    # CONFIG collection UUID, descriptor position or physical key is inferred.
    return result

def validate_xml(s,p,actual):
    expected=xml(s,p)
    if type(actual) is not dict or set(actual)!=set(expected):raise ValueError('register-fragments')
    for name,raw in expected.items():
        if linked._xml_signature(raw)!=linked._xml_signature(actual[name]):raise ValueError('register-xml-profile')
    return True

def rights(s,p,baseline):
    validate(s,p);linked.setup_adapter.add_rights(baseline,s.base) # exact baseline validation, discard additions
    start=baseline.index(b'<object><name>Catalog.NativeOracleItems</name>');end=baseline.index(b'</object>',start)+len(b'</object>')
    cat=baseline[start:end].replace(b'NativeOracleItems',p['catalog'].encode())
    reg=('<object><name>InformationRegister.'+p['register']+'</name>'+''.join('<right><name>'+r+'</name><value>true</value></right>' for r in ('Read','Update'))+'</object>').encode()
    return baseline.replace(b'</Rights>',cat+reg+b'</Rights>')

def validate_rights(s,p,baseline,actual):
    expected=rights(s,p,baseline)
    if type(actual) is not bytes or len(actual)>65536 or b'<!' in actual:raise ValueError('register-rights')
    def sig(n):return n.tag,tuple(sorted(n.attrib.items())),(n.text or '').strip(),(n.tail or '').strip(),tuple(sorted(sig(c) for c in n))
    if sig(ET.fromstring(expected))!=sig(ET.fromstring(actual)):raise ValueError('register-rights')
    return True

def target(s,p,key):
    validate(s,p);ident={'A':s.base.record_ids[0],'B':p['ids']['product2'],'missing':s.base.record_ids[1]}[key]
    return f'Catalogs.{p["catalog"]}.GetRef(New UUID("{ident}"))'

def controls(p):
    return [f'Metadata.InformationRegisters.{p["register"]}.Name',f'Catalogs.{p["catalog"]}.EmptyRef().Metadata().Name']

# Input data, never expected native ordering or cursor/default semantics.
T0='Date(2024,2,29,12,0,0)'
T1='Date(2024,2,29,12,0,1)'
T2='Date(2024,2,29,12,0,2)'
def records():
    # Deliberately not chronological or dimension-sorted insertion.
    return (('A',1,T2,'50','True','Date(2001,1,1,0,0,1)','late'),
            ('B',1,T1,'40','False','Date(1,1,1)','other'),
            ('A',1,T0,'10','False','Date(1,1,1)','early'),
            ('A',2,T1,'30','True','Date(2024,2,29,12,34,56)','variant'),
            ('A',1,T1,'20','True','Date(2024,2,29,12,34,56)','middle'))

def ordered_records():
    return sorted(records(),key=lambda r:(r[2],r[0],r[1]))

def key(s,p,product='A',variant=1):
    return f'New Structure("Product,Variant",{target(s,p,product)},{variant})'

def setup(s,p,state):
    validate(s,p)
    if type(state) is not str or state not in STATES:raise ValueError('register-state')
    obs=linked.observer();split=obs.index('Сообщить("CR-C1:')
    helper='Function RGCount(TableName)\nQ = New Query; Q.Text = "SELECT COUNT(*) AS N FROM " + TableName; W = Q.Execute().Select(); W.Next(); Return W.N;\nEndFunction\n'
    text=obs[:split]+helper+obs[split:];reg='InformationRegisters.'+p['register'];cat='Catalogs.'+p['catalog']
    for table in ('InformationRegister.'+p['register'],'Catalog.'+p['catalog']):text+=f'If RGCount("{table}") <> 0 Then Raise "setup-not-empty"; EndIf;\n'
    if state=='filled':
        for product,code,desc in (('A','10','First'),('B','20','Second')):
            text+=f'C = {cat}.CreateItem(); C.SetNewObjectRef({target(s,p,product)}); C.Code = "{code}"; C.Description = "{desc}"; C.Write();\n'
        for product,variant,period,price,available,date,note in records():
            text+=f'R = {reg}.CreateRecordManager(); R.Period = {period}; R.Product = {target(s,p,product)}; R.Variant = {variant}; R.Price = {price}; R.Available = {available}; R.ValidUntil = {date}; R.Note = "{note}"; R.Write(False);\n'
    text+=f'Q = New Query; Q.Text = "SELECT Period, Product, Variant, Price, Available, ValidUntil, Note FROM InformationRegister.{p["register"]} ORDER BY Period, Product.Code, Variant"; W = Q.Execute().Select();\n'
    expr=controls(p)+[f'RGCount("InformationRegister.{p["register"]}")',f'RGCount("Catalog.{p["catalog"]}")']
    for product,variant,period,price,available,date,note in ordered_records():
        expr+=['W.Next()','String(W.Product.UUID())','XMLString(W.Period)',f'W.Variant = {variant} And W.Price = {price} And W.Available = {available} And W.ValidUntil = {date} And W.Note = "{note}"']
    for i,e in enumerate(expr,1):text+=linked.emit(i,e)
    if len(expr)!=24 or len(text.encode())>8192:raise ValueError('register-setup-budget')
    return text

def preparation(s,p,block):
    reg='InformationRegisters.'+p['register'];k=key(s,p);a=f'New Structure("Product",{target(s,p,"A")})'
    if block=='get':
        return [(v,f'{reg}.{method}({date},{flt})') for v,method,date,flt in (
            ('G0','GetFirst',T0,k),('G1','GetFirst',T1,k),('G2','GetFirst',T1+' + 1',k),
            ('L0','GetLast',T0,k),('L1','GetLast',T1,k),('L2','GetLast',T1+' - 1',k),
            ('GM','GetLast',T1,key(s,p,'missing')),('GN','GetFirst',T2+' + 1',k))]
    if block=='slices':
        return [(v,f'{reg}.{method}({date}{","+flt if flt else ""})') for v,method,date,flt in (
            ('LF','SliceLast',T1,''),('FF','SliceFirst',T1,'New Structure'),('LP','SliceLast',T1,a),
            ('FP','SliceFirst',T1,a),('LK','SliceLast',T1,k),('FK','SliceFirst',T1,k))] + [(f'R{i}',f'LF.FindRows({key(s,p,product,variant)})')
                for i,(product,variant) in enumerate((('A',1),('A',2),('B',1)))]
    if block=='cursor':return [('S',f'{reg}.Select()')]
    if block=='edges':return [('E',f'{reg}.Select({T1},{T1},{a})'),('D',f'{reg}.Select({T0},{T2},{a},"Desc")'),
        ('M',f'{reg}.Select({T0},{T2},New Structure("Product",{target(s,p,"missing")}))')]
    raise ValueError('register-block')

def cases(s,p,block):
    validate(s,p);out=list(zip(('control.register','control.catalog'),controls(p)))
    if block=='get':
        for v in ('G0','G1','G2','L0','L1','L2','GM','GN'):out.append((v+'.price',f'XMLString({v}.Price)'))
        out += [('type','String(TypeOf(G1))'),('count','G1.Count()'),('has.period','G1.Property("Period")'),
            ('has.product','G1.Property("Product")'),('has.note','G1.Property("Note")'),
            ('boolean','G1.Available'),('date','XMLString(G1.ValidUntil)'),('missing.count','GM.Count()'),
            ('missing.boolean','GM.Available'),('missing.date','XMLString(GM.ValidUntil)'),
            ('future.count','GN.Count()'),('future.boolean','GN.Available'),('future.date','XMLString(GN.ValidUntil)'),
            ('manager.type',f'String(TypeOf(InformationRegisters.{p["register"]}))')]
    elif block=='slices':
        for v in ('LF','FF','LP','FP','LK','FK'):out.append((v+'.count',v+'.Count()'))
        out += [('table.type','String(TypeOf(LF))'),('columns','LF.Columns.Count()'),('period.type','String(TypeOf(LK[0].Период))'),
            ('last.period','XMLString(LK[0].Период)'),('last.price','XMLString(LK[0].Price)'),('first.period','XMLString(FK[0].Период)'),
            ('first.price','XMLString(FK[0].Price)'),('target','LK[0].Product.Description')]
        # Native41380811903 demonstrated differing, undocumented slice row order.
        # Three complete keys plus total count prove coverage/uniqueness without
        # imposing an order or discarding resource/attribute content.
        for i in range(3):
            row=f'R{i}[0]'
            values=' + "|" + '.join(f'XMLString({row}.{name})' for name in
                ('Период','Price','Available','ValidUntil','Note'))
            out += [(f'key.{i}.count',f'R{i}.Count()'),(f'key.{i}.values',values)]
        out += [('period.column.type','String(LF.Columns[0].ValueType)'),('column.names',' + "|" + '.join(f'LF.Columns[{i}].Name' for i in range(7)))]
    elif block=='cursor':
        for i in range(5):out += [(f'{i}.next','S.Next()'),(f'{i}.period','XMLString(S.Period)'),(f'{i}.product','String(S.Product.UUID())'),(f'{i}.variant','XMLString(S.Variant)')]
        out += [('exhaust','S.Next()'),('retained','XMLString(S.Period)')]
    elif block=='edges':
        out += [('type','String(TypeOf(E))'),('before','XMLString(E.Period)')]
        for i in range(2):out += [(f'exact.{i}.next','E.Next()'),(f'exact.{i}.variant','XMLString(E.Variant)'),(f'exact.{i}.period','XMLString(E.Period)')]
        out += [('exact.end','E.Next()'),('exact.again','E.Next()')]
        for i in range(4):out += [(f'desc.{i}.next','D.Next()'),(f'desc.{i}.price','XMLString(D.Price)')]
        out += [('desc.end','D.Next()'),('missing','M.Next()'),('missing.period','XMLString(M.Period)'),('period.type','String(TypeOf(E.Period))')]
    else:raise ValueError('register-block')
    if len(out)!=24:raise ValueError(('register-case-count',block,len(out)))
    return out

def render(s,p,block):
    validate(s,p);text=linked.observer()
    for name,expr in preparation(s,p,block):text+=f'{name} = Undefined; Try {name} = {expr}; Except EndTry;\n'
    for i,(label,expr) in enumerate(cases(s,p,block),1):text+=linked.emit(i,expr)+'// '+label+'\n'
    if len(text.encode())>8192:raise ValueError('register-observer-budget')
    return text


def capture(raw,s,p):
    validate(s,p);rows=linked.scalar_wire.validate_output(raw)
    for i,name in enumerate((p['register'],p['catalog']),1):
        if rows[i-1]!=dict(id=i,status='ok',kind='string',value=tuple(map(ord,name))):raise ValueError('register-control')
    if any(r['status']=='observer-error' for r in rows):raise ValueError('register-observer-error')
    return rows

def require_setup(raw,s,p,state):
    if type(state) is not str or state not in STATES:raise ValueError('register-state')
    rows=capture(raw,s,p);expected={1:p['register'],2:p['catalog'],3:5 if state=='filled' else 0,4:2 if state=='filled' else 0}
    for offset,record in zip((5,9,13,17,21),ordered_records()):
        product,variant,period,price,available,date,note=record
        expected[offset]=state=='filled'
        if state=='filled':
            second={T0:'00',T1:'01',T2:'02'}[period]
            expected.update({offset+1:s.base.record_ids[0] if product=='A' else p['ids']['product2'],offset+2:'2024-02-29T12:00:'+second,offset+3:True})
    for i,v in expected.items():
        kind='boolean' if type(v) is bool else 'number' if type(v) is int else 'string';value=tuple(map(ord,v)) if type(v) is str else v
        if rows[i-1]!=dict(id=i,status='ok',kind=kind,value=value):raise ValueError('register-setup-witness')
    return rows


def generate(destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('destination-exists')
    destination.mkdir(parents=True)
    for repeat in (1,2):
        s,p=fresh(repeat==2);root=destination/f'repeat-{repeat}';root.mkdir()
        for name,raw in xml(s,p).items():
            f=root/name;f.parent.mkdir(exist_ok=True);f.write_bytes(raw)
        for state in STATES:(root/f'setup-{state}.bsl').write_text(setup(s,p,state),encoding='utf-8')
        for block in BLOCKS:(root/f'{block}.bsl').write_text(render(s,p,block),encoding='utf-8')
        m=dict(profile=p,names=s.base.names,metadata_ids=s.base.metadata_ids,record_ids=s.base.record_ids,
            product_rows=s.product_rows,attribute_names=s.attribute_names,attribute_ids=s.attribute_ids,order=s.order,
            cases={b:cases(s,p,b) for b in BLOCKS})
        m['files']={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
        (root/'manifest.json').write_text(json.dumps(m,indent=2)+chr(10),encoding='utf-8')

# !todo Native Second normalization, temporal ordering/defaults and physical Period/key layout await actual evidence.
# Recorder/Boundary/PointInTime, totals, history, composite types, mutation and free chains remain excluded.
