"""Authored dialog sources, not native UI/timeout/default-button evidence."""
from configuration_form_results_fixture import sources as form_sources, OWNER_MODULE

QUESTION='ShowQueryBox(Callback,"Continue?",QuestionDialogMode.YesNoCancel);'
WARNING='ShowMessageBox(Callback,"Notice");'


def sources(*, warning=False, showing=None, completion=None, suffix='Greeting="waiting";'):
    files=form_sources()
    showing=(WARNING if warning else QUESTION) if showing is None else showing
    completion=(('Extra.Calls=Extra.Calls+1; Greeting="dismissed";' if warning else
        'Extra.Calls=Extra.Calls+1; Seen=Result; If Result=DialogReturnCode.Yes Then Greeting="yes"; Else Greeting="other"; EndIf;')
        if completion is None else completion)
    signature='Extra' if warning else 'Result, Extra'
    files[OWNER_MODULE]=('''Var Extra, Callback, Seen;
&AtServer
Procedure Created(Cancel,StandardProcessing) Greeting="owner"; EndProcedure
&AtClient
Procedure ShowDetails(Command)
 Extra=New Structure("Calls",0);
 Callback=New CallbackDescription("Completed",ThisObject,Extra);
 '''+showing+'\n'+suffix+'''
EndProcedure
&AtClient
Procedure Completed('''+signature+''') Export
 '''+completion+'''
EndProcedure
''').encode()
    return files
