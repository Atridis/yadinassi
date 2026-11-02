"""Fresh CatalogObject behavior observations: official XML/BSL interchange only.

One disposable configuration, one sequential session, 24 scalar observations.
No physical database inspection; no expected native duplicate/stale outcome.
"""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID,uuid4
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

CASES=('new.is_new','new.empty_ref','assigned.before_write_empty','assigned.absent',
       'written.not_new','written.fixed_ref','written.lookup_ref','loaded.not_new',
       'detached.persisted_unchanged','cancel.persisted_unchanged','edited.not_new',
       'edited.ref_stable','edited.readback','duplicate.write_succeeded','duplicate.is_new',
       'duplicate.empty_ref','duplicate.original_code','duplicate.record_count',
       'stale.write_succeeded','stale.persisted_description','stale.buffer_description',
       'reload.ref_stable','object.type_identity','reference.metadata_identity')

@dataclass(frozen=True)
class Setup:
    name:str
    metadata_uuid:str
    record_uuid:str
    generated_ids:tuple[str,...]
    def validate(self):
        if type(self.name) is not str or not self.name.isascii() or not self.name.isidentifier() or not 1<=len(self.name)<=64:
            raise ValueError('catalog name')
        if type(self.generated_ids) is not tuple or len(self.generated_ids)!=10:raise ValueError('generated IDs')
        ids=[]
        for value in (self.metadata_uuid,self.record_uuid,*self.generated_ids):
            if type(value) is not str:raise ValueError('UUID')
            try: parsed=UUID(value)
            except ValueError:raise ValueError('UUID') from None
            if not parsed.int or str(parsed)!=value:raise ValueError('UUID')
            ids.append(parsed)
        if len(set(ids))!=len(ids):raise ValueError('identity collision')
        return self

def fresh():
    return Setup('OwnedCatalog'+uuid4().hex[:8],str(uuid4()),str(uuid4()),tuple(str(uuid4()) for _ in range(10))).validate()

def render_program(setup):
    if type(setup) is not Setup:raise ValueError('setup')
    s=setup.validate()
    source=f'''M=Catalogs.{s.name};
P=M.CreateItem();
CBOEmit(1,P.IsNew()); CBOEmit(2,P.Ref.IsEmpty());
R=M.GetRef(New UUID("{s.record_uuid}"));P.SetNewObjectRef(R);
CBOEmit(3,P.Ref.IsEmpty());CBOEmit(4,R.GetObject()=Undefined);
P.Code="100";P.Description="initial";P.Write();
CBOEmit(5,Not P.IsNew());CBOEmit(6,P.Ref=R);CBOEmit(7,M.FindByCode("100")=R);
O=R.GetObject();CBOEmit(8,Not O.IsNew());O.Description="discarded";
CBOEmit(9,R.Description);O=Undefined;CBOEmit(10,R.GetObject().Description);
E=R.GetObject();E.Description="edited";E.Write();
CBOEmit(11,Not E.IsNew());CBOEmit(12,E.Ref=R);CBOEmit(13,R.Description);
D=M.CreateItem();D.Code="100";D.Description="duplicate";DuplicateSucceeded=False;
Try D.Write();DuplicateSucceeded=True;Except EndTry;
CBOEmit(14,DuplicateSucceeded);CBOEmit(15,D.IsNew());CBOEmit(16,D.Ref.IsEmpty());
CBOEmit(17,R.Code);
CS=M.Select();CBOCount=0;While CS.Next() Do
CBOCount=CBOCount+1;If CBOCount>3 Then Raise "owned row bound";EndIf;
EndDo;CBOEmit(18,CBOCount);
A=R.GetObject();B=R.GetObject();A.Description="first-update";A.Write();
B.Description="stale-update";StaleSucceeded=False;
Try B.Write();StaleSucceeded=True;Except EndTry;
CBOEmit(19,StaleSucceeded);CBOEmit(20,R.Description);CBOEmit(21,B.Description);
CBOEmit(22,R.GetObject().Ref=R);CBOEmit(23,TypeOf(E)=Type("CatalogObject.{s.name}"));
CBOEmit(24,R.Metadata()=Metadata.Catalogs.{s.name});
'''
    if len(source.encode('utf-8'))>8192:raise ValueError('source bound')
    return source

def validate_observations(rows):
    if type(rows) not in (list,tuple) or len(rows)!=24:raise ValueError('observation count')
    strings={9,10,13,17,20,21}
    for i,value in enumerate(rows,1):
        if i==18:
            if type(value) is not Decimal or not value.is_finite() or value!=value.to_integral_value() or not 0<=value<=3:raise ValueError('count observation')
        elif i in strings:
            if type(value) is not str or len(value)>64:raise ValueError('scalar observation')
        elif type(value) is not bool:raise ValueError('boolean observation')
    return True

TEMPLATE_SHA256='810823e2481d9aa56f2526a778fc1c3df75597d183e8107e885db04ea19fc8dc'

def render_xml(setup):
    if type(setup) is not Setup:raise ValueError('setup')
    s=setup.validate();raw=Path(__file__).with_name('Catalog.xml').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=TEMPLATE_SHA256:raise ValueError('template changed')
    text=raw.decode('utf-8').replace('@@CATALOG_NAME@@',s.name).replace('@@CATALOG_UUID@@',s.metadata_uuid)
    tokens=tuple('@@'+family+'_'+kind+'_UUID@@' for family in ('OBJECT','REF','SELECTION','LIST','MANAGER') for kind in ('TYPE','VALUE'))
    for token,value in zip(tokens,s.generated_ids):
        if text.count(token)!=1:raise ValueError('template identity')
        text=text.replace(token,value)
    if '@@' in text:raise ValueError('unbound token')
    root=ET.fromstring(text);md='{http://v8.1c.ru/8.3/MDClasses}'
    catalog=root.find(md+'Catalog')
    if catalog is None or catalog.get('uuid')!=s.metadata_uuid or catalog.find(md+'Properties/'+md+'Name').text!=s.name:raise ValueError('catalog identity')
    if len(catalog.find(md+'ChildObjects')):raise ValueError('unexpected children')
    return text.encode('utf-8')
