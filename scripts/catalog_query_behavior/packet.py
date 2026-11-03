"""One-session owned Query behavior packet, no physical database inspection.

Output contains only 24 bounded scalars. Regional comparison and cursor
boundary outcomes are observations, not assumed native expected values.
"""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
import hashlib
import json
import xml.etree.ElementTree as ET

CASES = ('regional.description_equality', 'result.type', 'selection.type',
         'missing_parameter.refused', 'numeric_parameter.codes', 'boolean_parameter.codes',
         'date_parameter.codes', 'reference_parameter.code', 'ascending.codes',
         'descending_top.codes', 'boolean_precedence.codes', 'russian_alias.codes',
         'empty.is_empty', 'empty.next', 'exhausted.next', 'before_position.field',
         'after_position.field', 'unload.type', 'unload.count', 'unload.column_names',
         'unload.column_types', 'unload.qualifiers', 'unload.detached_values',
         'selections_and_parameters.independent')
TEMPLATE_SHA256 = 'bb1fd837dc38498e03a2ae71ab1eee571d8f0d8d6710f032782b07c2e7a68186'
MD = '{http://v8.1c.ru/8.3/MDClasses}'


@dataclass(frozen=True)
class Setup:
    name: str
    metadata_uuid: str
    generated_ids: tuple[str, ...]
    field_ids: tuple[str, ...]
    record_ids: tuple[str, ...]

    def validate(self):
        if type(self.name) is not str or not self.name.isascii() or not self.name.isidentifier() or not 1 <= len(self.name) <= 64:
            raise ValueError('catalog name')
        for items, count in ((self.generated_ids,10),(self.field_ids,3),(self.record_ids,3)):
            if type(items) is not tuple or len(items) != count:
                raise ValueError('identity inventory')
        ids = (self.metadata_uuid, *self.generated_ids, *self.field_ids, *self.record_ids)
        for value in ids:
            if type(value) is not str:
                raise ValueError('identity type')
            try:
                parsed = UUID(value)
            except ValueError:
                raise ValueError('identity') from None
            if not parsed.int or str(parsed) != value:
                raise ValueError('identity')
        if len(set(ids)) != len(ids):
            raise ValueError('identity collision')
        return self


def fresh():
    return Setup('OwnedQuery'+uuid4().hex[:8], str(uuid4()),
                 tuple(str(uuid4()) for _ in range(10)),
                 tuple(str(uuid4()) for _ in range(3)),
                 tuple(str(uuid4()) for _ in range(3))).validate()


def render_xml(setup):
    if type(setup) is not Setup:
        raise ValueError('setup')
    s = setup.validate()
    raw = Path(__file__).with_name('Catalog.xml').read_bytes()
    if hashlib.sha256(raw).hexdigest() != TEMPLATE_SHA256:
        raise ValueError('template changed')
    text = raw.decode('utf-8').replace('@@CATALOG_NAME@@',s.name).replace('@@CATALOG_UUID@@',s.metadata_uuid)
    tokens = tuple('@@'+family+'_'+kind+'_UUID@@' for family in ('OBJECT','REF','SELECTION','LIST','MANAGER') for kind in ('TYPE','VALUE'))
    tokens += ('@@QUANTITY_UUID@@','@@ACTIVE_UUID@@','@@STAMP_UUID@@')
    for token, value in zip(tokens, (*s.generated_ids,*s.field_ids)):
        if text.count(token) != 1:
            raise ValueError('identity token')
        text = text.replace(token,value)
    if '@@' in text:
        raise ValueError('unbound identity')
    root = ET.fromstring(text)
    catalog = root.find(MD+'Catalog')
    if catalog is None or catalog.get('uuid') != s.metadata_uuid or catalog.find(MD+'Properties/'+MD+'Name').text != s.name:
        raise ValueError('catalog identity')
    fields = catalog.find(MD+'ChildObjects')
    if [(x.tag,x.get('uuid'),x.find(MD+'Properties/'+MD+'Name').text) for x in fields] != [
            (MD+'Attribute',i,n) for i,n in zip(s.field_ids,('Quantity','Active','Stamp'))]:
        raise ValueError('field inventory')
    return text.encode('utf-8')


def helper_source():
    return '''Function CQCodes(Result)
S=Result.Select();T="";N=0;
While S.Next() Do
N=N+1;If N>3 Then Raise "owned query row bound";EndIf;
If N>1 Then T=T+",";EndIf;T=T+S.Code;
EndDo;
Return T;
EndFunction
'''


