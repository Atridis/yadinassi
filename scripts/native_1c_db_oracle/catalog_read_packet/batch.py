"""Local batched catalog-read preparation. No runtime/native acceptance claims."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import uuid
import json
from . import probe
from . import setup_adapter as base
from . import scalar_wire

STATES=('empty','one','several','deleted','reused')
@dataclass(frozen=True)
class Batch:
    setup: probe.Setup
    extra_ids: tuple[str,str]
    def validate(self):
        self.setup.validate()
        if type(self.extra_ids) is not tuple or len(self.extra_ids)!=2: raise ValueError('extra-shape')
        all_ids=self.setup.metadata_ids+self.setup.record_ids+self.extra_ids
        if len(set(all_ids))!=6:raise ValueError('identity-collision')
        for value in all_ids:
            if type(value) is not str or str(uuid.UUID(value))!=value or uuid.UUID(value).int==0:raise ValueError('identity')
        return self
    @property
    def rows(self):
        # U is shared between catalogs. UUID sort is explicitly unlike insertion
        # by ordering all three UUIDs and assigning a nonidentity permutation.
        ids=sorted((self.setup.record_ids[0],)+self.extra_ids)
        return tuple(zip((ids[1],ids[2],ids[0]),('30','10','20'),('Alpha','Zulu','Mike'),('first','second','third'),(11,22,33),(False,True,False)))

def fresh():return Batch(probe.fresh_setup(),tuple(str(uuid.uuid4()) for _ in range(2))).validate()

def fragments(b):
    b.validate(); artifacts={};ids={};used=set(b.setup.metadata_ids+b.setup.record_ids+b.extra_ids)
    for name,meta in zip(b.setup.names,b.setup.metadata_ids):
        values={'CATALOG_UUID':meta}
        for key in sorted(set(probe.re.findall(r'@@([A-Z_]+)@@',Path(__file__).with_name('Catalog.xml').read_text(encoding='utf-8-sig')))-{'CATALOG_UUID','PAYLOAD_LENGTH'}):
            v=str(uuid.uuid4())
            if v in used:raise ValueError('generated-collision')
            used.add(v);values[key]=v
        ids[name]=values;artifacts['Catalogs/'+name+'.xml']=render_fragment(name,values)
    validate_fragments(b,artifacts,ids)
    return artifacts,ids

def render_fragment(name,values):
    raw=Path(__file__).with_name('Catalog.xml').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5':raise ValueError('template-provenance')
    text=raw.decode('utf-8-sig').replace('NativeOracleItems',name).replace('<DescriptionLength>0</DescriptionLength>','<DescriptionLength>8</DescriptionLength>')
    for key,value in {**values,'PAYLOAD_LENGTH':'32'}.items():text=text.replace('@@'+key+'@@',value)
    if '@@' in text:raise ValueError('unexpanded-template')
    return text.encode('utf-8')

def signature(node):return node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),(node.tail or '').strip(),tuple(signature(c) for c in node)

def validate_fragments(b,artifacts,ids):
    b.validate();names=b.setup.names
    if type(artifacts) is not dict or set(artifacts)!={'Catalogs/'+n+'.xml' for n in names} or type(ids) is not dict or set(ids)!=set(names):raise ValueError('saved-shape')
    used=set(b.setup.record_ids+b.extra_ids)
    expected={'CATALOG_UUID','PAYLOAD_UUID','AMOUNT_UUID'}|{f'{c}_{s}_UUID' for c in ('OBJECT','REF','SELECTION','LIST','MANAGER') for s in ('TYPE','VALUE')}
    for name,meta in zip(names,b.setup.metadata_ids):
        values=ids[name]
        if type(values) is not dict or set(values)!=expected or values['CATALOG_UUID']!=meta:raise ValueError('saved-ids')
        for v in values.values():
            if type(v) is not str or str(uuid.UUID(v))!=v or uuid.UUID(v).int==0 or v in used:raise ValueError('saved-identity')
            used.add(v)
        raw=artifacts['Catalogs/'+name+'.xml']
        if type(raw) is not bytes or len(raw)>65536 or b'<!' in raw:raise ValueError('saved-xml')
        if signature(base.parse_xml(raw))!=signature(base.parse_xml(render_fragment(name,values))):raise ValueError('saved-profile')
    return True

def extend_sources(b,artifacts,ids,configuration,rights):
    validate_fragments(b,artifacts,ids)
    return {**artifacts,'Configuration.xml':base.add_refs(configuration,b.setup),'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml':base.add_rights(rights,b.setup)}

def verify_redump(b,artifacts,ids,redump):
    validate_fragments(b,artifacts,ids);validate_fragments(b,redump,ids);return True

def observer():return Path(__file__).with_name('observer.bsl').read_text(encoding='utf-8')
def emit(i,expr):
    # Direct evaluation allows module cursor variables; Eval has other scope rules.
    return f'Попытка\n    Result = {expr};\nИсключение\n    Сообщить("CR-{i:02}: [action-error]");\n    Result = Неопределено; Failed = Истина;\nКонецПопытки;\nЕсли Не Failed Тогда CREmit("{i:02}", Result); КонецЕсли; Failed = Ложь;\n'

def render_setup(b,state):
    b.validate()
    if state not in STATES:raise ValueError('state')
    # Reuse only declaration section, keeping all functions before executable code.
    original=base.render_setup(b.setup);start=original.index('Функция CRCount');end=original.index('КонецФункции',start)+len('КонецФункции')
    obs=observer();split=obs.index('Сообщить("CR-C1:');text=obs[:split]+original[start:end]+'\n'+obs[split:]
    for offset,name in zip((0,6),b.setup.names):
        text+=f'Если CRCount("{name}") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;\nCREmit("{offset+1:02}", CRCount("{name}"));\nManager = Catalogs.{name};\n'
        rows=() if state=='empty' else ([(b.setup.record_ids[0],'30','Alpha','first',11,False)] if state=='one' else b.rows)
        for index,(ident,code,desc,payload,amount,mark) in enumerate(rows):
            text+=f'Object = Manager.CreateItem(); Object.SetNewObjectRef(Manager.GetRef(New UUID("{ident}")));\nObject.Code = "{code}"; Object.Description = "{desc}"; Object.Payload = "{payload}"; Object.Amount = {amount}; Object.Write();\n'
            if mark:text+='Object.SetDeletionMark(True);\n'
            if index==0 and state in ('deleted','reused'):
                text+=f'Ghost = Manager.CreateItem(); Ghost.SetNewObjectRef(Manager.GetRef(New UUID("{b.setup.record_ids[1]}"))); Ghost.Code = "40"; Ghost.Description = "Gone"; Ghost.Write();\n'
        if state in ('deleted','reused'):text+='Ghost.Delete();\n'
        if state=='reused':
            text+=f'Reused = Manager.CreateItem(); Reused.SetNewObjectRef(Manager.GetRef(New UUID("{b.setup.record_ids[1]}"))); Reused.Code = "40"; Reused.Description = "Reused"; Reused.Payload = "reused"; Reused.Amount = 44; Reused.Write();\n'
        text+=f'CREmit("{offset+2:02}", CRCount("{name}"));\nCREmit("{offset+3:02}", CRCount("{name}", Manager.GetRef(New UUID("{b.setup.record_ids[0]}"))));\nCREmit("{offset+4:02}", CRCount("{name}", Manager.GetRef(New UUID("{b.setup.record_ids[1]}"))));\nCREmit("{offset+5:02}", Manager.Metadata().Name);\nCREmit("{offset+6:02}", String(Manager.GetRef(New UUID("{b.setup.record_ids[0]}")).UUID()));\n'
    return text

def render_block(b,block):
    b.validate();name=b.setup.names[0];manager='Catalogs.'+name
    actions=[('control.name',f'{manager}.Metadata().Name'),('control.uuid',f'String({manager}.GetRef(New UUID("{b.setup.record_ids[0]}")).UUID())')]
    if block=='cursor':
        # Actions evaluated independently so unsupported Reset stays observable.
        actions += [('before.ref','String(S.Ref.UUID())'),('before.code','S.Code'),('before.desc','S.Description')]
        for n in range(1,5):actions += [(f'next.{n}','S.Next()'),(f'ref.{n}','String(S.Ref.UUID())')]
        actions += [('exhaust.next','S.Next()'),('exhaust.code','S.Code'),('reset','!S.Reset();'),('reset.ref','String(S.Ref.UUID())'),('reset.next','S.Next()'),('reset.code','S.Code'),('reset.next2','S.Next()'),('reset.next3','S.Next()'),('reset.next4','S.Next()'),('type','String(TypeOf(S))'),('metatype','TypeOf(TypeOf(S)) = Type("Type")')]
    elif block=='fields':
        for n in range(1,4):
            actions += [(f'row{n}.next','S.Next()'),(f'row{n}.uuid','String(S.Ref.UUID())'),(f'row{n}.code','S.Code'),(f'row{n}.description','S.Description'),(f'row{n}.payload','S.Payload'),(f'row{n}.amount','S.Amount'),(f'row{n}.deleted','S.DeletionMark')]
        actions += [('exhaust','S.Next()')]
    elif block=='row4':
        actions += [('next1','S.Next()'),('next2','S.Next()'),('next3','S.Next()'),('next4','S.Next()')]
        actions += [('fourth.'+field,'S.'+field) for field in ('Code','Description','Payload','Amount','DeletionMark')]
        actions += [('fourth.uuid','String(S.Ref.UUID())'),('exhaust','S.Next()')]
        # Reference dereference checks do not depend on the cursor's row ordering.
        ref=f'{manager}.GetRef(New UUID("{b.setup.record_ids[0]}"))'
        actions += [('ref.'+field,ref+'.'+field) for field in ('Code','Description','Payload','Amount','DeletionMark')]
        actions += [('ref.ref',ref+'.Ref = '+ref),('ref.type','TypeOf('+ref+') = Type("CatalogRef.'+name+'")'),('ref.filled','ValueIsFilled('+ref+')'),('ref.metadata',ref+'.Metadata() = Metadata.Catalogs.'+name),('ref.uuid','String('+ref+'.UUID())'),('empty.isempty',manager+'.EmptyRef().IsEmpty()')]
    elif block=='lookup':
        for code in ('10','20','30','40','99'):
            actions += [('code.'+code,f'String({manager}.FindByCode("{code}").UUID())'),('filled.'+code,f'ValueIsFilled({manager}.FindByCode("{code}"))')]
        for desc in ('Alpha','Zulu','Mike','Gone','Absent'):
            actions += [('desc.'+desc,f'String({manager}.FindByDescription("{desc}", True).UUID())'),('empty.'+desc,f'{manager}.FindByDescription("{desc}", True).IsEmpty()')]
        actions += [('sameuuid',f'{manager}.GetRef(New UUID("{b.setup.record_ids[0]}")) = Catalogs.{b.setup.names[1]}.GetRef(New UUID("{b.setup.record_ids[0]}"))'),('sametype',f'TypeOf({manager}.EmptyRef()) = TypeOf(Catalogs.{b.setup.names[1]}.EmptyRef())')]
    else:raise ValueError('block')
    if len(actions)!=24:raise ValueError(('case-count',block,len(actions)))
    text=observer()+'Failed = Ложь; S = Неопределено;\n'
    if block!='lookup':text+=f'Попытка S = {manager}.Select(); Исключение КонецПопытки;\n'
    for i,(key,expr) in enumerate(actions,1):
        if expr.startswith('!'):
            text+=f'Попытка {expr[1:]} CREmit("{i:02}", Истина); Исключение Сообщить("CR-{i:02}: [action-error]"); КонецПопытки; // {key}\n'
        else:text+=emit(i,expr)+'// '+key+'\n'
    return text,actions

def read_capture(raw,b):
    rows=scalar_wire.validate_output(raw)
    for index,value in ((0,b.setup.names[0]),(1,b.setup.record_ids[0])):
        if rows[index]!=dict(id=index+1,status='ok',kind='string',value=tuple(map(ord,value))):raise ValueError('availability-control')
    if any(r['status']=='observer-error' for r in rows):raise ValueError('observer-failure')
    return {'raw_sha256':hashlib.sha256(raw).hexdigest(),'records':rows,'status':'observed-not-parity-approved'}

def require_setup_evidence(raw,b,state):
    if state not in STATES:raise ValueError('state')
    records=scalar_wire.validate_output(raw,case_count=12)
    count={'empty':0,'one':1,'several':3,'deleted':3,'reused':4}[state]
    for offset,name in zip((0,6),b.setup.names):
        expected=[('number',0),('number',count),('number',int(state!='empty')),('number',int(state=='reused')),('string',tuple(map(ord,name))),('string',tuple(map(ord,b.setup.record_ids[0])))]
        for index,(kind,value) in enumerate(expected,offset):
            if records[index]!=dict(id=index+1,status='ok',kind=kind,value=value):raise ValueError('setup-evidence')
    return records

def generate(destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('destination-exists')
    destination.mkdir(parents=True)
    manifests=[]
    for repeat in range(1,3):
        b=fresh();root=destination/f'repeat-{repeat}';root.mkdir()
        artifacts,ids=fragments(b)
        for name,raw in artifacts.items():
            path=root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
        manifest={'names':b.setup.names,'metadata_ids':b.setup.metadata_ids,'record_ids':b.setup.record_ids,'extra_ids':b.extra_ids,'generated_ids':ids,'rows':b.rows,'status':'local-preparation-only','states':STATES,'source_hashes':{}}
        for state in STATES:(root/f'setup-{state}.bsl').write_text(render_setup(b,state),encoding='utf-8')
        for block in ('cursor','fields','lookup','row4'):
            text,cases=render_block(b,block);(root/f'{block}.bsl').write_text(text,encoding='utf-8');manifest[block]=cases
        for block in ('identity','types','errors'):(root/f'{block}.bsl').write_text(probe.render(b.setup,block),encoding='utf-8')
        (root/'fresh.bsl').write_text(probe.render_fresh(b.setup),encoding='utf-8')
        for path in sorted(root.rglob('*')):
            if path.is_file():manifest['source_hashes'][str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        manifests.append(manifest)
    return manifests
