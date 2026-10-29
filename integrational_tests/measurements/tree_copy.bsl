// Standalone bounded Copy observer. No native expectations or runtime implementation.
Функция TCFailureCode(Знач PrivateText)
    Tags = СтрРазделить("I:copy-identity-compare|G01:copy-identities-count62|G02:copy-identities-over62|G03:copy-number|G04:copy-word|G05:copy-cell|G06:copy-inner|G07:copy-rows|G08:copy-result-type|G09:copy-columns|G10:copy-column-type|G11:copy-types|G12:copy-date|G13:copy-collection-parent|G14:copy-root-parent|G15:copy-exception-result|S01:copy-snapshot-01|S02:copy-snapshot-02|S03:copy-snapshot-03|S04:copy-snapshot-04|S05:copy-snapshot-05|S06:copy-snapshot-06|S07:copy-snapshot-07|S08:copy-snapshot-08|S09:copy-snapshot-09|S10:copy-snapshot-10|S11:copy-snapshot-11|S12:copy-snapshot-12|S13:copy-snapshot-13|S14:copy-snapshot-14|S15:copy-snapshot-15|S16:copy-snapshot-16|S17:copy-snapshot-17|S18:copy-snapshot-18|S19:copy-snapshot-19|S20:copy-snapshot-20|S21:copy-snapshot-21|S22:copy-snapshot-22|S23:copy-snapshot-23|S24:copy-snapshot-24|S25:copy-snapshot-25|S26:copy-snapshot-26|S27:copy-snapshot-27|S28:copy-snapshot-28|S29:copy-snapshot-29|S30:copy-snapshot-30|S31:copy-snapshot-31|S32:copy-snapshot-32|S33:copy-snapshot-33|S34:copy-snapshot-34|S35:copy-snapshot-35|F01:copy-flatten-01|F02:copy-flatten-02|F03:copy-flatten-03", "|", Истина);
    Для Каждого Tag Из Tags Цикл
        Pair = СтрРазделить(Tag, ":", Истина);
        Если СтрНайти(PrivateText, Pair[1]) > 0 Или СтрНайти(PrivateText, "copy-detail-" + Pair[0]) > 0 Тогда Возврат Pair[0]; КонецЕсли;
    КонецЦикла;
    Возврат "";
