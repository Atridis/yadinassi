"""Authored host-command extension fixture; not native StandardCommand evidence."""
from uuid import UUID
from test_configuration_posting import source as core_source, wrap

FORM = 'Document.Order.Form.Card'
MODULE = 'Documents/Order/Ext/ObjectModule.bsl'
FORM_MODULE = 'Documents/Order/Forms/Card/Ext/Form/Module.bsl'
POSTING = '''Procedure Posting(Cancel, Mode)
 Movements = RegisterRecords.Rows;
 Movements.Write = True;
 Row = Movements.Add();
 Row.Key = Number(Number);
 Row.Amount = Amount;
EndProcedure
'''


def source(module=POSTING):
    files = core_source()
    field = f'<Attribute uuid="{UUID(int=20)}"><Properties><Name>Amount</Name><Type><v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>10</v8:Digits><v8:FractionDigits>0</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers></Type></Properties></Attribute>'
    section = f'<TabularSection uuid="{UUID(int=21)}"><Properties><Name>Lines</Name></Properties><ChildObjects>'+field.replace(str(UUID(int=20)),str(UUID(int=22))).replace('Amount','Quantity')+'</ChildObjects></TabularSection>'
    files['Documents/Order.xml'] = files['Documents/Order.xml'].replace(b'</Properties><ChildObjects>', b'<DefaultObjectForm>Document.Order.Form.Card</DefaultObjectForm></Properties><ChildObjects>', 1).replace(b'</ChildObjects></Document>', (field+section+'<Form>Card</Form></ChildObjects></Document>').encode())
    files[MODULE] = module.encode()
    prefix = 'Documents/Order/Forms/Card'
    files[prefix+'.xml'] = wrap('Form',30,'<Name>Card</Name><FormType>Managed</FormType>')
    commands = ''.join(f'<Command name="{name}" id="{i}"><Action>{name}Command</Action></Command>' for i,name in enumerate(('DoWrite','DoPost','DoUndo'),1))
    buttons = ''.join(f'<Button name="{name}Button" id="{i+10}"><CommandName>{name}</CommandName></Button>' for i,name in enumerate(('DoWrite','DoPost','DoUndo'),1))
    files[prefix+'/Ext/Form.xml'] = ('''<Form xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"><Attributes><Attribute name="Object" id="1"><Type><v8:Type>cfg:DocumentObject.Order</v8:Type></Type><MainAttribute>true</MainAttribute></Attribute></Attributes><ChildItems><InputField name="AmountInput" id="1"><DataPath>Object.Amount</DataPath></InputField><Table name="LinesTable" id="2"><DataPath>Object.Lines</DataPath></Table>'''+buttons+'</ChildItems><Commands>'+commands+'</Commands></Form>').encode()
    files[FORM_MODULE] = '\n'.join('&AtClient\nProcedure '+name+'Command(Command)\nEndProcedure\n' for name in ('DoWrite','DoPost','DoUndo')).encode()
    files['PostingApplication.xml'] = (f'<PostingApplication xmlns="urn:yadinassi:posting-application:1" version="1"><Form name="{FORM}">'+''.join(f'<Command name="{name}" id="{i}" mode="{mode}"/>' for i,(name,mode) in enumerate(zip(('DoWrite','DoPost','DoUndo'),('Write','Post','UndoPosting')),1))+'</Form></PostingApplication>').encode()
    return files
