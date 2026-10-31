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
CRObserve("01", "Catalogs.C01a9a4ac.Metadata().Name"); // manager.name
CRObserve("02", "Catalogs.C992ca266.Metadata().Name"); // other.name
CRObserve("03", "String(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).UUID())"); // ref.uuid
CRObserve("04", "String(Catalogs.C992ca266.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).UUID())"); // other.uuid
CRObserve("05", "String(Catalogs.C01a9a4ac.EmptyRef().UUID())"); // empty.uuid
CRObserve("06", "Catalogs.C01a9a4ac.EmptyRef().IsEmpty()"); // empty.isempty
CRObserve("07", "ValueIsFilled(Catalogs.C01a9a4ac.EmptyRef())"); // empty.filled
CRObserve("08", "Catalogs.C01a9a4ac.GetRef(New UUID(""00000000-0000-0000-0000-000000000000"")) = Catalogs.C01a9a4ac.EmptyRef()"); // zero.empty
CRObserve("09", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).IsEmpty()"); // record.isempty
CRObserve("10", "ValueIsFilled(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // record.filled
CRObserve("11", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")) = Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846""))"); // record.repeat
CRObserve("12", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")) = Catalogs.C01a9a4ac.GetRef(New UUID(""161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4""))"); // record.other
CRObserve("13", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")) = Catalogs.C992ca266.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846""))"); // record.crosscatalog
CRObserve("14", "Catalogs.C01a9a4ac.EmptyRef() = Catalogs.C992ca266.EmptyRef()"); // empty.crosscatalog
CRObserve("15", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")) = New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")"); // record.uuid_equal
CRObserve("16", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")) = Undefined"); // record.undefined
CRObserve("17", "Catalogs.C01a9a4ac.Metadata() = Metadata.Catalogs.C01a9a4ac"); // manager.metadata
CRObserve("18", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).Metadata() = Metadata.Catalogs.C01a9a4ac"); // ref.metadata
CRObserve("19", "Catalogs.C01a9a4ac.EmptyRef().Metadata() = Metadata.Catalogs.C01a9a4ac"); // empty.metadata
CRObserve("20", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).Metadata().FullName()"); // ref.fullname
CRObserve("21", "Catalogs.C992ca266.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).Metadata() = Metadata.Catalogs.C992ca266"); // ref.metadata.other
CRObserve("22", "String(Catalogs.C01a9a4ac.GetRef(New UUID(""161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"")).UUID())"); // absent.uuid
CRObserve("23", "Catalogs.C01a9a4ac.GetRef(New UUID(""161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"")).IsEmpty()"); // absent.empty
CRObserve("24", "ValueIsFilled(Catalogs.C01a9a4ac.GetRef(New UUID(""161a1dd2-e18e-472c-bf4d-ac8fba4cc7a4"")))"); // absent.filled
