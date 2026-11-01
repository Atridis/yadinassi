"""Finite install errors and bounded identity-verified synthetic redump XML.

These are the two source-owned disposable fixtures, never arbitrary metadata or
user data. Capturing a redump does not admit its defaults or physical layout.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from linked_card_diagnostics import PHASES, collect, validate, INSTALL_STAGES
from protocol import require, exact, digest, OracleError

MD='{http://v8.1c.ru/8.3/MDClasses}'
CATEGORIES=('document-lines-redump-inventory','document-lines-redump-profile','lines-profile','lines-xml-profile','lines-fragments','lines-xml-budget','lines-generated-types','baseline-document-catalog-inventory','document-redump-inventory','document-redump-profile','document-profile','document-xml-budget','schema-provenance',
    'saved-xml-bound','saved-namespace-profile','saved-xml','saved-xml-profile',
    'saved-fragments','configuration-bound','configuration-children',
    'configuration-span','baseline-catalogs','baseline-documents','baseline-children',
    'rights-bound','rights-profile','document-rights','document-xml',
    'other-value-error','import-error','filesystem-error','oracle-error','unexpected')


def _identity(raw):
    require(type(raw) is bytes and 0<len(raw)<=65536 and b'<!' not in raw,'artifact_limit')
    text=raw.decode('utf-8-sig')
    root=ET.fromstring(text)
    require(root.tag==MD+'MetaDataObject' and len(root)==1,'metadata_rejected')
    obj=root[0];kind=obj.tag.removeprefix(MD)
    require(kind in ('Document','Catalog') and obj.tag==MD+kind,'metadata_rejected')
    name=obj.findtext(MD+'Properties/'+MD+'Name');uuid=obj.get('uuid')
    require(type(name) is str and re.fullmatch(('D' if kind=='Document' else 'C')+'[0-9a-f]{8}',name) is not None,'metadata_rejected')
    require(type(uuid) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',uuid) is not None,'metadata_rejected')
    count=0
    def walk(node,depth):
        nonlocal count
        count+=1
        require(depth<=32 and count<=2048 and len(node.attrib)<=32,'artifact_limit')
        require(type(node.tag) is str and len(node.tag)<=512,'artifact_limit')
        for child in node:walk(child,depth+1)
    walk(root,0)
    # Duplicate property/object identities must not authorize capture.
    require(len(obj.findall(MD+'Properties'))==1 and len(obj.findall(MD+'Properties/'+MD+'Name'))==1,'metadata_rejected')
    return dict(kind=kind,name=name,metadata_uuid=uuid),count


def _projection(expected,raw):
    source,_=_identity(expected)
    actual,count=_identity(raw)
    require(actual==source,'metadata_rejected')
    return dict(identity=source,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                tags=count,xml_hex=raw.hex())


def install_failure(stage,error,saved,redumped):
    require(stage in INSTALL_STAGES)
    if isinstance(error,OracleError):category='oracle-error'
    elif isinstance(error,ImportError):category='import-error'
    elif isinstance(error,OSError):category='filesystem-error'
    elif isinstance(error,ValueError):category=str(error) if str(error) in CATEGORIES else 'other-value-error'
    else:category='unexpected'
    require(type(saved) is dict and len(saved)<=2,'artifact_limit')
    rows=[]
    for index,(name,expected) in enumerate(saved.items()):
        if name not in redumped:continue
        raw=redumped[name]
        require(type(raw) is bytes and len(raw)<=65536,'artifact_limit')
        row=dict(index=index,source_sha256=hashlib.sha256(expected).hexdigest(),
                 actual_bytes=len(raw),actual_sha256=hashlib.sha256(raw).hexdigest(),owned_xml=None)
        try:row['owned_xml']=_projection(expected,raw)
        except (OracleError,ValueError,ET.ParseError,UnicodeError):pass
        rows.append(row)
    value=dict(stage=stage,category=category,objects=rows)
    validate_install_failure(value,saved)
    return value


def validate_install_failure(value,saved):
    exact(value,('stage','category','objects'))
    require(value['stage'] in INSTALL_STAGES and value['category'] in CATEGORIES)
    rows=value['objects'];require(type(rows) is list and len(rows)<=2)
    source=list(saved.values());previous=-1
    for row in rows:
        exact(row,('index','source_sha256','actual_bytes','actual_sha256','owned_xml'))
        i=row['index'];require(type(i) is int and previous<i<len(source));previous=i
        require(row['source_sha256']==hashlib.sha256(source[i]).hexdigest() and digest(row['actual_sha256']))
        require(type(row['actual_bytes']) is int and 0<=row['actual_bytes']<=65536)
        capture=row['owned_xml']
        if capture is None:continue
        exact(capture,('identity','bytes','sha256','tags','xml_hex'))
        rawhex=capture['xml_hex']
        require(type(rawhex) is str and len(rawhex)<=131072 and re.fullmatch('[0-9a-f]*',rawhex) is not None)
        raw=bytes.fromhex(rawhex)
        require(capture==_projection(source[i],raw),'logical_mismatch')
        require(capture['bytes']==row['actual_bytes'] and capture['sha256']==row['actual_sha256'],'logical_mismatch')
    return value
