"""Independent synthetic CONFIG bytes; never native format evidence."""
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage')]
import config_framing_reader as core
from filedb_catalog import CatalogError
from test_filedb_catalog import P, Source, u32
from test_filedb_records import serialize

# Independent literals, not a descriptor echo or core-derived fixture layout.
DECLARATIONS = (
    ('FILENAME','NVC',0,128,0,'CI'), ('CREATION','DT',0,0,0,'CS'),
    ('MODIFIED','DT',0,0,0,'CS'), ('ATTRIBUTES','N',0,5,0,'CS'),
    ('DATASIZE','N',0,20,0,'CS'), ('BINARYDATA','I',0,0,0,'CS'),
    ('PARTNO','N',0,10,0,'CS'))


def profile():
    return core.ConfigFramingProfile(DECLARATIONS, '0', 0)


def row(name='', *, marker=0, raw=None, units=None):
    value = bytearray(b'\xa5'*301)
    value[0] = marker
    raw = name.encode('utf-16-le') if raw is None else raw
    value[1:3] = (len(raw)//2 if units is None else units).to_bytes(2,'little')
    value[3:3+len(raw)] = raw
    return bytes(value)


def source(rows=None, *, raw=None, declarations=DECLARATIONS, lock='0', format_item=0,
           table_name='CONFIG', blob_length=256):
    data = b''.join([row(marker=1), row('private_filename_Ω')]) if rows is None else b''.join(rows)
    if raw is not None: data = raw
    pages = list(range(10, 10 + (len(data)+P-1)//P))
    blob_page = max(11, 10 + len(pages))
    value = Source(page_count=max(20,blob_page+1))
    description = serialize((table_name,format_item,('Fields',*declarations),('Indexes',),
                             ('Recordlock',lock),('Files',5,8,9))).encode('utf-8')
    value.catalog((2,)); value.chain(tuple(range(2,2+(len(description)+249)//250)),description)
    for header_page, file_length, file_pages in ((5,len(data),pages),(8,blob_length,[blob_page] if blob_length else [])):
        header = value.page(header_page)
        header[:24] = b'\x1c\xfd\0\0' + bytes(12) + file_length.to_bytes(8,'little')
        for i,p in enumerate(file_pages): header[24+4*i:28+4*i] = u32(p)
    for i,p in enumerate(pages):
        chunk = data[i*P:(i+1)*P]; value.page(p)[:len(chunk)] = chunk
    value.page(blob_page)[:] = b'Q'*P
    value.data_pages, value.blob_page = pages, blob_page
    return value


class ConfigFramingCoreTests(unittest.TestCase):
    def read(self,value,**kwargs):
        return core.observe_config_framing(value.read_at,value.size,profile=profile(),**kwargs)

    def test_profile_exact_required_primitives_and_independent_layout(self):
        p = profile()
        self.assertEqual(p.record_size,301)
        self.assertEqual(p.placements,((1,258),(259,7),(266,7),(273,3),(276,11),(287,8),(295,6)))
        expected={'identifier':'config_framing_8380_8192_v1','declarations':DECLARATIONS,
            'recordlock':'0','format_item':0,'record_size':301,
            'placements':((1,258),(259,7),(266,7),(273,3),(276,11),(287,8),(295,6)),
            'framing':'reserved_one_remaining_zero_no_hidden_version_v1',
            'filename':'u16le_units_at_most_128_strict_utf16le_v1',
            'selection':'CONFIG_ascii_case_only_no_fallback_v1',
            'empty_data':'unsupported','reserved_only':'admitted'}
        self.assertEqual(p.recipe(),expected)
        self.assertEqual(p.recipe_sha256,hashlib.sha256(json.dumps(expected,ensure_ascii=True,
            sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest())
        with self.assertRaises(TypeError): core.ConfigFramingProfile()
        for lock,form in ((0,0),('1',0),('0',False),('0','0'),('0',1)):
            with self.assertRaises(ValueError): core.ConfigFramingProfile(DECLARATIONS,lock,form)
        for ds in (list(DECLARATIONS),DECLARATIONS[:-1],(list(DECLARATIONS[0]),*DECLARATIONS[1:]),
                   (('FILENAME','NVC',False,128,0,'CI'),*DECLARATIONS[1:]),
                   (('filename','NVC',0,128,0,'CI'),*DECLARATIONS[1:])):
            with self.assertRaises(ValueError): core.ConfigFramingProfile(ds,'0',0)
        with self.assertRaises(FrozenInstanceError): p.record_size=99
        recipe=p.recipe(); recipe['record_size']=99
        self.assertEqual(p.record_size,301)

    def test_finite_counts_only_all_names_validated_no_native_or_root_claim(self):
        value=source([row(marker=1),row(''),row('SECRET_Ω'),row('x'*126+'😀')])
        result=self.read(value)
        self.assertEqual((result.slots,result.active_slots,result.empty_filenames,result.nonempty_filenames,
                          result.max_filename_units),(4,3,1,2,128))
        self.assertEqual((result.data_logical_bytes,result.blob_logical_bytes),(1204,256))
        self.assertEqual(result.root_identity,'not_observed'); self.assertEqual(result.native_acceptance,'pending')
        self.assertNotIn('SECRET',repr(result)); self.assertNotIn('Ω',repr(result))
        self.assertNotIn((value.blob_page*P,P),value.calls)
        self.assertFalse(value.closed)
        with self.assertRaises(FrozenInstanceError): result.slots=9

    def test_does_not_assume_sixteen_slots_or_native_filename_length(self):
        for count in (1,2,3,16,29):
            result=self.read(source([row(marker=1)]+[row('s')]*(count-1)))
            self.assertEqual((result.slots,result.active_slots),(count,count-1))

    def test_reserved_only_is_framing_success_not_file_presence(self):
        result=self.read(source([row(marker=1)]))
        self.assertEqual((result.slots,result.active_slots,result.max_filename_units),(1,0,0))

    def test_filename_crosses_backing_page_without_reading_padding(self):
        value=source([row(marker=1)]+[row('a')]*26+[row('x'*128)])
        self.assertEqual(self.read(value).max_filename_units,128)
        # Slot 27 filename bytes start at logical 8130 and cross 8192.
        self.assertIn((10*P+8130,62),value.calls)
        self.assertIn((11*P,194),value.calls)

    def test_exact_slot_cap_and_one_over(self):
        self.assertEqual(self.read(source([row(marker=1)]+[row('a')]*4095)).slots,4096)
        value=source([row(marker=1)]+[row('a')]*4096)
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'): self.read(value)
        self.assertFalse([offset for offset,length in value.calls if offset>=10*P])

    def test_exact_config_selection_and_no_fallback(self):
        for name in ('config','CoNfIg','CONFIG'):
            self.assertEqual(self.read(source(table_name=name)).target,'CONFIG')
        for name in ('CONFIGSAVE','PARAMS','CONFIG ','CОNFIG','CONFIG\x00'):
            value=source(table_name=name)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_missing'): self.read(value)
            self.assertNotIn((5*P,P),value.calls)

    def test_profile_mismatch_rejects_before_data_or_blob_mapping(self):
        for changes in ({'lock':'1'},{'format_item':'0'},{'format_item':1},
                {'declarations':DECLARATIONS[:-1]},
                {'declarations':(('FILENAME','NVC',0,127,0,'CI'),*DECLARATIONS[1:])}):
            value=source(**changes)
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_profile_mismatch'): self.read(value)
            self.assertNotIn((5*P,P),value.calls); self.assertNotIn((8*P,P),value.calls)

    def test_duplicate_case_variant_table_rejects_before_mapping(self):
        original=core.CatalogReader.read_catalog
        def duplicate(reader):
            catalog=original(reader)
            return replace(catalog,tables=(*catalog.tables,replace(catalog.tables[0],name='config')))
        value=source()
        with mock.patch.object(core.CatalogReader,'read_catalog',duplicate):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_table_ambiguous'): self.read(value)
        self.assertNotIn((5*P,P),value.calls)

    def test_alignment_and_empty_data_rejected_without_row_read(self):
        for raw,kind,code in ((b'',core.UnsupportedLayout,'config_empty_data'),
                (bytes(300),core.InvalidStructure,'config_record_length'),
                (bytes(302),core.InvalidStructure,'config_record_length')):
            value=source(raw=raw)
            with self.assertRaisesRegex(kind,code): self.read(value)
            self.assertFalse([offset for offset,length in value.calls if offset>=10*P])

    def test_reserved_marker_is_exact_and_reserved_payload_is_opaque(self):
        for marker in (0,2,255):
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_reserved_slot'):
                self.read(source([row(marker=marker)]))
        reserved=b'\x01'+b'\xff'*300
        self.assertEqual(self.read(source([reserved])).active_slots,0)

    def test_every_later_marker_checked_no_free_slot_skip_or_early_success(self):
        for marker in (1,2,255):
            value=source([row(marker=1),row('valid'),row('ignored',marker=marker)])
            with self.assertRaisesRegex(core.UnsupportedLayout,'config_nonreserved_slot'): self.read(value)
            self.assertNotIn((10*P+603,2),value.calls)

    def test_filename_length_and_strict_surrogates_fail_with_finite_codes(self):
        for raw,units,kind,code in ((b'',129,core.InvalidStructure,'config_filename_length'),
                (b'\0\xd8',1,core.UnsupportedLayout,'config_filename_encoding'),
                (b'\0\xdc',1,core.UnsupportedLayout,'config_filename_encoding'),
                (b'\0\xd8A\0',2,core.UnsupportedLayout,'config_filename_encoding')):
            value=source([row(marker=1),row('ok'),row(raw=raw,units=units)])
            with self.assertRaisesRegex(kind,code): self.read(value)
        # NUL and BOM are structural Unicode, not semantic filename acceptance.
        self.assertEqual(self.read(source([row(marker=1),row('\0\ufeff')])).max_filename_units,2)

    def test_only_marker_length_and_declared_filename_bytes_are_read(self):
        value=source([row(marker=1),row('abc')]); self.read(value)
        calls=[call for call in value.calls if call[0]>=10*P]
        self.assertEqual(calls,[(10*P,1),(10*P+301,1),(10*P+302,2),(10*P+304,6)])

    def test_limits_are_exact_lowerable_and_apply_before_row_reads(self):
        for value in (False,0,-1,4097,1.0,'1'):
            with self.assertRaises(ValueError): core.ConfigFramingLimits(max_slots=value)
            with self.assertRaises(ValueError): core.ConfigFramingLimits(max_record_bytes=value)
        value=source()
        with self.assertRaisesRegex(core.ResourceLimit,'config_record_bytes'):
            self.read(value,limits=core.ConfigFramingLimits(max_record_bytes=300))
        self.assertEqual(value.calls,[])
        value=source()
        with self.assertRaisesRegex(core.ResourceLimit,'config_slots'):
            self.read(value,limits=core.ConfigFramingLimits(max_slots=1))
        self.assertFalse([offset for offset,length in value.calls if offset>=10*P])
        with self.assertRaises(ValueError): self.read(source(),limits={})
        with self.assertRaises(ValueError): self.read(source(),catalog_limits={})

    def test_shared_catalog_budgets_are_not_reset_for_scanning_or_result(self):
        value=source(); result=self.read(value)
        self.assertGreater(result.usage.read_bytes,0)
        limits=core.CatalogLimits(max_output_bytes=result.usage.output_bytes-1)
        with self.assertRaises(core.ResourceLimit): self.read(source(),catalog_limits=limits)

    def test_blob_ownership_is_checked_without_payload_read(self):
        for mutation in (lambda v: v.page(8).__setitem__(slice(0,2),b'xx'),
                         lambda v: v.page(8).__setitem__(slice(24,28),u32(10)),
                         lambda v: v.page(8).__setitem__(slice(24,28),u32(9))):
            value=source(); mutation(value)
            with self.assertRaises(CatalogError):
                self.read(value)
            self.assertFalse([offset for offset,length in value.calls if offset>=10*P])

    def test_cold_stdlib_only_import_and_observation(self):
        code=('import sys,json,dataclasses;sys.path[:0]=sys.argv[1:];import config_framing_reader as c;'
            'raw=sys.stdin.buffer.read();p=c.ConfigFramingProfile(c.DECLARATIONS,"0",0);'
            'o=c.observe_config_framing(lambda a,n:raw[a:a+n],len(raw),profile=p);'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print(json.dumps(dataclasses.asdict(o),sort_keys=True))')
        value=source()
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,
            str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')],
            input=value.full_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),asdict(self.read(value)))


if __name__ == '__main__': unittest.main()
