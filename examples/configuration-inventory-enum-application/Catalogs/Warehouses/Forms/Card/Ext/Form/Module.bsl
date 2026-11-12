&AtServer
Procedure Created(Cancel, StandardProcessing)
 Dirty = False;
 Status = "";
EndProcedure
&AtClient
Procedure SaveCommand(Command)
 SaveAtServer();
EndProcedure
&AtServer
Procedure SaveAtServer()
 State = WriteObject();
 Status = State;
 If State = "saved" Or State = "unchanged" Then Dirty = False; EndIf;
EndProcedure
&AtClient
Procedure Changed(Element)
 Dirty = True;
 Status = "";
EndProcedure
&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
 If Dirty Then Cancel = True; EndIf;
EndProcedure
