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
CRObserve("01", "Catalogs.C01a9a4ac.Metadata().Name"); // control.name
CRObserve("02", "String(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).UUID())"); // control.uuid
CRObserve("03", "String(TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846""))))"); // ref.type
CRObserve("04", "TypeOf(TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))) = Type(""Type"")"); // ref.metatype
CRObserve("05", "String(TypeOf(Catalogs.C01a9a4ac.EmptyRef()))"); // empty.type
CRObserve("06", "TypeOf(TypeOf(Catalogs.C01a9a4ac.EmptyRef())) = Type(""Type"")"); // empty.metatype
CRObserve("07", "String(TypeOf(Catalogs.C01a9a4ac))"); // manager.type
CRObserve("08", "TypeOf(TypeOf(Catalogs.C01a9a4ac)) = Type(""Type"")"); // manager.metatype
CRObserve("09", "String(TypeOf(Catalogs))"); // global.type
CRObserve("10", "TypeOf(TypeOf(Catalogs)) = Type(""Type"")"); // global.metatype
CRObserve("11", "Type(""СправочникСсылка.C01a9a4ac"") = TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // ru.resolve
CRObserve("12", "Type(""CatalogRef.C01a9a4ac"") = TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // en.resolve
CRObserve("13", "Type(""catalogref.c01a9a4ac"") = TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // lower.resolve
CRObserve("14", "Type(""CATALOGREF.C01A9A4AC"") = TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // upper.resolve
CRObserve("15", "TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846""))) = TypeOf(Catalogs.C01a9a4ac.EmptyRef())"); // ref.empty_type
CRObserve("16", "TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846""))) = TypeOf(Catalogs.C992ca266.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // ref.cross_type
CRObserve("17", "Type(""CatalogManager.C01a9a4ac"") = TypeOf(Catalogs.C01a9a4ac)"); // manager.resolve
CRObserve("18", "Тип(""СправочникМенеджер.C01a9a4ac"") = ТипЗнч(Catalogs.C01a9a4ac)"); // manager.ru
CRObserve("19", "TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).UUID()) = Type(""UUID"")"); // ref.uuid_type
CRObserve("20", "String(Type(""CatalogRef.AbsentProbe""))"); // type.missing
CRObserve("21", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).Метаданные() = Метаданные.Справочники.C01a9a4ac"); // ref.metadata.ru
CRObserve("22", "String(Type(1))"); // type.number
CRObserve("23", "Type(""CatalogRef.C01a9a4ac"",1) = TypeOf(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // type.extra
CRObserve("24", "ТипЗнч(Справочники.C01a9a4ac.ПустаяСсылка()) = TypeOf(Catalogs.C01a9a4ac.EmptyRef())"); // type.ru_en
