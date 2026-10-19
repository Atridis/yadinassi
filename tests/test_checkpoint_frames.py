"""Observation framing checks are independent of unconfirmed native XML values."""
import unittest

from scripts.smoke_test import null_checkpoint_output, validate_xml_checkpoint_output


class CheckpointFrameTests(unittest.TestCase):
    null = 'null.sample: [{"N",1}]\nnull.checkpoint.complete: [ok]\n'
    labels = ['xml.first', 'xml.second']
    first = 'xml.first: [{\n{"N",1},\n{"S","synthetic"}\n}]\n'
    second = 'xml.second: [serialize-error]\n'
    final = 'xml.checkpoint.complete: [ok]\n'

    def test_native_null_output_is_bounded_before_new_themes(self):
        self.assertEqual(null_checkpoint_output(self.null + self.first + self.final), self.null)
        for output in (self.null.replace('null.checkpoint.complete: [ok]', 'missing'),
                       self.null + self.null):
            with self.subTest(output=output), self.assertRaises(AssertionError):
                null_checkpoint_output(output)

    def test_multiline_frames_preserve_original_null_and_ignore_payload_semantics(self):
        output = self.null + self.first + self.second + self.final
        # Future native files may contain different XML answers. Only the exact
        # original Null prefix is an established native expectation here.
        future_native = self.null + 'xml.first: [different native answer]\n' + self.final
        validate_xml_checkpoint_output(output, future_native, self.labels)

    def test_missing_duplicate_reordered_and_malformed_frames_are_rejected(self):
        invalid = [
            self.second + self.final,
            self.first + self.first + self.second + self.final,
            self.second + self.first + self.final,
            self.first.replace('}]\n', '}\n') + self.second + self.final,
            self.first.replace(': [', ': ') + self.second + self.final,
            self.first + self.second.replace('xml.second', 'xml.unknown') + self.final,
            self.first + self.second,
            self.first + self.second + self.final + self.final,
            self.first + self.second + self.final + 'unexpected output\n',
            'unexpected output\n' + self.first + self.second + self.final,
        ]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(AssertionError):
                validate_xml_checkpoint_output(self.null + body, self.null, self.labels)
        with self.assertRaises(AssertionError):
            validate_xml_checkpoint_output(
                self.null.replace('{"N",1}', '{"N",2}') + self.first + self.second + self.final,
                self.null, self.labels)


if __name__ == '__main__':
    unittest.main()
