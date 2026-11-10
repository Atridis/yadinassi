&AtClient
Procedure SearchCommand(Command)
    RemoteSearch();
EndProcedure

&AtClient
Procedure ChooseCommand(Command)
    RemoteChoose();
EndProcedure

&AtClient
Procedure CancelCommand(Command)
    RemoteCancel();
EndProcedure

&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
    RemoteCancel();
EndProcedure