КонецФункции
Функция TCNum(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "copy-number"; КонецЕсли;
    Возврат Сред("0123456789", V + 1, 1);
КонецФункции
Функция TCId(Знач V, Знач Registry)
    Попытка Missing = (V = Неопределено);
    Исключение
        PrivateIdentityDescription = ОписаниеОшибки();
        ВызватьИсключение "copy-identity-compare";
    КонецПопытки;
    Если Missing Тогда Возврат "_"; КонецЕсли;
    Для I = 0 По Registry.Count() - 1 Цикл
        Candidate = Registry[I];
        Попытка Same = (V = Candidate);
        Исключение
            PrivateIdentityDescription = ОписаниеОшибки();
            ВызватьИсключение "copy-identity-compare";
        КонецПопытки;
        Если Same Тогда Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", I + 1, 1); КонецЕсли;
    КонецЦикла;
    Count = Registry.Count();
    Если Count >= 62 Тогда
        Если Count = 62 Тогда ВызватьИсключение "copy-identities-count62"; КонецЕсли;
        ВызватьИсключение "copy-identities-over62";
    КонецЕсли;
    Registry.Add(V); Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", Registry.Count(), 1);
КонецФункции
Функция TCExact(Знач A, Знач B)
    Если ТипЗнч(A) <> Тип("Строка") Или ТипЗнч(B) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(A) <> СтрДлина(B) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(A) Цикл Если КодСимвола(A, P) <> КодСимвола(B, P) Тогда Возврат Ложь; КонецЕсли; КонецЦикла;
    Возврат Истина;
КонецФункции
Функция TCWord(Знач V)
    Words = СтрРазделить("Payload|N|Text|P|Q|X|Y|a|b|c|d|e|f", "|", Истина);
    Для I = 0 По Words.Count() - 1 Цикл
        Если TCExact(V, Words[I]) Тогда Возврат Сред("abcdefghijklm", I+1, 1); КонецЕсли;
    КонецЦикла;
    ВызватьИсключение "copy-word";
КонецФункции
Функция TCFlag(Знач V) Если V Тогда Возврат "1"; Иначе Возврат "0"; КонецЕсли; КонецФункции
Функция TCCell(Знач V, Знач Registry)
    K = ТипЗнч(V);
    Если K = Тип("Неопределено") Тогда Возврат "U_____"; КонецЕсли;
    Если K = Тип("Null") Тогда Возврат "L_____"; КонецЕсли;
    Если K = Тип("Булево") Тогда Возврат "B" + TCFlag(V) + "____"; КонецЕсли;
    Если K = Тип("Число") Тогда Возврат "N" + TCNum(V) + "____"; КонецЕсли;
    Если K = Тип("Строка") Тогда Возврат "S" + TCWord(V) + "____"; КонецЕсли;
    Если K <> Тип("Массив") Или V.Count() <> 2 Тогда ВызватьИсключение "copy-cell"; КонецЕсли;
    Inner = V[1]; Если ТипЗнч(Inner) <> Тип("Массив") Или Inner.Count() <> 1 Тогда ВызватьИсключение "copy-inner"; КонецЕсли;
    Возврат "A" + TCId(V, Registry) + TCId(Inner, Registry) + TCNum(V[0]) + TCNum(Inner[0]) + "_";
КонецФункции
Процедура TCFlatten(Знач Rows, Знач Nodes)
    Point = "01";
    Попытка
        Для Каждого R Из Rows Цикл
            Point = "01"; Если Nodes.Count() >= 5 Тогда ВызватьИсключение "copy-rows"; КонецЕсли;
            Point = "02"; Nodes.Add(R);
            Point = "03"; TCFlatten(R.Rows, Nodes);
            Point = "01";
        КонецЦикла;
    Исключение
        PrivateFlattenDescription = ОписаниеОшибки();
        Code = TCFailureCode(PrivateFlattenDescription);
        Если Code = "" Тогда Code = "F" + Point; КонецЕсли;
        ВызватьИсключение "copy-detail-" + Code;
    КонецПопытки;
КонецПроцедуры
Функция TCSnapshot(Знач T, Знач Registry)
    Point = "01";
    Попытка
        Если ТипЗнч(T) <> Тип("ДеревоЗначений") Тогда ВызватьИсключение "copy-result-type"; КонецЕсли;
        Point = "02"; Если T.Columns.Count() > 4 Тогда ВызватьИсключение "copy-columns"; КонецЕсли;
        Point = "03"; Out = TCId(T, Registry);
        Point = "04"; Out = Out + TCId(T.Rows, Registry);
        Point = "05"; Out = Out + TCId(T.Columns, Registry);
        Point = "06"; Out = Out + TCNum(T.Columns.Count());
        Point = "07";
        Для Каждого C Из T.Columns Цикл
            Point = "08"; D = C.ValueType;
            Point = "09"; Types = D.Types(); Kind = "U";
            Point = "10";
            Если Types.Count() = 1 Тогда
                Если Types[0] = Тип("Число") Тогда Kind = "N";
                ИначеЕсли Types[0] = Тип("Строка") Тогда Kind = "S";
                Иначе ВызватьИсключение "copy-column-type"; КонецЕсли;
            ИначеЕсли Types.Count() <> 0 Тогда ВызватьИсключение "copy-types"; КонецЕсли;
            DateKind = "0"; Point = "11";
            Если D.DateQualifiers.DateFractions = DateFractions.Date Тогда DateKind = "1";
            ИначеЕсли D.DateQualifiers.DateFractions = DateFractions.Time Тогда DateKind = "2";
            ИначеЕсли D.DateQualifiers.DateFractions <> DateFractions.DateTime Тогда ВызватьИсключение "copy-date"; КонецЕсли;
            Point = "12"; Out = Out + TCId(C, Registry);
            Point = "13"; Out = Out + TCWord(C.Name);
            Point = "14"; Out = Out + TCWord(C.Title);
            Point = "15"; Out = Out + TCNum(C.Width) + Kind;
            Point = "16"; Out = Out + TCNum(D.NumberQualifiers.Digits);
            Point = "17"; Out = Out + TCNum(D.NumberQualifiers.FractionDigits);
            Point = "18"; Out = Out + TCFlag(D.NumberQualifiers.AllowedSign = AllowedSign.Nonnegative);
            Point = "19"; Out = Out + TCNum(D.StringQualifiers.Length);
            Point = "20"; Out = Out + TCFlag(D.StringQualifiers.AllowedLength = AllowedLength.Fixed) + DateKind;
            Point = "21"; Out = Out + TCNum(D.BinaryDataQualifiers.Length);
            Point = "22"; Out = Out + TCFlag(D.BinaryDataQualifiers.AllowedLength = AllowedLength.Fixed);
            Point = "07";
        КонецЦикла;
        Nodes = Новый Массив;
        Point = "23"; TCFlatten(T.Rows, Nodes);
        Point = "24"; Out = Out + TCNum(Nodes.Count());
        Point = "25";
        Для Каждого R Из Nodes Цикл
            Point = "26"; Out = Out + TCId(R, Registry);
            Point = "27"; Out = Out + TCId(R.Parent, Registry);
            Point = "28"; Out = Out + TCId(R.Owner(), Registry);
            Point = "29"; Out = Out + TCNum(R.Level());
            Point = "30"; Out = Out + TCId(R.Rows, Registry);
            Point = "31"; Out = Out + TCNum(R.Rows.Count());
            Point = "32"; Если R.Rows.Parent <> R Тогда ВызватьИсключение "copy-collection-parent"; КонецЕсли;
            Point = "33";
            Для I = 0 По T.Columns.Count() - 1 Цикл
                Point = "34"; Out = Out + TCCell(R.Get(I), Registry);
                Point = "33";
            КонецЦикла;
            Point = "25";
        КонецЦикла;
        Point = "35"; Если T.Rows.Parent <> Неопределено Тогда ВызватьИсключение "copy-root-parent"; КонецЕсли;
        Возврат Out;
    Исключение
        PrivateSnapshotDescription = ОписаниеОшибки();
        Code = TCFailureCode(PrivateSnapshotDescription);
        Если Code = "" Тогда Code = "S" + Point; КонецЕсли;
        ВызватьИсключение "copy-detail-" + Code;
    КонецПопытки;
КонецФункции
Функция TCArray()
    Inner = Новый Массив; Inner.Add(2); A = Новый Массив; A.Add(1); A.Add(Inner); Возврат A;
КонецФункции
Функция TCFixture(Знач Case)
    T = Новый ДеревоЗначений;
    Если Case = 1 Тогда Возврат T; КонецЕсли;
    T.Columns.Add("Payload", , "P", 3);
    T.Columns.Add("N", Новый ОписаниеТипов("Число", Новый КвалификаторыЧисла(6, 2)), "N", 4);
    T.Columns.Add("Text", Новый ОписаниеТипов("Строка", , Новый КвалификаторыСтроки(5)), "Text", 5);
    Если Case = 2 Или Case = 6 Тогда Возврат T; КонецЕсли;
    R = T.Rows.Add(); Child = R.Rows.Add(); Grand = Child.Rows.Add(); Other = T.Rows.Add();
    Nodes = Новый Массив; TCFlatten(T.Rows, Nodes);
    Для I = 0 По Nodes.Count() - 1 Цикл Nodes[I].Payload = I + 1; Nodes[I].N = I + 1; Nodes[I].Text = Сред("abcd", I + 1, 1); КонецЦикла;
    Child.Payload = Истина; Grand.Payload = Null; Other.Payload = Неопределено;
    Если Case = 7 Тогда A = TCArray(); R.Payload = A; Child.Payload = A; Grand.Payload = TCArray(); КонецЕсли;
    Возврат T;
КонецФункции
Функция TCError(Знач Text)
    Если СтрНайти(Text, "Метод объекта не обнаружен") > 0 Или СтрНайти(Text, "Метод не найден:") > 0
        Или СтрНайти(Text, "Метод или свойство не найдено:") > 0 Тогда Возврат "M"; КонецЕсли;
    Если СтрНайти(Text, "параметров") > 0 Или СтрНайти(Text, "параметры") > 0 Тогда Возврат "A"; КонецЕсли;
    Возврат "O";
КонецФункции
Функция TCProbe(Знач Case)
    Stage = "B";
    Попытка
        Registry = Новый Массив; T = TCFixture(Case); Before = TCSnapshot(T, Registry); Result = Неопределено;
        Status = "S"; Stage = "I";
        Попытка
            Если Case = 8 Тогда Result = T.Скопировать();
            ИначеЕсли Case = 9 Тогда Result = T.Copy(1);
            Иначе Result = T.Copy(); КонецЕсли;
        Исключение
            PrivateDescription = ОписаниеОшибки();
            Status = TCError(PrivateDescription);
        КонецПопытки;
        Stage = "O"; Out = Before + "/" + TCSnapshot(T, Registry) + "/";
        Если Status <> "S" Тогда
            Если Result <> Неопределено Тогда ВызватьИсключение "copy-exception-result"; КонецЕсли;
            Возврат Status + "/" + Out + "-";
        КонецЕсли;
        Out = Out + TCSnapshot(Result, Registry); Stage = "M";
        Если Case = 4 Тогда
            Result.Rows.Get(0).Payload = 5;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            T.Rows.Get(0).Rows.Get(0).N = 6;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
        ИначеЕсли Case = 5 Тогда
            Stage = "M01"; R = Result.Rows.Get(0).Rows.Add();
            Stage = "M02"; R.Payload = 5;
            Stage = "M03"; R.N = 5;
            Stage = "M04"; R.Text = "e";
            Stage = "M05"; Out = Out + "/" + TCSnapshot(T, Registry);
            Stage = "M06"; Out = Out + "/" + TCSnapshot(Result, Registry);
            Stage = "M07"; Result.Rows.Delete(Result.Rows.Get(1));
            Stage = "M08"; Out = Out + "/" + TCSnapshot(T, Registry);
            Stage = "M09"; Out = Out + "/" + TCSnapshot(Result, Registry);
            Stage = "M10"; R = T.Rows.Add();
            Stage = "M11"; R.Payload = 6;
            Stage = "M12"; R.N = 6;
            Stage = "M13"; R.Text = "f";
            Stage = "M14"; Out = Out + "/" + TCSnapshot(T, Registry);
            Stage = "M15"; Out = Out + "/" + TCSnapshot(Result, Registry);
            Stage = "M16"; T.Rows.Get(0).Rows.Delete(T.Rows.Get(0).Rows.Get(0));
            Stage = "M17"; Out = Out + "/" + TCSnapshot(T, Registry);
            Stage = "M18"; Out = Out + "/" + TCSnapshot(Result, Registry);
        ИначеЕсли Case = 6 Тогда
            C = Result.Columns.Get(0); C.Name = "X"; C.Title = "Q"; C.Width = 6;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            Result.Columns.Add("Y", , "Y");
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            C = T.Columns.Get(0); C.Name = "Y"; C.Title = "P"; C.Width = 7;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            T.Columns.Add("X", , "X");
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            T.Columns.Delete(T.Columns.Get(1));
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            Result.Columns.Delete(Result.Columns.Get(1));
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
        ИначеЕсли Case = 7 Тогда
            A = Result.Rows.Get(0).Payload; A[0] = 3;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            Inner = A[1]; Inner[0] = 4;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            A = T.Rows.Get(0).Payload; A[0] = 5;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
            Inner = A[1]; Inner[0] = 6;
            Out = Out + "/" + TCSnapshot(T, Registry) + "/" + TCSnapshot(Result, Registry);
        КонецЕсли;
        Возврат Status + "/" + Out;
    Исключение
        PrivateProbeDescription = ОписаниеОшибки();
        Code = TCFailureCode(PrivateProbeDescription);
        Если Code <> "" Тогда Возврат "X" + Stage + Code; КонецЕсли;
        Возврат "X" + Stage;
    КонецПопытки;
КонецФункции
Функция TCCalibrate()
    Попытка
        T = TCFixture(3); U = TCFixture(3); Alias = T;
        Если T <> Alias Или T = U Или T.Rows.Get(0) <> T.Rows.Get(0) Или T.Rows.Get(0) = T.Rows.Get(1)
            Или T.Columns.Get(0) = U.Columns.Get(0) Или T.Rows.Count() <> 2 Тогда Возврат "I"; КонецЕсли;
        A = TCArray(); B = TCArray(); Alias = A;
        Если A <> Alias Или A = B Или A[1] = B[1] Тогда Возврат "A"; КонецЕсли;
        Nodes = Новый Массив; TCFlatten(T.Rows, Nodes);
        Если Nodes.Count() <> 4 Или Nodes[2].Level() <> 2 Или Nodes[2].Owner() <> T Или Nodes[2].Parent <> Nodes[1] Тогда Возврат "R"; КонецЕсли;
        C = T.Columns.Get(0); C.Name = "X"; C.Title = "Q"; C.Width = 6; Nodes[0].X = 5;
        Если C.Name <> "X" Или C.Title <> "Q" Или C.Width <> 6 Или Nodes[0].X <> 5 Тогда Возврат "M"; КонецЕсли;
        R = T.Rows.Add(); T.Rows.Delete(R); Если T.Rows.Count() <> 2 Тогда Возврат "D"; КонецЕсли;
        Registry = Новый Массив; S = TCSnapshot(T, Registry);
    Исключение Возврат "E"; КонецПопытки;
    Возврат "-";
КонецФункции
Сообщить("TC-C: [" + TCCalibrate() + "]");
Для Case = 1 По 9 Цикл Сообщить("TC-" + Строка(Case) + ": [" + TCProbe(Case) + "]"); КонецЦикла;
