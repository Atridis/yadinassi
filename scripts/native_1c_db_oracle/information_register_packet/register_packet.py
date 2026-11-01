"""NEW v2 owned InformationRegister preparation. No native/storage admission."""
from pathlib import Path
import json,hashlib,re,uuid,xml.etree.ElementTree as ET
from decimal import Decimal
from linked_card_packet import linked
BASE='273d40ab0abb3fad2a4489ba2cefa100c189dfc8'
FIELDS=('Product','Variant','Price','Available','ValidUntil','Note')
FAMILIES=('Manager','Selection','List','RecordSet','RecordManager','RecordKey','Record')
BLOCKS=('get','cursor','filter','types')
STATES=('empty','filled')
SCHEMA=Path(__file__).with_name('schema_facts.json')
SCHEMA_SHA='a0a717e7950e281beaee0ade31f3e1aa1785913f28326ffcf4bdabe262795d0a'
ID_KEYS={*FIELDS,'product2',*(f'{f}.{k}' for f in FAMILIES for k in ('TypeId','ValueId'))}

def fresh(reverse=False):
    s=linked.fresh(reverse)
    return s,dict(register='I'+s.base.names[0][1:],catalog=s.base.names[1],
        metadata_uuid=s.base.metadata_ids[0],periodicity='Nonperiodical',write_mode='Independent',
        columns=list(reversed(FIELDS)) if reverse else list(FIELDS),
        catalog_schema=linked.schema_request(s),ids={k:str(uuid.uuid4()) for k in sorted(ID_KEYS)},
        status='v2-prospective-not-native-applied')

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
        'periodicity':'Nonperiodical','write_mode':'Independent','status':'v2-prospective-not-native-applied'}
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
    required=json.loads(facts)['required_register_properties'];values=dict.fromkeys(required,'')
    values.update(Name=p['register'],ObjectBelonging='Native',UseStandardCommands='false',EditType='InList',
        InformationRegisterPeriodicity='Nonperiodical',WriteMode='Independent',MainFilterOnPeriod='false',
        IncludeHelpInContents='false',DataLockControlMode='Automatic',FullTextSearch='DontUse',
        EnableTotalsSliceFirst='false',EnableTotalsSliceLast='false',DataHistory='DontUse',
        UpdateDataHistoryImmediatelyAfterWrite='false',ExecuteAfterWriteDataHistoryVersionProcessing='false')
    ns=' '.join(('xmlns' if not k else 'xmlns:'+k)+'="'+v+'"' for k,v in linked.NAMESPACES.items())
    text='<?xml version="1.0" encoding="UTF-8"?>'+f'<MetaDataObject {ns} version="2.20"><InformationRegister uuid="{p["metadata_uuid"]}"><InternalInfo>'
    for family in FAMILIES:
        text+=f'<xr:GeneratedType name="InformationRegister{family}.{p["register"]}" category="{family}"><xr:TypeId>{p["ids"][family+".TypeId"]}</xr:TypeId><xr:ValueId>{p["ids"][family+".ValueId"]}</xr:ValueId></xr:GeneratedType>'
    text+='</InternalInfo><Properties>'+''.join(f'<{k}>{values[k]}</{k}>' for k in required)+'</Properties><ChildObjects>'
    number='<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>9</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'
    types={'Product':'<v8:Type>cfg:CatalogRef.'+p['catalog']+'</v8:Type>',
        'Variant':number.replace('<v8:FractionDigits>2','<v8:FractionDigits>0'),'Price':number,
        'Available':'<v8:Type>xs:boolean</v8:Type>',
        'ValidUntil':'<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>',
        'Note':'<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>32</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'}
    for family,names in (('Resource',('Price','Available','ValidUntil')),('Attribute',('Note',)),('Dimension',('Product','Variant'))):
        for name in p['columns']:
            if name not in names:continue
            text+=f'<{family} uuid="{p["ids"][name]}"><Properties><Name>{name}</Name><Synonym/><Comment/><Type>{types[name]}</Type><FillChecking>DontCheck</FillChecking>'
            if family=='Dimension':text+='<Indexing>'+('Index' if name=='Product' else 'DontIndex')+'</Indexing><Master>false</Master><MainFilter>false</MainFilter>'
            text+='</Properties></'+family+'>'
    text+='</ChildObjects></InformationRegister></MetaDataObject>'
    target=linked.render_catalog_xml(s,p['catalog_schema'])['Catalogs/'+p['catalog']+'.xml']
    result={'InformationRegisters/'+p['register']+'.xml':text.encode(),'Catalogs/'+p['catalog']+'.xml':target}
    if any(len(v)>65536 for v in result.values()):raise ValueError('register-xml-budget')
    # !todo Native XML defaults/GeneratedType inventory must be measured. No
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

