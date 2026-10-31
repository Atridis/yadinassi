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
Try CREmit("01", Catalogs.Cc4e0bd7a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.product
Try CREmit("02", Catalogs.C3ee974be.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.category
Try CREmit("03", Catalogs.Cc4e0bd7a.FindByCode("10").Ae089a1a5.IsEmpty()); Except Message("CR-03: [action-error]"); EndTry;
// 10.empty
Try CREmit("04", Catalogs.Cc4e0bd7a.FindByCode("10").Ae089a1a5.Code); Except Message("CR-04: [action-error]"); EndTry;
// 10.code
Try CREmit("05", Catalogs.Cc4e0bd7a.FindByCode("10").Ae089a1a5.Description); Except Message("CR-05: [action-error]"); EndTry;
// 10.description
Try CREmit("06", TypeOf(Catalogs.Cc4e0bd7a.FindByCode("10").Ae089a1a5) = Type("CatalogRef.C3ee974be")); Except Message("CR-06: [action-error]"); EndTry;
// 10.type
Try CREmit("07", Catalogs.Cc4e0bd7a.FindByCode("10").Ae089a1a5.Metadata() = Metadata.Catalogs.C3ee974be); Except Message("CR-07: [action-error]"); EndTry;
// 10.metadata
Try CREmit("08", Catalogs.Cc4e0bd7a.FindByCode("20").Ae089a1a5.IsEmpty()); Except Message("CR-08: [action-error]"); EndTry;
// 20.empty
Try CREmit("09", Catalogs.Cc4e0bd7a.FindByCode("20").Ae089a1a5.Code); Except Message("CR-09: [action-error]"); EndTry;
// 20.code
Try CREmit("10", Catalogs.Cc4e0bd7a.FindByCode("20").Ae089a1a5.Description); Except Message("CR-10: [action-error]"); EndTry;
// 20.description
Try CREmit("11", TypeOf(Catalogs.Cc4e0bd7a.FindByCode("20").Ae089a1a5) = Type("CatalogRef.C3ee974be")); Except Message("CR-11: [action-error]"); EndTry;
// 20.type
Try CREmit("12", Catalogs.Cc4e0bd7a.FindByCode("20").Ae089a1a5.Metadata() = Metadata.Catalogs.C3ee974be); Except Message("CR-12: [action-error]"); EndTry;
// 20.metadata
Try CREmit("13", Catalogs.Cc4e0bd7a.FindByCode("30").Ae089a1a5.IsEmpty()); Except Message("CR-13: [action-error]"); EndTry;
// 30.empty
Try CREmit("14", Catalogs.Cc4e0bd7a.FindByCode("30").Ae089a1a5.Code); Except Message("CR-14: [action-error]"); EndTry;
// 30.code
Try CREmit("15", Catalogs.Cc4e0bd7a.FindByCode("30").Ae089a1a5.Description); Except Message("CR-15: [action-error]"); EndTry;
// 30.description
Try CREmit("16", TypeOf(Catalogs.Cc4e0bd7a.FindByCode("30").Ae089a1a5) = Type("CatalogRef.C3ee974be")); Except Message("CR-16: [action-error]"); EndTry;
// 30.type
Try CREmit("17", Catalogs.Cc4e0bd7a.FindByCode("30").Ae089a1a5.Metadata() = Metadata.Catalogs.C3ee974be); Except Message("CR-17: [action-error]"); EndTry;
// 30.metadata
Try CREmit("18", Catalogs.Cc4e0bd7a.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9")).Ae089a1a5 = Catalogs.C3ee974be.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9"))); Except Message("CR-18: [action-error]"); EndTry;
// sameuuid.typed
Try CREmit("19", Catalogs.Cc4e0bd7a.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9")).Ae089a1a5 = Catalogs.Cc4e0bd7a.GetRef(New UUID("54fd4c31-8dd3-4b6a-8440-653b0d3a0de9"))); Except Message("CR-19: [action-error]"); EndTry;
// sameuuid.cross
Try CREmit("20", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-20: [action-error]"); EndTry;
// control.pad17
Try CREmit("21", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
// control.pad18
Try CREmit("22", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad19
Try CREmit("23", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad20
Try CREmit("24", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad21
