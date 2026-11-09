// Trusted client handlers. Remote names are fixed by client.json, never the UI.
&AtClient
Procedure Changed(Element)
    ThisObject.Dirty = True;
    ThisObject.Status = "Unsaved changes; recalculate or save the order";
EndProcedure

&AtClient
Procedure AddCommand(Command)
    RemoteAdd();
EndProcedure

&AtClient
Procedure DeleteCommand(Command)
    RemoteDelete();
EndProcedure

&AtClient
Procedure RecalculateCommand(Command)
    RemoteRecalculate();
EndProcedure

&AtClient
Procedure SaveCommand(Command)
    RemoteSave();
    Message(ThisObject.Status);
EndProcedure

&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
    If ThisObject.Dirty Then
        Cancel = True;
        If ThisObject.SaveAttempted Then
            Message("A save was attempted. Reconcile the database before restarting; stop the launcher to leave this locked form.");
        Else
            Message("Unsaved order: save before closing, or stop the launcher to discard edits.");
        EndIf;
    EndIf;
EndProcedure