def records():
    return (('A',2,'0','False','Date(1,1,1)',''),('B',1,'-7.25','True','Date(2001,1,1,0,0,1)','second'),('A',1,'12.50','True','Date(2024,2,29,12,34,56)','first'))

def setup(s,p,state):
    validate(s,p)
    if type(state) is not str or state not in STATES:raise ValueError('register-state')
    obs=linked.observer();split=obs.index('Сообщить("CR-C1:')
    helper='Function RGCount(TableName)\nQ = New Query; Q.Text = "SELECT COUNT(*) AS N FROM " + TableName; W = Q.Execute().Select(); W.Next(); Return W.N;\nEndFunction\n'
    text=obs[:split]+helper+obs[split:];reg='InformationRegisters.'+p['register'];cat='Catalogs.'+p['catalog']
    for table in ('InformationRegister.'+p['register'],'Catalog.'+p['catalog']):text+=f'If RGCount("{table}") <> 0 Then Raise "setup-not-empty"; EndIf;\n'
    if state=='filled':
        for key,code,desc in (('A','10','First'),('B','20','Second')):
            text+=f'C = {cat}.CreateItem(); C.SetNewObjectRef({target(s,p,key)}); C.Code = "{code}"; C.Description = "{desc}"; C.Write();\n'
        for product,variant,price,available,date,note in records():
            text+=f'R = {reg}.CreateRecordManager(); R.Product = {target(s,p,product)}; R.Variant = {variant}; R.Price = {price}; R.Available = {available}; R.ValidUntil = {date}; R.Note = "{note}"; R.Write(False);\n'
    text+=f'Q = New Query; Q.Text = "SELECT Product, Variant, Price, Available, ValidUntil FROM InformationRegister.{p["register"]} ORDER BY Product.Code, Variant"; W = Q.Execute().Select();\n'
    expr=controls(p)+[f'RGCount("InformationRegister.{p["register"]}")',f'RGCount("Catalog.{p["catalog"]}")']
    for date in ('Date(2024,2,29,12,34,56)','Date(1,1,1)','Date(2001,1,1,0,0,1)'):
        expr+=['W.Next()','String(W.Product.UUID())','W.Variant','XMLString(W.Price)','W.Available','W.ValidUntil = '+date]
    expr+=['W.Next()',controls(p)[0]]
    for i,e in enumerate(expr,1):text+=linked.emit(i,e)
    if len(text.encode())>8192:raise ValueError('register-setup-budget')
    return text

