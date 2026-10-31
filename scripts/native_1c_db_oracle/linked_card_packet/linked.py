"""Local linked-card measurement request. No XML/type/physical admission guessed."""
from pathlib import Path
from dataclasses import dataclass
import hashlib
import json
import uuid
import re
import io
import xml.etree.ElementTree as ET
from .base import probe, setup_adapter, scalar_wire

STATES = ('empty', 'filled')
BLOCKS = ('identity', 'values', 'references', 'cursor')
ROLES = ('text', 'number', 'boolean', 'datetime', 'reference')

@dataclass(frozen=True)
class Setup:
    base: probe.Setup
    product_rows: tuple[str, str]
    attribute_names: tuple[str, ...]
    attribute_ids: tuple[str, ...]
    order: tuple[str, ...]
    def validate(self):
        self.base.validate()
        if (type(self.product_rows) is not tuple or len(self.product_rows) != 2
                or type(self.attribute_names) is not tuple or len(self.attribute_names) != 5
                or type(self.attribute_ids) is not tuple or len(self.attribute_ids) != 5
                or type(self.order) is not tuple or set(self.order) != set(ROLES) or len(self.order) != 5):
            raise ValueError('setup-shape')
        if len(set(self.attribute_names)) != 5 or any(type(n) is not str or not probe.re.fullmatch(r'A[a-f0-9]{8}', n) for n in self.attribute_names):
            raise ValueError('attribute-name')
        ids = self.base.metadata_ids + self.base.record_ids + self.product_rows + self.attribute_ids
        if len(set(ids)) != len(ids): raise ValueError('identity-collision')
        if any(type(v) is not str or str(uuid.UUID(v)) != v or uuid.UUID(v).int == 0 for v in ids): raise ValueError('identity')
        return self
    @property
    def attrs(self): return dict(zip(ROLES, self.attribute_names))


def fresh(reverse=False):
    return Setup(probe.fresh_setup(), tuple(str(uuid.uuid4()) for _ in range(2)),
        tuple('A'+uuid.uuid4().hex[:8] for _ in ROLES), tuple(str(uuid.uuid4()) for _ in ROLES),
        tuple(reversed(ROLES)) if reverse else ROLES).validate()


def schema_request(s, generated_ids=None):
    s.validate(); ids = {} if generated_ids is None else generated_ids; used = set(s.base.metadata_ids+s.base.record_ids+s.product_rows+s.attribute_ids)
    for name, metadata in (() if generated_ids is not None else zip(s.base.names, s.base.metadata_ids)):
        mapping = {'CATALOG_UUID': metadata}
        for family in ('OBJECT', 'REF', 'SELECTION', 'LIST', 'MANAGER'):
            for suffix in ('TYPE', 'VALUE'):
                value = str(uuid.uuid4())
                if value in used: raise ValueError('generated-identity-collision')
                used.add(value); mapping[f'{family}_{suffix}_UUID'] = value
        ids[name] = mapping
    product, category = s.base.names
    definitions = {
        'text': {'type': 'String', 'length': 32, 'allowed_length': 'Variable'},
        'number': {'type': 'Number', 'digits': 9, 'fraction_digits': 2, 'allowed_sign': 'Any'},
        'boolean': {'type': 'Boolean'},
        'datetime': {'type': 'Date', 'date_fractions': 'DateTime'},
        'reference': {'type': 'SingleCatalogRef', 'target_name': category,
                      'target_metadata_uuid': s.base.metadata_ids[1],
                      'target_requested_ref_type_uuid': ids[category]['REF_TYPE_UUID']}}
    attributes = {role: dict(name=s.attrs[role], metadata_uuid=s.attribute_ids[i], **definitions[role]) for i,role in enumerate(ROLES)}
    return dict(status='schema-backed-Designer-input-not-native-applied', generated_ids=ids,
        catalogs=[dict(name=product, metadata_uuid=s.base.metadata_ids[0], code_length=2,
                       code_type='String', description_length=8, hierarchical=False,
                       attributes=[attributes[role] for role in s.order]),
                  dict(name=category, metadata_uuid=s.base.metadata_ids[1], code_length=2,
                       code_type='String', description_length=8, hierarchical=False, attributes=[])],
        pending=['schema-defined Designer inputs require native apply and saved-identity redump',
                 'saved-identity applied configuration and redump',
                 'CONFIG descriptors and target typeUUID-to-metadataUUID mapping',
                 'DBNames and physical declarations/slot bytes on same frozen postimage'])


