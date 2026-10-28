"""All 81 synthetic Rows diagnostics remain rejected, finite and nonexportable."""
import copy
import itertools
import json
import unittest

import test_native_1c_output_artifact as artifact

full = artifact.full
VECTORS = tuple(''.join(parts) for parts in itertools.product('TFE', repeat=4))


def output(vector):
    prefix = b''.join(f'old{i}: [ok]\n'.encode('ascii') for i in range(976))
    payload = b'1?D0' + vector.encode('ascii') + b'!' + b'.'*56
    return prefix + b''.join(f'TL{i:02d}: ['.encode('ascii') + payload + b']\n' for i in range(1,46)) + __import__('test_native_tree_move_contract').synthetic_record()[1]


class RowsFailureTests(artifact.SyntheticFilesystemCase):
    invoke = artifact.OrchestrationTests.invoke

    def native(self, **updates):
        value = dict(source_sha256=full.COLLECTIONS_SOURCE_SHA256, message_count=1022)
        value.update(updates); return value

    def test_exact_81_vocabulary_packets_and_strict_decoder_rejection(self):
        self.assertEqual(full.TREE_ROWS_DIAGNOSTIC_FAILURES, frozenset('tree_rows_'+v for v in VECTORS))
        for vector in VECTORS:
            data = output(vector)
            self.assertEqual(full.tree_rows_diagnostic_failure(data,self.native()),'tree_rows_'+vector)
            with self.assertRaisesRegex(full.FullError,'^tree_load_observation_invalid$'):
                full.validate_tree_load_observations(data)
            self.assertEqual(len(data[:data.index(b'TM:')])-len(data[:data.index(b'TL01:')])-45,3285)

    def test_malformed_mixed_unknown_or_unbound_is_generic(self):
        original = output('TFTT')
        variants = [original.replace(b'1?D0TFTT',b'1?D0TFFT',1),
            original.replace(b'TL01:',b'TL99:',1), original.replace(b'TL45:',b'TL44:',1),
            original.replace(b'1?D0TFTT',b'1?D0tFTT'), original.replace(b'1?D0TFTT',b'1?D0????'),
            original.replace(b'1?D0TFTT',b'1?D0TFT'), original.replace(b'1?D0TFTT!',b'1?D0TFTT?'),
            original.replace(b'old0: [ok]\n',b'',1), original+b'extra: [ok]\n', original[:-1],
            b'\xff'+original]
        for changed in variants:
            self.assertIsNone(full.tree_rows_diagnostic_failure(changed,self.native()))
        for metadata in (self.native(source_sha256='0'*64),self.native(message_count=1020),
                         self.native(message_count='1022'),self.native(message_count=True)):
            self.assertIsNone(full.tree_rows_diagnostic_failure(original,metadata))

    def test_all_81_through_both_main_contexts_keep_export_failure(self):
        for vector,mode in itertools.product(VECTORS,(full.BYTE_EXACT,full.MAP_MODE)):
            with self.subTest(vector=vector,mode=mode):
                result,exported,retained = self.invoke(through_main=True,comparison_mode=mode,
                    collections_payload=output(vector),post_create=(artifact.PAYLOAD,(0,artifact.PAYLOAD,b'')))
                self.assertNotEqual(result['exit_code'],0); self.assertEqual(exported,[])
                self.assertNotIn('native_output_artifact_ready=true',result['ready'])
                report=result['summary']; self.assertFalse(report['native_evidence_accepted'])
                self.assertEqual(report['error'],'native_artifact_evidence_invalid')
                case=report['probe']['comparison']['cases'][0]
                self.assertEqual(case['failure_kind'],'tree_rows_'+vector)
                self.assertEqual((case['status'],case['acceptance_status']),('error','rejected'))
                for field in ('interpreter_size','interpreter_sha256','mismatch','semantic'):
                    self.assertIsNone(case[field])
                generic=copy.deepcopy(report)
                generic['probe']['comparison']['cases'][0]['failure_kind']='tree_load_observation_invalid'
                self.assertLess(len(json.dumps(report)),len(json.dumps(generic)))
                target=full.LINUX_TARGET if mode==full.MAP_MODE else full.WINDOWS_TARGET
                for badkind in ('tree_rows_TFTX','tree_rows_tftt','tree_rows_TFT','tree_rows_TFTTT'):
                    bad=copy.deepcopy(report['probe']['comparison']);bad['cases'][0]['failure_kind']=badkind
                    with self.assertRaises(full.FullError):
                        full.validate_comparison(bad,report['probe']['stage3'],target,mode)


if __name__ == '__main__': unittest.main()
