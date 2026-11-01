"""Owned document-lines preparation only; no physical schema inference."""
from pathlib import Path
import hashlib,json,re,uuid,xml.etree.ElementTree as ET
from document_read_packet import document_packet as base
linked=base.linked
SOURCE='9be9d601e4598de21c87098161928e827341973c'
COLUMNS=('Product','Quantity','Price','Amount','Note')
BLOCKS=('identity','rows','find_total','selection')
STATES=('initial','rewritten')
# Exact identity-free native redump subtree, run 41261482492; input only.
# Report SHA256 2bc781dd838ee8e27a86446c0cc443ceec41f2a29cc416dc2599093416235a90.
LINE_NUMBER_STANDARD = '<xr:StandardAttribute name="LineNumber"><xr:LinkByType/><xr:FillChecking>DontCheck</xr:FillChecking><xr:MultiLine>false</xr:MultiLine><xr:FillFromFillingValue>false</xr:FillFromFillingValue><xr:CreateOnInput>Auto</xr:CreateOnInput><xr:TypeReductionMode>TransformValues</xr:TypeReductionMode><xr:MaxValue xsi:nil="true"/><xr:ToolTip/><xr:ExtendedEdit>false</xr:ExtendedEdit><xr:Format/><xr:ChoiceForm/><xr:QuickChoice>Auto</xr:QuickChoice><xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput><xr:EditFormat/><xr:PasswordMode>false</xr:PasswordMode><xr:DataHistory>Use</xr:DataHistory><xr:MarkNegatives>false</xr:MarkNegatives><xr:MinValue xsi:nil="true"/><xr:Synonym/><xr:Comment/><xr:FullTextSearch>Use</xr:FullTextSearch><xr:ChoiceParameterLinks/><xr:FillValue xsi:nil="true"/><xr:Mask/><xr:ChoiceParameters/></xr:StandardAttribute>'

def fresh(reverse=False):
    s=linked.fresh(reverse);p=base.profile(s,linked.schema_request(s))
    ids={name:str(uuid.uuid4()) for name in ('section',*COLUMNS,'section_type','section_value','row_type','row_value','product2','lookup_absent')}
    return s,dict(source=SOURCE,base=p,section='Items',columns=list(reversed(COLUMNS)) if reverse else list(COLUMNS),ids=ids)

def validate(s,p):
    if type(p) is not dict or set(p)!={'source','base','section','columns','ids'}:raise ValueError('lines-profile')
    base.validate_profile(s,p['base'])
    if type(p['source']) is not str or type(p['section']) is not str or p['source']!=SOURCE or p['section']!='Items' or type(p['columns']) is not list or any(type(c) is not str for c in p['columns']) or p['columns'] not in (list(COLUMNS),list(reversed(COLUMNS))):raise ValueError('lines-profile')
    ids=p['ids'];keys={'section',*COLUMNS,'section_type','section_value','row_type','row_value','product2','lookup_absent'}
    if type(ids) is not dict or set(ids)!=keys:raise ValueError('lines-identities')
    for v in ids.values():
        if type(v) is not str or str(uuid.UUID(v))!=v or not uuid.UUID(v).int:raise ValueError('lines-identity')
    prior=json.dumps(p['base'],sort_keys=True)+json.dumps([s.base.record_ids,s.product_rows])
    if len(set(ids.values()))!=len(ids) or any(v in prior for v in ids.values()):raise ValueError('lines-identity-collision')
    return p