# Official EDT8.3.27 schema definitions, not a claim of native dump equivalence.
SCHEMA_EVIDENCE = {
    'plugin_url': 'https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform_v8.3.27_1.0.400.v202609220822.jar',
    'plugin_sha256': '4af9e1355b14b2836df4e89ae5d6c6e834d308e4233a490c12232e7dede67e4e',
    'doc_plugin_sha256': 'a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642',
    'doc_ref_path': 'nl/en/html/SyntaxHelperContext/objects/catalog125/catalog126/object129.html',
    'backend_sha256': '8569cd5d718b4009e09c2fa43a21e0bac6811d78018da0e8ec234b2a38101827',
    'xdto_sha256': 'c492ad1c5d8d13b2961263c0c449ec25e21f7d2285f48d908957c9fe24b2fa14'}
CFG = 'http://v8.1c.ru/8.1/data/enterprise/current-config'
NAMESPACES = {'': setup_adapter.MD, 'v8': 'http://v8.1c.ru/8.1/data/core',
    'xr': setup_adapter.XR, 'xs': 'http://www.w3.org/2001/XMLSchema',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'cfg': CFG}


def validate_request(s, request):
    s.validate()
    if type(request) is not dict or type(request.get('generated_ids')) is not dict:
        raise ValueError('saved-schema-shape')
    ids=request['generated_ids']
    if set(ids)!=set(s.base.names):raise ValueError('saved-schema-catalogs')
    expected={'CATALOG_UUID'}|{f'{c}_{v}_UUID' for c in ('OBJECT','REF','SELECTION','LIST','MANAGER') for v in ('TYPE','VALUE')}
    used=set(s.base.record_ids+s.product_rows+s.attribute_ids)
    for name,metadata in zip(s.base.names,s.base.metadata_ids):
        mapping=ids[name]
        if type(mapping) is not dict or set(mapping)!=expected or mapping['CATALOG_UUID']!=metadata:
            raise ValueError('saved-generated-identities')
        for value in mapping.values():
            if type(value) is not str or str(uuid.UUID(value))!=value or uuid.UUID(value).int==0 or value in used:
                raise ValueError('saved-generated-identity-collision')
            used.add(value)
    # Complete closed logical profile: no extra field/type/default/target options.
    if json.dumps(request,sort_keys=True,allow_nan=False) != json.dumps(schema_request(s,ids),sort_keys=True,allow_nan=False):raise ValueError('saved-schema-profile')
    return request


def render_catalog_xml(s, request):
    validate_request(s,request)
    template=Path(__file__).with_name('base').joinpath('Catalog.xml').read_bytes()
    if hashlib.sha256(template).hexdigest()!='612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5':
        raise ValueError('template-provenance')
    source=template.decode('utf-8-sig')
    attribute_templates=re.findall(r'<Attribute uuid="@@(?:PAYLOAD|AMOUNT)_UUID@@">.*?</Attribute>',source,re.S)
    if len(attribute_templates)!=2:raise ValueError('attribute-template')
    types={
        'String':'<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>32</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>',
        'Number':'<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>9</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>',
        'Boolean':'<v8:Type>xs:boolean</v8:Type>',
        'Date':'<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>',
        'SingleCatalogRef':'<v8:Type>cfg:CatalogRef.'+s.base.names[1]+'</v8:Type>'}
    artifacts={}
    for catalog in request['catalogs']:
        attributes=[]
        for attribute in catalog['attributes']:
            kind=attribute['type']; text=attribute_templates[int(kind=='Number')]
            text=re.sub(r'@@(?:PAYLOAD|AMOUNT)_UUID@@',attribute['metadata_uuid'],text)
            text=re.sub(r'<Name>(?:Payload|Amount)</Name>','<Name>'+attribute['name']+'</Name>',text)
            text=re.sub(r'<Type>.*?</Type>','<Type>'+types[kind]+'</Type>',text,count=1,flags=re.S)
            if kind not in ('String','Number'):
                # Schema AttributeProperties.FillValue is optional (lowerBound0).
                # Avoid inheriting a String default into a Boolean/date/ref type.
                text=re.sub(r'<FillValue\b[^>]*>.*?</FillValue>\n?','',text,count=1,flags=re.S)
            attributes.append(text)
        start=source.index('<ChildObjects>');end=source.index('</ChildObjects>')+len('</ChildObjects>')
        body='<ChildObjects>\n'+'\n'.join(attributes)+'\n</ChildObjects>' if attributes else '<ChildObjects/>'
        text=source[:start]+body+source[end:]
        text=text.replace('NativeOracleItems',catalog['name']).replace('<DescriptionLength>0</DescriptionLength>','<DescriptionLength>8</DescriptionLength>')
        text=text.replace(' xmlns:v8=',f' xmlns:cfg="{CFG}" xmlns:v8=',1)
        for key,value in request['generated_ids'][catalog['name']].items():text=text.replace('@@'+key+'@@',value)
        if '@@' in text:raise ValueError('unexpanded-template')
        artifacts['Catalogs/'+catalog['name']+'.xml']=text.encode('utf-8')
    return artifacts


