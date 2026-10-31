"""LOCAL generated probe; no native launch, runtime type, or storage codec."""
from dataclasses import dataclass
import hashlib
import re
import uuid
from pathlib import Path
from .scalar_wire import validate_output

@dataclass(frozen=True)
class Setup:
    names: tuple[str, str]
    metadata_ids: tuple[str, str]
    record_ids: tuple[str, str]

    def validate(self):
        if any(type(v) is not tuple or len(v) != 2 for v in (self.names,self.metadata_ids,self.record_ids)):
            raise ValueError('setup-shape')
        if any(type(n) is not str or not re.fullmatch(r'C[a-f0-9]{8}',n) for n in self.names):
            raise ValueError('setup-name')
        if len(set(self.names)) != 2: raise ValueError('setup-name')
        ids=self.metadata_ids+self.record_ids
        for value in ids:
            if type(value) is not str: raise ValueError('setup-uuid')
            try: parsed=uuid.UUID(value)
            except (ValueError,AttributeError): raise ValueError('setup-uuid') from None
            if str(parsed)!=value or parsed.int==0: raise ValueError('setup-uuid')
        if len(set(ids))!=4: raise ValueError('identity-role-collision')
        return self

def fresh_setup():
    return Setup(tuple('C'+uuid.uuid4().hex[:8] for _ in range(2)),
                 tuple(str(uuid.uuid4()) for _ in range(2)),
                 tuple(str(uuid.uuid4()) for _ in range(2))).validate()

def cases(s):
    s.validate(); a,b=s.names; u,v=s.record_ids
    m=f'Catalogs.{a}'; n=f'Catalogs.{b}'
    r=f'{m}.GetRef(New UUID("{u}"))'; t=f'{n}.GetRef(New UUID("{u}"))'
    e=f'{m}.EmptyRef()'; z=f'{m}.GetRef(New UUID("00000000-0000-0000-0000-000000000000"))'
    identity=[
      ('control.name',f'{m}.EmptyRef().Metadata().Name'),('control.other_name',f'{n}.EmptyRef().Metadata().Name'),
      ('ref.uuid',f'String({r}.UUID())'),('other.uuid',f'String({t}.UUID())'),
      ('empty.uuid',f'String({e}.UUID())'),('empty.isempty',f'{e}.IsEmpty()'),
      ('empty.filled',f'ValueIsFilled({e})'),('zero.empty',f'{z} = {e}'),
      ('record.isempty',f'{r}.IsEmpty()'),('record.filled',f'ValueIsFilled({r})'),
      ('record.repeat',f'{r} = {r}'),('record.other',f'{r} = {m}.GetRef(New UUID("{v}"))'),
      ('record.crosscatalog',f'{r} = {t}'),('empty.crosscatalog',f'{e} = {n}.EmptyRef()'),
      ('record.uuid_equal',f'{r} = New UUID("{u}")'),('record.undefined',f'{r} = Undefined'),
      ('manager.metadata',f'{m}.Metadata() = Metadata.Catalogs.{a}'),
      ('ref.metadata',f'{r}.Metadata() = Metadata.Catalogs.{a}'),
      ('empty.metadata',f'{e}.Metadata() = Metadata.Catalogs.{a}'),
      ('ref.fullname',f'{r}.Metadata().FullName()'),
      ('ref.metadata.other',f'{t}.Metadata() = Metadata.Catalogs.{b}'),
      ('absent.uuid',f'String({m}.GetRef(New UUID("{v}")).UUID())'),
      ('absent.empty',f'{m}.GetRef(New UUID("{v}")).IsEmpty()'),
      ('absent.filled',f'ValueIsFilled({m}.GetRef(New UUID("{v}")))')]
    types=[('control.name',f'{m}.EmptyRef().Metadata().Name'),('control.uuid',f'String({r}.UUID())')]
    for key,expr in [('ref',r),('empty',e),('manager',m),('global','Catalogs')]:
        types += [(key+'.type',f'String(TypeOf({expr}))'),(key+'.metatype',f'TypeOf(TypeOf({expr})) = Type("Type")')]
    for key,name in [('ru',f'СправочникСсылка.{a}'),('en',f'CatalogRef.{a}'),('lower',f'catalogref.{a.lower()}'),('upper',f'CATALOGREF.{a.upper()}')]:
        types.append((key+'.resolve',f'Type("{name}") = TypeOf({r})'))
    types += [('ref.empty_type',f'TypeOf({r}) = TypeOf({e})'),('ref.cross_type',f'TypeOf({r}) = TypeOf({t})'),
      ('manager.resolve',f'Type("CatalogManager.{a}") = TypeOf({m})'),
      ('manager.ru',f'Тип("СправочникМенеджер.{a}") = ТипЗнч({m})'),
      ('ref.uuid_type',f'TypeOf({r}.UUID()) = Type("UUID")'),
      ('type.missing','String(Type("CatalogRef.AbsentProbe"))'),
      ('ref.metadata.ru',f'{r}.Метаданные() = Метаданные.Справочники.{a}'),('type.number','String(Type(1))'),
      ('type.extra',f'Type("CatalogRef.{a}",1) = TypeOf({r})'),
      ('type.ru_en',f'ТипЗнч(Справочники.{a}.ПустаяСсылка()) = TypeOf({e})')]
    errors=[('control.name',f'{m}.EmptyRef().Metadata().Name'),('control.uuid',f'String({r}.UUID())'),
      ('manager.ru',f'Справочники.{a}.Метаданные() = Metadata.Catalogs.{a}'),
      ('ref.ru',f'Строка(Справочники.{a}.ПолучитьСсылку(Новый УникальныйИдентификатор("{u}")).УникальныйИдентификатор())'),
      ('empty.ru',f'Справочники.{a}.ПустаяСсылка().Пустая()'),
      ('filled.ru',f'ЗначениеЗаполнено({r})'),('index.name',f'Catalogs["{a}"].Metadata().Name'),
      ('property.lower',f'Catalogs.{a.lower()}.Metadata().Name'),('index.upper',f'Catalogs["{a.upper()}"].Metadata().Name'),
      ('index.number','Catalogs[0].Metadata().Name'),('index.undefined','Catalogs[Undefined].Metadata().Name'),
      ('property.missing','Catalogs.AbsentProbe.Metadata().Name'),('index.missing','Catalogs["AbsentProbe"].Metadata().Name'),
      ('getref.string',f'{m}.GetRef("{u}").IsEmpty()'),('getref.undefined',f'{m}.GetRef(Undefined).IsEmpty()'),
      ('getref.number',f'{m}.GetRef(1).IsEmpty()'),('getref.extra',f'{m}.GetRef(New UUID("{u}"),1).IsEmpty()'),
      ('empty.extra',f'{m}.EmptyRef(1).IsEmpty()'),('uuid.extra',f'String({r}.UUID(1))'),
      ('isempty.extra',f'{r}.IsEmpty(1)'),('metadata.extra',f'{m}.Metadata(1).Name'),
      ('readonly.manager',f'!Catalogs.{a} = Undefined;'),
      ('readonly.ref',f'!{r}.Ref = Undefined;'),('postwrite.name',f'{m}.Metadata().Name')]
    result=dict(identity=identity,types=types,errors=errors)
    if any(len(v)!=24 for v in result.values()): raise ValueError('case-count')
    return result

