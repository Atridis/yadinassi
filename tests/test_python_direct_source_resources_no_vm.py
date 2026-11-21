"""Source template/resource behavior with legacy execution poisoned."""
import unittest
from unittest.mock import patch
import test_source_common_templates as existing
from yadinassi.runtime import Interpreter


class SourceResourcesNoVM(existing.SourceTemplateTests):
    def setUp(self):
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start(); self.addCleanup(poison.stop)

    def test_bilingual_text_constructor_and_saved_method(self):
        app=self.app()
        app.interpreter.execute('D=New ТекстовыйДокумент; D.УстановитьТекст("one"); F=D.AddLine; F("two");')
        self.assertEqual(app.interpreter.execute('D.GetText()'),'one\ntwo\n')
        self.assertEqual(app.interpreter.execute('D.КоличествоСтрок()'),2)


class SourceResourceFormsNoVM(unittest.TestCase):
    import test_source_forms as _forms
    setUp=SourceResourcesNoVM.setUp
    app=_forms.SourceFormTests.app
    test_safe_mode_effect_guard_in_client_event=_forms.SourceFormTests.test_safe_mode_effect_guard_in_client_event


if __name__ == '__main__':
    unittest.main()
