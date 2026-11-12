"""Authored bounded owned-form sources; not native acquisition evidence."""
from test_configuration_host import host_files

OWNER_MODULE = 'CommonForms/Welcome/Ext/Form/Module.bsl'
CHILD_MODULE = 'CommonForms/Details/Ext/Form/Module.bsl'
CHILD_FORM = 'CommonForms/Details/Ext/Form.xml'
OPEN = '''OpenForm("CommonForm.Details", New Structure("Message", "choose"), ThisObject,
 Undefined, Undefined, Undefined, Callback);'''


def sources(*, opening=OPEN, completion='Greeting=String(Result); Extra.Calls=Extra.Calls+1;',
            accept='Close("chosen");', child_events='', child_handlers=''):
    files = host_files()
    files[OWNER_MODULE] = ('''Var Extra, Callback;
&AtServer
Procedure Created(Cancel, StandardProcessing) Greeting="owner"; EndProcedure
&AtClient
Procedure ShowDetails(Command)
 Extra=New Structure("Calls", 0);
 Callback=New CallbackDescription("Completed", ThisObject, Extra);
 ''' + opening + '''
EndProcedure
&AtClient
Procedure Completed(Result, Extra) Export
 ''' + completion + '''
EndProcedure
''').encode()
    files[CHILD_FORM] = files[CHILD_FORM].replace(b'</ChildItems>',
        b'<Button name="AcceptButton" id="2"><Title>Accept</Title><CommandName>Accept</CommandName></Button></ChildItems>').replace(
        b'<Events>', b'<Commands><Command name="Accept" id="1"><Action>AcceptResult</Action></Command></Commands><Events>'+child_events.encode())
    files[CHILD_MODULE] += ('\n&AtClient\nProcedure AcceptResult(Command)\n'+accept+'\nEndProcedure\n'+child_handlers).encode()
    return files


def business_sources(kind='catalog', *, save=False, fail=False):
    from business_configuration_fixture import sources as base_sources
    files=base_sources()
    common=sources()
    files.update({p:b for p,b in common.items() if p.startswith('CommonForms/')})
    prefix = 'Catalogs/Items/Forms/Card' if kind=='catalog' else 'Documents/Orders/Forms/Card'
    form=files[prefix+'/Ext/Form.xml']
    form=form.replace(b'</ChildItems>', b'<Button name="ChooseButton" id="12"><CommandName>Choose</CommandName></Button></ChildItems>')
    command=b'<Command name="Choose" id="12"><Action>Choose</Action></Command>'
    form=(form.replace(b'</Commands>', command+b'</Commands>') if b'</Commands>' in form else
          form.replace(b'</Form>', b'<Commands>'+command+b'</Commands></Form>'))
    files[prefix+'/Ext/Form.xml']=form
    field='Description' if kind=='catalog' else 'Number'
    module='''Var Extra, Callback;
&AtClient
Procedure Choose(Command)
 Extra=New Structure("Calls",0);
 Callback=New CallbackDescription("Completed",ThisObject,Extra);
 '''+OPEN+'''
EndProcedure
&AtClient
Procedure Completed(Result, Extra) Export
 Object.'''+field+'''=String(Result); Extra.Calls=Extra.Calls+1;
 '''+('SaveChosen();' if save else '')+('Raise "after explicit save";' if fail else '')+'''
EndProcedure
&AtServer
Procedure SaveChosen() WriteObject(); EndProcedure
'''
    files[prefix+'/Ext/Form/Module.bsl']=files.get(prefix+'/Ext/Form/Module.bsl',b'')+b'\n'+module.encode()
    return files
