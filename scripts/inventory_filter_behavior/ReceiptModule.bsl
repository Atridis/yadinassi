Procedure Posting(Cancel, PostingMode)
    Mode = 0; AdditionalProperties.Property("Mode", Mode);
    Set = RegisterRecords.Stock; Set.Clear();
    For Each Line In Lines Do
        Row = Set.Add(); Row.Period = Date; Row.Active = True;
        Row.RecordType = AccumulationRecordType.Receipt;
        Row.Product = Line.Product; Row.Warehouse = Warehouse;
        Row.Quantity = Line.Quantity; Row.Amount = Line.Amount; Row.Note = "receipt:" + Number;
    EndDo;
    If Mode = 1 Or Mode = 2 Then
        Set.Write();
        Q = New Query("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock AS R WHERE R.Note=&Tag");
        Q.SetParameter("Tag", "receipt:" + Number); S = Q.Execute().Select(); S.Next();
        AdditionalProperties.Insert("Inside", S.N);
        If Mode = 1 Then Cancel = True; Else Raise "owned inventory cancellation"; EndIf;
    Else
        Set.Write = True;
    EndIf;
EndProcedure
