// Fixed ordinary FillPropertyValues acquisition. No predicted native answers.
// 48 fresh fixtures, no metadata, database writes, file IO, reflection or Eval.
Функция PVExact(Знач A, Знач B)
    Если ТипЗнч(A) <> Тип("Строка") Или ТипЗнч(B) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(A) <> СтрДлина(B) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(A) Цикл
        Если КодСимвола(A, P) <> КодСимвола(B, P) Тогда Возврат Ложь; КонецЕсли;
    КонецЦикла;
    Возврат Истина;
КонецФункции
Функция PVDigit(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "property-count"; КонецЕсли;
    Возврат Сред("0123456789", V + 1, 1);
КонецФункции
Функция PVFlag(Знач V)
    Если V Тогда Возврат "1"; Иначе Возврат "0"; КонецЕсли;
КонецФункции
Функция PVCell(Знач V, Знач Shared, Знач Target, Знач Source)
    K = ТипЗнч(V);
    Если K = Тип("Неопределено") Тогда Возврат "U_"; КонецЕсли;
    Если K = Тип("Null") Тогда Возврат "L_"; КонецЕсли;
    Если K = Тип("Булево") Тогда Возврат "B" + PVFlag(V); КонецЕсли;
    Если K = Тип("Число") Тогда
        Numbers = Новый Массив;
        Numbers.Add(0); Numbers.Add(1); Numbers.Add(2); Numbers.Add(3); Numbers.Add(4);
        Numbers.Add(5); Numbers.Add(6); Numbers.Add(7); Numbers.Add(8); Numbers.Add(9);
        Numbers.Add(10); Numbers.Add(20); Numbers.Add(30); Numbers.Add(40); Numbers.Add(8.6);
        Для P = 0 По Numbers.Count() - 1 Цикл
            Если V = Numbers[P] Тогда Возврат "N" + Сред("0123456789ABCDE", P + 1, 1); КонецЕсли;
        КонецЦикла;
    ИначеЕсли K = Тип("Строка") Тогда
        Words = СтрРазделить("|old|new|hold|ABCD|ABC|bad|0|1|10|7|9|8.6|8,6", "|", Истина);
        Для P = 0 По Words.Count() - 1 Цикл
            Если PVExact(V, Words[P]) Тогда Возврат "S" + Сред("0123456789ABCD", P + 1, 1); КонецЕсли;
        КонецЦикла;
    ИначеЕсли K = Тип("Массив") Тогда
        Count = V.Count();
        Если Count < 1 Или Count > 2 Или ТипЗнч(V[0]) <> Тип("Число") Или V[0] <> 7 Тогда ВызватьИсключение "property-array"; КонецЕсли;
        Если Count = 2 Тогда
            Если ТипЗнч(V[1]) <> Тип("Число") Или V[1] <> 8 Тогда ВызватьИсключение "property-array"; КонецЕсли;
        КонецЕсли;
        Если V = Shared Тогда Возврат "A" + PVDigit(Count - 1); КонецЕсли;
        Возврат "A" + PVDigit(Count + 1);
    ИначеЕсли K = Тип("СтрокаДереваЗначений") Тогда
        Если ТипЗнч(Target) = Тип("СтрокаДереваЗначений") Тогда
            Если V = Target Тогда Возврат "R0"; КонецЕсли;
            Если V = Target.Parent Тогда Возврат "R2"; КонецЕсли;
        КонецЕсли;
        Если ТипЗнч(Source) = Тип("СтрокаДереваЗначений") Тогда
            Если V = Source Тогда Возврат "R1"; КонецЕсли;
            Если V = Source.Parent Тогда Возврат "R3"; КонецЕсли;
        КонецЕсли;
    ИначеЕсли K = Тип("КоллекцияСтрокДереваЗначений") Тогда
        Если V.Count() > 2 Тогда ВызватьИсключение "property-children"; КонецЕсли;
        Если ТипЗнч(Target) = Тип("СтрокаДереваЗначений") Тогда
            Если V.Parent = Target Тогда Возврат "C0"; КонецЕсли;
        КонецЕсли;
        Если ТипЗнч(Source) = Тип("СтрокаДереваЗначений") Тогда
            Если V.Parent = Source Тогда Возврат "C1"; КонецЕсли;
        КонецЕсли;
    КонецЕсли;
    ВызватьИсключение "property-cell-domain";
КонецФункции
// Access failure is observed; an unencodable value fails the observer instead.
Функция PVRead(Знач Object, Знач Name, Знач Shared, Знач Target, Знач Source)
    Попытка
        K = ТипЗнч(Object);
        Если K = Тип("Структура") Или K = Тип("ФиксированнаяСтруктура") Тогда
            V = Неопределено;
            Если Не Object.Property(Name, V) Тогда Возврат "M_"; КонецЕсли;
        ИначеЕсли K = Тип("СтрокаДереваЗначений") И Name = "Parent" Тогда V = Object.Parent;
        ИначеЕсли K = Тип("СтрокаДереваЗначений") И Name = "Rows" Тогда V = Object.Rows;
        Иначе
            Если Object.Owner().Columns.Find(Name) = Неопределено Тогда Возврат "M_"; КонецЕсли;
            V = Object[Name];
        КонецЕсли;
    Исключение
        Возврат "E_";
    КонецПопытки;
    Возврат PVCell(V, Shared, Target, Source);
КонецФункции
Функция PVShape(Знач Object)
    K = ТипЗнч(Object);
    Если K = Тип("Структура") Тогда Возврат "S" + PVDigit(Object.Count()) + "------"; КонецЕсли;
    Если K = Тип("ФиксированнаяСтруктура") Тогда Возврат "F" + PVDigit(Object.Count()) + "------"; КонецЕсли;
    Owner = Object.Owner();
    Если K = Тип("СтрокаТаблицыЗначений") Тогда
        OldHits = Owner.FindRows(Новый Структура("First", 1));
        NewHits = Owner.FindRows(Новый Структура("First", 10));
        FirstHit = Ложь; LastHit = Ложь;
        Если NewHits.Count() > 0 Тогда
            FirstHit = NewHits[0] = Object; LastHit = NewHits[NewHits.Count() - 1] = Object;
        КонецЕсли;
        Возврат "T" + PVDigit(Owner.Columns.Count()) + PVDigit(Owner.Count()) + "-"
            + PVDigit(OldHits.Count()) + PVDigit(NewHits.Count()) + PVFlag(FirstHit) + PVFlag(LastHit);
    КонецЕсли;
    Если K = Тип("СтрокаДереваЗначений") Тогда
        Возврат "R" + PVDigit(Owner.Columns.Count()) + PVDigit(Owner.Rows.Count())
            + PVDigit(Object.Rows.Count()) + PVFlag(Object.Parent <> Неопределено)
            + PVDigit(Object.Level()) + "00";
    КонецЕсли;
    ВызватьИсключение "property-shape-type";
КонецФункции
Функция PVSnapshot(Знач Target, Знач Source, Знач Shared, Знач Reference, Знач RefStatus)
    Out = "";
    Names = СтрРазделить("First,Last,Keep,Parent,Rows", ",", Истина);
    Для Каждого Name Из Names Цикл Out = Out + PVRead(Target, Name, Shared, Target, Source); КонецЦикла;
    Для Каждого Name Из Names Цикл Out = Out + PVRead(Source, Name, Shared, Target, Source); КонецЦикла;
    Out = Out + PVShape(Target) + PVShape(Source) + PVCell(Shared, Shared, Target, Source) + RefStatus;
    Если Reference = Неопределено Тогда Out = Out + "U_U_";
    Иначе
        Out = Out + PVRead(Reference, "First", Shared, Target, Source) + PVRead(Reference, "Last", Shared, Target, Source);
    КонецЕсли;
    Если СтрДлина(Out) <> 43 Тогда ВызватьИсключение "property-snapshot-size"; КонецЕсли;
    Возврат Out;
КонецФункции
Функция PVObject(Знач Kind, Знач IsSource, Знач Typed)
    Если IsSource Тогда Names = "First,Last,Extra"; N = 10; Text = "new"; Tail = 40;
    Иначе Names = "First,Last,Keep"; N = 1; Text = "old"; Tail = 3; КонецЕсли;
    Если Kind = "S" Или Kind = "F" Тогда
        Object = Новый Структура(Names, N, Text, Tail);
        Если Kind = "F" Тогда Возврат Новый ФиксированнаяСтруктура(Object); КонецЕсли;
        Возврат Object;
    КонецЕсли;
    Если Kind = "T" Тогда Owner = Новый ТаблицаЗначений; Иначе Owner = Новый ДеревоЗначений; КонецЕсли;
    Если Typed Тогда
        Owner.Columns.Add("First", Новый ОписаниеТипов("Число", Новый КвалификаторыЧисла(2, 0)));
        Owner.Columns.Add("Last", Новый ОписаниеТипов("Строка", , Новый КвалификаторыСтроки(3)));
    Иначе Owner.Columns.Add("First"); Owner.Columns.Add("Last"); КонецЕсли;
    NamesArray = СтрРазделить(Names, ",", Истина); Owner.Columns.Add(NamesArray[2]);
    Если Kind = "T" Тогда
        Object = Owner.Add(); Other = Owner.Add(); Other.First = 10; Other.Last = "hold";
        Owner.Indexes.Add("First");
    Иначе
        ParentRow = Owner.Rows.Add(); ParentRow.First = 7; ParentRow.Last = "hold";
        Object = ParentRow.Rows.Add();
    КонецЕсли;
    Object.First = N; Object.Last = Text; Object[NamesArray[2]] = Tail;
    Возврат Object;
КонецФункции
Функция PVProbe(Знач Case)
    Stage = "0";
    Попытка
        Shared = Новый Массив; Shared.Add(7); Reference = Неопределено; RefStatus = "-";
        TargetKind = "S"; SourceKind = "S"; Mode = 0; Typed = Ложь;
        Если Case = 1 Тогда TargetKind = "T"; ИначеЕсли Case = 2 Тогда TargetKind = "R";
        ИначеЕсли Case >= 5 И Case <= 14 Тогда
            TargetKind = Сред("TTSTRRSRRT", Case - 4, 1);
            SourceKind = Сред("SFTTSFRRTR", Case - 4, 1);
        ИначеЕсли Case >= 15 И Case <= 34 Тогда
            Если Case <= 24 Тогда TargetKind = "T"; Mode = Case - 14;
            Иначе TargetKind = "R"; Mode = Case - 24; КонецЕсли;
        ИначеЕсли Case >= 35 И Case <= 40 Тогда
            Typed = Истина;
            Если Case <= 37 Тогда TargetKind = "T"; Иначе TargetKind = "R"; КонецЕсли;
        ИначеЕсли Case >= 41 И Case <= 44 Тогда TargetKind = "R";
        ИначеЕсли Case = 45 Или Case = 46 Тогда SourceKind = "R";
        ИначеЕсли Case = 47 Тогда TargetKind = "T";
        ИначеЕсли Case = 48 Тогда TargetKind = "R";
        КонецЕсли;
        Target = PVObject(TargetKind, Ложь, Typed); Source = PVObject(SourceKind, Истина, Ложь);
        Если Typed Тогда
            Source.First = 8.6; Source.Last = "ABCD";
            Если Case = 36 Или Case = 39 Тогда Source.First = Неопределено; Source.Last = Неопределено; КонецЕсли;
            Если Case = 37 Или Case = 40 Тогда Source.First = "bad"; КонецЕсли;
            Reference = PVObject(TargetKind, Ложь, Истина); RefStatus = "S";
            Попытка Reference.First = Source.First; Reference.Last = Source.Last;
            Исключение RefStatus = "E"; КонецПопытки;
        КонецЕсли;
        Если Case >= 41 И Case <= 44 Тогда
            Source.Insert("Parent", Target.Parent); Source.Insert("Rows", Target.Rows);
        КонецЕсли;
        Если Case = 45 Или Case = 46 Тогда Target.Insert("Parent"); Target.Insert("Rows"); КонецЕсли;
        Если Case = 47 Или Case = 48 Тогда Source.Last = Shared; КонецЕсли;
        Stage = "1"; Before = PVSnapshot(Target, Source, Shared, Reference, RefStatus);
        Status = "S";
        Попытка
            Если Case = 1 Или Case = 2 Тогда Target.First = Source.First; Target.Last = Source.Last;
            ИначеЕсли Case = 4 Тогда ЗаполнитьЗначенияСвойств(Target, Source);
            ИначеЕсли Mode = 1 Тогда FillPropertyValues(Target, Source, Неопределено);
            ИначеЕсли Mode = 2 Тогда FillPropertyValues(Target, Source, "last,FIRST,First");
            ИначеЕсли Mode = 3 Тогда FillPropertyValues(Target, Source, "First,Keep,Last");
            ИначеЕсли Mode = 4 Тогда FillPropertyValues(Target, Source, "First,Extra,Last");
            ИначеЕсли Mode = 5 Тогда FillPropertyValues(Target, Source, "");
            ИначеЕсли Mode = 6 Тогда FillPropertyValues(Target, Source, Неопределено, "First");
            ИначеЕсли Mode = 7 Тогда FillPropertyValues(Target, Source, Неопределено, "Extra");
            ИначеЕсли Mode = 8 Тогда FillPropertyValues(Target, Source, Неопределено, "Keep");
            ИначеЕсли Mode = 9 Тогда FillPropertyValues(Target, Source, "First", "First");
            ИначеЕсли Mode = 10 Тогда FillPropertyValues(Target, Source, "First", 7);
            ИначеЕсли Case = 42 Тогда FillPropertyValues(Target, Source, "First,Parent,Last");
            ИначеЕсли Case = 43 Тогда FillPropertyValues(Target, Source, "First,Rows,Last");
            ИначеЕсли Case = 44 Тогда FillPropertyValues(Target, Source, Неопределено, "Parent,Rows");
            ИначеЕсли Case = 46 Тогда FillPropertyValues(Target, Source, "First,Parent,Rows,Last");
            Иначе FillPropertyValues(Target, Source);
            КонецЕсли;
        Исключение Status = "E"; КонецПопытки;
        Stage = "2"; After = PVSnapshot(Target, Source, Shared, Reference, RefStatus);
        Shared.Add(8); Stage = "3"; SharedAfter = PVSnapshot(Target, Source, Shared, Reference, RefStatus);
        Возврат Status + "/" + Before + "/" + After + "/" + SharedAfter;
    Исключение
        Возврат "X" + Stage;
    КонецПопытки;
КонецФункции
Сообщить("PV-C1: [wire-v1]");
CalibrationArray = Новый Массив; CalibrationArray.Add(7);
Сообщить("PV-C2: [" + PVCell(0, CalibrationArray, Неопределено, Неопределено)
    + PVCell("", CalibrationArray, Неопределено, Неопределено)
    + PVCell(Неопределено, CalibrationArray, Неопределено, Неопределено)
    + PVCell(Null, CalibrationArray, Неопределено, Неопределено)
    + PVCell(Ложь, CalibrationArray, Неопределено, Неопределено)
    + PVCell(Истина, CalibrationArray, Неопределено, Неопределено) + "]");
Для Case = 1 По 48 Цикл Сообщить("PV-" + Прав("0" + Строка(Case), 2) + ": [" + PVProbe(Case) + "]"); КонецЦикла;
