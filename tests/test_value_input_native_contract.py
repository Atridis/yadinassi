"""Offline authored-input/controller contracts. These are not native observations."""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/native_1c_bootstrap'))
import value_input_packet as packet
from value_input_packet import route
import value_input_controller as controller


def records():
    types = ('string', 'number', 'date', 'boolean', 'undefined', 'item', 'undefined', 'string')
    return ''.join(f'VI{i}=1;{kind};1;{int(i==6)};{int(i not in (5,7))};start,returned,callback,finish,|'
                   for i,kind in enumerate(types,1)).encode()


class ValueInputNativeContracts(unittest.TestCase):
    def test_five_authored_packet_hashes(self):
        self.assertEqual(len(packet.packet()), 5)
        self.assertEqual({n:hashlib.sha256(v).hexdigest() for n,v in packet.packet().items()},packet.PACKET_HASHES)

    def test_authored_module_and_source_binding(self):
        self.assertEqual(route.validate_redump(route.sources()),route.module_digest())
        self.assertNotIn(b'SOURCE_VALUE',route.module())

    def test_redump_only_binds_executable_modules(self):
        files = {n:route.sources()[n] for n in route.EXECUTABLE_MODULES}
        self.assertEqual(route.validate_executable_redump(files),route.module_digest())
        files[route.MODULES[0]] += b'bad'
        with self.assertRaises(ValueError): route.validate_executable_redump(files)

    def test_eight_bounded_observations(self):
        self.assertEqual(len(packet.require_available(packet.parse_records(records()))),8)

    def test_both_callback_orders_are_observed(self):
        changed=records().replace(b'start,returned,callback,finish,',b'start,callback,returned,finish,')
        self.assertEqual(packet.parse_records(changed)[0][-1],('start','callback','returned','finish'))

    def test_different_native_value_is_evidence_not_fake_parity(self):
        changed=records().replace(b';string;1;0;1;',b';other;1;0;0;',1)
        self.assertEqual(packet.parse_records(changed)[0][:4],('other',1,0,0))

    def test_duplicate_missing_unknown_records_refused(self):
        for raw in (records()+records(),records().replace(b'VI2',b'VI1'),b'unknown',b'x'*4097):
            with self.assertRaises(ValueError):packet.parse_records(raw)

    def test_list_identity_and_value_are_independent(self):
        code=route.module().decode('utf-8')
        self.assertIn('If Result = ExpectedItem Then Identity = 1;',code)
        self.assertIn('If Result.Value = "second" Then ValueMatch = 1;',code)
        self.assertEqual(packet.parse_records(records())[5][2:4],(1,1))

    def test_callbacks_never_directly_invoked(self):
        code=route.module().decode('utf-8')
        self.assertEqual(code.count('InputDone('),1)
        self.assertIn('New CallbackDescription("InputDone", ThisObject, Shared)',code)
        self.assertIn('Items.ShowChooseItem(Callback, Title, ExpectedItem)',code)

    def test_unique_nonce_titles_and_eight_fixed_plans(self):
        self.assertEqual(len(controller.PLANS),8)
        self.assertEqual(len(set(controller.TITLES)),8)
        self.assertEqual(controller.PLANS[4],('Escape',))
        self.assertEqual(controller.PLANS[6],('Escape',))

    def test_action_budget_bounds(self):
        count=sum(len(key.split('+')) for plan in controller.PLANS for key in plan)
        self.assertLessEqual(count,controller.MAX_KEYS)
        self.assertEqual(controller.MAX_KEYS,48)
        self.assertEqual(controller.MAX_POLLS,2400)

    def test_nonprivate_display_refused_before_loading_libraries(self):
        with mock.patch.dict(os.environ,{'DISPLAY':':0','XAUTHORITY':'/tmp/onec-smoke/xauth'}),mock.patch.object(controller.C,'CDLL') as load:
            with self.assertRaises(controller.OwnershipError):controller.Display()
            load.assert_not_called()

    def test_unknown_xauthority_refused_before_loading(self):
        with mock.patch.dict(os.environ,{'DISPLAY':':99','XAUTHORITY':'/home/user/.Xauthority'}),mock.patch.object(controller.C,'CDLL') as load:
            with self.assertRaises(controller.OwnershipError):controller.Display()
            load.assert_not_called()

    def test_invalid_run_path_refused_before_display(self):
        with mock.patch.object(controller,'Display') as display:
            with self.assertRaises(Exception):controller.run_owned(['/usr/bin/1cv8','/C','/tmp/request'],Path('/tmp/other'),Path('/tmp/log'),'0'*32)
            display.assert_not_called()

    def test_process_identity_parser_bounds(self):
        fields=[b'S',b'1',b'77',b'77']+[b'0']*15+[b'123']
        with mock.patch.object(Path,'read_bytes',return_value=b'77 (native worker) '+b' '.join(fields)):
            self.assertEqual(controller.process_identity(77),(77,77,123))
        with mock.patch.object(Path,'read_bytes',return_value=b'x'*4097):
            with self.assertRaises(controller.OwnershipError):controller.process_identity(77)

    def test_pid_and_exact_title_required(self):
        display=object.__new__(controller.Display)
        display.title=lambda window:b'expected'
        display.property=lambda window,name:None
        with mock.patch.object(controller,'process_identity',return_value=(77,77,123)):
            with self.assertRaises(controller.OwnershipError):display.owned(9,b'expected',77,(77,77,123),Path('/native'))
            with self.assertRaises(controller.OwnershipError):display.owned(9,b'other',77,(77,77,123),Path('/native'))

    def test_reused_leader_identity_refused(self):
        display=object.__new__(controller.Display)
        display.title=lambda window:b'expected'
        with mock.patch.object(controller,'process_identity',return_value=(77,77,124)):
            with self.assertRaises(controller.OwnershipError):display.owned(9,b'expected',77,(77,77,123),Path('/native'))

    def test_foreign_process_group_refused(self):
        display=object.__new__(controller.Display)
        display.title=lambda window:b'expected'
        display.property=lambda window,name:88
        with mock.patch.object(controller,'process_identity',side_effect=[(77,77,123),(88,88,321)]):
            with self.assertRaises(controller.OwnershipError):display.owned(9,b'expected',77,(77,77,123),Path('/native'))

    def test_injection_is_bounded_and_server_grab_released(self):
        tree=ast.parse((ROOT/'scripts/native_1c_bootstrap/value_input_controller.py').read_text(encoding='utf-8'))
        drive=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='drive')
        text=ast.unparse(drive)
        self.assertIn('self.owned(',text)
        self.assertIn('self.focused(',text)
        self.assertIn('finally:',text)
        self.assertIn('XUngrabServer',text)
        self.assertNotIn('subprocess',text)

    def test_history_pinned_runners_are_not_staged(self):
        text=(ROOT/'scripts/native_1c_value_inputs_profile.py').read_text(encoding='utf-8')
        self.assertIn("'scripts/native_1c_bootstrap/run_value_inputs_stage.py':'bootstrap/run_stage.py'",text)
        self.assertIn("'scripts/native_1c_bootstrap/value_input_controller.py':'bootstrap/value_input_controller.py'",text)
        self.assertIn("'scripts/native_1c_smoke_probe.sh','scripts/native_1c_bootstrap/run_stage.py'",text)

    def test_network_and_display_remain_isolated(self):
        text=(ROOT/'scripts/native_1c_value_inputs_profile.py').read_text(encoding='utf-8')
        self.assertIn("'--network', 'none'",text)
        self.assertIn("'no-new-privileges:true'",text)
        probe=(ROOT/'scripts/native_1c_value_inputs_probe.sh').read_text(encoding='utf-8')
        self.assertIn('-rfbport -1 -nolisten tcp',probe)
        self.assertIn('-auth "$XAUTHORITY"',probe)

    def test_stage_uses_real_driver_not_callback_replay(self):
        text=(ROOT/'scripts/native_1c_bootstrap/value_inputs_suite.py').read_text(encoding='utf-8')
        self.assertIn('controller.run_owned',text)
        self.assertIn("report['input_ownership_verified']=report['input_actions']==8",text)
        self.assertNotIn('InputDone(',text)
        self.assertIn('route.validate_executable_redump',text)

    def test_source_profile_is_separate(self):
        text=(ROOT/'scripts/native_1c_value_inputs_profile.py').read_text(encoding='utf-8')
        self.assertIn("PROFILE='managed-value_inputs-v1'",text)
        self.assertIn("'status':'not_evaluated'",text)
        self.assertIn("stage['input_actions']==8",text)

    def test_partial_chord_releases_modifiers_without_masking_primary(self):
        for budget, primary_message in ((True, 'key budget'), (False, 'key delivery failed')):
            with self.subTest(budget=budget):
                display=object.__new__(controller.Display)
                display.display=object(); display.keys=47 if budget else 0
                display.x=mock.Mock(); display.xt=mock.Mock()
                display.owned=mock.Mock(); display.focused=mock.Mock()
                display.sync=mock.Mock(side_effect=[None,RuntimeError('cleanup sync')])
                display.x.XStringToKeysym.side_effect=lambda name: {b'Control_L':1,b'a':2}[name]
                display.x.XKeysymToKeycode.side_effect=lambda _,sym:sym
                events=[]
                def key(_,code,down,delay):
                    events.append(('key',code,down))
                    if code==2 and down: return 0
                    if code==2 and not down: raise RuntimeError('cleanup release')
                    return 1
                display.xt.XTestFakeKeyEvent.side_effect=key
                display.x.XUngrabServer.side_effect=lambda _:events.append(('ungrab',))
                with self.assertRaisesRegex(controller.OwnershipError,primary_message):
                    display.drive(9,b'title',77,(77,77,123),Path('/native'),('Control_L+a',))
                self.assertIn(('key',1,0),events)
                self.assertLess(events.index(('key',1,0)),events.index(('ungrab',)))
                display.x.XUngrabServer.assert_called_once()
                self.assertEqual(display.sync.call_count,2)
