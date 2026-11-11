&AtServer
Procedure Created(Cancel, StandardProcessing)
 Dirty = False;
 Status = "";
EndProcedure
&AtClient
Procedure Changed(Element)
 Dirty = True;
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
 If State = "saved" Or State = "unchanged" Then
  Dirty = False;
 EndIf;
EndProcedure
&AtServer
Procedure PreparingWrite(Cancel)
 Object.Description = TrimAll(Object.Description);
 If Object.Description = "" Or Object.Description = "Form reject" Then
  Cancel = True;
 EndIf;
 If Object.Price < 0 Then Cancel = True; EndIf;
EndProcedure
&AtClient
Procedure CustomCommand(Command)
 Object.Price = Object.Price * 0.9;
 Dirty = True;
 Status = "";
EndProcedure
&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
 If Dirty Then Cancel = True; EndIf;
EndProcedure
&AtClient
Procedure CategoryCommand(Command)
 OpenForm("Catalog.Categories.Form.Card");
EndProcedure
