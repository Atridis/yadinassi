"""Ordinary closed CONFIG/key/type guards; native replay lives separately."""
import copy
from decimal import Decimal
import tempfile
from pathlib import Path
import unittest
import test_information_register_native_replay as replay
from yadinassi import Interpreter
from yadinassi.database_context import FileDBContext
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage.config_information_register_metadata import project_information_register_metadata
from yadinassi.storage.config_catalog_attributes import CatalogAttributeError
from yadinassi.storage.information_register_reader import read_information_register_rows


class InformationRegisterGuards(unittest.TestCase):
    def parse(self, raw):
        return project_information_register_metadata(raw, budget=c._Budget(c.CatalogLimits()))

    def raw(self, repeat=1):
        state = next(s for s in replay.CAPTURE['states'] if s['repeat'] == repeat)
        uid = state['physical']['objects'][0]['metadata_uuid']
        return bytes.fromhex(next(f['raw_hex'] for f in replay.CAPTURE['configs'][str(repeat)] if f['filename'] == uid))

    def test_both_actual_collection_roles_and_generated_identities(self):
        for repeat in (1, 2):
            identity, dimensions, resources, attributes = self.parse(self.raw(repeat))
            self.assertEqual([x.name for x in dimensions.attributes], ['Product','Variant'] if repeat == 1 else ['Variant','Product'])
            self.assertEqual([x.name for x in resources.attributes], ['Price','Available','ValidUntil'] if repeat == 1 else ['ValidUntil','Available','Price'])
            self.assertEqual([x.name for x in attributes.attributes], ['Note'])
            self.assertEqual(len(identity.generated_types), 7)
            self.assertEqual(len({uid for _,a,b in identity.generated_types for uid in (a,b)}), 14)

    def test_quoted_header_profile_counts_types_and_suffix_refused(self):
        raw = self.raw()
        mutations = [(b'{1,', b'{"1",'), (b'{33,', b'{"33",'),
            (b'13134202-f60b-11d5-a3c7-0050bae0a776,3', b'13134202-f60b-11d5-a3c7-0050bae0a776,2'),
            (b'13134203-f60b-11d5-a3c7-0050bae0a776,2', b'13134203-f60b-11d5-a3c7-0050bae0a776,3'),
            (b'{"N",9,0,0}', b'{"N",9,1,0}'), (b'{"B"}', b'{"B"},{"S",32,1}')]
        for old,new in mutations:
            changed = raw.replace(old,new,1)
            self.assertNotEqual(changed,raw)
            with self.subTest(old=old), self.assertRaises(CatalogAttributeError): self.parse(changed)
        for suffix in (b',0', b'{}'):
            with self.assertRaises(CatalogAttributeError): self.parse(raw+suffix)
        # The exact independent/nonperiodic header has eight bare zero flags.
        old = b',0,0,0,0,0,0,0,0,'
        self.assertIn(old,raw)
        for i in range(8):
            values = ['0']*8; values[i]='1'
            changed = raw.replace(old, (','+','.join(values)+',').encode(), 1)
            with self.subTest(header_flag=i), self.assertRaises(CatalogAttributeError): self.parse(changed)

    def test_duplicate_generated_field_ids_and_missing_target_refused(self):
        raw = self.raw(); identity, dims, resources, attrs = self.parse(raw)
        for old,new in ((identity.generated_types[1][1],identity.generated_types[0][1]),
                        (resources.attributes[0].metadata_uuid,dims.attributes[0].metadata_uuid)):
            changed=raw.replace(old.encode(),new.encode(),1)
            with self.assertRaises(CatalogAttributeError):self.parse(changed)
        state=replay.CAPTURE['states'][0]
        for before,after in ((b'"Note"',b'"Next"'),
                            (dims.attributes[0].reference_type_uuid.encode(),identity.metadata_uuid.encode())):
            configs=copy.deepcopy(replay.CAPTURE['configs']['1'])
            descriptor=next(f for f in configs if f['filename']==identity.metadata_uuid)
            original=bytes.fromhex(descriptor['raw_hex']);changed=original.replace(before,after,1)
            self.assertNotEqual(changed,original);descriptor['raw_hex']=changed.hex()
            image=replay.image(state,configs)
            with self.assertRaises(c.CatalogError):
                read_information_register_rows(image.read_at,image.size,register_name=identity.name)
            self.assertFalse(any(offset==43*replay.base.P for offset,_ in image.calls))

    def test_runtime_key_readonly_and_unsupported_consumers(self):
        state=next(s for s in replay.CAPTURE['states'] if s['state']=='filled')
        image=replay.image(state);name=state['physical']['objects'][0]['name'];lines=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'1Cv8.1CD').write_bytes(image.read_at(0,image.size))
            vm=Interpreter(output=lines.append,database_context=FileDBContext(root))
            code=f'M=InformationRegisters.{name}; S=M.Select(); S.Next(); P=S.Product; T=TypeOf(S); '
            bad=('M.Get(New Structure("Product",P))',
                 'M.Get(New Structure("Product,Variant",P,1.5))',
                 'M.Get(New Structure("Product,Variant",P,-1))',
                 'M.Get(New Structure("Product,Variant","bad",1))',
                 'M.Select(New Structure("Variant",1))','M.Select(New Structure("Product",P),"garbage")',
                 'M.CreateRecordSet()','M.CreateRecordManager()','S.Reset()','S.Price=0',
                 'ValueToStringInternal(S)','ValueToStringInternal(M)','ValueToStringInternal(T)',
                 'ValueToStringInternal(TypeOf(InformationRegisters))','New TypeDescription(T)','New(T)')
            for expression in bad:
                code+='Try '+expression+'; Message("bad"); Except Message("closed"); EndTry; '
            code+='G=M.Get(New Structure("Product,Variant",P,S.Variant)); G.Price=999; H=M.Get(New Structure("Product,Variant",P,S.Variant)); Message(H.Price<>999); '
            code+='While S.Next() Do EndDo; Message(Not S.Next()); Message(Not S.Next()); '
            try:vm.execute(code)
            finally:vm.close()
        self.assertEqual(lines,['closed']*len(bad)+['Да']*3)

    def test_descriptor_hostile_family_and_namespace_codec_are_closed(self):
        from uuid import UUID
        from yadinassi.information_registers import BSLInformationRegisterType
        from yadinassi.serialization import _UNSUPPORTED_CODEC_TYPES
        from yadinassi.values import BSLType
        class Hostile:
            def __eq__(self, other):
                raise AssertionError('host hook must not execute')
        with self.assertRaises(ValueError):
            BSLInformationRegisterType(UUID(int=1), UUID(int=2), 'Register', object(), Hostile())
        self.assertIn(BSLType.INFORMATION_REGISTERS_MANAGER, _UNSUPPORTED_CODEC_TYPES)

    def test_foreign_snapshot_reference_is_not_a_register_key(self):
        from yadinassi.structures import BSLStructure
        state=next(s for s in replay.CAPTURE['states'] if s['state']=='filled');image=replay.image(state)
        name=state['physical']['objects'][0]['name']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'1Cv8.1CD').write_bytes(image.read_at(0,image.size))
            a=Interpreter(database_context=FileDBContext(root));b=Interpreter(database_context=FileDBContext(root))
            try:
                first=a._information_registers.get_index(name);other=b._information_registers.get_index(name)
                selection=other.select();self.assertTrue(selection.next())
                key=BSLStructure('Product,Variant',selection.get_member('Product'),Decimal(1))
                with self.assertRaises(TypeError):first.get(key)
                self.assertNotEqual(first._selection_type,other._selection_type)
            finally:a.close();b.close()


if __name__ == '__main__': unittest.main()