def _xml_signature(raw):
    if type(raw) is not bytes or len(raw)>65536 or b'<!' in raw:raise ValueError('saved-xml-bound')
    try:
        namespaces=list(ET.iterparse(io.BytesIO(raw),events=('start-ns',)))
        bindings=[pair for _,pair in namespaces]
        if len(bindings)!=len(NAMESPACES) or dict(bindings)!=NAMESPACES:raise ValueError('saved-namespace-profile')
        root=ET.fromstring(raw)
    except ET.ParseError:raise ValueError('saved-xml') from None
    def signature(node):
        return node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),(node.tail or '').strip(),tuple(signature(c) for c in node)
    return signature(root)


def validate_fragments(s, request, artifacts):
    expected=render_catalog_xml(s,request)
    if type(artifacts) is not dict or set(artifacts)!=set(expected):raise ValueError('saved-fragments')
    for name in expected:
        if _xml_signature(artifacts[name])!=_xml_signature(expected[name]):raise ValueError('saved-xml-profile')
    return True


def verify_redump(s, request, saved, redumped):
    # !todo Native apply/redump must confirm these schema-defined generated inputs.
    # Prefix/shape changes remain explicit mismatches, not permissive XML parsing.
    validate_fragments(s,request,saved);validate_fragments(s,request,redumped)
    return True


def extend_rights_and_refs(s, configuration, rights):
    """Reuse exact complete existing Rights profile; no authorization expansion."""
    s.validate()
    return {'Configuration.xml': setup_adapter.add_refs(configuration, s.base),
            'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml': setup_adapter.add_rights(rights, s.base)}


def extend_sources(s, request, saved_fragments, configuration, rights):
    validate_fragments(s,request,saved_fragments)
    return {**saved_fragments, **extend_rights_and_refs(s,configuration,rights)}


def observer(): return Path(__file__).with_name('base').joinpath('observer.bsl').read_text(encoding='utf-8')

def emit(index, expression):
    # Expression evaluates before CREmit; CREmit separately labels encoding errors.
    return (f'Try CREmit("{index:02}", {expression}); Except '
            f'Message("CR-{index:02}: [action-error]"); EndTry;\n')


