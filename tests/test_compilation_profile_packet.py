"""Офлайн-контракты пакета; не доказательство поведения платформы."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from compilation_profile_packet import packet, PACKET_HASHES, parse_records, COUNT
from compilation_profile_packet import route, fixture

class PacketTests(unittest.TestCase):
    def test_inventory(self):
        self.assertEqual(COUNT,16);self.assertEqual(len(packet()),14)
        self.assertEqual(set(packet()),set(PACKET_HASHES))
    def test_hashes(self):
        for name,raw in packet().items():self.assertEqual(hashlib.sha256(raw).hexdigest(),PACKET_HASHES[name])
    def test_prepared(self):self.assertEqual(route.validate_prepared(route.sources()),route.module_digest())
    def test_changed_packet(self):
        values=route.sources();values['Extensions/Session.bsl']+=b'// drift'
        with self.assertRaises(ValueError):route.validate_prepared(values)
    def test_extra_packet(self):
        values=route.sources();values['extra']=b'x'
        with self.assertRaises(ValueError):route.validate_prepared(values)
    def test_exact_anchor(self):
        raw=('before\n'+fixture.SESSION_ANCHOR+'\nafter').encode()
        result=fixture.insert_exact(raw,fixture.SESSION_ANCHOR,fixture.SESSION_INSERT)
        self.assertEqual(result.replace(fixture.SESSION_INSERT.encode(),b'',1),raw)
    def test_missing_anchor(self):
        with self.assertRaises(ValueError):fixture.insert_exact(b'other',fixture.SESSION_ANCHOR,fixture.SESSION_INSERT)
    def test_duplicate_anchor(self):
        with self.assertRaises(ValueError):fixture.insert_exact((fixture.SESSION_ANCHOR*2).encode(),fixture.SESSION_ANCHOR,fixture.SESSION_INSERT)
    def test_bootstrap_preservation(self):
        source=(ROOT/'scripts/compilation_profile_packet/fixture.py').read_text(encoding='utf-8')
        self.assertLess(source.index('original._baseline(files,setup)'),source.index("expected=dict(files)"))
        self.assertIn("route.normalized(bootstrap_application)",source)
        self.assertIn("route.normalized(bootstrap_module)",source)
        self.assertNotIn('ПользователиИнформационнойБазы',source)
    def test_masks_not_expected_constants(self):
        for name in ('ClientProbe','ServerProbe','DualProbe'):
            s=packet()[f'CommonModules/{name}/Ext/Module.bsl'].decode()
            for keyword in ('Client','Server','AtClient','AtServer','ThickClientManagedApplication','ThickClientOrdinaryApplication','ThinClient','WebClient','ExternalConnection','MobileAppClient','MobileAppServer'):
                self.assertIn('#If '+keyword+' Then',s)
    def test_unknown_mobile_not_admitted(self):
        for raw in packet().values():
            self.assertNotIn(b'MobileStandaloneServer',raw);self.assertNotIn(b'#If MobileClient ',raw)
    def test_application_initialization(self):
        self.assertIn('CPStartup = "0"',fixture.APPLICATION_INSERT)
        self.assertIn('#If Client And Not Client Then',fixture.APPLICATION_INSERT)
        self.assertIn('CPStartupValue()',route.module().decode())
    def test_observation_errors_are_narrow(self):
        s=route.module().decode()
        self.assertIn('  Value = Observe(Number);',s)
        self.assertNotIn('Try Value = Observe(Number)',s)
        self.assertNotIn('ErrorDescription',s)
        self.assertIn('Marker(Request.completed, "error", "")',s)
    def test_numeric_output_only(self):
        valid=''.join(f'CP{i}=511:511|' for i in range(1,17)).encode()
        self.assertEqual(len(parse_records(valid)),16)
        for value in ('error','message','1234','1:2:3:4:5','-1'):
            with self.assertRaises(ValueError):parse_records(valid.replace(b'CP1=511:511|',('CP1='+value+'|').encode()))
    def test_two_events_preserved(self):
        s=route.module().decode();self.assertIn('AttachIdleHandler("SecondEvent", 1, True);',s)
        self.assertNotIn('SecondEvent();',s);self.assertIn('Value = Observe(16)',s)
    def test_no_runtime_changes_required(self):
        # Packet contracts do not parse with authored VM or call it as an oracle.
        s=(ROOT/'scripts/compilation_profile_packet/fixture.py').read_text(encoding='utf-8')
        self.assertNotIn('yadinassi',s);self.assertNotIn('Interpreter',s)

    def test_complete_session_and_dual_mobile_matrix(self):
        self.assertIn('CPMaskEN()+":"+CPMaskRU()+":"+CPMobileEN()+":"+CPMobileRU()',fixture.SESSION_INSERT)
        self.assertIn('DualProbe.CPMobileEN()+":"+DualProbe.CPMobileRU()+":"+ServerProbe.DualMobile()',route.module().decode())
        server=packet()['CommonModules/ServerProbe/Ext/Module.bsl'].decode()
        self.assertIn('Function DualMobile() Export Return DualProbe.CPMobileEN()+":"+DualProbe.CPMobileRU()',server)
