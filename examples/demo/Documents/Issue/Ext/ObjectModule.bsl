Процедура Posting(Cancel, PostingMode)
    Mode = 0; AdditionalProperties.Property("Mode", Mode);
    Set = RegisterRecords.Stock; Set.Clear();
    Для Каждого Line Из Lines Цикл
        Row = Set.Add(); Row.Period = Date; Row.Active = Истина;
        Row.RecordType = AccumulationRecordType.Expense;
        Row.Product = Line.Product; Row.Warehouse = Warehouse;
        Row.Unit = Line.Unit; Row.State = State;
        Row.Quantity = Line.Quantity; Row.Amount = Line.Amount; Row.Note = "issue:" + Number;
    КонецЦикла;
    Если Mode = 1 Или Mode = 2 Тогда
        Set.Write();
        Q = Новый Запрос("SELECT COUNT(*) AS N FROM AccumulationRegister.Stock AS R WHERE R.Note=&Tag");
        Q.SetParameter("Tag", "issue:" + Number); S = Q.Execute().Select(); S.Next();
        AdditionalProperties.Insert("Inside", S.N);
        Если Mode = 1 Тогда Cancel = Истина; Иначе ВызватьИсключение "owned inventory cancellation"; КонецЕсли;
    Иначе
        // Demo business rule: refuse an issue that would make stock negative.
        Set.Write();
        Query = Новый Запрос("SELECT B.QuantityBalance AS Quantity FROM AccumulationRegister.Stock.Balance(&At) AS B WHERE B.Warehouse=&Warehouse AND B.QuantityBalance<0");
        Query.SetParameter("At", Date + 1);
        Query.SetParameter("Warehouse", Warehouse);
        Если Не Query.Execute().IsEmpty() Тогда
            Cancel = Истина;
        КонецЕсли;
    КонецЕсли;
КонецПроцедуры
