Procedure Posting(Cancel, PostingMode)
    Movements = RegisterRecords.Stock;
    Movements.Clear(); Movements.Write = True;
    For Each Line In Lines Do
        Row = Movements.Add(); Row.Period = Date;
        Row.RecordType = AccumulationRecordType.Receipt;
        Row.Product = Line.Product; Row.Warehouse = Warehouse;
        Row.Quantity = Line.Quantity; Row.Amount = Line.Amount; Row.Note = "receipt:" + Number;
    EndDo;
EndProcedure
