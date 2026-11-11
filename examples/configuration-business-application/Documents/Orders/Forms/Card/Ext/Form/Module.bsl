&AtServer
Procedure Created(Cancel, StandardProcessing)
 Dirty = False;
 Status = "Rows loaded: " + String(Object.Lines.Count());
EndProcedure
&AtClient
Procedure Changed(Element)
 Dirty = True;
 Status = "";
EndProcedure
&AtClient
Procedure NewLineCommand(Command)
 AddAtServer();
EndProcedure
&AtServer
Procedure AddAtServer()
 Row = Object.Lines.Add();
 Row.Label = "New line";
 Row.Quantity = 1;
 Row.Checked = False;
 Dirty = True;
 Status = "";
EndProcedure
&AtClient
Procedure DeleteSelectedCommand(Command)
 DeleteAtServer();
EndProcedure
&AtServer
Procedure DeleteAtServer()
 Row = Items.LinesTable.CurrentData;
 If Row <> Undefined Then
  Object.Lines.Delete(Row);
  Dirty = True;
  Status = "";
 EndIf;
EndProcedure
&AtClient
Procedure WriteCommand(Command)
 WriteAtServer();
EndProcedure
&AtServer
Procedure WriteAtServer()
 State = WriteObject();
 Status = State;
 If State = "saved" Or State = "unchanged" Then Dirty = False; EndIf;
EndProcedure
&AtClient
Procedure BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
 If Dirty Then Cancel = True; EndIf;
EndProcedure
