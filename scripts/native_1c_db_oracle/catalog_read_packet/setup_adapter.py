"""LOCAL closed source/setup adapter. No native runner; no current lane changes.

Input is an already inspected existing owned v1 export. Replay SAVED catalog
fragments and IDs; never call catalog_artifacts during replay/redump verification.
"""
import hashlib
from xml.parsers import expat
import xml.etree.ElementTree as ET
from pathlib import Path
from . import probe
from . import scalar_wire

MD='http://v8.1c.ru/8.3/MDClasses'
XR='http://v8.1c.ru/8.3/xcf/readable'

def parse_xml(raw):
    try:return ET.fromstring(raw)
    except ET.ParseError:raise ValueError('invalid-xml') from None


def validate_saved(s,fragments,ids):
    s.validate()
    if type(fragments) is not dict or set(fragments)!={f'Catalogs/{n}.xml' for n in s.names} or type(ids) is not dict or set(ids)!=set(s.names):raise ValueError('saved-shape')
    used=set(s.record_ids)
    expected={'CATALOG_UUID'}|{f'{category}_{suffix}_UUID' for category in ('OBJECT','REF','SELECTION','LIST','MANAGER') for suffix in ('TYPE','VALUE')}
    for name,identity in zip(s.names,s.metadata_ids):
        mapping=ids[name]
        if type(mapping) is not dict or set(mapping)!=expected or mapping['CATALOG_UUID']!=identity:raise ValueError('saved-identity')
        raw=fragments[f'Catalogs/{name}.xml']
        if type(raw) is not bytes or len(raw)>65536 or b'<!' in raw:raise ValueError('saved-xml')
        root=parse_xml(raw);catalog=root.find('{'+MD+'}Catalog')
        if catalog is None or catalog.attrib!={'uuid':identity}:raise ValueError('saved-catalog')
        if catalog.findtext('{'+MD+'}Properties/{'+MD+'}Name')!=name:raise ValueError('saved-name')
        children=catalog.find('{'+MD+'}ChildObjects')
        if children is None or len(children)!=0:raise ValueError('saved-children')
        nodes=catalog.findall('{'+MD+'}InternalInfo/{'+XR+'}GeneratedType')
        if len(nodes)!=5:raise ValueError('saved-types')
        for node in nodes:
            category=node.attrib.get('category','')
            if category not in ('Object','Ref','Selection','List','Manager') or node.attrib.get('name')!=f'Catalog{category}.{name}':raise ValueError('saved-type')
            for suffix,tag in [('TYPE','TypeId'),('VALUE','ValueId')]:
                if node.findtext('{'+XR+'}'+tag)!=mapping[f'{category.upper()}_{suffix}_UUID']:raise ValueError('saved-type-id')
        for value in mapping.values():
            if type(value) is not str or str(probe.uuid.UUID(value))!=value or probe.uuid.UUID(value).int==0 or value in used:raise ValueError('saved-collision')
            used.add(value)
        # Close the entire permitted XML shape against the pinned source, not
        # merely selected identity fields. Whitespace-only redump changes allowed.
        template=Path(probe.__file__).with_name('Catalog.xml').read_bytes()
        if hashlib.sha256(template).hexdigest()!='612fa20fc7a30262c27ccb52201ce57bbbba8cbbab60ae9ac82e0358a36024c5':raise ValueError('template-provenance')
        text=template.decode('utf-8-sig');start=text.index('<ChildObjects>');end=text.index('</ChildObjects>')
        text=text[:start]+'<ChildObjects/>'+text[end+len('</ChildObjects>'):]
        text=text.replace('NativeOracleItems',name)
        for key,value in mapping.items():text=text.replace('@@'+key+'@@',value)
        def signature(node):
            return node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),(node.tail or '').strip(),tuple(signature(c) for c in node)
        if signature(root)!=signature(parse_xml(text)):raise ValueError('saved-profile')
    return True


def add_refs(raw,s):
    """Existing injector's bounded Expat byte-splice pattern, no XML rewrite."""
    s.validate()
    if type(raw) is not bytes or len(raw)>1048576 or b'<!' in raw:raise ValueError('configuration-bound')
    root=parse_xml(raw)
    children=root.find('{'+MD+'}Configuration/{'+MD+'}ChildObjects')
    if children is None or [n.text for n in children if n.tag=='{'+MD+'}Catalog']!=['NativeOracleItems']:raise ValueError('baseline-catalogs')
    parser,stack,spans=expat.ParserCreate(),[],[]
    def start(name,attrs):
        stack.append(name.split(':')[-1])
        if stack==['MetaDataObject','Configuration','ChildObjects']:
            if attrs:raise ValueError('configuration-children')
            index=parser.CurrentByteIndex;spans.append((index,raw.find(b'>',index)+1,name))
    parser.StartElementHandler=start;parser.EndElementHandler=lambda _:stack.pop();parser.Parse(raw,True)
    if len(spans)!=1:raise ValueError('configuration-span')
    start,end,name=spans[0];prefix=name.rsplit(':',1)[0]+':' if ':' in name else ''
    refs=''.join(f'<{prefix}Catalog>{n}</{prefix}Catalog>' for n in s.names).encode()
    # Existing v1 has baseline child references, so self-closing is invalid.
    if raw[start:end].rstrip().endswith(b'/>'):raise ValueError('baseline-children')
    return raw[:end]+refs+raw[end:]