def render_setup(s, state):
    s.validate()
    if state not in STATES: raise ValueError('state')
    product, category = s.base.names; u, absent = s.base.record_ids; a = s.attrs
    inherited = setup_adapter.render_setup(s.base)
    first = inherited.index('Функция CRCount'); end = inherited.index('КонецФункции', first)+len('КонецФункции')
    obs = observer(); split = obs.index('Сообщить("CR-C1:')
    text = obs[:split]+inherited[first:end]+'\n'+obs[split:]
    for name in s.base.names:
        text += f'Если CRCount("{name}") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;\n'
    if state == 'filled':
        text += f'CM = Catalogs.{category}; PM = Catalogs.{product};\nC = CM.CreateItem(); C.SetNewObjectRef(CM.GetRef(New UUID("{u}"))); C.Code = "10"; C.Description = "Category"; C.Write();\n'
        rows = [(u,'30','First','hello', '12.50','True','Date(2024,2,29,12,34,56)',f'CM.GetRef(New UUID("{u}"))'),
                (s.product_rows[0],'10','Second','', '0','False','Date(1,1,1)', 'CM.EmptyRef()'),
                (s.product_rows[1],'20','Third','third', '-7.25','True','Date(2001,1,1,0,0,1)',f'CM.GetRef(New UUID("{absent}"))')]
        for ident,code,desc,label,number,boolean,date,ref in rows:
            text += f'P = PM.CreateItem(); P.SetNewObjectRef(PM.GetRef(New UUID("{ident}"))); P.Code = "{code}"; P.Description = "{desc}";\n'
            text += f'P.{a["text"]} = "{label}"; P.{a["number"]} = {number}; P.{a["boolean"]} = {boolean}; P.{a["datetime"]} = {date}; P.{a["reference"]} = {ref}; P.Write();\n'
    witnesses = [f'Catalogs.{product}.EmptyRef().Metadata().Name',
                 f'Catalogs.{category}.EmptyRef().Metadata().Name',
                 f'CRCount("{product}")', f'CRCount("{category}")']
    for name in s.base.names:
        for ident in (u, absent): witnesses.append(f'CRCount("{name}", Catalogs.{name}.GetRef(New UUID("{ident}")))')
    # Query witnesses independently check committed field/reference values.
    text += f'Q = New Query; Q.Text = "SELECT Code, {a["text"]} AS Label, {a["number"]} AS Price, {a["boolean"]} AS Enabled, {a["datetime"]} AS Stamp, {a["reference"]} AS Category FROM Catalog.{product} ORDER BY Code"; W = Q.Execute().Select();\n'
    for expected_date in ('Date(1,1,1)', 'Date(2001,1,1,0,0,1)', 'Date(2024,2,29,12,34,56)'):
        witnesses += ['W.Next()', 'W.Code', 'W.Enabled', 'W.Stamp = '+expected_date, 'String(W.Category.UUID())']
    witnesses += ['W.Next()']
    if len(witnesses) != 24: raise ValueError('setup-case-count')
    for i, expr in enumerate(witnesses, 1): text += emit(i,expr)

    return text, witnesses


def cases(s, block):
    s.validate(); p,c=s.base.names; u,absent=s.base.record_ids; a=s.attrs
    manager='Catalogs.'+p; category='Catalogs.'+c; ref=f'{manager}.GetRef(New UUID("{u}"))'
    controls=[('control.product',manager+'.EmptyRef().Metadata().Name'),('control.category',category+'.EmptyRef().Metadata().Name')]
    values=[]
    if block=='identity':
        values=[('product.ref',f'String({ref}.UUID())'),('cross.uuid',f'{ref} = {category}.GetRef(New UUID("{u}"))'),
                ('ref.target.type',f'TypeOf({ref}.{a["reference"]}) = Type("CatalogRef.{c}")'),
                ('ref.target.metadata',f'{ref}.{a["reference"]}.Metadata() = Metadata.Catalogs.{c}')]
        for role in ROLES: values.append((role+'.type',f'String(TypeOf({ref}.{a[role]}))'))
        values += [('ref.metadata.name',f'{ref}.Metadata().Name'),('category.code',f'{category}.FindByCode("10").Code'),
                   ('category.description',f'{category}.FindByCode("10").Description')]
    elif block=='values':
        for code in ('10','20','30'):
            r=f'{manager}.FindByCode("{code}")'
            values.extend([(code+'.text',r+'.'+a['text']),(code+'.number',f'XMLString({r}.{a["number"]})'),
                           (code+'.boolean',r+'.'+a['boolean']),(code+'.date',f'XMLString({r}.{a["datetime"]})'),
                           (code+'.filled',f'ValueIsFilled({r}.{a["reference"]})'),(code+'.ref',f'String({r}.{a["reference"]}.UUID())')])
    elif block=='references':
        for code in ('10','20','30'):
            r=f'{manager}.FindByCode("{code}").{a["reference"]}'
            values.extend([(code+'.empty',r+'.IsEmpty()'),(code+'.code',r+'.Code'),(code+'.description',r+'.Description'),
                (code+'.type',f'TypeOf({r}) = Type("CatalogRef.{c}")'),(code+'.metadata',f'{r}.Metadata() = Metadata.Catalogs.{c}')])
        values += [('sameuuid.typed',f'{ref}.{a["reference"]} = {category}.GetRef(New UUID("{u}"))'),
                   ('sameuuid.cross',f'{ref}.{a["reference"]} = {ref}')]
    elif block=='cursor':
        for n in range(3):
            values.extend([(f'{n}.next','S.Next()'),(f'{n}.code','S.Code'),(f'{n}.boolean','S.'+a['boolean']),
                (f'{n}.date',f'XMLString(S.{a["datetime"]})'),(f'{n}.category',f'S.{a["reference"]}.Description')])
        values += [('exhaust','S.Next()'),('restart','S.Next()'),('restart.code','S.Code')]
    else: raise ValueError('block')
    # Padding is stable positive scalar evidence, not normalization of failures.
    while len(controls+values)<24: values.append((f'control.pad{len(values)}',f'{manager}.EmptyRef().IsEmpty()'))
    if len(controls+values)!=24: raise ValueError('case-count')
    return controls+values