def xml(s,p):
    validate(s,p);out=base.document_xml(s,p['base']);name='Documents/'+p['base']['document_name']+'.xml'
    text=out[name].decode();attrs=re.findall(r'<Attribute uuid="[^"]+">.*?</Attribute>',text,re.S)
    if len(attrs)!=5:raise ValueError('base-attributes')
    byname={ET.fromstring(a.replace('<Attribute ', '<Attribute xmlns="'+base.MD[1:-1]+'" xmlns:v8="'+linked.NAMESPACES['v8']+'" xmlns:xs="'+linked.NAMESPACES['xs']+'" xmlns:xsi="'+linked.NAMESPACES['xsi']+'" xmlns:cfg="'+linked.CFG+'" ')).findtext(base.MD+'Properties/'+base.MD+'Name'):a for a in attrs}
    roles={'Product':'reference','Quantity':'number','Price':'number','Amount':'number','Note':'text'}
    columns=[]
    for column in p['columns']:
        old=byname[s.attrs[roles[column]]]
        new=re.sub(r'<Attribute uuid="[^"]+">','<Attribute uuid="'+p['ids'][column]+'">',old,count=1)
        new=new.replace('<Name>'+s.attrs[roles[column]]+'</Name>','<Name>'+column+'</Name>')
        # Native redump omits these two properties only for section columns.
        # Header attribute defaults remain byte-identical to the measured base.
        new,count=re.subn(r'<FillFromFillingValue>false</FillFromFillingValue>\s*', '', new)
        if count!=1:raise ValueError('lines-column-fill-from')
        new,count=re.subn(r'<FillValue\b[^>]*(?:/>|>[^<]*</FillValue>)\s*', '', new)
        if count!=1:raise ValueError('lines-column-fill-value')
        columns.append(new)
    ids=p['ids'];document=p['base']['document_name']
    info='<InternalInfo>'
    for kind,key in (('TabularSection','section'),('TabularSectionRow','row')):
        info+=f'<xr:GeneratedType name="Document{kind}.{document}.Items" category="{kind}"><xr:TypeId>{ids[key+"_type"]}</xr:TypeId><xr:ValueId>{ids[key+"_value"]}</xr:ValueId></xr:GeneratedType>'
    info+='</InternalInfo>'
    section=f'<TabularSection uuid="{ids["section"]}">'+info+'<Properties><Name>Items</Name><Synonym/><Comment/><ToolTip/><FillChecking>DontCheck</FillChecking><StandardAttributes>'+LINE_NUMBER_STANDARD+'</StandardAttributes><LineNumberLength>5</LineNumberLength></Properties><ChildObjects>'+''.join(columns)+'</ChildObjects></TabularSection>'
    # Append at the top-level Document ChildObjects end, never inside an attr.
    end=text.rindex('</ChildObjects>')
    out[name]=(text[:end]+section+text[end:]).encode()
    if any(len(v)>65536 for v in out.values()):raise ValueError('lines-xml-budget')
    # !todo Repeat 2 and the full row scenario still require native apply/redump.
    # Repeat 1 input defaults match the source-bound native redump above.
    return out

def validate_xml(s,p,actual):
    expected=xml(s,p)
    if type(actual) is not dict or set(actual)!=set(expected):raise ValueError('lines-fragments')
    for name in expected:
        if linked._xml_signature(expected[name])!=linked._xml_signature(actual[name]):raise ValueError('lines-xml-profile')
    return True

def specs(state,number):
    if state not in STATES or number not in ('10','20','30'):raise ValueError('lines-state')
    if number=='30':return ()
    if number=='10':return (('second','1','2.50','2.50','single'),)
    if state=='initial':return (('present','2','3.25','6.50','first'),('second','1','2','2','second'),('present','-1','1.25','-1.25','last'))
    return (('present','-1','1.25','-1.25','last'),('absent','4','2','8','replacement'),('present','2','3.25','6.50','first'))

def add_rows(s,p,number,state):
    c='Catalogs.'+p['base']['catalog_name'];u,absent=s.base.record_ids
    targets={'present':f'{c}.GetRef(New UUID("{u}"))','empty':c+'.EmptyRef()','absent':f'{c}.GetRef(New UUID("{absent}"))'}
    targets['second']=c+'.GetRef(New UUID("'+p['ids']['product2']+'"))'
    text=''
    for target,quantity,price,amount,note in specs(state,number):
        text+=f'L = P.Items.Add(); L.Product = {targets[target]}; L.Quantity = {quantity}; L.Price = {price}; L.Amount = {amount}; L.Note = "{note}";\n'
    return text

