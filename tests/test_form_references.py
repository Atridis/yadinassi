"""Host-functional form-only references; no native transport parity claim."""
from copy import deepcopy
from uuid import UUID, uuid4
import unittest

from yadinassi.catalog_types import BSLCatalogReference, BSLCatalogType
from yadinassi.form_references import FormReferenceBinding, FormReferenceScope, FormCatalogReference
from yadinassi.form_model import BSLFormAttribute, scalar
from yadinassi.form_tables import FormTableColumn, FormTableSchema
from yadinassi.form_replication import (ReplicatedFormServer, ReplicatedFormSession,
    _pack_state, _unpack_state, _admit_delta, _capture)
from yadinassi.form_table_replication import admit_table_delta
from yadinassi.invocation import _encode_scalar
from yadinassi.type_descriptions import BSLTypeDescription


def scopes():
    snapshot=object(); kind=BSLCatalogType(uuid4(),'Products',snapshot)
    empty=BSLCatalogReference(kind,UUID(int=0)); ref=BSLCatalogReference(kind,uuid4())
    def validate(value):
        if value.value_type != kind: raise ValueError('foreign snapshot')
        return value
    binding=FormReferenceBinding(kind,empty,validate,lambda value:'' if value.is_empty() else 'Product')
    return FormReferenceScope(bindings={1:binding}),FormReferenceScope(targets={1:'Products'}),empty,ref


def pair():
    server_scope,client_scope,empty,ref=scopes()
    kind=server_scope.descriptor(1)
    server=ReplicatedFormServer('',{},handlers=(),reference_scope=server_scope,
        attributes=(BSLFormAttribute('Product',kind),), initial_values={'Product':ref},
        tables=(FormTableSchema('Lines',(FormTableColumn('Product',kind,read_only=True),)),))
    server.session.form._tables['lines']._replace_rows(((1,(ref,)),),1)
    client=ReplicatedFormSession('',server.exchange,handlers=(),reference_scope=client_scope)
    return server,client,server_scope,client_scope,empty,ref


