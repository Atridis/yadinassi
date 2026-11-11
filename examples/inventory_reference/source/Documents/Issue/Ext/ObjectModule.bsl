// This example authors a negative-stock rule, not a built-in platform policy.
Procedure Posting(Cancel, PostingMode)
    Movements = RegisterRecords.Stock;
    Movements.Clear();
    For Each Line In Lines Do
        Row = Movements.Add(); Row.Period = Date;
        Row.RecordType = AccumulationRecordType.Expense;
        Row.Product = Line.Product; Row.Warehouse = Warehouse;
        Row.Quantity = Line.Quantity; Row.Amount = Line.Amount; Row.Note = "issue:" + Number;
    EndDo;
    Movements.Write();
    Query = New Query("SELECT B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B WHERE B.Warehouse=&Warehouse AND B.QuantityBalance<0");
    Query.SetParameter("At", Date + 1);
    Query.SetParameter("Warehouse", Warehouse);
    If Not Query.Execute().IsEmpty() Then
        Cancel = True;
    EndIf;
EndProcedure
