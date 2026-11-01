// LOCAL preparation: generated owned-config probe. No native answers predicted.
Функция CRText(Знач Text)
    Если СтрДлина(Text) > 64 Тогда ВызватьИсключение "metadata-observer-bound"; КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "metadata-observer-unit"; КонецЕсли;
        Digits = "";
        Для D = 1 По 4 Цикл
            Q = Цел(Code / 16);
            Digits = Сред("0123456789abcdef", Code - Q * 16 + 1, 1) + Digits;
            Code = Q;
        КонецЦикла;
        Record = Record + Digits;
    КонецЦикла;
    Возврат Record;
КонецФункции
Функция CRScalar(Знач Value)
    Если ТипЗнч(Value) = Тип("Строка") Тогда Возврат CRText(Value); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Булево") Тогда Возврат ?(Value, "B1", "B0"); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Неопределено") Тогда Возврат "U"; КонецЕсли;
    Если ТипЗнч(Value) = Тип("Число") Тогда
        Если Value < 0 Или Value > 64 Или Value <> Цел(Value) Тогда ВызватьИсключение "metadata-observer-number"; КонецЕсли;
        Возврат "N" + Строка(Value);
    КонецЕсли;
    ВызватьИсключение "metadata-observer-type";
КонецФункции
Процедура CREmit(Знач Label, Знач Value)
    Попытка
        Encoded = CRScalar(Value);
    Исключение
        Сообщить("CR-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("CR-" + Label + ": [ok|" + Encoded + "]");
КонецПроцедуры
Процедура CRObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("CR-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    CREmit(Label, Value);
КонецПроцедуры
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
Q = New Query; Q.Text = "SELECT Ref.Number AS Owner, LineNumber, Product, Quantity, Price, Amount, Note FROM Document.De777997a.Items ORDER BY Ref.Number, LineNumber"; W = Q.Execute().Select();
Try CREmit("01", Documents.De777997a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
Try CREmit("02", Catalogs.Cb27de61e.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
Try CREmit("03", W.Next()); Except Message("CR-03: [action-error]"); EndTry;
Try CREmit("04", W.Owner); Except Message("CR-04: [action-error]"); EndTry;
Try CREmit("05", W.LineNumber); Except Message("CR-05: [action-error]"); EndTry;
Try CREmit("06", XMLString(W.Amount)); Except Message("CR-06: [action-error]"); EndTry;
Try CREmit("07", String(W.Product.UUID())); Except Message("CR-07: [action-error]"); EndTry;
Try CREmit("08", W.Next()); Except Message("CR-08: [action-error]"); EndTry;
Try CREmit("09", W.Owner); Except Message("CR-09: [action-error]"); EndTry;
Try CREmit("10", W.LineNumber); Except Message("CR-10: [action-error]"); EndTry;
Try CREmit("11", XMLString(W.Amount)); Except Message("CR-11: [action-error]"); EndTry;
Try CREmit("12", String(W.Product.UUID())); Except Message("CR-12: [action-error]"); EndTry;
Try CREmit("13", W.Next()); Except Message("CR-13: [action-error]"); EndTry;
Try CREmit("14", W.Owner); Except Message("CR-14: [action-error]"); EndTry;
Try CREmit("15", W.LineNumber); Except Message("CR-15: [action-error]"); EndTry;
Try CREmit("16", XMLString(W.Amount)); Except Message("CR-16: [action-error]"); EndTry;
Try CREmit("17", String(W.Product.UUID())); Except Message("CR-17: [action-error]"); EndTry;
Try CREmit("18", W.Next()); Except Message("CR-18: [action-error]"); EndTry;
Try CREmit("19", W.Owner); Except Message("CR-19: [action-error]"); EndTry;
Try CREmit("20", W.LineNumber); Except Message("CR-20: [action-error]"); EndTry;
Try CREmit("21", XMLString(W.Amount)); Except Message("CR-21: [action-error]"); EndTry;
Try CREmit("22", String(W.Product.UUID())); Except Message("CR-22: [action-error]"); EndTry;
Try CREmit("23", W.Next()); Except Message("CR-23: [action-error]"); EndTry;
Try CREmit("24", Documents.De777997a.FindByNumber("30").Items.Count()); Except Message("CR-24: [action-error]"); EndTry;
