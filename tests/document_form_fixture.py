"""Authored, non-native document form source."""
from uuid import UUID
from test_document_configuration_xml import document_files


def sources():
    files=document_files(catalogs=False,fields=False)
    files['Documents/Orders.xml']=files['Documents/Orders.xml'].replace(b'</Properties><ChildObjects>',b'<DefaultObjectForm>Document.Orders.Form.Card</DefaultObjectForm></Properties><ChildObjects>',1).replace(b'</Document>',b'</Document>')
    # Insert the form into the document inventory, not the section inventory.
    files['Documents/Orders.xml']=files['Documents/Orders.xml'].replace(b'</ChildObjects></Document>',b'<Form>Card</Form></ChildObjects></Document>')
    prefix='Documents/Orders/Forms/Card'
    files[prefix+'.xml']=b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Form uuid="32905974-0e52-41a4-9399-d24aa799b00a"><Properties><Name>Card</Name><FormType>Managed</FormType></Properties><ChildObjects/></Form></MetaDataObject>'
    files[prefix+'/Ext/Form.xml']=b'''<Form xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"><Title>Order</Title><Attributes><Attribute name="Object" id="1"><Type><v8:Type>cfg:DocumentObject.Orders</v8:Type></Type><MainAttribute>true</MainAttribute></Attribute></Attributes><ChildItems><InputField name="NumberField" id="1"><DataPath>Object.Number</DataPath></InputField><Table name="LinesTable" id="2"><DataPath>Object.Lines</DataPath></Table><Button name="SaveButton" id="3"><CommandName>Save</CommandName></Button></ChildItems><Commands><Command name="Save" id="1"><Action>SaveCommand</Action></Command></Commands></Form>'''
    files[prefix+'/Ext/Form/Module.bsl']=b'''&AtClient
Procedure SaveCommand(Command) SaveAtServer(); EndProcedure
&AtServer
Procedure SaveAtServer() WriteObject(); EndProcedure
&AtServer
Procedure AddLine() Row=Object.Lines.Add(); Row.Flag=True; EndProcedure
'''
    return files