def setup(s,p,state):
    validate(s,p)
    if type(state) is not str or state not in STATES:raise ValueError('lines-state')
    if state=='initial':
        text,_=base.render_setup(s,p['base'],'filled')
        c='Catalogs.'+p['base']['catalog_name']
        second=f'C = {c}.CreateItem(); C.SetNewObjectRef({c}.GetRef(New UUID("{p["ids"]["product2"]}"))); C.Code = "20"; C.Description = "Second"; C.Write();\n'
        text=text.replace('C.Write();\n','C.Write();\n'+second,1)
        marker='P.Write(DocumentWriteMode.Write);'
        chunks=text.split(marker)
        if len(chunks)!=3:raise ValueError('base-setup-shape')
        text=chunks[0]+add_rows(s,p,'10',state)+marker+chunks[1]+add_rows(s,p,'20',state)+marker+chunks[2]
    else:
        # Only transition initial -> rewritten. Host must require initial Query
        # witness before this separately captured owned-document rewrite.
        d='Documents.'+p['base']['document_name']
        text=linked.observer()+f'P = {d}.FindByNumber("20").GetObject(); If P.Items.Count() <> 3 Or P.Posted Or String(P.Ref.UUID()) <> "{s.product_rows[1]}" Then Raise "rewrite-precondition"; EndIf;\n'
        text+='P.Items.Clear();\n'+add_rows(s,p,'20',state)+'P.Write(DocumentWriteMode.Write);\n'
        for i,(key,expr) in enumerate(cases(s,p,'identity'),1):text+=linked.emit(i,expr)
    if len(text.encode())>8192:raise ValueError('lines-setup-budget')
    return text

def witness(s,p,state):
    validate(s,p)
    if type(state) is not str or state not in STATES:raise ValueError('lines-state')
    d=p['base']['document_name'];c=p['base']['catalog_name']
    text=linked.observer()
    # Query independently binds section rows to owners; row count is not a
    # fabricated Python cursor or an assumption about physical slot layout.
    text+=f'Q = New Query; Q.Text = "SELECT Ref.Number AS Owner, LineNumber, Product, Quantity, Price, Amount, Note FROM Document.{d}.Items ORDER BY Ref.Number, LineNumber"; W = Q.Execute().Select();\n'
    expressions=[f'Documents.{d}.EmptyRef().Metadata().Name',f'Catalogs.{c}.EmptyRef().Metadata().Name']
    for i in range(4):expressions+=['W.Next()','W.Owner','W.LineNumber','XMLString(W.Amount)','String(W.Product.UUID())']
    expressions+=['W.Next()',f'Documents.{d}.FindByNumber("30").Items.Count()']
    for i,expr in enumerate(expressions,1):text+=linked.emit(i,expr)
    return text

