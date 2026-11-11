"""Build the separate authored 2.20 source, not a native dump acceptance shim.

Retain only the explicitly proposed accumulation-reference-v1 source grant.
This deterministic developer utility is never staged for native acquisition.
Native material signatures compare this projection in host regression tests;
actual native acceptance is established only by the Designer redump gate.
"""
from pathlib import Path
from copy import deepcopy
from uuid import uuid5
from xml.etree import ElementTree as ET
from .native_source import NAMESPACE
ROOT=Path(__file__).parent
MD='http://v8.1c.ru/8.3/MDClasses'
V8='http://v8.1c.ru/8.1/data/core'
XR='http://v8.1c.ru/8.3/xcf/readable'
XSI='http://www.w3.org/2001/XMLSchema-instance'
def tag(name):return '{'+MD+'}'+name
def emit(obj):
    root=ET.Element(tag('MetaDataObject'),{'version':'2.20','xmlns:xs':'http://www.w3.org/2001/XMLSchema','xmlns:cfg':'http://v8.1c.ru/8.1/data/enterprise/current-config'})
    root.append(obj)
    # This offline, single-threaded developer utility must not change the
    # namespace choices of its importing process, including other XML tests.
    previous = ET._namespace_map.copy()
    try:
        for prefix, uri in (('',MD),('v8',V8),('xr',XR),('xsi',XSI)):
            ET.register_namespace(prefix, uri)
        return ET.tostring(root,encoding='utf-8',xml_declaration=True)
    finally:
        ET._namespace_map.clear()
        ET._namespace_map.update(previous)
def fields(source):
    result=ET.Element(tag('ChildObjects'))
    for child in source:
        kind=child.tag.removeprefix('{'+MD+'}')
        node=ET.SubElement(result,child.tag,dict(child.attrib));props=ET.SubElement(node,tag('Properties'))
        old=child.find(tag('Properties'))
        for name in ('Name','Type','UseInTotals'):
            field=old.find(tag(name))
            if field is not None:props.append(deepcopy(field))
        if kind=='TabularSection':node.append(fields(child.find(tag('ChildObjects'))))
    return result

def derive():
    files={};config=ET.Element(tag('Configuration'),{'uuid':str(uuid5(NAMESPACE,'Configuration'))})
    props=ET.SubElement(config,tag('Properties'));ET.SubElement(props,tag('Name')).text='InventoryReferences'
    declarations=ET.SubElement(config,tag('ChildObjects'))
    for kind,name,folder in [('Catalog','Products','Catalogs'),('Catalog','Warehouses','Catalogs'),('Document','Receipt','Documents'),('Document','Issue','Documents'),('AccumulationRegister','Stock','AccumulationRegisters')]:
        old=ET.fromstring((ROOT/(name+'.xml')).read_bytes())[0]
        obj=ET.Element(tag(kind),dict(old.attrib));props=ET.SubElement(obj,tag('Properties'));oldprops=old.find(tag('Properties'))
        wanted={'Catalog':('Name','CodeType','CodeLength','DescriptionLength','CodeAllowedLength','CheckUnique','Autonumbering','Hierarchical'),
                'Document':('Name','NumberType','NumberLength','NumberPeriodicity','CheckUnique','Autonumbering','Posting','RealTimePosting','RegisterRecordsDeletion','RegisterRecordsWritingOnPost','RegisterRecords','PostInPrivilegedMode','UnpostInPrivilegedMode'),
                'AccumulationRegister':('Name','RegisterType','EnableTotalsSplitting')}[kind]
        for key in wanted:props.append(deepcopy(oldprops.find(tag(key))))
        obj.append(fields(old.find(tag('ChildObjects'))))
        files[folder+'/'+name+'.xml']=emit(obj);ET.SubElement(declarations,tag(kind)).text=name
        if kind=='Document':files[folder+'/'+name+'/Ext/ObjectModule.bsl']=(ROOT/(name+'Module.bsl')).read_bytes()
    files['Configuration.xml']=emit(config);return files
if __name__=='__main__':
    for name,raw in derive().items():
        path=ROOT/'runtime_source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
