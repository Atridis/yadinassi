"""Explicit fresh-only source grant for a closed document/recorder profile.

Not wired to legacy import/open paths. All source bytes remain immutable and
canonical admission reimports those bytes with the identical explicit grant.
The initial profile excludes catalog/UI/common-module grants and migrations.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID
from . import configuration_xml as xml
from .document_movements import RecorderRegisterSchema

PROFILE='document-recorder-scalar-v1'
FORMAT_VERSION=13


@dataclass(frozen=True,slots=True)
class PostingConfiguration:
    identity: UUID
    name: str
    files: tuple
    documents: tuple
    registers: tuple
    handlers: tuple
    profile: str
    source_digest: str


def import_posting_configuration(files,*,posting_runtime=None):
    if type(posting_runtime) is not str or posting_runtime!=PROFILE:raise ValueError('explicit posting source grant required')
    if type(files) is not dict or not 1<=len(files)<=xml.MAX_FILES:raise ValueError('posting source count')
    total=0
    for path,raw in files.items():
        if type(path) is not str or type(raw) is not bytes or len(raw)>xml.MAX_FILE_BYTES:raise ValueError('posting source shape')
        total+=len(raw)
    if total>xml.MAX_TOTAL_BYTES or 'Configuration.xml' not in files:raise ValueError('posting source budget')
    obj,ns,root=xml._object(files['Configuration.xml'],'Configuration',include_root=True)
    props=xml._props(obj);identity=xml._uuid(obj.get('uuid'));name=xml._name(xml._text(props,'Name'))
    issues=[];xml._envelope_issues(root,obj,issues,name)
    xml._activation_properties(obj,{'Name','Synonym','Comment'},issues,name)
    child=obj.find('{'+xml.MD+'}ChildObjects');declared={};used={identity}
    if child is None:raise ValueError('posting declarations missing')
    for item in child:
        kind=item.tag.removeprefix('{'+xml.MD+'}')
        if kind not in ('Document','InformationRegister') or item.tag!='{'+xml.MD+'}'+kind or len(item) or item.attrib:raise ValueError('unsupported posting declaration')
        n=xml._name(item.text or '');key=(kind,n)
        if any(k==kind and v.casefold()==n.casefold() for k,v in declared):raise ValueError('duplicate posting declaration')
        path=('Documents/' if kind=='Document' else 'InformationRegisters/')+n+'.xml'
        if path not in files:raise ValueError('posting metadata missing')
        declared[key]=path
    if len(declared)>512:raise ValueError('posting metadata bound')
    documents=[];registers=[];links={};handlers=[];accepted={'Configuration.xml'}
    for (kind,n),path in sorted(declared.items()):
        accepted.add(path)
        if kind=='Document':
            document=xml._document_schema(files[path],n,{},used,issues,recorder_profile=True)
            node,ns=xml._object(files[path],'Document');p=xml._props(node)
            for key,value in (('RealTimePosting','Deny'),('RegisterRecordsDeletion','AutoDeleteOnUnpost'),('RegisterRecordsWritingOnPost','WriteSelected'),('PostInPrivilegedMode','false'),('UnpostInPrivilegedMode','false')):
                if xml._text(p,key)!=value:raise ValueError('unsupported posting controls')
            recorders=p.get('{'+xml.MD+'}RegisterRecords');targets=[]
            if recorders is None:raise ValueError('recorder declarations missing')
            for item in recorders:
                text=item.text or ''
                xr='http://v8.1c.ru/8.3/xcf/readable';xsi='http://www.w3.org/2001/XMLSchema-instance'
                qname=item.get('{'+xsi+'}type','').split(':')
                if (item.tag!='{'+xr+'}Item' or set(item.attrib)!={'{'+xsi+'}type'} or len(qname)!=2 or ns[id(item)].get(qname[0])!=xr or qname[1]!='MDObjectRef' or (item.tail or '').strip()):raise ValueError('unknown recorder XML grant')
                if len(item) or not text.startswith('InformationRegister.') or text.count('.')!=1:raise ValueError('recorder declaration')
                target=text.split('.')[1]
                if ('InformationRegister',target) not in declared or target in targets:raise ValueError('recorder target')
                targets.append(target)
            if not targets:raise ValueError('empty posting movements')
            links[document.identity]=tuple(targets);documents.append(document)
            module='Documents/'+n+'/Ext/ObjectModule.bsl'
            if module not in files:raise ValueError('posting handler source missing')
            files[module].decode('utf-8-sig');accepted.add(module);handlers.append((document.identity,module,sha256(files[module]).hexdigest()))
        else:
            register=xml._register_schema(files[path],n,{},used,issues,recorder_profile=True)
            if register.periodicity!='Nonperiodical':raise ValueError('periodic recorder profile unsupported')
            if any(f.kind not in ('string','number','boolean','datetime') for f in register.declared_fields):raise ValueError('recorder scalar fields only')
            registers.append(register)
    if not documents or not registers or issues or set(files)!=accepted:raise ValueError('unsupported posting source or executable grant')
    schemas=[]
    for register in registers:
        owners=tuple(sorted((d for d,targets in links.items() if register.name in targets),key=str))
        if not owners:raise ValueError('unowned recorder register')
        schemas.append(RecorderRegisterSchema(register.identity,owners,register.declared_fields,register.name,len(register.dimensions)))
    source=tuple((path,files[path]) for path in sorted(files))
    digest=sha256(b''.join(path.encode()+b'\0'+sha256(raw).digest() for path,raw in source)).hexdigest()
    return PostingConfiguration(identity,name,source,tuple(sorted(documents,key=lambda d:str(d.identity))),tuple(schemas),tuple(handlers),PROFILE,digest)


def canonical(config):
    if type(config) is not PostingConfiguration or config.profile!=PROFILE:raise ValueError('posting configuration required')
    fresh=import_posting_configuration(dict(config.files),posting_runtime=PROFILE)
    if fresh!=config:raise ValueError('posting source/schema divergence')
    return fresh


def validate_shape_projection(obj, kind):
    """Validate measured passive metadata before legacy scalar shape parsing.

    This only removes validated passive nodes from the temporary parsed tree;
    original XML and all UUIDs remain bound in the canonical source digest.
    """
    defaults={'UseStandardCommands':'false','StandardAttributes':'',
        'DataLockControlMode':'Managed'}
    defaults.update({'NumberAllowedLength':'Variable','SequenceFilling':'AutoFill'}
        if kind=='Document' else {'EnableTotalsSliceFirst':'false','EnableTotalsSliceLast':'false'})
    props=xml._props(obj);container=obj.find('{'+xml.MD+'}Properties')
    for name,value in defaults.items():
        node=props.get('{'+xml.MD+'}'+name)
        if node is not None:
            if node.attrib or len(node) or (node.text or '')!=value or (node.tail or '').strip():
                raise ValueError('unsupported posting passive property')
            container.remove(node)
    internal=obj.find('{'+xml.MD+'}InternalInfo')
    if internal is None:return
    if internal.attrib or (internal.text or '').strip() or (internal.tail or '').strip():
        raise ValueError('unsupported posting internal envelope')
    xr='{http://v8.1c.ru/8.3/xcf/readable}'
    categories=(('Object','Ref','Selection','List','Manager') if kind=='Document' else
        ('Record','Manager','Selection','List','RecordSet','RecordKey','RecordManager'))
    name=xml._text(props,'Name');seen=set();ids=set()
    for node in internal:
        category=node.get('category')
        expected=kind+category+'.'+name if category in categories else ''
        if (node.tag!=xr+'GeneratedType' or node.attrib!={'name':expected,'category':category}
                or category in seen or (node.text or '').strip() or (node.tail or '').strip()
                or [child.tag for child in node]!=[xr+'TypeId',xr+'ValueId']):
            raise ValueError('unsupported posting generated identity')
        seen.add(category)
        for child in node:
            if child.attrib or len(child) or (child.tail or '').strip():
                raise ValueError('unsupported posting generated identity')
            identity=xml._uuid(child.text or '')
            if identity in ids:raise ValueError('duplicate posting generated identity')
            ids.add(identity)
    if seen and seen!=set(categories):raise ValueError('incomplete posting generated identities')
    obj.remove(internal)