def render(s,block):
    selected=cases(s)[block]
    text=Path(__file__).with_name('observer.bsl').read_text(encoding='utf-8')
    for i,(name,expr) in enumerate(selected,1):
        if expr.startswith('!'):
            text+=f'Попытка\n    {expr[1:]}\n    CREmit("{i:02}", Истина);\nИсключение\n    Сообщить("CR-{i:02}: [action-error]");\nКонецПопытки; // {name}\n'
        else:
            text+=f'CRObserve("{i:02}", "{expr.replace(chr(34),chr(34)*2)}"); // {name}\n'
    return text

def require_available(raw,s,block):
    records=validate_output(raw); expected=s.validate()
    controls={0:expected.names[0],1:expected.names[1],2:expected.record_ids[0],3:expected.record_ids[0]} if block=='identity' else {0:expected.names[0],1:expected.record_ids[0]}
    if block not in cases(s): raise ValueError('block')
    if any(r['status']=='observer-error' for r in records):raise ValueError('observer-failed')
    for index,value in controls.items():
        if records[index] != dict(id=index+1,status='ok',kind='string',value=tuple(map(ord,value))):
            raise ValueError('availability-control')
    return records

def catalog_artifacts(s):
    """Render only catalog fragments, NOT an installable complete configuration.

    Reuses the reviewed Catalog.xml and field-matrix child-removal pattern.
    Metadata UUID, generated type/value UUID and record UUID remain distinct.
    """
    s.validate()
    raw=Path(__file__).with_name('Catalog.xml').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5':
        raise ValueError('template-provenance')
    text=raw.decode('utf-8-sig')
    if text.count('<ChildObjects>')!=1 or text.count('</ChildObjects>')!=1 or text.count('NativeOracleItems')!=6:
        raise ValueError('template-shape')
    start,end=text.index('<ChildObjects>'),text.index('</ChildObjects>')
    text=text[:start]+'<ChildObjects/>'+text[end+len('</ChildObjects>'):]
    keys=set(re.findall(r'@@([A-Z_]+)@@',text))
    expected={'CATALOG_UUID'}|{f'{category}_{suffix}_UUID' for category in ('OBJECT','REF','SELECTION','LIST','MANAGER') for suffix in ('TYPE','VALUE')}
    if keys!=expected:raise ValueError('template-keys')
    used=set(s.metadata_ids+s.record_ids); output={}; generated={}
    for name,identity in zip(s.names,s.metadata_ids):
        values={'CATALOG_UUID':identity}
        for key in sorted(keys-{'CATALOG_UUID'}):
            value=str(uuid.uuid4())
            if value in used:raise ValueError('generated-identity-collision')
            used.add(value);values[key]=value
        rendered=text.replace('NativeOracleItems',name)
        for key,value in values.items():rendered=rendered.replace('@@'+key+'@@',value)
        if '@@' in rendered:raise ValueError('template-unexpanded')
        output[f'Catalogs/{name}.xml']=rendered.encode('utf-8')
        generated[name]=values
    return output,generated


