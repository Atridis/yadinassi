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
Procedure ChooseCustomerCommand(Command)
    RemoteChooseCustomer();
EndProcedure

&AtClient
Procedure ChooseProductCommand(Command)
    RemoteChooseProduct();
EndProcedure

&AtClient
Procedure DiscardCommand(Command)
    RemoteDiscard();
EndProcedure

&AtClient
Procedure ResolveCommand(Command)
    RemoteResolve();
EndProcedure

&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
    If ThisObject.Dirty Or ThisObject.Locked Then
        Cancel = True;
        If ThisObject.Locked Then
            Message("Resolve the pending save before closing. A broken transport cannot reconnect or replay it.");
        Else
            Message("Unsaved changes: Save or Discard / Reload before closing.");
        EndIf;
    EndIf;
EndProcedure
