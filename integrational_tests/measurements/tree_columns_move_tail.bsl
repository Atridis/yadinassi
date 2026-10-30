// Standalone bounded Columns.Move tail observer. No native answers assumed.
Функция CTNum(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "columns-move-number"; КонецЕсли;
    Возврат Сред("0123456789", V + 1, 1);
КонецФункции
Функция CTId(Знач V, Знач Registry)
    Попытка Missing = (V = Неопределено);
    Исключение
        PrivateIdentityDescription = ОписаниеОшибки();
        ВызватьИсключение "columns-move-identity-compare";
    КонецПопытки;
    Если Missing Тогда Возврат "_"; КонецЕсли;
    Для I = 0 По Registry.Count() - 1 Цикл
        Candidate = Registry[I];
        Попытка Same = (V = Candidate);
        Исключение
            PrivateIdentityDescription = ОписаниеОшибки();
            ВызватьИсключение "columns-move-identity-compare";
        КонецПопытки;
        Если Same Тогда Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", I + 1, 1); КонецЕсли;
    КонецЦикла;
    Count = Registry.Count();
    Если Count >= 62 Тогда
        Если Count = 62 Тогда ВызватьИсключение "columns-move-identities-count62"; КонецЕсли;
        ВызватьИсключение "columns-move-identities-over62";
    КонецЕсли;
    Registry.Add(V); Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", Registry.Count(), 1);
КонецФункции
Функция CTExact(Знач A, Знач B)
    Если ТипЗнч(A) <> Тип("Строка") Или ТипЗнч(B) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(A) <> СтрДлина(B) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(A) Цикл Если КодСимвола(A, P) <> КодСимвола(B, P) Тогда Возврат Ложь; КонецЕсли; КонецЦикла;
    Возврат Истина;
КонецФункции
Функция CTWord(Знач V)
    Words = СтрРазделить("Key|Secondary|Tag|P|Q|X|Y|a|b|c|d|e|f", "|", Истина);
    Для I = 0 По Words.Count() - 1 Цикл
        Если CTExact(V, Words[I]) Тогда Возврат Сред("abcdefghijklm", I+1, 1); КонецЕсли;
    КонецЦикла;
    ВызватьИсключение "columns-move-word";
КонецФункции
Функция CTFlag(Знач V) Если V Тогда Возврат "1"; Иначе Возврат "0"; КонецЕсли; КонецФункции
Функция CTCount(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 5 Или Цел(V) <> V Тогда ВызватьИсключение "columns-move-count"; КонецЕсли;
    Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", V + 1, 1);
КонецФункции
Функция CTCell(Знач V, Знач Registry)
    K = ТипЗнч(V);
    Если K = Тип("Неопределено") Тогда Возврат "U_"; КонецЕсли;
    Если K = Тип("Null") Тогда Возврат "L_"; КонецЕсли;
    Если K = Тип("Булево") Тогда Возврат "B" + CTFlag(V); КонецЕсли;
    Если K = Тип("Число") Тогда Возврат "N" + CTNum(V); КонецЕсли;
    Если K = Тип("Строка") И СтрДлина(V) = 1 Тогда
        Для I = 1 По 18 Цикл
            Если CTExact(V, Сред("abcdefghijklmnopqr", I, 1)) Тогда Возврат "S" + V; КонецЕсли;
        КонецЦикла;
    КонецЕсли;
    ВызватьИсключение "columns-move-cell";
КонецФункции
Процедура CTFlatten(Знач Rows, Знач Nodes)
    Для Каждого R Из Rows Цикл
        Если Nodes.Count() >= 5 Тогда ВызватьИсключение "columns-move-rows"; КонецЕсли;
        Nodes.Add(R); CTFlatten(R.Rows, Nodes);
    КонецЦикла;
КонецПроцедуры
Функция CTSnapshot(Знач T, Знач Registry)
    Point = "01";
    Попытка
        Если ТипЗнч(T) <> Тип("ДеревоЗначений") Тогда ВызватьИсключение "columns-move-result-type"; КонецЕсли;
        Point = "02"; Если T.Columns.Count() > 3 Тогда ВызватьИсключение "columns-move-columns"; КонецЕсли;
        Point = "03"; Out = CTId(T, Registry);
        Point = "04"; Out = Out + CTId(T, Registry); // Structural root Rows owner label, not wrapper identity.
        Point = "05"; Out = Out + CTId(T.Columns, Registry);
        Point = "06"; Out = Out + CTNum(T.Columns.Count());
        Point = "07";
        Для Каждого C Из T.Columns Цикл
            Point = "08"; D = C.ValueType;
            Point = "09"; Types = D.Types(); Kind = "U";
            Point = "10";
            Если Types.Count() = 1 Тогда
                Если Types[0] = Тип("Число") Тогда Kind = "N";
                ИначеЕсли Types[0] = Тип("Строка") Тогда Kind = "S";
                Иначе ВызватьИсключение "columns-move-column-type"; КонецЕсли;
            ИначеЕсли Types.Count() <> 0 Тогда ВызватьИсключение "columns-move-types"; КонецЕсли;
            DateKind = "0"; Point = "11";
            Если D.DateQualifiers.DateFractions = DateFractions.Date Тогда DateKind = "1";
            ИначеЕсли D.DateQualifiers.DateFractions = DateFractions.Time Тогда DateKind = "2";
            ИначеЕсли D.DateQualifiers.DateFractions <> DateFractions.DateTime Тогда ВызватьИсключение "columns-move-date"; КонецЕсли;
            Point = "12"; Out = Out + CTId(C, Registry);
            Point = "13"; Out = Out + CTWord(C.Name);
            Point = "14"; Out = Out + CTWord(C.Title);
            Point = "15"; Out = Out + CTNum(C.Width) + Kind;
            Point = "16"; Out = Out + CTNum(D.NumberQualifiers.Digits);
            Point = "17"; Out = Out + CTNum(D.NumberQualifiers.FractionDigits);
            Point = "18"; Out = Out + CTFlag(D.NumberQualifiers.AllowedSign = AllowedSign.Nonnegative);
            Point = "19"; Out = Out + CTNum(D.StringQualifiers.Length);
            Point = "20"; Out = Out + CTFlag(D.StringQualifiers.AllowedLength = AllowedLength.Fixed) + DateKind;
            Point = "21"; Out = Out + CTNum(D.BinaryDataQualifiers.Length);
            Point = "22"; Out = Out + CTFlag(D.BinaryDataQualifiers.AllowedLength = AllowedLength.Fixed);
            Point = "07";
        КонецЦикла;
        Nodes = Новый Массив;
        Point = "23"; CTFlatten(T.Rows, Nodes);
        Point = "24"; Out = Out + CTCount(Nodes.Count());
        Point = "25";
        Для Каждого R Из Nodes Цикл
            Point = "26"; Out = Out + CTId(R, Registry);
            Point = "27"; Out = Out + CTId(R.Parent, Registry);
            Point = "28"; Out = Out + CTId(R.Owner(), Registry);
            Point = "29"; Out = Out + CTNum(R.Level());
            Point = "30"; Out = Out + CTId(R, Registry); // Structural child Rows owner label, not wrapper identity.
            Point = "31"; Out = Out + CTNum(R.Rows.Count());
            Point = "32"; Если R.Rows.Parent <> R Тогда ВызватьИсключение "columns-move-collection-parent"; КонецЕсли;
            Point = "33";
            Для I = 0 По T.Columns.Count() - 1 Цикл
                Point = "34"; Out = Out + CTCell(R.Get(I), Registry);
                Point = "33";
            КонецЦикла;
            Для I = 0 По T.Columns.Count() - 1 Цикл
                Point = "36"; Out = Out + CTCell(R[T.Columns.Get(I).Name], Registry);
            КонецЦикла;
            Point = "25";
        КонецЦикла;
        Point = "35"; Если T.Rows.Parent <> Неопределено Тогда ВызватьИсключение "columns-move-root-parent"; КонецЕсли;
        Возврат Out;
    Исключение
        PrivateSnapshotDescription = ОписаниеОшибки();
        Code = "S" + Point;
        ВызватьИсключение "columns-move-detail-" + Code;
    КонецПопытки;
КонецФункции
Функция CTFixture(Знач Case)
    T = Новый ДеревоЗначений;
    Если Case = 17 Тогда Возврат T; КонецЕсли;
    T.Columns.Add("Key", , "Key", 3);
    Если Case <> 18 Тогда
        T.Columns.Add("Secondary", , "Secondary", 4);
        T.Columns.Add("Tag", , "Tag", 5);
    КонецЕсли;
    A = T.Rows.Add(); B = T.Rows.Add();
    A1 = A.Rows.Add(); A2 = A.Rows.Add(); G = A1.Rows.Add();
    Nodes = Новый Массив; CTFlatten(T.Rows, Nodes);
    Для I = 0 По Nodes.Count() - 1 Цикл
        R = Nodes[I]; R.Key = I + 1;
        Если Case <> 18 Тогда R.Secondary = (I + 3) % 9; R.Tag = (I + 6) % 9; КонецЕсли;
    КонецЦикла;
    Возврат T;
КонецФункции
Функция CTError(Знач OriginalErrorDescription)
    Если СтрНайти(OriginalErrorDescription, "Метод объекта не обнаружен") > 0
        Или СтрНайти(OriginalErrorDescription, "Метод не найден:") > 0
        Или СтрНайти(OriginalErrorDescription, "Метод или свойство не найдено:") > 0 Тогда Возврат "M"; КонецЕсли;
    Если СтрНайти(OriginalErrorDescription, "параметров") > 0
        Или СтрНайти(OriginalErrorDescription, "параметры") > 0 Тогда Возврат "A"; КонецЕсли;
    Возврат "O";
КонецФункции
Функция CTProbe(Знач Case)
    Stage = "B";
    Попытка
        Registry = Новый Массив; T = CTFixture(1);
        Foreign = Новый ДеревоЗначений; ForeignColumn = Foreign.Columns.Add("Key");
        Deleted = T.Columns.Add("P"); T.Columns.Delete(Deleted);
        Selected = Неопределено;
        Если T.Columns.Count() > 1 Тогда Selected = T.Columns.Get(1); КонецЕсли;
        Before = CTSnapshot(T, Registry);
        Status = "S";
        Попытка
            Если Case = 1 Тогда T.Columns.Move(1, 1);
            ИначеЕсли Case = 2 Тогда T.Columns.Сдвинуть(Selected, 1);
            ИначеЕсли Case = 3 Тогда T.Columns.Move(Deleted, 2);
            ИначеЕсли Case = 4 Тогда T.Columns.Move(Deleted, 3);
            ИначеЕсли Case = 5 Тогда T.Columns.Move(Deleted, 4);
            ИначеЕсли Case = 6 Тогда T.Columns.Move(Deleted, 5);
            КонецЕсли;
        Исключение
            OriginalErrorDescription = ОписаниеОшибки();
            Status = CTError(OriginalErrorDescription);
        КонецПопытки;
        Stage = "O"; After = CTSnapshot(T, Registry);
        Возврат Status + "/" + Before + "/" + After;
    Исключение
        OriginalObserverErrorDescription = ОписаниеОшибки();
        Возврат "X" + Stage;
    КонецПопытки;
КонецФункции
Функция CTCalibrate()
    Попытка
        T = CTFixture(1); U = CTFixture(1); Alias = T;
        Если T <> Alias Или T = U Тогда Возврат "I"; КонецЕсли;
        Если T.Columns <> T.Columns Или T.Columns = U.Columns Тогда Возврат "I"; КонецЕсли;
        Если T.Columns.Get(0) <> T.Columns.Get(0) Или T.Columns.Get(0) = T.Columns.Get(1) Тогда Возврат "I"; КонецЕсли;
        R = T.Rows.Get(0); Alias = R;
        Если R <> Alias Или R = T.Rows.Get(1) Тогда Возврат "I"; КонецЕсли;
        Если R.Rows.Get(0).Parent <> R Или R.Owner() <> T Или R.Level() <> 0 Тогда Возврат "R"; КонецЕсли;
        Если R.Rows.Count() <> 2 Или T.Rows.Count() <> 2 Тогда Возврат "R"; КонецЕсли;
        Registry = Новый Массив; Before = CTSnapshot(T, Registry); After = CTSnapshot(T, Registry);
        Если Не CTExact(Before, After) Тогда Возврат "I"; КонецЕсли;
        Если Не CTExact(CTCell(1, Registry), "N1") Или Не CTExact(CTCell("a", Registry), "Sa") Тогда Возврат "V"; КонецЕсли;
    Исключение
        OriginalCalibrationErrorDescription = ОписаниеОшибки();
        Возврат "E";
    КонецПопытки;
    Возврат "-";
КонецФункции
Сообщить("CT-C1: [" + CTCalibrate() + "]");
Для Case = 1 По 6 Цикл Сообщить("CT-" + Строка(Case) + ": [" + CTProbe(Case) + "]"); КонецЦикла;