def add_rights(raw,s):
    s.validate()
    if type(raw) is not bytes or len(raw)>65536 or b'<!' in raw:raise ValueError('rights-bound')
    rights_root=parse_xml(raw)
    rns='{http://v8.1c.ru/8.2/roles}'
    names=[node.findtext(rns+'name') for node in rights_root.findall(rns+'object')]
    if len(names)!=2 or len(set(names))!=2 or any('Catalog.'+n in names for n in s.names):raise ValueError('rights-objects')
    configs=[n for n in names if type(n) is str and n.startswith('Configuration.')]
    if len(configs)!=1 or not probe.re.fullmatch(r'[^\W\d]\w*',configs[0][len('Configuration.'):]):raise ValueError('rights-configuration')
    template=Path(__file__).with_name('CRUDRights.xml').read_bytes()
    if hashlib.sha256(template).hexdigest()!='2fff57d1bff111e1b592e25129b5b03adbc664571189b38f0ef77ca91555ef21':raise ValueError('rights-template-provenance')
    expected_root=parse_xml(template.replace(b'@@CONFIGURATION_NAME@@',configs[0][len('Configuration.'):].encode()))
    def signature(node):
        return node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),(node.tail or '').strip(),tuple(sorted(signature(c) for c in node))
    if signature(rights_root)!=signature(expected_root):raise ValueError('rights-profile')
    anchor=b'<object><name>Catalog.NativeOracleItems</name>'
    if raw.count(anchor)!=1 or raw.count(b'</Rights>')!=1:raise ValueError('rights-anchor')
    start=raw.index(anchor);end=raw.find(b'</object>',start)+len(b'</object>')
    if end<len(b'</object>'):raise ValueError('rights-object')
    obj=raw[start:end]
    expected={('Read','true'),('Insert','true'),('Update','true'),('Delete','true')}
    node=parse_xml(obj)
    actual={(r.findtext('name'),r.findtext('value')) for r in node.findall('right')}
    if actual!=expected or len(node.findall('right'))!=4:raise ValueError('rights-profile')
    added=b''.join(obj.replace(b'NativeOracleItems',n.encode()) for n in s.names)
    result=raw.replace(b'</Rights>',added+b'</Rights>');parse_xml(result);return result


def extend_sources(s,saved_fragments,saved_ids,configuration,crud_rights):
    validate_saved(s,saved_fragments,saved_ids)
    return {**saved_fragments,'Configuration.xml':add_refs(configuration,s),
      'Roles/NativeOracleCatalogCRUD/Ext/Rights.xml':add_rights(crud_rights,s)}


def verify_redump(s,saved_fragments,saved_ids,redumped_fragments):
    # First verify both against the SAME saved identities (not regenerated IDs).
    validate_saved(s,saved_fragments,saved_ids);validate_saved(s,redumped_fragments,saved_ids)
    def signature(node):
        return node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(signature(c) for c in node)
    for name in saved_fragments:
        if signature(parse_xml(saved_fragments[name]))!=signature(parse_xml(redumped_fragments[name])):raise ValueError('redump-mismatch')
    return True


def render_setup(s):
    """Setup-only native Query/Write; NOT part of proposed public runtime scope."""
    s.validate();u,v=s.record_ids
    observer=Path(probe.__file__).with_name('observer.bsl').read_text()
    split=observer.index('Сообщить("CR-C1:')
    text=observer[:split]
    text+='''
Функция CRCount(Name, Ref = Неопределено)
    Q = Новый Запрос;
    Q.Текст = "ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК N ИЗ Справочник." + Name;
    Если Ref <> Неопределено Тогда
        Q.Текст = Q.Текст + " ГДЕ Ссылка = &Ref";
        Q.УстановитьПараметр("Ref", Ref);
    КонецЕсли;
    Row = Q.Выполнить().Выбрать();
    Если Не Row.Следующий() Тогда ВызватьИсключение "setup-count"; КонецЕсли;
    Возврат Row.N;
КонецФункции
'''
    text+=observer[split:]
    for offset,name in zip((0,6),s.names):
        # Fresh owned catalog required. Stop setup rather than modifying a reused DB.
        text+=f'''Если CRCount("{name}") <> 0 Тогда ВызватьИсключение "setup-not-empty"; КонецЕсли;
CREmit("{offset+1:02}", CRCount("{name}"));
Manager = Catalogs.{name};
RefU = Manager.GetRef(New UUID("{u}"));
RefV = Manager.GetRef(New UUID("{v}"));
Object = Manager.СоздатьЭлемент();
Object.УстановитьСсылкуНового(RefU);
Object.Код = "1";
Object.Записать();
CREmit("{offset+2:02}", CRCount("{name}"));
CREmit("{offset+3:02}", CRCount("{name}", RefU));
CREmit("{offset+4:02}", CRCount("{name}", RefV));
CREmit("{offset+5:02}", String(Object.Ссылка.UUID()));
CREmit("{offset+6:02}", Object.Ссылка = RefU);
'''
    return text


def require_setup_evidence(raw,s):
    s.validate();records=scalar_wire.validate_output(raw,case_count=12)
    for offset in (0,6):
        values=[('number',0),('number',1),('number',1),('number',0),('string',tuple(map(ord,s.record_ids[0]))),('boolean',True)]
        for i,(kind,value) in enumerate(values,offset):
            if records[i]!=dict(id=i+1,status='ok',kind=kind,value=value):raise ValueError('setup-evidence')
    return records
