"""All constant writes compile handlers using the owning source profile."""
from pathlib import Path
import tempfile
import unittest
from test_source_constant_store import configuration
from yadinassi.configuration_source_runtime import SourceApplication

WRITES=(
    'Constants.Text.Set("original");',
    'M=Constants.Text.CreateValueManager();M.Value="original";M.Write();',
    'S=Constants.CreateSet("Text");S.Text="original";S.Write();',
)

class ConstantProfileTests(unittest.TestCase):
    def run_case(self,profile,write,module):
        with tempfile.TemporaryDirectory() as directory:
            files={'Ext/SessionModule.bsl':('Procedure SessionParametersSetting(Names)\n'+write+'\nEndProcedure').encode(),
                   'Constants/Text/Ext/ValueManagerModule.bsl':module.encode()}
            app=SourceApplication(configuration(files),scratch_database=Path(directory)/'scratch.sqlite',
                                  compilation_profile=profile,output=lambda _:None)
            try:
                app.start()
                return app.constant_store.get('Text')
            finally:app.close()

    def test_handler_body_branch_for_each_write_path(self):
        module='''Procedure BeforeWrite(Cancel)
#If ThickClientManagedApplication Then
 Value="managed";
#Else
 Value="standalone";
#EndIf
EndProcedure'''
        for profile,expected in [('standalone','standalone'),('managed-thick-file','managed')]:
            for write in WRITES:
                with self.subTest(profile=profile,write=write):
                    self.assertEqual(self.run_case(profile,write,module),expected)

    def test_handler_presence_branch_for_each_write_path(self):
        for symbol in ['ThickClientManagedApplication','Not ThickClientManagedApplication']:
            module='#If '+symbol+' Then\nProcedure BeforeWrite(Cancel)\nValue="selected";\nEndProcedure\n#EndIf'
            for profile in ['standalone','managed-thick-file']:
                selected=(profile=='managed-thick-file') == (symbol=='ThickClientManagedApplication')
                for write in WRITES:
                    with self.subTest(profile=profile,write=write,symbol=symbol):
                        self.assertEqual(self.run_case(profile,write,module),'selected' if selected else 'original')
