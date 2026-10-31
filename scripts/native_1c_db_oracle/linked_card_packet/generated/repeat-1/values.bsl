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
Failed = Ложь;
Try CREmit("01", Catalogs.C8011eed4.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.product
Try CREmit("02", Catalogs.Cfedffdf5.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.category
Try CREmit("03", Catalogs.C8011eed4.FindByCode("10").Acb092b78); Except Message("CR-03: [action-error]"); EndTry;
// 10.text
Try CREmit("04", XMLString(Catalogs.C8011eed4.FindByCode("10").A442761a6)); Except Message("CR-04: [action-error]"); EndTry;
// 10.number
Try CREmit("05", Catalogs.C8011eed4.FindByCode("10").Ade9513c6); Except Message("CR-05: [action-error]"); EndTry;
// 10.boolean
Try CREmit("06", XMLString(Catalogs.C8011eed4.FindByCode("10").Aa312fe5e)); Except Message("CR-06: [action-error]"); EndTry;
// 10.date
Try CREmit("07", ValueIsFilled(Catalogs.C8011eed4.FindByCode("10").A2bd85387)); Except Message("CR-07: [action-error]"); EndTry;
// 10.filled
Try CREmit("08", String(Catalogs.C8011eed4.FindByCode("10").A2bd85387.UUID())); Except Message("CR-08: [action-error]"); EndTry;
// 10.ref
Try CREmit("09", Catalogs.C8011eed4.FindByCode("20").Acb092b78); Except Message("CR-09: [action-error]"); EndTry;
// 20.text
Try CREmit("10", XMLString(Catalogs.C8011eed4.FindByCode("20").A442761a6)); Except Message("CR-10: [action-error]"); EndTry;
// 20.number
Try CREmit("11", Catalogs.C8011eed4.FindByCode("20").Ade9513c6); Except Message("CR-11: [action-error]"); EndTry;
// 20.boolean
Try CREmit("12", XMLString(Catalogs.C8011eed4.FindByCode("20").Aa312fe5e)); Except Message("CR-12: [action-error]"); EndTry;
// 20.date
Try CREmit("13", ValueIsFilled(Catalogs.C8011eed4.FindByCode("20").A2bd85387)); Except Message("CR-13: [action-error]"); EndTry;
// 20.filled
Try CREmit("14", String(Catalogs.C8011eed4.FindByCode("20").A2bd85387.UUID())); Except Message("CR-14: [action-error]"); EndTry;
// 20.ref
Try CREmit("15", Catalogs.C8011eed4.FindByCode("30").Acb092b78); Except Message("CR-15: [action-error]"); EndTry;
// 30.text
Try CREmit("16", XMLString(Catalogs.C8011eed4.FindByCode("30").A442761a6)); Except Message("CR-16: [action-error]"); EndTry;
// 30.number
Try CREmit("17", Catalogs.C8011eed4.FindByCode("30").Ade9513c6); Except Message("CR-17: [action-error]"); EndTry;
// 30.boolean
Try CREmit("18", XMLString(Catalogs.C8011eed4.FindByCode("30").Aa312fe5e)); Except Message("CR-18: [action-error]"); EndTry;
// 30.date
Try CREmit("19", ValueIsFilled(Catalogs.C8011eed4.FindByCode("30").A2bd85387)); Except Message("CR-19: [action-error]"); EndTry;
// 30.filled
Try CREmit("20", String(Catalogs.C8011eed4.FindByCode("30").A2bd85387.UUID())); Except Message("CR-20: [action-error]"); EndTry;
// 30.ref
Try CREmit("21", Catalogs.C8011eed4.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
// control.pad18
Try CREmit("22", Catalogs.C8011eed4.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad19
Try CREmit("23", Catalogs.C8011eed4.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad20
Try CREmit("24", Catalogs.C8011eed4.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad21
