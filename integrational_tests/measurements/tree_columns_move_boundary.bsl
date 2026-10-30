// Standalone bounded Columns.Move boundary observer. No native answers assumed.
Функция CBNum(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "columns-move-number"; КонецЕсли;
    Возврат Сред("0123456789", V + 1, 1);
КонецФункции
Функция CBId(Знач V, Знач Registry)
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
Функция CBExact(Знач A, Знач B)
    Если ТипЗнч(A) <> Тип("Строка") Или ТипЗнч(B) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(A) <> СтрДлина(B) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(A) Цикл Если КодСимвола(A, P) <> КодСимвола(B, P) Тогда Возврат Ложь; КонецЕсли; КонецЦикла;
    Возврат Истина;
КонецФункции
Функция CBWord(Знач V)
    Words = СтрРазделить("Key|Secondary|Tag|P|Q|X|Y|a|b|c|d|e|f", "|", Истина);
    Для I = 0 По Words.Count() - 1 Цикл
        Если CBExact(V, Words[I]) Тогда Возврат Сред("abcdefghijklm", I+1, 1); КонецЕсли;
    КонецЦикла;
    ВызватьИсключение "columns-move-word";
КонецФункции
Функция CBFlag(Знач V) Если V Тогда Возврат "1"; Иначе Возврат "0"; КонецЕсли; КонецФункции
Функция CBCount(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 5 Или Цел(V) <> V Тогда ВызватьИсключение "columns-move-count"; КонецЕсли;
    Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", V + 1, 1);
КонецФункции
Функция CBCell(Знач V, Знач Registry)
    K = ТипЗнч(V);
    Если K = Тип("Неопределено") Тогда Возврат "U_"; КонецЕсли;
    Если K = Тип("Null") Тогда Возврат "L_"; КонецЕсли;
    Если K = Тип("Булево") Тогда Возврат "B" + CBFlag(V); КонецЕсли;
    Если K = Тип("Число") Тогда Возврат "N" + CBNum(V); КонецЕсли;
    Если K = Тип("Строка") И СтрДлина(V) = 1 Тогда
        Для I = 1 По 18 Цикл
            Если CBExact(V, Сред("abcdefghijklmnopqr", I, 1)) Тогда Возврат "S" + V; КонецЕсли;
        КонецЦикла;
    КонецЕсли;
    ВызватьИсключение "columns-move-cell";
КонецФункции
Процедура CBFlatten(Знач Rows, Знач Nodes)
    Для Каждого R Из Rows Цикл
        Если Nodes.Count() >= 5 Тогда ВызватьИсключение "columns-move-rows"; КонецЕсли;
        Nodes.Add(R); CBFlatten(R.Rows, Nodes);
    КонецЦикла;
КонецПроцедуры
Функция CBSnapshot(Знач T, Знач Registry)
    Point = "01";
    Попытка
        Если ТипЗнч(T) <> Тип("ДеревоЗначений") Тогда ВызватьИсключение "columns-move-result-type"; КонецЕсли;
        Point = "02"; Если T.Columns.Count() > 3 Тогда ВызватьИсключение "columns-move-columns"; КонецЕсли;
        Point = "03"; Out = CBId(T, Registry);
        Point = "04"; Out = Out + CBId(T, Registry); // Structural root Rows owner label, not wrapper identity.
        Point = "05"; Out = Out + CBId(T.Columns, Registry);
        Point = "06"; Out = Out + CBNum(T.Columns.Count());
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
            Point = "12"; Out = Out + CBId(C, Registry);
            Point = "13"; Out = Out + CBWord(C.Name);
            Point = "14"; Out = Out + CBWord(C.Title);
            Point = "15"; Out = Out + CBNum(C.Width) + Kind;
            Point = "16"; Out = Out + CBNum(D.NumberQualifiers.Digits);
            Point = "17"; Out = Out + CBNum(D.NumberQualifiers.FractionDigits);
            Point = "18"; Out = Out + CBFlag(D.NumberQualifiers.AllowedSign = AllowedSign.Nonnegative);
            Point = "19"; Out = Out + CBNum(D.StringQualifiers.Length);
            Point = "20"; Out = Out + CBFlag(D.StringQualifiers.AllowedLength = AllowedLength.Fixed) + DateKind;
            Point = "21"; Out = Out + CBNum(D.BinaryDataQualifiers.Length);
            Point = "22"; Out = Out + CBFlag(D.BinaryDataQualifiers.AllowedLength = AllowedLength.Fixed);
            Point = "07";
        КонецЦикла;
        Nodes = Новый Массив;
        Point = "23"; CBFlatten(T.Rows, Nodes);
        Point = "24"; Out = Out + CBCount(Nodes.Count());
        Point = "25";
        Для Каждого R Из Nodes Цикл
            Point = "26"; Out = Out + CBId(R, Registry);
            Point = "27"; Out = Out + CBId(R.Parent, Registry);
            Point = "28"; Out = Out + CBId(R.Owner(), Registry);
            Point = "29"; Out = Out + CBNum(R.Level());
            Point = "30"; Out = Out + CBId(R, Registry); // Structural child Rows owner label, not wrapper identity.
            Point = "31"; Out = Out + CBNum(R.Rows.Count());
            Point = "32"; Если R.Rows.Parent <> R Тогда ВызватьИсключение "columns-move-collection-parent"; КонецЕсли;
            Point = "33";
            Для I = 0 По T.Columns.Count() - 1 Цикл
                Point = "34"; Out = Out + CBCell(R.Get(I), Registry);
                Point = "33";
            КонецЦикла;
            Для I = 0 По T.Columns.Count() - 1 Цикл
                Point = "36"; Out = Out + CBCell(R[T.Columns.Get(I).Name], Registry);
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
Функция CBFixture(Знач Case)
    T = Новый ДеревоЗначений;
    Если Case = 17 Тогда Возврат T; КонецЕсли;
    T.Columns.Add("Key", , "Key", 3);
    Если Case <> 18 Тогда
        T.Columns.Add("Secondary", , "Secondary", 4);
        T.Columns.Add("Tag", , "Tag", 5);
    КонецЕсли;
    A = T.Rows.Add(); B = T.Rows.Add();
    A1 = A.Rows.Add(); A2 = A.Rows.Add(); G = A1.Rows.Add();
    Nodes = Новый Массив; CBFlatten(T.Rows, Nodes);
    Для I = 0 По Nodes.Count() - 1 Цикл
        R = Nodes[I]; R.Key = I + 1;
        Если Case <> 18 Тогда R.Secondary = (I + 3) % 9; R.Tag = (I + 6) % 9; КонецЕсли;
    КонецЦикла;
    Возврат T;
КонецФункции
Функция CBError(Знач OriginalErrorDescription)
    Если СтрНайти(OriginalErrorDescription, "Метод объекта не обнаружен") > 0
        Или СтрНайти(OriginalErrorDescription, "Метод не найден:") > 0
        Или СтрНайти(OriginalErrorDescription, "Метод или свойство не найдено:") > 0 Тогда Возврат "M"; КонецЕсли;
    Если СтрНайти(OriginalErrorDescription, "параметров") > 0
        Или СтрНайти(OriginalErrorDescription, "параметры") > 0 Тогда Возврат "A"; КонецЕсли;
    Возврат "O";
КонецФункции
Функция CBProbe(Знач Case)
    Stage = "B";
    Попытка
        Registry = Новый Массив; T = CBFixture(1);
        Foreign = Новый ДеревоЗначений; ForeignColumn = Foreign.Columns.Add("Key");
        Deleted = T.Columns.Add("P"); T.Columns.Delete(Deleted);
        Selected = Неопределено;
        Если T.Columns.Count() > 1 Тогда Selected = T.Columns.Get(1); КонецЕсли;
        Before = CBSnapshot(T, Registry);
        Status = "S";
        Попытка
            Если Case = 1 Тогда T.Columns.Move(1, 1);
            ИначеЕсли Case = 2 Тогда T.Columns.Сдвинуть(Selected, 1);
            ИначеЕсли Case = 3 Тогда T.Columns.Move(0, 3);
            ИначеЕсли Case = 4 Тогда T.Columns.Move(1, 2);
            ИначеЕсли Case = 5 Тогда T.Columns.Move(2, 2);
            ИначеЕсли Case = 6 Тогда T.Columns.Move(Deleted, 0);
            ИначеЕсли Case = 7 Тогда T.Columns.Move(Deleted, -1);
            ИначеЕсли Case = 8 Тогда T.Columns.Move(Deleted, 1000000);
            ИначеЕсли Case = 9 Тогда T.Columns.Move(Deleted, "bad");
            ИначеЕсли Case = 10 Тогда T.Columns.Move(Deleted, Неопределено);
            ИначеЕсли Case = 11 Тогда T.Columns.Move(1, -1.9);
            ИначеЕсли Case = 12 Тогда T.Columns.Move(0, -0.5);
            ИначеЕсли Case = 13 Тогда T.Columns.Move(2, 1.9);
            ИначеЕсли Case = 14 Тогда T.Columns.Move(1, "2");
            ИначеЕсли Case = 15 Тогда T.Columns.Move(1, "bad");
            ИначеЕсли Case = 16 Тогда T.Columns.Move(1, "-1.9");
            ИначеЕсли Case = 17 Тогда T.Columns.Move(1, Ложь);
            КонецЕсли;
        Исключение
            OriginalErrorDescription = ОписаниеОшибки();
            Status = CBError(OriginalErrorDescription);
        КонецПопытки;
        Stage = "O"; After = CBSnapshot(T, Registry);
        Возврат Status + "/" + Before + "/" + After;
    Исключение
        OriginalObserverErrorDescription = ОписаниеОшибки();
        Возврат "X" + Stage;
    КонецПопытки;
КонецФункции
Функция CBCalibrate()
    Попытка
        T = CBFixture(1); U = CBFixture(1); Alias = T;
        Если T <> Alias Или T = U Тогда Возврат "I"; КонецЕсли;
        Если T.Columns <> T.Columns Или T.Columns = U.Columns Тогда Возврат "I"; КонецЕсли;
        Если T.Columns.Get(0) <> T.Columns.Get(0) Или T.Columns.Get(0) = T.Columns.Get(1) Тогда Возврат "I"; КонецЕсли;
        R = T.Rows.Get(0); Alias = R;
        Если R <> Alias Или R = T.Rows.Get(1) Тогда Возврат "I"; КонецЕсли;
        Если R.Rows.Get(0).Parent <> R Или R.Owner() <> T Или R.Level() <> 0 Тогда Возврат "R"; КонецЕсли;
        Если R.Rows.Count() <> 2 Или T.Rows.Count() <> 2 Тогда Возврат "R"; КонецЕсли;
        Registry = Новый Массив; Before = CBSnapshot(T, Registry); After = CBSnapshot(T, Registry);
        Если Не CBExact(Before, After) Тогда Возврат "I"; КонецЕсли;
        Если Не CBExact(CBCell(1, Registry), "N1") Или Не CBExact(CBCell("a", Registry), "Sa") Тогда Возврат "V"; КонецЕсли;
    Исключение
        OriginalCalibrationErrorDescription = ОписаниеОшибки();
        Возврат "E";
    КонецПопытки;
    Возврат "-";
КонецФункции
Сообщить("CB-C1: [" + CBCalibrate() + "]");
Для Case = 1 По 17 Цикл Сообщить("CB-" + Строка(Case) + ": [" + CBProbe(Case) + "]"); КонецЦикла;
