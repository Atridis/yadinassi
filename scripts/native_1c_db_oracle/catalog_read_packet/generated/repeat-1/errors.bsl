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
CRObserve("01", "Catalogs.C01a9a4ac.EmptyRef().Metadata().Name"); // control.name
CRObserve("02", "String(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).UUID())"); // control.uuid
CRObserve("03", "Справочники.C01a9a4ac.Метаданные() = Metadata.Catalogs.C01a9a4ac"); // manager.ru
CRObserve("04", "Строка(Справочники.C01a9a4ac.ПолучитьСсылку(Новый УникальныйИдентификатор(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).УникальныйИдентификатор())"); // ref.ru
CRObserve("05", "Справочники.C01a9a4ac.ПустаяСсылка().Пустая()"); // empty.ru
CRObserve("06", "ЗначениеЗаполнено(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")))"); // filled.ru
CRObserve("07", "Catalogs[""C01a9a4ac""].Metadata().Name"); // index.name
CRObserve("08", "Catalogs.c01a9a4ac.Metadata().Name"); // property.lower
CRObserve("09", "Catalogs[""C01A9A4AC""].Metadata().Name"); // index.upper
CRObserve("10", "Catalogs[0].Metadata().Name"); // index.number
CRObserve("11", "Catalogs[Undefined].Metadata().Name"); // index.undefined
CRObserve("12", "Catalogs.AbsentProbe.Metadata().Name"); // property.missing
CRObserve("13", "Catalogs[""AbsentProbe""].Metadata().Name"); // index.missing
CRObserve("14", "Catalogs.C01a9a4ac.GetRef(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"").IsEmpty()"); // getref.string
CRObserve("15", "Catalogs.C01a9a4ac.GetRef(Undefined).IsEmpty()"); // getref.undefined
CRObserve("16", "Catalogs.C01a9a4ac.GetRef(1).IsEmpty()"); // getref.number
CRObserve("17", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846""),1).IsEmpty()"); // getref.extra
CRObserve("18", "Catalogs.C01a9a4ac.EmptyRef(1).IsEmpty()"); // empty.extra
CRObserve("19", "String(Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).UUID(1))"); // uuid.extra
CRObserve("20", "Catalogs.C01a9a4ac.GetRef(New UUID(""895e6e79-e0c6-474d-bad2-7aeee4aa3846"")).IsEmpty(1)"); // isempty.extra
CRObserve("21", "Catalogs.C01a9a4ac.Metadata(1).Name"); // metadata.extra
Попытка
    Catalogs.C01a9a4ac = Undefined;
    CREmit("22", Истина);
Исключение
    Сообщить("CR-22: [action-error]");
КонецПопытки; // readonly.manager
Попытка
    Catalogs.C01a9a4ac.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846")).Ref = Undefined;
    CREmit("23", Истина);
Исключение
    Сообщить("CR-23: [action-error]");
КонецПопытки; // readonly.ref
CRObserve("24", "Catalogs.C01a9a4ac.Metadata().Name"); // postwrite.name
