Procedure Posting(Cancel, PostingMode)
    Mode = 0; AdditionalProperties.Property("Mode", Mode);
    Set = RegisterRecords.Stock; Set.Clear();
    For Each Line In Lines Do
        Row = Set.Add(); Row.Period = Date; Row.Active = True;
        Row.RecordType = AccumulationRecordType.Expense;
        Row.Product = Line.Product; Row.Warehouse = Warehouse;
        Row.Unit = Line.Unit; Row.State = State;
        Row.Quantity = Line.Quantity; Row.Amount = Line.Amount; Row.Note = "issue:" + Number;
    EndDo;
    If Mode = 1 Or Mode = 2 Then
        Set.Write();
        Q = New Query("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock AS R WHERE R.Note=&Tag");
        Q.SetParameter("Tag", "issue:" + Number); S = Q.Execute().Select(); S.Next();
        AdditionalProperties.Insert("Inside", S.N);
        If Mode = 1 Then Cancel = True; Else Raise "owned inventory cancellation"; EndIf;
    Else
        // Demo business rule: refuse an issue that would make stock negative.
        Set.Write();
        Query = New Query("SELECT B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B WHERE B.Warehouse=&Warehouse AND B.QuantityBalance<0");
        Query.SetParameter("At", Date + 1);
        Query.SetParameter("Warehouse", Warehouse);
        If Not Query.Execute().IsEmpty() Then
            Cancel = True;
        EndIf;
    EndIf;
EndProcedure