def render_program(setup):
    if type(setup) is not Setup:
        raise ValueError('setup')
    s = setup.validate()
    source = helper_source()+f'''M=Catalogs.{s.name};
'''
    # Deliberately not insertion order. Three fixed refs make parameters and
    # witnesses identity-bound without disclosing random external identities.
    for i in (2,3,1):
        source += f'''P=M.CreateItem();P.SetNewObjectRef(M.GetRef(New UUID("{s.record_ids[i-1]}")));
P.Code="0{i}";P.Description="{('alpha','Alpha','beta')[i-1]}";P.Quantity={i*10};P.Active={'False' if i==2 else 'True'};P.Stamp=Date(2024,2,29,12,0,{i-1});P.Write();
'''
    prefix = f'SELECT Code FROM Catalog.{s.name}'
    source += f'''Q=New Query("{prefix} WHERE Description=&Name ORDER BY Quantity");Q.SetParameter("Name","alpha");CQEmit(1,CQCodes(Q.Execute()));
Q.Text="{prefix} ORDER BY Quantity";R=Q.Execute();S=R.Select();
CQEmit(2,TypeOf(R)=Type("QueryResult"));CQEmit(3,TypeOf(S)=Type("QueryResultSelection"));
Q.Text="{prefix} WHERE Quantity=&Missing";Refused=False;Try Q.Execute();Except Refused=True;EndTry;CQEmit(4,Refused);
Q.Text="{prefix} WHERE Quantity>=&Min ORDER BY Quantity";Q.SetParameter("Min",20);CQEmit(5,CQCodes(Q.Execute()));
Q.Text="{prefix} WHERE Active=&Flag ORDER BY Quantity";Q.SetParameter("Flag",True);CQEmit(6,CQCodes(Q.Execute()));
Q.Text="{prefix} WHERE Stamp>=&Moment ORDER BY Quantity";Q.SetParameter("Moment",Date(2024,2,29,12,0,1));CQEmit(7,CQCodes(Q.Execute()));
Q.Text="{prefix} WHERE Ref=&Item";Q.SetParameter("Item",M.GetRef(New UUID("{s.record_ids[0]}")));CQEmit(8,CQCodes(Q.Execute()));
Q.Text="{prefix} ORDER BY Quantity ASC";CQEmit(9,CQCodes(Q.Execute()));
Q.Text="SELECT TOP 2 Code FROM Catalog.{s.name} ORDER BY Quantity DESC";CQEmit(10,CQCodes(Q.Execute()));
Q.Text="{prefix} WHERE (Quantity=10 OR Quantity=20) AND Active=TRUE ORDER BY Quantity";CQEmit(11,CQCodes(Q.Execute()));
Q.Text="ВЫБРАТЬ П.Код КАК Code ИЗ Справочник.{s.name} КАК П ГДЕ П.Quantity>10 УПОРЯДОЧИТЬ ПО П.Quantity УБЫВ";CQEmit(12,CQCodes(Q.Execute()));
Q.Text="{prefix} WHERE Quantity>100";Empty=Q.Execute();CQEmit(13,Empty.IsEmpty());ES=Empty.Select();CQEmit(14,ES.Next());
Q.Text="{prefix} ORDER BY Quantity";R=Q.Execute();S=R.Select();
Probe="action-error";Try Probe=String(TypeOf(S.Code))+":"+String(S.Code);Except EndTry;CQEmit(16,Probe);
Counter=0;While S.Next() Do Counter=Counter+1;If Counter>3 Then Raise "owned query row bound";EndIf;EndDo;
CQEmit(15,S.Next());Probe="action-error";Try Probe=String(TypeOf(S.Code))+":"+String(S.Code);Except EndTry;CQEmit(17,Probe);
Q.Text="SELECT Code,Quantity,Active,Stamp FROM Catalog.{s.name} ORDER BY Quantity";R=Q.Execute();T=R.Unload();CQEmit(18,TypeOf(T)=Type("ValueTable"));CQEmit(19,T.Count());
CQEmit(20,T.Columns[0].Name+"/"+T.Columns[1].Name+"/"+T.Columns[2].Name+"/"+T.Columns[3].Name);
CQEmit(21,String(T.Columns[0].ValueType)+"/"+String(T.Columns[1].ValueType)+"/"+String(T.Columns[2].ValueType)+"/"+String(T.Columns[3].ValueType));
CQEmit(22,String(T.Columns[0].ValueType.StringQualifiers.Length)+"/"+String(T.Columns[1].ValueType.NumberQualifiers.Digits)+"/"+String(T.Columns[1].ValueType.NumberQualifiers.FractionDigits)+"/"+String(T.Columns[3].ValueType.DateQualifiers.DateFractions));
T[0].Quantity=999;S=R.Select();S.Next();CQEmit(23,String(S.Quantity)+"/"+String(M.FindByCode("01").Quantity));
A=R.Select();B=R.Select();A.Next();A.Next();B.Next();Q.SetParameter("Min",100);
CQEmit(24,A.Code="02" AND B.Code="01" AND R.Unload()[0].Quantity=10);
'''
    # Emission order must be canonical even though the before-position probe
    # must happen before consuming the selection.
    source = source.replace('CQEmit(16,Probe);\nCounter=', 'BeforeProbe=Probe;\nCounter=')
    source = source.replace('CQEmit(15,S.Next());Probe=', 'CQEmit(15,S.Next());CQEmit(16,BeforeProbe);Probe=')
    if len(source.encode('utf-8')) > 16384:
        raise ValueError('program bound')
    return source


def validate_observations(rows):
    if type(rows) not in (tuple,list) or len(rows) != len(CASES):
        raise ValueError('observation count')
    booleans = {2,3,4,13,14,15,18,24}
    for index,value in enumerate(rows,1):
        if index in booleans:
            if type(value) is not bool:
                raise ValueError('boolean observation')
        elif index == 19:
            if type(value) is not Decimal or not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 3:
                raise ValueError('count observation')
        elif type(value) is not str or len(value) > 64 or any(c in value for c in '|\r\n'):
            raise ValueError('text observation')
    return True


def load_saved():
    root = Path(__file__).with_name('generated')
    raw = (root/'setup.json').read_bytes()
    if len(raw) > 8192:
        raise ValueError('setup bound')
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError('duplicate setup key')
            result[key] = value
        return result
    obj = json.loads(raw, object_pairs_hook=pairs)
    if type(obj) is not dict or set(obj) != {'name','metadata_uuid','generated_ids','field_ids','record_ids'}:
        raise ValueError('setup shape')
    for key in ('generated_ids','field_ids','record_ids'):
        if type(obj[key]) is not list: raise ValueError('setup identity list')
        obj[key] = tuple(obj[key])
    setup = Setup(**obj).validate()
    xml = (root/'Catalog.xml').read_bytes()
    source = (root/'observe.bsl').read_bytes()
    if xml != render_xml(setup) or source != render_program(setup).encode('utf-8'):
        raise ValueError('saved render mismatch')
    return setup, xml, source
