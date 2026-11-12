"""Три собственных модуля и один параметр только в проверенной временной базе."""
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
SESSION_ANCHOR='Процедура УстановкаПараметровСеанса(ТребуемыеПараметры)'
APPLICATION_ANCHOR='Процедура ПриНачалеРаботыСистемы()'
SESSION_INSERT='\n    SessionParameters.CPState = CPMaskEN()+":"+CPMaskRU()+":"+CPMobileEN()+":"+CPMobileRU();\n'
APPLICATION_INSERT='\n    CPStartup = "0";\n#If Client And Not Client Then\n    CPStartup = "99";\n#EndIf\n'

def insert_exact(raw,anchor,addition):
    text=route.normalized(raw).decode('utf-8')
    original._require(text.count(anchor)==1)
    return text.replace(anchor,anchor+addition,1).encode('utf-8')

def prepare(files, bootstrap_module, bootstrap_application):
    setup=original.load_saved()[0]
    original._baseline(files,setup)
    original._require(not any(p.startswith(('CommonModules/','SessionParameters/')) for p in files))
    original._require(route.normalized(files['Ext/SessionModule.bsl'])==route.normalized(bootstrap_module))
    original._require(route.normalized(files['Ext/ManagedApplicationModule.bsl'])==route.normalized(bootstrap_application))
    expected=dict(files);md=original.MD
    children=lambda p:''.join('<'+p+'CommonModule>'+n+'</'+p+'CommonModule>' for n in ('ClientProbe','ServerProbe','DualProbe'))+'<'+p+'SessionParameter>CPState</'+p+'SessionParameter>'
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),children)
    packet=route.sources()
    expected.update({p:raw for p,raw in packet.items() if p.startswith(('CommonModules/','SessionParameters/'))})
    expected['Ext/SessionModule.bsl']=insert_exact(files['Ext/SessionModule.bsl'],SESSION_ANCHOR,SESSION_INSERT)+b'\n'+packet['Extensions/Session.bsl']
    expected['Ext/ManagedApplicationModule.bsl']=b'Var CPStartup;\n'+insert_exact(files['Ext/ManagedApplicationModule.bsl'],APPLICATION_ANCHOR,APPLICATION_INSERT)+b'\n'+packet['Extensions/Application.bsl']
    original._files(expected)
    used=set()
    for path,raw in expected.items():
        if path.endswith('.xml'):
            root,_=original._xml(raw)
            for node in root.iter():
                if 'uuid' in node.attrib:
                    value=original._uuid(node.attrib['uuid'])
                    original._require(value not in used);used.add(value)
    return expected