def cases(s,p,block):
    validate(s,p);reg='InformationRegisters.'+p['register'];out=list(zip(('control.register','control.catalog'),controls(p)))
    if block=='get':
        for label,g in (('a1','G1'),('a2','G2'),('b1','G3'),('missing','GM')):
            out += [(label+'.price',f'XMLString({g}.Price)'),(label+'.available',g+'.Available'),(label+'.date',f'XMLString({g}.ValidUntil)')]
        out += [('type','String(TypeOf(G1))'),('count','G1.Count()'),('has.price','G1.Property("Price")'),
            ('has.product','G1.Property("Product")'),('has.variant','G1.Property("Variant")'),('has.note','G1.Property("Note")'),
            ('key.order',f'{reg}.Get(New Structure("Variant,Product",1,{target(s,p,"A")})).Price = G1.Price'),
            ('missing.variant','XMLString(GV.Price)'),('missing.type','String(TypeOf(GM))'),('missing.count','GM.Count()')]
    elif block=='cursor':
        for i in range(3):
            out += [(f'{i}.next','S.Next()'),(f'{i}.product','String(S.Product.UUID())'),(f'{i}.variant','XMLString(S.Variant)'),
                (f'{i}.price','XMLString(S.Price)'),(f'{i}.available','S.Available'),(f'{i}.date','XMLString(S.ValidUntil)'),(f'{i}.note','S.Note')]
        out += [('exhaust','S.Next()')]
    elif block=='filter':
        out += [('type','String(TypeOf(F))'),('before','F.Variant')]
        for i in range(2):out += [(f'{i}.next','F.Next()'),(f'{i}.variant','XMLString(F.Variant)'),(f'{i}.price','XMLString(F.Price)'),(f'{i}.target','F.Product.Description')]
        out += [('exhaust','F.Next()'),('retained','F.Variant'),('restart','F.Next()'),('missing','FM.Next()'),
            ('desc1','D.Next()'),('desc1.variant','XMLString(D.Variant)'),('desc2','D.Next()'),('desc2.variant','XMLString(D.Variant)'),('desc.end','D.Next()')]
    elif block=='types':
        out += [('global','String(TypeOf(InformationRegisters))'),('manager',f'String(TypeOf({reg}))'),
            ('selection','String(TypeOf(S))'),('before','XMLString(S.Price)'),('next','S.Next()')]
        for name in FIELDS:out.append((name+'.type',f'String(TypeOf(S.{name}))'))
        out += [('target.type',f'TypeOf(S.Product) = Type("CatalogRef.{p["catalog"]}")'),('target.description','S.Product.Description'),
            ('selection.identity',f'TypeOf(S) = Type("InformationRegisterSelection.{p["register"]}")'),
            ('partial.key',f'{reg}.Get(New Structure("Product",{target(s,p,"A")})) = Undefined'),
            ('next2','S.Next()'),('next3','S.Next()'),('exhaust','S.Next()'),('retained','XMLString(S.Price)'),('restart','S.Next()')]
    else:raise ValueError('register-block')
    while len(out)<24:out.append(('pad'+str(len(out)),controls(p)[0]))
    if len(out)!=24:raise ValueError('register-case-count')
    return out

def render(s,p,block):
    validate(s,p);items=cases(s,p,block);reg='InformationRegisters.'+p['register'];text=linked.observer()
    if block=='get':
        for name,key,variant in (('G1','A',1),('G2','A',2),('G3','B',1),('GM','missing',1),('GV','A',99)):
            text+=f'{name} = Undefined; Try {name} = {reg}.Get(New Structure("Product,Variant",{target(s,p,key)},{variant})); Except EndTry;\n'
    if block in ('cursor','types'):text+=f'S = Undefined; Try S = {reg}.Select(); Except EndTry;\n'
    if block=='filter':
        for name,key in (('F','A'),('FM','missing')):
            text+=f'{name} = Undefined; Try {name} = {reg}.Select(New Structure("Product",{target(s,p,key)})); Except EndTry;\n'
        text+=f'D = Undefined; Try D = {reg}.Select(New Structure("Product",{target(s,p,"A")}),"Desc"); Except EndTry;\n'
    for i,(key,expr) in enumerate(items,1):text+=linked.emit(i,expr)+'// '+key+'\n'
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
    rows=capture(raw,s,p);expected={1:p['register'],2:p['catalog'],3:3 if state=='filled' else 0,4:2 if state=='filled' else 0,23:False,24:p['register']};decimals={}
    if state=='filled':
        for offset,(key,variant,price,available,date,note) in zip((5,11,17),sorted(records(),key=lambda r:(r[0],r[1]))):
            expected.update({offset:True,offset+1:s.base.record_ids[0] if key=='A' else p['ids']['product2'],offset+2:variant,offset+4:available=='True',offset+5:True})
            decimals[offset+3]=Decimal(price)
    else:expected.update({i:False for i in (5,11,17)})
    for i,v in expected.items():
        kind='boolean' if type(v) is bool else 'number' if type(v) is int else 'string';value=tuple(map(ord,v)) if type(v) is str else v
        if rows[i-1]!=dict(id=i,status='ok',kind=kind,value=value):raise ValueError('register-setup-witness')
    for i,value in decimals.items():
        row=rows[i-1]
        if row['status']!='ok' or row.get('kind')!='string':raise ValueError('register-setup-decimal')
        text=''.join(chr(c) for c in row['value'])
        if not re.fullmatch(r'-?[0-9]{1,9}(?:[.][0-9]{1,2})?',text) or Decimal(text)!=value:raise ValueError('register-setup-decimal')
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
        (root/'manifest.json').write_text(json.dumps(m,indent=2)+chr(10))

# !todo Periodic/recorder-driven registers, slices, composite dimensions,
# advanced filters/order, public mutations and unmeasured free chains excluded.
