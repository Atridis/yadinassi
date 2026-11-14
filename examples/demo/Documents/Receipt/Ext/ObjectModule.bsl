Процедура Posting(Cancel, PostingMode)
    Mode = 0; AdditionalProperties.Property("Mode", Mode);
    Set = RegisterRecords.Stock; Set.Clear();
    Для Каждого Line Из Lines Цикл
        Row = Set.Add(); Row.Period = Date; Row.Active = Истина;
        Row.RecordType = AccumulationRecordType.Receipt;
        Row.Product = Line.Product; Row.Warehouse = Warehouse;
        Row.Unit = Line.Unit; Row.State = State;
        Row.Quantity = Line.Quantity; Row.Amount = Line.Amount; Row.Note = "receipt:" + Number;
    КонецЦикла;
    Если Mode = 1 Или Mode = 2 Тогда
        Set.Write();
        Q = Новый Запрос("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock AS R WHERE R.Note=&Tag");
        Q.SetParameter("Tag", "receipt:" + Number); S = Q.Execute().Select(); S.Next();
        AdditionalProperties.Insert("Inside", S.N);
        Если Mode = 1 Тогда Cancel = Истина; Иначе ВызватьИсключение "owned inventory cancellation"; КонецЕсли;
    Иначе
        Set.Write = Истина;
    КонецЕсли;
КонецПроцедуры
