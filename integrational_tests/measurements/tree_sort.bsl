// Standalone bounded Rows.Sort observer. No native answers assumed.
Функция TSNum(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "sort-number"; КонецЕсли;
    Возврат Сред("0123456789", V + 1, 1);
КонецФункции
Функция TSId(Знач V, Знач Registry)
    Попытка Missing = (V = Неопределено);
    Исключение
        PrivateIdentityDescription = ОписаниеОшибки();
        ВызватьИсключение "sort-identity-compare";
    КонецПопытки;
    Если Missing Тогда Возврат "_"; КонецЕсли;
    Для I = 0 По Registry.Count() - 1 Цикл
        Candidate = Registry[I];
        Попытка Same = (V = Candidate);
        Исключение
            PrivateIdentityDescription = ОписаниеОшибки();
            ВызватьИсключение "sort-identity-compare";
        КонецПопытки;
        Если Same Тогда Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", I + 1, 1); КонецЕсли;
    КонецЦикла;
    Count = Registry.Count();
    Если Count >= 62 Тогда
        Если Count = 62 Тогда ВызватьИсключение "sort-identities-count62"; КонецЕсли;
        ВызватьИсключение "sort-identities-over62";
    КонецЕсли;
    Registry.Add(V); Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", Registry.Count(), 1);
КонецФункции
Функция TSExact(Знач A, Знач B)
    Если ТипЗнч(A) <> Тип("Строка") Или ТипЗнч(B) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(A) <> СтрДлина(B) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(A) Цикл Если КодСимвола(A, P) <> КодСимвола(B, P) Тогда Возврат Ложь; КонецЕсли; КонецЦикла;
    Возврат Истина;
КонецФункции
Функция TSWord(Знач V)
    Words = СтрРазделить("Key|Secondary|Tag|P|Q|X|Y|a|b|c|d|e|f", "|", Истина);
    Для I = 0 По Words.Count() - 1 Цикл
        Если TSExact(V, Words[I]) Тогда Возврат Сред("abcdefghijklm", I+1, 1); КонецЕсли;
    КонецЦикла;
    ВызватьИсключение "sort-word";
КонецФункции
Функция TSFlag(Знач V) Если V Тогда Возврат "1"; Иначе Возврат "0"; КонецЕсли; КонецФункции
Функция TSCount(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 18 Или Цел(V) <> V Тогда ВызватьИсключение "sort-count"; КонецЕсли;
    Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", V + 1, 1);
КонецФункции
Функция TSCell(Знач V, Знач Registry)
    K = ТипЗнч(V);
    Если K = Тип("Неопределено") Тогда Возврат "U_"; КонецЕсли;
    Если K = Тип("Null") Тогда Возврат "L_"; КонецЕсли;
    Если K = Тип("Булево") Тогда Возврат "B" + TSFlag(V); КонецЕсли;
    Если K = Тип("Число") Тогда Возврат "N" + TSNum(V); КонецЕсли;
    Если K = Тип("Строка") И СтрДлина(V) = 1 Тогда
        Для I = 1 По 18 Цикл
            Если TSExact(V, Сред("abcdefghijklmnopqr", I, 1)) Тогда Возврат "S" + V; КонецЕсли;
        КонецЦикла;
    КонецЕсли;
    ВызватьИсключение "sort-cell";
КонецФункции
Процедура TSFlatten(Знач Rows, Знач Nodes)
    Для Каждого R Из Rows Цикл
        Если Nodes.Count() >= 18 Тогда ВызватьИсключение "sort-rows"; КонецЕсли;
        Nodes.Add(R); TSFlatten(R.Rows, Nodes);
    КонецЦикла;
КонецПроцедуры
Функция TSSnapshot(Знач T, Знач Registry)
    Point = "01";
    Попытка
        Если ТипЗнч(T) <> Тип("ДеревоЗначений") Тогда ВызватьИсключение "sort-result-type"; КонецЕсли;
        Point = "02"; Если T.Columns.Count() > 3 Тогда ВызватьИсключение "sort-columns"; КонецЕсли;
        Point = "03"; Out = TSId(T, Registry);
        Point = "04"; Out = Out + TSId(T, Registry); // Structural root Rows owner label, not wrapper identity.
        Point = "05"; Out = Out + TSId(T.Columns, Registry);
        Point = "06"; Out = Out + TSNum(T.Columns.Count());
        Point = "07";
        Для Каждого C Из T.Columns Цикл
            Point = "08"; D = C.ValueType;
            Point = "09"; Types = D.Types(); Kind = "U";
            Point = "10";
            Если Types.Count() = 1 Тогда
                Если Types[0] = Тип("Число") Тогда Kind = "N";
                ИначеЕсли Types[0] = Тип("Строка") Тогда Kind = "S";
                Иначе ВызватьИсключение "sort-column-type"; КонецЕсли;
            ИначеЕсли Types.Count() <> 0 Тогда ВызватьИсключение "sort-types"; КонецЕсли;
            DateKind = "0"; Point = "11";
            Если D.DateQualifiers.DateFractions = DateFractions.Date Тогда DateKind = "1";
            ИначеЕсли D.DateQualifiers.DateFractions = DateFractions.Time Тогда DateKind = "2";
            ИначеЕсли D.DateQualifiers.DateFractions <> DateFractions.DateTime Тогда ВызватьИсключение "sort-date"; КонецЕсли;
            Point = "12"; Out = Out + TSId(C, Registry);
            Point = "13"; Out = Out + TSWord(C.Name);
            Point = "14"; Out = Out + TSWord(C.Title);
            Point = "15"; Out = Out + TSNum(C.Width) + Kind;
            Point = "16"; Out = Out + TSNum(D.NumberQualifiers.Digits);
            Point = "17"; Out = Out + TSNum(D.NumberQualifiers.FractionDigits);
            Point = "18"; Out = Out + TSFlag(D.NumberQualifiers.AllowedSign = AllowedSign.Nonnegative);
            Point = "19"; Out = Out + TSNum(D.StringQualifiers.Length);
            Point = "20"; Out = Out + TSFlag(D.StringQualifiers.AllowedLength = AllowedLength.Fixed) + DateKind;
            Point = "21"; Out = Out + TSNum(D.BinaryDataQualifiers.Length);
            Point = "22"; Out = Out + TSFlag(D.BinaryDataQualifiers.AllowedLength = AllowedLength.Fixed);
            Point = "07";
        КонецЦикла;
        Nodes = Новый Массив;
        Point = "23"; TSFlatten(T.Rows, Nodes);
        Point = "24"; Out = Out + TSCount(Nodes.Count());
        Point = "25";
        Для Каждого R Из Nodes Цикл
            Point = "26"; Out = Out + TSId(R, Registry);
            Point = "27"; Out = Out + TSId(R.Parent, Registry);
            Point = "28"; Out = Out + TSId(R.Owner(), Registry);
            Point = "29"; Out = Out + TSNum(R.Level());
            Point = "30"; Out = Out + TSId(R, Registry); // Structural child Rows owner label, not wrapper identity.
            Point = "31"; Out = Out + TSNum(R.Rows.Count());
            Point = "32"; Если R.Rows.Parent <> R Тогда ВызватьИсключение "sort-collection-parent"; КонецЕсли;
            Point = "33";
            Для I = 0 По T.Columns.Count() - 1 Цикл
                Point = "34"; Out = Out + TSCell(R.Get(I), Registry);
                Point = "33";
            КонецЦикла;
            Point = "25";
        КонецЦикла;
        Point = "35"; Если T.Rows.Parent <> Неопределено Тогда ВызватьИсключение "sort-root-parent"; КонецЕсли;
        Возврат Out;
    Исключение
        PrivateSnapshotDescription = ОписаниеОшибки();
        Code = "S" + Point;
        ВызватьИсключение "sort-detail-" + Code;
    КонецПопытки;
КонецФункции
Функция TSFixture(Знач Case)
    T = Новый ДеревоЗначений;
    T.Columns.Add("Key", , "Key", 3);
    T.Columns.Add("Secondary", , "Secondary", 4);
    T.Columns.Add("Tag", , "Tag", 5);
    Если Case = 10 Тогда Возврат T; КонецЕсли;
    Если Case = 8 Или Case = 9 Тогда
        Для I = 0 По 17 Цикл R = T.Rows.Add(); КонецЦикла;
    Иначе
        A = T.Rows.Add(); B = T.Rows.Add();
        A1 = A.Rows.Add(); A2 = A.Rows.Add();
        B1 = B.Rows.Add(); B2 = B.Rows.Add();
        G1 = A1.Rows.Add(); G2 = A1.Rows.Add();
    КонецЕсли;
    Nodes = Новый Массив; TSFlatten(T.Rows, Nodes);
    Для I = 0 По Nodes.Count() - 1 Цикл
        R = Nodes[I];
        Если Case = 8 Или Case = 9 Тогда
            R.Key = 2 - (I % 3); R.Secondary = 2 - (I % 2);
        Иначе
            R.Key = Число(Сред("22211111", I + 1, 1));
            R.Secondary = Число(Сред("11122112", I + 1, 1));
        КонецЕсли;
        R.Tag = Сред("abcdefghijklmnopqr", I + 1, 1);
    КонецЦикла;
    Возврат T;
КонецФункции
Функция TSError(Знач OriginalErrorDescription)
    Если СтрНайти(OriginalErrorDescription, "Метод объекта не обнаружен") > 0
        Или СтрНайти(OriginalErrorDescription, "Метод не найден:") > 0
        Или СтрНайти(OriginalErrorDescription, "Метод или свойство не найдено:") > 0 Тогда Возврат "M"; КонецЕсли;
    Если СтрНайти(OriginalErrorDescription, "параметров") > 0
        Или СтрНайти(OriginalErrorDescription, "параметры") > 0 Тогда Возврат "A"; КонецЕсли;
    Возврат "O";
КонецФункции
Функция TSProbe(Знач Case)
    Stage = "B";
    Попытка
        Registry = Новый Массив; T = TSFixture(Case); Before = TSSnapshot(T, Registry);
        Status = "S";
        Попытка
            Если Case = 1 Тогда T.Rows.Sort("Key");
            ИначеЕсли Case = 2 Тогда T.Rows.Сортировать("Key", Ложь);
            ИначеЕсли Case = 3 Тогда T.Rows.Sort("Key", Истина);
            ИначеЕсли Case = 4 Тогда T.Rows.Get(0).Rows.Sort("Key", Истина);
            ИначеЕсли Case = 5 Тогда T.Rows.Get(0).Rows.Sort("Key");
            ИначеЕсли Case = 6 Тогда T.Rows.Sort("Key ASC, Secondary DESC", Истина);
            ИначеЕсли Case = 7 Тогда T.Rows.Сортировать("Key Возр, Secondary Убыв", Истина);
            ИначеЕсли Case = 8 Тогда T.Rows.Sort("Key ASC");
            ИначеЕсли Case = 9 Тогда T.Rows.Sort("Key DESC");
            ИначеЕсли Case = 10 Тогда T.Rows.Sort("Key");
            ИначеЕсли Case = 11 Тогда T.Rows.Sort("Missing");
            ИначеЕсли Case = 12 Тогда T.Rows.Sort("Key, Missing");
            ИначеЕсли Case = 13 Тогда T.Rows.Sort("Missing, Key");
            ИначеЕсли Case = 14 Тогда T.Rows.Sort("");
            ИначеЕсли Case = 15 Тогда T.Rows.Sort();
            ИначеЕсли Case = 16 Тогда T.Rows.Sort("Key", Ложь, Неопределено, 1);
            ИначеЕсли Case = 17 Тогда T.Rows.Sort(1);
            ИначеЕсли Case = 18 Тогда T.Rows.Sort("Key", Новый Массив);
            ИначеЕсли Case = 19 Тогда T.Rows.Sort("Key", Ложь, Неопределено);
            ИначеЕсли Case = 20 Тогда T.Rows.Sort("Key", Ложь, 1);
            ИначеЕсли Case = 21 Тогда Выполнить("Result = T.Rows.Sort(""Key"");");
            КонецЕсли;
        Исключение
            OriginalErrorDescription = ОписаниеОшибки();
            Status = TSError(OriginalErrorDescription);
        КонецПопытки;
        Stage = "O"; After = TSSnapshot(T, Registry);
        Возврат Status + "/" + Before + "/" + After;
    Исключение
        OriginalObserverErrorDescription = ОписаниеОшибки();
        Возврат "X" + Stage;
    КонецПопытки;
КонецФункции
Функция TSCalibrate()
    Попытка
        T = TSFixture(1); U = TSFixture(1); Alias = T;
        Если T <> Alias Или T = U Тогда Возврат "I"; КонецЕсли;
        Если T.Columns <> T.Columns Или T.Columns = U.Columns Тогда Возврат "I"; КонецЕсли;
        Если T.Columns.Get(0) <> T.Columns.Get(0) Или T.Columns.Get(0) = T.Columns.Get(1) Тогда Возврат "I"; КонецЕсли;
        R = T.Rows.Get(0); Alias = R;
        Если R <> Alias Или R = T.Rows.Get(1) Тогда Возврат "I"; КонецЕсли;
        Если R.Rows.Get(0).Parent <> R Или R.Owner() <> T Или R.Level() <> 0 Тогда Возврат "R"; КонецЕсли;
        Если R.Rows.Count() <> 2 Или T.Rows.Count() <> 2 Тогда Возврат "R"; КонецЕсли;
        Registry = Новый Массив; Before = TSSnapshot(T, Registry); After = TSSnapshot(T, Registry);
        Если Не TSExact(Before, After) Тогда Возврат "I"; КонецЕсли;
        Если Не TSExact(TSCell(1, Registry), "N1") Или Не TSExact(TSCell("a", Registry), "Sa") Тогда Возврат "V"; КонецЕсли;
    Исключение
        OriginalCalibrationErrorDescription = ОписаниеОшибки();
        Возврат "E";
    КонецПопытки;
    Возврат "-";
КонецФункции
Сообщить("TS-C1: [" + TSCalibrate() + "]");
Для Case = 1 По 21 Цикл Сообщить("TS-" + Строка(Case) + ": [" + TSProbe(Case) + "]"); КонецЦикла;
