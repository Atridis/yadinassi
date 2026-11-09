&AtClient
Procedure Changed(Element)
    ThisObject.Dirty = True;
    ThisObject.Status = "Unsaved changes";
EndProcedure
&AtClient
Procedure RunCommand(Command)
    RemoteRun();
    ThisObject.Dirty = False;
    Message(ThisObject.Status);
EndProcedure
&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
    If ThisObject.Dirty Then
        Cancel = True;
        Message("Run the command before closing, or stop the launcher to discard edits.");
    EndIf;
EndProcedure
