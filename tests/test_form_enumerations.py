"""Explicit host-owned form enum transport, not native form parity."""
from copy import deepcopy
from dataclasses import replace
import unittest
from test_enum_storage_binding import Lifetime
from test_enum_storage_values import DB, UNITS, definitions
from yadinassi.enum_storage_binding import EnumStorageBinding
from yadinassi.enum_storage_values import EnumValueDomain
from yadinassi.enumerations import BSLEnumerations
from yadinassi.form_references import FormReferenceScope, FormEnumBinding, FormEnumTarget, FormEnumReference
from yadinassi.form_model import BSLFormAttribute, scalar
from yadinassi.form_tables import FormTableSchema, FormTableColumn
from yadinassi.form_replication import ReplicatedFormServer, ReplicatedFormSession, _pack_state, _unpack_state
from yadinassi.catalog_backend import BackendError
from yadinassi.invocation import _encode_scalar


def scopes():
    declared=definitions(); lifetime=Lifetime(); namespace=BSLEnumerations(declared)
    binding=EnumStorageBinding(EnumValueDomain(DB,declared),declared,namespace,require_live=lifetime.require)
    server=FormReferenceScope(bindings={1:FormEnumBinding(binding,UNITS)})
    client=FormReferenceScope(targets={1:FormEnumTarget('Unit')})
    manager=namespace._managers['unit']
    return server,client,manager,lifetime


class FormEnumTests(unittest.TestCase):
    def test_canonical_empty_and_named_roundtrip(self):
        server,client,manager,_=scopes()
        for ref in (manager._empty,*manager._values):
            packet=server.encode(1,ref);self.assertEqual(packet['type'],'FormEnumRef')
            proxy=client.decode(1,packet)
            self.assertIs(type(proxy),FormEnumReference)
            self.assertEqual(proxy.is_empty(),ref.is_empty())
            self.assertIs(server.decode(1,client.encode(1,proxy)),ref)

    def test_foreign_and_fabricated_values_denied(self):
        server,client,manager,_=scopes();_,_,other,_=scopes()
        for ref in (replace(manager._values[0]),other._values[0],None,'Piece'):
            with self.assertRaises((BackendError,ValueError)):server.encode(1,ref)

    def test_closed_owner_denied_even_for_issued_packet(self):
        server,client,manager,lifetime=scopes();packet=server.encode(1,manager._values[0]);lifetime.open=False
        with self.assertRaises(BackendError):server.decode(1,packet)
        with self.assertRaises(BackendError):server.descriptor(1).adjust_value()

    def test_catalog_family_cannot_alias_enum(self):
        server,client,manager,_=scopes();packet=server.encode(1,manager._values[0])
        packet['type']='FormCatalogRef'
        for scope in (server,client):
            with self.assertRaises(ValueError):scope.decode(1,packet)
        catalog_client=FormReferenceScope(targets={1:'Unit'})
        with self.assertRaises(ValueError):catalog_client.decode(1,server.encode(1,manager._values[0]))

    def test_proxy_has_no_generic_codec_or_uuid_reader(self):
        server,client,manager,_=scopes();proxy=client.decode(1,server.encode(1,manager._values[0]))
        for encoder in (scalar,_encode_scalar):
            with self.assertRaises((ValueError,TypeError)):encoder(proxy)
        for member in ('UUID','GetObject','Metadata'):
            with self.assertRaises(ValueError):proxy.get_member(member)

    def test_actual_attribute_and_table_replication(self):
        ss,cs,manager,_=scopes();kind=ss.descriptor(1);ref=manager._values[0]
        server=ReplicatedFormServer('',{},handlers=(),reference_scope=ss,
            attributes=(BSLFormAttribute('Unit',kind),),initial_values={'Unit':ref},
            tables=(FormTableSchema('Lines',(FormTableColumn('Unit',kind,read_only=True),)),))
        server.session.form._tables['lines']._replace_rows(((1,(ref,)),),1)
        client=ReplicatedFormSession('',server.exchange,handlers=(),reference_scope=cs);client.open()
        self.assertIs(type(client.form._data['unit']),FormEnumReference)
        self.assertEqual(client.form._data['unit'],client.form._tables['lines']._by_id[1]._data['unit'])
        state=_pack_state(server.session,{})
        self.assertEqual(state['attributes'][0][1],'FormEnumRef')
        bad=deepcopy(state);bad['attributes'][0][1]='FormCatalogRef'
        with self.assertRaises(ValueError):_unpack_state(bad,client,{})
        self.assertEqual(client.form._data['unit'].presentation,str(ref))
