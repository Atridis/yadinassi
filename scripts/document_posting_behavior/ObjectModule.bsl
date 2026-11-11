Procedure TraceStage(Name)
    Trace = "";
    AdditionalProperties.Property("Trace", Trace);
    AdditionalProperties.Insert("Trace", Trace + Name + ":" + String(Number(Posted)) + ";");
EndProcedure
Procedure BeforeWrite(Cancel, WriteMode, PostingMode)
    TraceStage("before");
    If Number = "10" Then Cancel = True; EndIf;
EndProcedure
Procedure OnWrite(Cancel)
    TraceStage("after");
EndProcedure
Procedure Posting(Cancel, PostingMode)
    TraceStage("posting");
    Mode = 0; AdditionalProperties.Property("Mode", Mode);
    If Mode = 10 Then Cancel = True; Return; EndIf;
    Set = RegisterRecords.OwnedPostingRows;
    If Mode <> 5 Then
        Row = Set.Add(); Row.Active = True; Row.Key = Mode; Row.Amount = Mode + 1;
        If Mode = 3 Then Row = Set.Add(); Row.Active = True; Row.Key = 99; Row.Amount = 2; EndIf;
    EndIf;
    If Mode = 3 Or Mode = 4 Or Mode = 5 Then Set.Write = True; EndIf;
    If Mode = 8 Or Mode = 9 Or Mode = 11 Then Set.Write(); EndIf;
    If Mode = 9 Then Set.Clear(); Row = Set.Add(); Row.Active = True; Row.Key = 88; Row.Amount = 88; Set.Write(); EndIf;
    If Mode = 11 Then Raise "owned posting cancellation"; EndIf;
EndProcedure
Procedure UndoPosting(Cancel)
    TraceStage("undo");
EndProcedure
