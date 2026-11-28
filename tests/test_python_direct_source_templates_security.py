"""Source template markers cannot be retargeted or invoke unowned hooks."""
import unittest
from unittest.mock import patch
import test_source_common_templates as existing
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.configuration.common_templates import SourceTemplateCall, SourceCommonTemplates
from yadinassi.runtime import Interpreter


class SourceTemplateSecurity(unittest.TestCase):
    app=existing.SourceTemplateTests.app

    def test_foreign_source_marker_before_argument(self):
        app,other=self.app(allow_extensions=True),self.app()
        app.interpreter.register_function('Read',SourceTemplateCall(other.common_templates))
        app.interpreter.execute('Function Touch() Raise "wrong"; EndFunction')
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('Read(Touch())')

    def test_forged_owner_pointer_and_inventory_no_callbacks(self):
        for field in ('_app','_entries'):
            with self.subTest(field=field):
                app=self.app();calls=[]
                if field=='_app':
                    app.common_templates._app=lambda:(calls.append('wrong'),app)[1]
                else:
                    class Fake:
                        @property
                        def name(self):
                            calls.append('wrong');return 'OwnedText'
                    app.common_templates._entries['ownedtext']=Fake()
                with self.assertRaises(BoundaryViolation):
                    app.interpreter.execute('GetCommonTemplate("OwnedText")')
                self.assertEqual(calls,[])

    def test_factory_and_store_hook_rejected_before_callback(self):
        from yadinassi.streams.text_documents import BSLTextDocument
        for cls,name in ((BSLTextDocument,'__init__'),(SourceCommonTemplates,'get')):
            with self.subTest(name=name):
                app=self.app()
                callback=unittest.mock.Mock(side_effect=AssertionError('wrong-hook'))
                with patch.object(cls,name,callback):
                    with self.assertRaises(BoundaryViolation):
                        app.interpreter.execute('GetCommonTemplate("OwnedText")')
                callback.assert_not_called()

    def test_standalone_saved_template_marker_is_not_capability(self):
        app=self.app();vm=Interpreter(lambda _:None, allow_extensions=True);self.addCleanup(vm.close)
        vm.register_function('GetCommonTemplate',SourceTemplateCall(app.common_templates))
        vm.variables['saved']=vm.functions['getcommontemplate']
        vm.execute('Function Touch() Raise "wrong"; EndFunction')
        from yadinassi.types.errors import BSLError
        with self.assertRaisesRegex(BSLError,'foreign or inactive'):
            vm.execute('Saved(Touch())')

    def test_forged_metadata_entry_rejected_without_property_callback(self):
        app=self.app();calls=[]
        metadata=app.metadata.find_by_full_name('CommonTemplate.OwnedText')
        class Fake:
            @property
            def family(self):
                calls.append('wrong');return 'CommonTemplate'
        metadata._entry=Fake()
        app.interpreter.variables['resource']=metadata
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('GetCommonTemplate(Resource)')
        self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