class FormReferenceTests(unittest.TestCase):
    def test_typed_empty_and_identity_roundtrip(self):
        server,client,empty,ref=scopes()
        a=client.decode(1,server.encode(1,ref)); b=client.decode(1,server.encode(1,ref))
        self.assertEqual(a,b); self.assertEqual(str(a),'Product'); self.assertFalse(a.is_empty())
        self.assertTrue(client.decode(1,server.encode(1,empty)).is_empty())
        invalid=server.encode(1,empty);invalid['text']='not empty'
        with self.assertRaises(ValueError):client.decode(1,invalid)
        self.assertIs(server.decode(1,server.encode(1,ref)),ref)

    def test_packet_has_no_uuid_or_readers(self):
        server,client,empty,ref=scopes(); packet=server.encode(1,ref)
        self.assertEqual(set(packet),{'type','scope','target','key','text'})
        self.assertNotIn(str(ref.reference_uuid),str(packet));self.assertNotIn(str(ref.value_type.metadata_uuid),str(packet))
        proxy=client.decode(1,packet)
        for member in ('UUID','UniqueIdentifier','GetObject','Metadata'):
            with self.subTest(member=member),self.assertRaises(ValueError):proxy.get_member(member)

    def test_foreign_snapshot_target_and_scope_rejected(self):
        server,client,empty,ref=scopes(); other,_,_,otherref=scopes()
        with self.assertRaises(ValueError):server.encode(1,otherref)
        with self.assertRaises(ValueError):server.encode(2,ref)
        packet=server.encode(1,ref)
        with self.assertRaises(ValueError):other.decode(1,packet)
        client.decode(1,packet)
        with self.assertRaises(ValueError):client.decode(1,other.encode(1,otherref))

    def test_unissued_and_modified_packets_rejected(self):
        server,_,empty,ref=scopes();packet=server.encode(1,ref)
        for key,value in [('key','0'*32),('target',True),('text','forged'),('scope','f'*32)]:
            changed=dict(packet);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):server.decode(1,changed)

    def test_unissued_proxy_rejected(self):
        server,client,_,ref=scopes();proxy=client.decode(1,server.encode(1,ref))
        fake=FormCatalogReference(client,1,proxy.key,proxy.presentation)
        with self.assertRaises(ValueError):client.encode(1,fake)

    def test_explicit_normalizer_can_admit_registered_snapshot(self):
        scope,_,empty,ref=scopes(); binding=scope.targets[1]
        other_kind=BSLCatalogType(binding.value_type.metadata_uuid,'Products',object())
        other=BSLCatalogReference(other_kind,ref.reference_uuid)
        def normalize(value):
            if value.value_type not in (binding.value_type,other_kind): raise ValueError('unregistered snapshot')
            return BSLCatalogReference(binding.value_type,value.reference_uuid)
        normal=FormReferenceScope(bindings={1:FormReferenceBinding(binding.value_type,empty,normalize,binding.presentation)})
        self.assertEqual(normal.descriptor(1).adjust_value(other).value_type,binding.value_type)

    def test_generic_scalar_and_invocation_stay_closed(self):
        server,client,empty,ref=scopes();proxy=client.decode(1,server.encode(1,ref))
        for value in (ref,proxy):
            for encoder in (scalar,_encode_scalar):
                with self.subTest(encoder=encoder,value=type(value)),self.assertRaises((TypeError,ValueError)):encoder(value)
        with self.assertRaises((TypeError,ValueError)):BSLTypeDescription(ref.value_type)

    def test_replica_attribute_and_table_are_real_typed_values(self):
        server,client,ss,cs,empty,ref=pair();client.open()
        self.assertIs(server.session.form._data['product'],ref)
        self.assertIsInstance(client.form._data['product'],FormCatalogReference)
        self.assertEqual(client.form._data['product'],client.form._tables['lines']._by_id[1]._data['product'])
        self.assertEqual(_capture(client.form)['attributes']['product']['type'],'FormCatalogRef')

    def test_no_optin_replica_rejects_reference_schema(self):
        server,_,ss,cs,empty,ref=pair()
        client=ReplicatedFormSession('',server.exchange,handlers=())
        with self.assertRaises(Exception):client.open()

    def test_client_attribute_and_cell_assignments_readonly(self):
        server,client,ss,cs,empty,ref=pair();client.open();value=client.form._data['product']
        with self.assertRaises(ValueError):client.form.set_member('Product',value)
        with self.assertRaises(ValueError):client.form._tables['lines']._by_id[1].set_member('Product',value)

    def test_reference_attribute_delta_cannot_retarget(self):
        server,client,ss,cs,empty,ref=pair();client.open()
        packet={'attributes':[['product',ss.encode(1,empty)]],'items':[],'title':None,'cells':[],'selections':[]}
        with self.assertRaises(ValueError):_admit_delta(server.session.form,packet)
        self.assertIs(server.session.form._data['product'],ref)

    def test_reference_cell_delta_cannot_retarget(self):
        server,client,ss,cs,empty,ref=pair();client.open()
        with self.assertRaises(ValueError):admit_table_delta(server.session.form,[[1,1,0,ss.encode(1,empty)]],[],server.session.form._data)
        self.assertIs(server.session.form._tables['lines']._by_id[1]._data['product'],ref)

    def test_bad_state_does_not_poison_client_scope(self):
        server,client,ss,cs,empty,ref=pair();client.open()
        previous=_capture(client.form); identity=cs.identity; issued=dict(cs._client)
        packet=deepcopy(_pack_state(server.session,{}));packet['attributes'][0][-1]['text']='changed'
        packet['items']=[['malformed']]
        with self.assertRaises(ValueError):_unpack_state(packet,client,{})
        self.assertEqual(cs.identity,identity);self.assertEqual(cs._client,issued)
        self.assertEqual(_capture(client.form),previous)
        old=client.form._data['product']; changed=ss.encode(1,ref);changed['text']='Renamed'
        new=cs.decode(1,changed)
        self.assertEqual(old,new);self.assertEqual(cs.encode(1,old)['text'],'Product')
        self.assertEqual(cs.encode(1,new)['text'],'Renamed')

    def test_scope_cannot_be_shared_by_two_forms(self):
        server,client,ss,cs,empty,ref=pair()
        with self.assertRaises(ValueError):ReplicatedFormServer('',{},handlers=(),reference_scope=ss)

    def test_bounded_presentation_and_reference_inventory(self):
        server,client,empty,ref=scopes();packet=server.encode(1,ref);packet['text']='x'*1025
        with self.assertRaises(ValueError):client.decode(1,packet)
        with self.assertRaises(ValueError):FormReferenceScope(targets={True:'Products'})
