"""Empty Date is local form state, not generic Invocation/native evidence."""
import unittest
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.dates import BSLDate, MAX_TICKS
from yadinassi.form_replication import _encode_form_scalar, _decode_form_scalar
from yadinassi.invocation import _encode_scalar, _decode_scalar, InvocationServer, PROTOCOL
from yadinassi.ui.form_app import FormController, PROTOCOL as FORM_PROTOCOL
from yadinassi.ui.protocol import encode_line, decode_line, UIError
from test_configuration_forms import sources, pair

class EmptyDateStateTests(unittest.TestCase):
    def definition(self):
        files = sources('counter')
        path = 'CommonForms/Counter/Ext/Form.xml'
        files[path] = files[path].replace(b'</Attributes>', b'<Attribute name="Moment" id="9"><Type><v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers></Type></Attribute></Attributes>')
        files[path] = files[path].replace(b'</ChildItems>', b'<InputField name="MomentInput" id="9"><DataPath>Moment</DataPath></InputField></ChildItems>')
        return load_configuration_forms(files).resolve('CommonForm.Counter')

    def test_empty_date_state_pack_unpack_and_delta(self):
        server, client = pair(self.definition())
        client.open()
        self.assertEqual(client.form._data['moment'], BSLDate(0))
        client.dispatch('change',revision=client.revision,control='MomentInput',value=BSLDate(10000000))
        client.dispatch('command',revision=client.revision,control='IncrementButton')
        self.assertEqual(server.session.form._data['moment'],BSLDate(10000000))
        client.dispatch('change',revision=client.revision,control='MomentInput',value=BSLDate(0))
        client.dispatch('command',revision=client.revision,control='IncrementButton')
        self.assertEqual(server.session.form._data['moment'],BSLDate(0))

    def test_typed_form_event_accepts_plain_empty_date_not_boundary(self):
        definition=self.definition(); server=definition.create_server()
        client=FormController(definition.client_package(),server.exchange)
        client.exchange({'jsonrpc':'2.0','id':1,'method':'form.hello','params':{'protocol':FORM_PROTOCOL}})
        result=client.exchange({'jsonrpc':'2.0','id':2,'method':'form.event','params':{
            'event':'change','revision':client.session.revision,'control':'MomentInput',
            'value':{'type':'Date','ticks':'0'}}})
        self.assertIsNone(result['result']['error'])
        self.assertEqual(client.session.form._data['moment'],BSLDate(0))

    def test_codec_remains_closed_for_fraction_and_boundary(self):
        self.assertEqual(_decode_form_scalar(_encode_form_scalar(BSLDate(0))),BSLDate(0))
        for value in (BSLDate(1),BSLDate(0,boundary=True),BSLDate(MAX_TICKS)):
            with self.subTest(value=value),self.assertRaises(ValueError): _encode_form_scalar(value)
        for value in ({'type':'Date','ticks':'00'},{'type':'Date','ticks':'-1'},
                      {'type':'Date','ticks':'0','boundary':False}):
            with self.subTest(value=value),self.assertRaises((ValueError, UIError)): _decode_form_scalar(value)

    def test_generic_invocation_arguments_and_results_still_reject_empty_date(self):
        with self.assertRaises(ValueError): _encode_scalar(BSLDate(0))
        with self.assertRaises(ValueError): _decode_scalar({'type':'Date','ticks':'0'})
        server=InvocationServer('&AtServerNoContext\nFunction Echo(Val X)\nReturn X;\nEndFunction',{1:'Echo'})
        reply=decode_line(server.exchange(encode_line({'protocol':PROTOCOL,'id':1,'endpoint':1,
                                  'arguments':[{'type':'Date','ticks':'0'}]})))
        self.assertEqual(reply['status'],'error')
        self.assertEqual(decode_line(server._reply(2,value=BSLDate(0)))['status'],'error')
