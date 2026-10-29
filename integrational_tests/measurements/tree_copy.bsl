// Standalone bounded Copy observer. No native expectations or runtime implementation.
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
    Если Registry.Count() >= 62 Тогда ВызватьИсключение "copy-identities"; КонецЕсли;
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
    Для Каждого R Из Rows Цикл
        Если Nodes.Count() >= 5 Тогда ВызватьИсключение "copy-rows"; КонецЕсли;
        Nodes.Add(R); TCFlatten(R.Rows, Nodes);
    КонецЦикла;
КонецПроцедуры
Функция TCSnapshot(Знач T, Знач Registry)
    Если ТипЗнч(T) <> Тип("ДеревоЗначений") Тогда ВызватьИсключение "copy-result-type"; КонецЕсли;
    Если T.Columns.Count() > 4 Тогда ВызватьИсключение "copy-columns"; КонецЕсли;
    Out = TCId(T, Registry) + TCId(T.Rows, Registry) + TCId(T.Columns, Registry) + TCNum(T.Columns.Count());
    Для Каждого C Из T.Columns Цикл
        D = C.ValueType; Types = D.Types(); Kind = "U";
        Если Types.Count() = 1 Тогда
            Если Types[0] = Тип("Число") Тогда Kind = "N";
            ИначеЕсли Types[0] = Тип("Строка") Тогда Kind = "S";
            Иначе ВызватьИсключение "copy-column-type"; КонецЕсли;
        ИначеЕсли Types.Count() <> 0 Тогда ВызватьИсключение "copy-types"; КонецЕсли;
        DateKind = "0";
        Если D.DateQualifiers.DateFractions = DateFractions.Date Тогда DateKind = "1";
        ИначеЕсли D.DateQualifiers.DateFractions = DateFractions.Time Тогда DateKind = "2";
        ИначеЕсли D.DateQualifiers.DateFractions <> DateFractions.DateTime Тогда ВызватьИсключение "copy-date"; КонецЕсли;
        Out = Out + TCId(C, Registry) + TCWord(C.Name) + TCWord(C.Title) + TCNum(C.Width) + Kind
            + TCNum(D.NumberQualifiers.Digits) + TCNum(D.NumberQualifiers.FractionDigits)
            + TCFlag(D.NumberQualifiers.AllowedSign = AllowedSign.Nonnegative)
            + TCNum(D.StringQualifiers.Length) + TCFlag(D.StringQualifiers.AllowedLength = AllowedLength.Fixed)
            + DateKind + TCNum(D.BinaryDataQualifiers.Length) + TCFlag(D.BinaryDataQualifiers.AllowedLength = AllowedLength.Fixed);
    КонецЦикла;
    Nodes = Новый Массив; TCFlatten(T.Rows, Nodes); Out = Out + TCNum(Nodes.Count());
    Для Каждого R Из Nodes Цикл
        Out = Out + TCId(R, Registry) + TCId(R.Parent, Registry) + TCId(R.Owner(), Registry)
            + TCNum(R.Level()) + TCId(R.Rows, Registry) + TCNum(R.Rows.Count());
        Если R.Rows.Parent <> R Тогда ВызватьИсключение "copy-collection-parent"; КонецЕсли;
        Для I = 0 По T.Columns.Count() - 1 Цикл Out = Out + TCCell(R.Get(I), Registry); КонецЦикла;
    КонецЦикла;
    Если T.Rows.Parent <> Неопределено Тогда ВызватьИсключение "copy-root-parent"; КонецЕсли;
    Возврат Out;
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
        Если СтрНайти(PrivateProbeDescription, "copy-identity-compare") > 0 Тогда Возврат "X" + Stage + "I"; КонецЕсли;
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
