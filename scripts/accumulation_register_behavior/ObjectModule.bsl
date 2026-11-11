Procedure AppendRows(Set, Rows)
    For Each Input In Rows Do
        Row = Set.Add();
        Row.Period = Input.Period; Row.Active = Input.Active; Row.RecordType = Input.RecordType;
        Row.Item = Input.Item; Row.Warehouse = Input.Warehouse;
        Row.Amount = Input.Amount; Row.Quantity = Input.Quantity; Row.Note = Input.Note;
    EndDo;
EndProcedure
Function PersistedCount()
    Q = New Query("SELECT COUNT(*) AS N FROM AccumulationRegister.OwnedAccumulationRows AS R WHERE R.Recorder=&Recorder");
    Q.SetParameter("Recorder", Ref); S = Q.Execute().Select(); S.Next(); Return S.N;
EndFunction
Procedure Posting(Cancel, PostingMode)
    Rows = New Array; Mode = 0;
    AdditionalProperties.Property("Rows", Rows); AdditionalProperties.Property("Mode", Mode);
    Set = RegisterRecords.OwnedAccumulationRows; Set.Write = False;
    AppendRows(Set, Rows);
    If Mode = 11 Then
        Set.Write(); First = PersistedCount(); Set.Clear();
        Replacement = New Array; AdditionalProperties.Property("Replacement", Replacement);
        AppendRows(Set, Replacement); Set.Write();
        AdditionalProperties.Insert("Inside", String(First) + "," + String(PersistedCount()));
    ElsIf Mode = 14 Or Mode = 15 Then
        Set.Write(); AdditionalProperties.Insert("Inside", String(PersistedCount()));
        If Mode = 14 Then Cancel = True; Else Raise "owned accumulation cancellation"; EndIf;
    Else
        Set.Write = True;
    EndIf;
EndProcedure