def cases(s,p,block):
    validate(s,p);d='Documents.'+p['base']['document_name'];c='Catalogs.'+p['base']['catalog_name'];u,absent=s.base.record_ids
    t=d+'.FindByNumber("20").Items';one=d+'.FindByNumber("10").Items';empty=d+'.FindByNumber("30").Items'
    out=[('control.document',d+'.EmptyRef().Metadata().Name'),('control.catalog',c+'.EmptyRef().Metadata().Name')]
    if block=='identity':
        out += [('zero',empty+'.Count()'),('one',one+'.Count()'),('three',t+'.Count()'),
            ('section.type',f'String(TypeOf({t}))'),('row.type',f'String(TypeOf({t}.Get(0)))'),
            ('section.type.identity',f'TypeOf({t}) = Type("DocumentTabularSection.{p["base"]["document_name"]}.Items")'),
            ('row.type.identity',f'TypeOf({t}.Get(0)) = Type("DocumentTabularSectionRow.{p["base"]["document_name"]}.Items")'),
            ('first.line',t+'.Get(0).LineNumber'),('other.owner.line',one+'.Get(0).LineNumber'),
            ('index.get',t+'[0] = '+t+'.Get(0)'),('cross.owner.row',t+'.Get(0) = '+one+'.Get(0)'),
            ('product.type',f'TypeOf({t}.Get(0).Product) = Type("CatalogRef.{p["base"]["catalog_name"]}")'),
            ('product.description',t+'.Get(0).Product.Description'),('second.product.description',one+'.Get(0).Product.Description'),
            ('repeat.section.identity',t+' = '+t),('repeat.row.identity',t+'.Get(0) = '+t+'.Get(0)'),
            ('empty.ref.count',d+'.EmptyRef().Items.Count()'),
            ('missing.ref.count',f'{d}.GetRef(New UUID("{absent}")).Items.Count()')]
    elif block=='rows':
        for i in range(3):
            r=f'{t}.Get({i})'
            out += [(f'{i}.line',r+'.LineNumber'),(f'{i}.product',f'String({r}.Product.UUID())'),
                (f'{i}.quantity',f'XMLString({r}.Quantity)'),(f'{i}.price',f'XMLString({r}.Price)'),
                (f'{i}.amount',f'XMLString({r}.Amount)'),(f'{i}.note',r+'.Note')]
    elif block=='find_total':
        sought=f'{c}.GetRef(New UUID("{u}"))';missing=c+'.GetRef(New UUID("'+p['ids']['lookup_absent']+'"))'
        out += [('find.first',f'{t}.Find({sought},"Product").LineNumber'),
            ('find.index',f'XMLString({t}.IndexOf({t}.Find({sought},"Product")))'),
            ('find.missing',f'{t}.Find({missing},"Product") = Undefined'),
            ('row.index',f'XMLString({t}.IndexOf({t}.Get(2)))'),
            ('foreign.index',f'XMLString({t}.IndexOf({one}.Get(0)))'),
            ('total',f'XMLString({t}.Total("Amount"))'),('empty.total',f'XMLString({empty}.Total("Amount"))'),
            ('one.total',f'XMLString({one}.Total("Amount"))'),('foreach.count','IterCount'),
            ('foreach.amount','XMLString(IterAmount)'),('foreach.lines','IterLines')]
    elif block=='selection':
        out += [('next20','S.Next()'),('owner20','S.Number'),('count20','S.Items.Count()'),
            ('selection.section.type','String(TypeOf(S.Items))'),('selection.row.type','String(TypeOf(S.Items.Get(0)))'),
            ('first20','S.Items.Get(0).LineNumber'),('next30','S.Next()'),('owner30','S.Number'),
            ('count30','S.Items.Count()'),('next10','S.Next()'),('owner10','S.Number'),
            ('count10','S.Items.Count()'),('first10','S.Items.Get(0).LineNumber'),('exhaust','S.Next()')]
    else:raise ValueError('lines-block')
    while len(out)<24:out.append(('control.pad'+str(len(out)),d+'.EmptyRef().IsEmpty()'))
    if len(out)!=24:raise ValueError('lines-case-count')
    return out

def render(s,p,block):
    validate(s,p);items=cases(s,p,block);d='Documents.'+p['base']['document_name'];text=linked.observer()
    if block=='selection':text+=f'S = Undefined; Try S = {d}.Select(); Except EndTry;\n'
    if block=='find_total':
        text+=f'IterCount = Undefined; IterAmount = Undefined; IterLines = Undefined; Try IterCount = 0; IterAmount = 0; IterLines = ""; For Each R In {d}.FindByNumber("20").Items Do IterCount = IterCount + 1; IterAmount = IterAmount + R.Amount; IterLines = IterLines + String(R.LineNumber) + ";"; EndDo; Except IterCount = Undefined; IterAmount = Undefined; IterLines = Undefined; EndTry;\n'
    for i,(key,expr) in enumerate(items,1):text+=linked.emit(i,expr)+'// '+key+'\n'
    if len(text.encode())>8192:raise ValueError('lines-block-budget')
    return text

