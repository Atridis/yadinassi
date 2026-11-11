&AtServer
Procedure Created(Cancel, StandardProcessing)
 If Object.Number = "" Then
  Object.Date = Date(2026, 11, 11, 12, 0, 0);
  Object.MovementKey = 1;
 EndIf;
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
EndProcedure
&AtClient
Procedure PostCommand(Command)
EndProcedure
&AtClient
Procedure UndoCommand(Command)
EndProcedure
