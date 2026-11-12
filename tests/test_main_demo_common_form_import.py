"""One exact main-demo envelope; common forms do not gain inventory authority."""
from dataclasses import replace
from hashlib import sha256
from unittest.mock import patch
import unittest

from yadinassi import configuration_main_demo as main
from test_main_demo_configuration import source


def old_source():
    files = {path: raw for path, raw in source().items() if not path.startswith('CommonForms/')}
    for name in (b'OperationDraft', b'DraftDetails'):
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'\t\t\t<CommonForm>' + name + b'</CommonForm>\n', b'')
    return files


class MainDemoCommonFormImportTests(unittest.TestCase):
    def test_exact_current_source_loads_both_forms_but_only_document_manifest(self):
        manifest = main._manifest
        with patch.object(main, '_manifest', wraps=manifest) as called:
            config = main.import_main_demo_configuration(source(), profile=main.PROFILE)
        self.assertEqual(config.profile, 'main-demo-v1')
        self.assertEqual(len(config.files), 39)
        self.assertEqual(main.canonical(config), config)
        self.assertEqual(set(called.call_args_list[0].args[1]),
                         {'document.receipt.form.card', 'document.issue.form.card'})
        self.assertEqual((len(config.commands), len(config.reports)), (6, 4))

    def test_old_exact_33_file_envelope_is_not_silently_admitted(self):
        files = old_source()
        self.assertEqual(len(files), 33)
        self.assertEqual(sha256(files['Configuration.xml']).hexdigest(),
                         '8deb0314f711790f9ea02d3fdcdf2c34403e7f249f55038ed3146859053f346c')
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            main.import_main_demo_configuration(files, profile=main.PROFILE)

    def test_mixed_old_root_and_new_forms_are_refused(self):
        files = source()
        files['Configuration.xml'] = old_source()['Configuration.xml']
        with self.assertRaises(ValueError):
            main.import_main_demo_configuration(files, profile=main.PROFILE)

    def test_each_common_form_source_is_bound_and_cannot_be_injected(self):
        original = source()
        names = [name for name in original if name.startswith('CommonForms/')]
        self.assertEqual(len(names), 6)
        for name in names:
            with self.subTest(path=name):
                changed = dict(original)
                changed[name] += b'\n'
                with self.assertRaises(ValueError):
                    main.import_main_demo_configuration(changed, profile=main.PROFILE)
        original['CommonForms/Foreign.xml'] = b'<CommonForm/>'
        with self.assertRaises(ValueError):
            main.import_main_demo_configuration(original, profile=main.PROFILE)

    def test_canonical_warm_cache_rejects_previous_and_mixed_source(self):
        config = main.import_main_demo_configuration(source(), profile=main.PROFILE)
        main.canonical(config)
        with self.assertRaises(ValueError):
            main.canonical(replace(config, files=tuple(sorted(old_source().items()))))

    def test_common_forms_never_expand_global_inventory_manifest(self):
        # Even a host-side forged manifest is not a route to CommonForm commands.
        from yadinassi.configuration_inventory_application import _manifest
        with self.assertRaises(ValueError):
            _manifest(dict(main.import_main_demo_configuration(source(), profile=main.PROFILE).files)
                      ['InventoryApplication.xml'], {'commonform.operationdraft': object()}, source(), ())