# !todo Composite fields, unmeasured free chains, public mutation, Unload and
# sorting are excluded. Native evidence must establish section owner linkage,
# row order/liveness and typed field layout before production admission.

def capture(raw,s,p):
    validate(s,p)
    return base.require_capture(raw,s,p['base'])

def require_initial_setup(raw,s,p):
    rows=capture(raw,s,p);u,absent=s.base.record_ids
    values=[p['base']['document_name'],p['base']['catalog_name'],3,2]
    for number,target in (('20',absent),('30',u),('10',str(uuid.UUID(int=0)))):
        values += [True,number,True,number=='30',target]
    values += [False]+[True]*4
    for i,value in enumerate(values,1):
        kind='boolean' if type(value) is bool else 'number' if type(value) is int else 'string'
        typed=tuple(map(ord,value)) if type(value) is str else value
        if rows[i-1]!=dict(id=i,status='ok',kind=kind,value=typed):raise ValueError('lines-initial-setup')
    return rows


def require_witness(raw,s,p,state):
    from decimal import Decimal,InvalidOperation
    if type(state) is not str or state not in STATES:raise ValueError('lines-state')
    rows=capture(raw,s,p);u,absent=s.base.record_ids
    expected=[p['base']['document_name'],p['base']['catalog_name']]
    amounts={}
    for owner in ('10','20'):
        for line,(target,quantity,price,amount,note) in enumerate(specs(state,owner),1):
            expected += [True,owner,line,amount,{'present':u,'empty':str(uuid.UUID(int=0)),'absent':absent,'second':p['ids']['product2']}[target]]
            amounts[len(expected)-1]=Decimal(amount)
    expected += [False,0]
    for i,value in enumerate(expected,1):
        row=rows[i-1]
        if i in amounts:
            if row['status']!='ok' or row.get('kind')!='string':raise ValueError('lines-witness')
            text=''.join(chr(c) for c in row['value'])
            if not re.fullmatch(r'-?[0-9]{1,9}(?:[.][0-9]{1,2})?',text):raise ValueError('lines-witness')
            try:matches=Decimal(text)==amounts[i]
            except InvalidOperation:matches=False
            if not matches:raise ValueError('lines-witness')
        else:
            kind='boolean' if type(value) is bool else 'number' if type(value) is int else 'string'
            typed=tuple(map(ord,value)) if type(value) is str else value
            if row!=dict(id=i,status='ok',kind=kind,value=typed):raise ValueError('lines-witness')
    return rows

def generate(destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('destination-exists')
    destination.mkdir(parents=True)
    for repeat in (1,2):
        s,p=fresh(repeat==2);root=destination/f'repeat-{repeat}';root.mkdir()
        for name,raw in xml(s,p).items():
            path=root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        for state in STATES:
            (root/f'setup-{state}.bsl').write_text(setup(s,p,state),encoding='utf-8')
            (root/f'witness-{state}.bsl').write_text(witness(s,p,state),encoding='utf-8')
        for block in BLOCKS:(root/f'{block}.bsl').write_text(render(s,p,block),encoding='utf-8')
        manifest=dict(profile=p,names=s.base.names,metadata_ids=s.base.metadata_ids,record_ids=s.base.record_ids,
            product_rows=s.product_rows,attribute_names=s.attribute_names,attribute_ids=s.attribute_ids,order=s.order,
            cases={b:cases(s,p,b) for b in BLOCKS},native_status='not-applied')
        manifest['files']={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