def render_fresh(s):
    s.validate(); a=s.names[0];u=s.record_ids[0]
    text=Path(__file__).with_name('observer.bsl').read_text(encoding='utf-8')
    # Capture exactly twice. Failure remains visible in dependent records.
    for v in ('FreshA','FreshB'):
        text+=f'{v} = Неопределено;\nПопытка\n    {v} = Catalogs.{a}.GetRef();\nИсключение\nКонецПопытки;\n'
    expressions=[f'Catalogs.{a}.EmptyRef().Metadata().Name',f'String(Catalogs.{a}.GetRef(New UUID("{u}")).UUID())',
      'String(FreshA.UUID())','String(FreshB.UUID())','FreshA.IsEmpty()','FreshB.IsEmpty()',
      'ValueIsFilled(FreshA)','ValueIsFilled(FreshB)','FreshA <> FreshB',
      f'FreshA <> Catalogs.{a}.GetRef(New UUID("{u}"))',f'FreshB <> Catalogs.{a}.GetRef(New UUID("{u}"))',
      f'FreshA.Metadata() = FreshB.Metadata() And FreshA.Metadata() = Metadata.Catalogs.{a}']
    for i,expr in enumerate(expressions,1):
        text+=f'Observed = Истина;\nПопытка\n    Result = {expr};\nИсключение\n    Сообщить("CR-{i:02}: [action-error]");\n    Observed = Ложь;\nКонецПопытки;\nЕсли Observed Тогда CREmit("{i:02}", Result); КонецЕсли;\n'
    return text


def assess_fresh(raw,s):
    """Preserve observations including failures. Provisional relation gate only;
    target native observations must establish the behavior before implementation.
    Never normalize random values into U or compare their bytes across captures.
    """
    s.validate();records=validate_output(raw,case_count=12);reasons=[]
    for index,value in {0:s.names[0],1:s.record_ids[0]}.items():
        if records[index] != dict(id=index+1,status='ok',kind='string',value=tuple(map(ord,value))):reasons.append('availability-control')
    ids=[]
    for r in records[2:4]:
        try:
            if r['status']!='ok' or r['kind']!='string': raise ValueError()
            value=''.join(map(chr,r['value']));parsed=uuid.UUID(value)
            if str(parsed)!=value or parsed.int==0 or value in s.metadata_ids+s.record_ids:raise ValueError()
            ids.append(value)
        except (ValueError,TypeError):reasons.append('fresh-uuid')
    if len(ids)==2 and ids[0]==ids[1]:reasons.append('constant-fresh-uuid')
    for index,expected in {4:False,5:False,6:True,7:True,8:True,9:True,10:True,11:True}.items():
        if records[index] != dict(id=index+1,status='ok',kind='boolean',value=expected):reasons.append('fresh-relation-'+str(index+1))
    return dict(accepted=not reasons,reasons=reasons,raw=raw,raw_sha256=hashlib.sha256(raw).hexdigest(),records=records)
