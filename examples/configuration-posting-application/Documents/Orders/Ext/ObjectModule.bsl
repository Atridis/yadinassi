Procedure BeforeWrite(Cancel, WriteMode, PostingMode)
 If Note = "cancel" Then Cancel = True; EndIf;
EndProcedure
Procedure Posting(Cancel, PostingMode)
 Set = RegisterRecords.Rows;
 Counter = 0;
 For Each Line In Lines Do
  Counter = Counter + 1;
  Row = Set.Add();
  Row.Active = True;
  Row.Key = MovementKey * 1000 + Counter;
  Row.Amount = Line.Quantity;
 EndDo;
 Set.Write = True;
EndProcedure