def render_block(s, block):
    text=observer()+'Failed = Ложь;\n'
    if block=='cursor':text+=f'S = Undefined;\nTry S = Catalogs.{s.base.names[0]}.Select(); Except EndTry;\n'
    for i,(key,expr) in enumerate(cases(s,block),1): text+=emit(i,expr)+'// '+key+'\n'
    return text


def read_capture(raw,s):
    rows=scalar_wire.validate_output(raw)
    for index,name in enumerate(s.base.names):
        if rows[index]!=dict(id=index+1,status='ok',kind='string',value=tuple(map(ord,name))):raise ValueError('availability-control')
    if any(row['status']=='observer-error' for row in rows):raise ValueError('observer-failure')
    return dict(status='observed-not-native-accepted',raw_sha256=hashlib.sha256(raw).hexdigest(),records=rows)


def require_setup_evidence(raw, s, state):
    if state not in STATES: raise ValueError('state')
    records = scalar_wire.validate_output(raw)
    product, category = s.base.names; u, absent = s.base.record_ids
    expected = [product, category, 3 if state == 'filled' else 0,
                1 if state == 'filled' else 0, int(state == 'filled'), 0,
                int(state == 'filled'), 0]
    if state == 'filled':
        for code, active, target in [('10', False, str(uuid.UUID(int=0))),
                                     ('20', True, absent), ('30', True, u)]:
            expected += [True, code, active, True, target]
        expected += [False]
    for index,value in enumerate(expected):
        kind = 'boolean' if type(value) is bool else 'number' if type(value) is int else 'string'
        encoded = tuple(map(ord,value)) if kind == 'string' else value
        if records[index] != dict(id=index+1,status='ok',kind=kind,value=encoded): raise ValueError('setup-witness')
    if state == 'empty':
        # No native default claim for unpositioned Query selection fields.
        # Still require all four Next controls false and preserve other raw rows.
        for index in (8,13,18,23):
            if records[index] != dict(id=index+1,status='ok',kind='boolean',value=False):raise ValueError('setup-empty-next')
    if any(r['status'] == 'observer-error' for r in records):raise ValueError('observer-failure')
    return records


def generate(destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('destination-exists')
    destination.mkdir(parents=True)
    for n in (1,2):
        s=fresh(n==2);root=destination/f'repeat-{n}';root.mkdir()
        request=schema_request(s)
        artifacts=render_catalog_xml(s,request)
        validate_fragments(s,request,artifacts)
        for name,raw in artifacts.items():
            path=root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        manifest=dict(names=s.base.names,metadata_ids=s.base.metadata_ids,record_ids=s.base.record_ids,
            product_rows=s.product_rows,attribute_names=s.attribute_names,attribute_ids=s.attribute_ids,order=s.order,
            status='local-preparation-only',schema=request,schema_evidence=SCHEMA_EVIDENCE,cases={b:cases(s,b) for b in BLOCKS})
        for state in STATES:(root/f'setup-{state}.bsl').write_text(render_setup(s,state)[0],encoding='utf-8')
        for block in BLOCKS:(root/f'{block}.bsl').write_text(render_block(s,block),encoding='utf-8')
        manifest['source_hashes']={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
        (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
