"""Direct RPC preserves endpoint admission and protocol effects."""
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from yadinassi.form_replication import ReplicatedFormServer,PROTOCOL
from yadinassi.form_model import BSLFormAttribute
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.ui.protocol import encode_line,decode_line
from yadinassi.invocation import _encode_scalar,_decode_scalar
from yadinassi.runtime import Interpreter

SOURCE='''&AtServer
Function Calculate(Val X)
Value=Value+X;Return Value;
EndFunction
&AtServer
Procedure Write(Val X)
Value=X;
EndProcedure
&AtServer
Function Private(Val X)
Value=999;Return X;
EndFunction
&AtServer
Function Fail(Val X)
Value=X;Raise "intentional failure";
EndFunction'''
class DirectFormRPCTests(TestCase):
    def setUp(self):
        self.server=ReplicatedFormServer(SOURCE,{1:'Calculate',2:'Write',3:'Fail'},handlers=(),
            attributes=(BSLFormAttribute('Value',BSLTypeDescription('Number')),),initial_values={'Value':Decimal(1)})
        self.addCleanup(self.server.session.interpreter.close);self.request_id=0
        self.assertEqual(self.request('open')['status'],'ok')
    def request(self,operation='call',endpoint=0,args=(),delta=None,revision=None):
        self.request_id+=1
        if operation=='call' and delta is None:delta={'attributes':[],'items':[],'title':None,'cells':[],'selections':[]}
        return decode_line(self.server.exchange(encode_line({'protocol':PROTOCOL,'id':self.request_id,
            'operation':operation,'revision':self.server.session.revision if revision is None else revision,
            'sequence':self.server._sequence+1,'endpoint':endpoint,'arguments':[_encode_scalar(v) for v in args],'delta':delta})))
    def test_function_result_and_procedure_without_dispatch(self):
        with patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy call')):
            result=self.request(endpoint=1,args=(Decimal(4),))
            self.assertEqual(result['status'],'ok');self.assertEqual(_decode_scalar(result['value']),5)
            result=self.request(endpoint=2,args=(Decimal(8),))
            self.assertEqual(result['status'],'ok');self.assertIsNone(_decode_scalar(result['value']))
        self.assertEqual(self.server.session.form._data['value'],8)
    def test_private_endpoint_wrong_arity_delta_revision_no_effects(self):
        for options,reason in [({'endpoint':4,'args':(Decimal(1),)},'unknown_endpoint'),
            ({'endpoint':1},'invalid_arguments'),({'endpoint':1,'args':(Decimal(2),),'revision':0},'stale_revision'),
            ({'endpoint':1,'args':(Decimal(2),),'delta':{'attributes':[['foreign',_encode_scalar(Decimal(7))]],'items':[],'title':None,'cells':[],'selections':[]}},'invalid_delta')]:
            with self.subTest(reason=reason):
                response=self.request(**options);self.assertEqual(response['reason'],reason);self.assertFalse(response['accepted'])
                self.assertEqual(self.server.session.form._data['value'],1)
    def test_source_failure_preserves_protocol_partial_state_not_fake_rollback(self):
        before=self.server.session.revision
        response=self.request(endpoint=3,args=(Decimal(6),))
        self.assertTrue(response['accepted']);self.assertEqual(response['reason'],'server_error')
        self.assertEqual(self.server.session.revision,before+1)
        self.assertEqual(self.server.session.form._data['value'],6)
        self.assertFalse(self.server.session._busy)
        self.assertEqual(len(self.server.session.interpreter._context_stack),1)

    def test_owned_schema_recompile_keeps_endpoint_identity(self):
        routine=self.server._routines[1]
        # Replica installs schema separately from declarations. Force that same
        # owned-factory refresh without replacing endpoint metadata identities.
        self.server.session._direct_form_schema=frozenset()
        response=self.request(endpoint=1,args=(Decimal(2),))
        self.assertEqual(response['status'],'ok');self.assertEqual(_decode_scalar(response['value']),3)
        self.assertIs(self.server.session.interpreter.server_routines['calculate'],routine)
