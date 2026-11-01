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
S = Undefined; Try S = Documents.Dad0328ac.Select(); Except EndTry;
T = Undefined; Try T = Documents.Dad0328ac.Select(Date(2024,2,29,12,34,56),Date(2024,2,29,12,34,56)); Except EndTry;
E = Undefined; Try E = Documents.Dad0328ac.Select(Date(1999,1,1),Date(1999,1,2)); Except EndTry;
Try CREmit("01", Documents.Dad0328ac.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.document
Try CREmit("02", Catalogs.C95217507.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", String(TypeOf(S))); Except Message("CR-03: [action-error]"); EndTry;
// selection.type
Try CREmit("04", S.Number); Except Message("CR-04: [action-error]"); EndTry;
// before.number
Try CREmit("05", S.Next()); Except Message("CR-05: [action-error]"); EndTry;
// 0.next
Try CREmit("06", S.Number); Except Message("CR-06: [action-error]"); EndTry;
// 0.number
Try CREmit("07", XMLString(S.Date)); Except Message("CR-07: [action-error]"); EndTry;
// 0.date
Try CREmit("08", S.A5449af58.Description); Except Message("CR-08: [action-error]"); EndTry;
// 0.target
Try CREmit("09", S.Next()); Except Message("CR-09: [action-error]"); EndTry;
// 1.next
Try CREmit("10", S.Number); Except Message("CR-10: [action-error]"); EndTry;
// 1.number
Try CREmit("11", XMLString(S.Date)); Except Message("CR-11: [action-error]"); EndTry;
// 1.date
Try CREmit("12", S.A5449af58.Description); Except Message("CR-12: [action-error]"); EndTry;
// 1.target
Try CREmit("13", S.Next()); Except Message("CR-13: [action-error]"); EndTry;
// 2.next
Try CREmit("14", S.Number); Except Message("CR-14: [action-error]"); EndTry;
// 2.number
Try CREmit("15", XMLString(S.Date)); Except Message("CR-15: [action-error]"); EndTry;
// 2.date
Try CREmit("16", S.A5449af58.Description); Except Message("CR-16: [action-error]"); EndTry;
// 2.target
Try CREmit("17", S.Next()); Except Message("CR-17: [action-error]"); EndTry;
// exhaust
Try CREmit("18", S.Number); Except Message("CR-18: [action-error]"); EndTry;
// retained
Try CREmit("19", S.Next()); Except Message("CR-19: [action-error]"); EndTry;
// after.exhaust
Try CREmit("20", T.Next()); Except Message("CR-20: [action-error]"); EndTry;
// range.first
Try CREmit("21", T.Number); Except Message("CR-21: [action-error]"); EndTry;
// range.number
Try CREmit("22", T.Next()); Except Message("CR-22: [action-error]"); EndTry;
// range.exhaust
Try CREmit("23", E.Next()); Except Message("CR-23: [action-error]"); EndTry;
// empty.range
Try CREmit("24", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
