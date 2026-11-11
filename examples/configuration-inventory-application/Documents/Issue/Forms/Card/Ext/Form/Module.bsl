&AtServer
Procedure Created(Cancel, StandardProcessing)
 If Object.Number = "" Then Object.Date = Date(2026, 11, 11, 12, 0, 0); EndIf;
 Dirty = False;
 Status = "";
EndProcedure
&AtClient
Procedure AddLineCommand(Command)
 AddAtServer();
EndProcedure
&AtServer
Procedure AddAtServer()
 Row = Object.Lines.Add();
 Row.Quantity = 1;
 Row.Amount = 0;
 Dirty = True;
 Status = "";
EndProcedure
&AtClient
Procedure DeleteLineCommand(Command)
 DeleteAtServer();
EndProcedure
&AtServer
Procedure DeleteAtServer()
 Row = Items.LinesTable.CurrentData;
 If Row <> Undefined Then Object.Lines.Delete(Row); Dirty = True; EndIf;
EndProcedure
&AtClient
Procedure WriteCommand(Command)
EndProcedure
&AtClient
Procedure PostCommand(Command)
EndProcedure
&AtClient
Procedure UndoPostingCommand(Command)
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
