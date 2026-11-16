"""Три собственных модуля и один параметр только в проверенной временной базе."""
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
SESSION_ANCHOR='Процедура УстановкаПараметровСеанса(ТребуемыеПараметры)'
APPLICATION_ANCHOR='Процедура ПриНачалеРаботыСистемы()'
SESSION_INSERT='\n    SessionParameters.CPState = CPSessionMaskEN()+":"+CPSessionMaskRU()+":"+CPSessionMobileEN()+":"+CPSessionMobileRU();\n'
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
    # A session parameter requires explicit read/write rights (1Ci standards).
    # Only the owned calibration parameter is added; baseline grants stay exact.
    rights=original.ROLE_FILES[1];rn=original.RIGHTS
    expected[rights]=original._append(files[rights],(rn+'}Rights',),lambda p:
        '<'+p+'object><'+p+'name>SessionParameter.CPState</'+p+'name>'+''.join(
            '<'+p+'right><'+p+'name>'+right+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>'
            for right in ('Get','Set'))+'</'+p+'object>')
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

def verify_loaded_rights(expected,actual):
    path=original.ROLE_FILES[1]
    original._require(path in expected and path in actual)
    original._require(original._signature(expected[path])==original._signature(actual[path]))
    return True
